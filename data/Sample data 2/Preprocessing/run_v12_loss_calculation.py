#!/usr/bin/env python3
"""Run the repository-local without_Other loss calculation.

This is the portable extraction of the loss-calculation part of
``run_full_fix_v12.py``.  It deliberately keeps the scientific steps used by
that workflow: the Japanese vulnerability curves, the multi-hazard 3-D
fragility surface, a spatial Gaussian copula, and 2,000 Monte Carlo samples.

The calculator is not tied to the two demonstration events.  Reviewers can
replace ``--grid-file`` and ``--exposure-file`` (or add a case to cases.json)
as long as the input schema is preserved:

* grid: Unique_ID, longitude, latitude, one wind-speed column in m/s, PGA in
  gal;
* exposure: Unique_ID, Vulner_ID_y, value_split in JPY;
* model: the packaged vulnerability_module.py/.pkl and vulnerability curves.

Only the 270 non-Other vulnerability IDs are published.  For strict v12
reproducibility, the engine first evaluates the hidden ``with_Other`` stream
and then evaluates ``without_Other`` with the same random-generator order;
the hidden results are discarded.  The three published outputs are loss
distributions in 100 million JPY (``loss_oku``): Earthquake, Typhoon, and
Coupled.  The PNG files are generated from the same distributions, so the web
page never substitutes a precomputed result.
"""
from __future__ import annotations

import argparse
import json
import pickle
import shutil
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.spatial.distance import cdist
from scipy.stats import beta as scipy_beta
from scipy.stats import norm


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[2]
DEFAULT_CONFIG = HERE / "cases.json"
DEFAULT_EXPOSURE = HERE / "inputs" / "Chiba_exposure.csv"
DEFAULT_MODEL = HERE / "model" / "vulnerability_module.pkl"
DEFAULT_MODEL_MODULE = HERE / "model"
DEFAULT_VULNERABILITY = HERE / "model" / "vulnerability_curves.csv"
DEFAULT_OUTPUT = HERE.parent / "risk-loss"
GAL = 980.665
DEFAULT_SAMPLES = 2000
DEFAULT_SEED = 20260706
DEFAULT_SPATIAL_CORRELATION = -0.02524
DEFAULT_MC_GRIDS = 5000


class CompatibleUnpickler(pickle.Unpickler):
    """Load the model saved by v12, whose class was pickled as __main__."""

    def find_class(self, module: str, name: str) -> Any:
        if module == "__main__" and name == "MultiHazardFragilityModel":
            from vulnerability_module import MultiHazardFragilityModel

            return MultiHazardFragilityModel
        return super().find_class(module, name)


def load_model(pickle_path: Path, module_dir: Path):
    sys.path.insert(0, str(module_dir))
    with pickle_path.open("rb") as handle:
        model = CompatibleUnpickler(handle).load()
    return model


def beta_parameters(mean: np.ndarray, std: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert MDR mean/std values to stable beta-distribution parameters."""
    mean = np.maximum(np.asarray(mean, dtype=float), 1e-8)
    variance = np.asarray(std, dtype=float) ** 2
    max_variance = np.maximum(mean * (1.0 - mean) - 1e-15, 1e-15)
    variance = np.clip(variance, 1e-15, max_variance)
    concentration = np.maximum(mean * (1.0 - mean) / variance - 1.0, 0.1)
    return np.maximum(mean * concentration, 1e-10), np.maximum(
        (1.0 - mean) * concentration, 1e-10
    )


def gaussian_copula_mc(
    grids: pd.DataFrame,
    samples: int,
    rng: np.random.Generator,
    spatial_correlation: float = DEFAULT_SPATIAL_CORRELATION,
    max_grids: int = DEFAULT_MC_GRIDS,
) -> np.ndarray:
    """Reproduce v12's spatial Gaussian-copula Monte Carlo calculation."""
    n_total = len(grids)
    n_copula = min(n_total, max_grids)
    if n_copula < n_total:
        order = np.argsort(grids["el"].to_numpy())[::-1]
        copula_indices, rest_indices = order[:n_copula], order[n_copula:]
    else:
        copula_indices = np.arange(n_total)
        rest_indices = np.array([], dtype=int)

    copula = grids.iloc[copula_indices]
    rest = grids.iloc[rest_indices] if len(rest_indices) else None
    deterministic_loss = float(rest["el"].sum()) if rest is not None else 0.0

    means = copula["md"].to_numpy(dtype=float)
    stds = np.where(copula["sd"].to_numpy(dtype=float) < 1e-10, 1e-4, copula["sd"])
    values = copula["tv"].to_numpy(dtype=float)
    alpha, beta = beta_parameters(means, stds)

    latitudes = np.radians(copula["latitude"].to_numpy(dtype=float))
    x_scale = 111.32 * np.cos(np.mean(latitudes))
    coordinates = np.column_stack(
        (
            copula["longitude"].to_numpy(dtype=float) * x_scale,
            copula["latitude"].to_numpy(dtype=float) * 111.32,
        )
    )
    distances = cdist(coordinates, coordinates)
    correlation = np.exp(spatial_correlation * distances)
    correlation = (correlation + correlation.T) / 2.0
    np.fill_diagonal(correlation, 1.0)
    minimum_eigenvalue = np.linalg.eigvalsh(correlation).min()
    if minimum_eigenvalue < 1e-8:
        correlation += np.eye(n_copula) * (abs(minimum_eigenvalue) + 1e-6)
    cholesky = np.linalg.cholesky(correlation)

    result = np.zeros(samples, dtype=float)
    for sample_index in range(samples):
        correlated_normal = cholesky @ rng.standard_normal(n_copula)
        uniform = norm.cdf(correlated_normal)
        damage_ratio = np.clip(scipy_beta.ppf(uniform, alpha, beta), 0.0, 1.0)
        result[sample_index] = float(np.sum(damage_ratio * values) + deterministic_loss)
    return result / 1e8


def build_vulnerability_interpolators(curves_path: Path):
    curves = pd.read_csv(curves_path)
    mean_interpolators: dict[int, Any] = {}
    std_interpolators: dict[int, Any] = {}
    thresholds: dict[int, float] = {}
    for vulnerability_id, group in curves.groupby("vulner_ID"):
        ordered = group.sort_values("pga")
        pga = ordered["pga"].to_numpy(dtype=float)
        mean = ordered["mdr"].to_numpy(dtype=float)
        std = ordered["std"].to_numpy(dtype=float)
        nonzero = mean > 0
        thresholds[int(vulnerability_id)] = (
            float(pga[~nonzero][-1]) if (~nonzero).any() else 0.0
        )
        mean_interpolators[int(vulnerability_id)] = interp1d(
            pga, mean, bounds_error=False, fill_value=(0.0, float(mean[-1]))
        )
        std_interpolators[int(vulnerability_id)] = interp1d(
            pga, std, bounds_error=False, fill_value=(0.0, float(std[-1]))
        )
    return mean_interpolators, std_interpolators, thresholds


def load_case(config_path: Path, case_key: str) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        return dict(config["cases"][case_key])
    except KeyError as exc:
        available = ", ".join(sorted(config.get("cases", {})))
        raise ValueError(f"Unknown case {case_key!r}; available cases: {available}") from exc


def evaluate_mode(
    grids: pd.DataFrame,
    mode: str,
    model: Any,
    sequence: str,
    mean_interpolators: dict[int, Any],
    std_interpolators: dict[int, Any],
    thresholds: dict[int, float],
    samples: int,
    rng: np.random.Generator,
    max_grids: int,
) -> np.ndarray:
    working = grids.copy()
    if mode == "earthquake":
        working["md"] = working["earthquake_mean"]
        working["sd"] = working["earthquake_std"]
    else:
        structure = working["Vulner_ID_y"].map(model.get_structure_type)
        code_level = working["Vulner_ID_y"].map(model.get_code_level)
        mdr = np.zeros(len(working), dtype=float)
        for (structure_type, code), group_index in working.groupby([structure, code_level]).groups.items():
            if structure_type == "Unknown":
                continue
            try:
                interpolator = model.interpolators[structure_type][sequence][code]
            except KeyError:
                continue
            positions = group_index.to_numpy()
            if mode == "typhoon":
                pga = np.zeros(len(positions), dtype=float)
            else:
                pga = working.loc[group_index, "pga_g"].to_numpy(dtype=float)
            wind = working.loc[group_index, "wind_v"].to_numpy(dtype=float)
            mdr[positions] = np.clip(
                interpolator(np.column_stack((wind, pga))).reshape(-1), -1.0, 1.0
            )
        if mode == "typhoon":
            working["md"] = np.clip(mdr, 0.0, 1.0)
            working["sd"] = working["md"] * np.log(10.0) * 1.5
        else:
            working["md"] = np.clip(working["earthquake_mean"] + mdr, 0.0, 1.0)
            working["sd"] = np.maximum(working["earthquake_std"], working["md"] * 0.05)

    working["el"] = working["md"] * working["value_split"]
    working["tv"] = working["value_split"]
    expected = float(working["el"].sum())
    if expected <= 0 or len(working) < 5:
        return np.full(samples, expected / 1e8, dtype=float)
    return gaussian_copula_mc(working, samples, rng, max_grids=max_grids)


def nice_ticks(lo: float, hi: float, max_ticks: int = 6) -> tuple[list[float], str]:
    """The same readable tick selection used by run_full_fix_v12.py."""
    if lo >= hi:
        return [lo], "%.1f"
    width = hi - lo
    raw = width / max_ticks
    exponent = np.floor(np.log10(raw))
    mantissa = raw / 10**exponent
    if mantissa < 1.5:
        normalized = 1
    elif mantissa < 2.5:
        normalized = 2
    elif mantissa < 5:
        normalized = 5
    else:
        normalized = 10
    step = normalized * 10**exponent
    first = np.ceil(lo / step) * step
    ticks: list[float] = []
    tick = first
    while tick <= hi + step * 0.01:
        if tick >= lo - step * 0.01:
            ticks.append(round(float(tick), 12))
        tick += step
    if len(ticks) > max_ticks:
        larger_step = step * 2
        kept = [ticks[0]]
        for value in ticks[1:-1]:
            if len(kept) >= max_ticks - 1:
                break
            if value - kept[-1] >= larger_step * 0.9:
                kept.append(value)
        kept.append(ticks[-1])
        ticks = kept
    if step >= 1:
        tick_format = "%.0f"
    elif step >= 0.1:
        tick_format = "%.1f"
    elif step >= 0.01:
        tick_format = "%.2f"
    elif step >= 0.001:
        tick_format = "%.3f"
    elif step >= 0.0001:
        tick_format = "%.4f"
    else:
        tick_format = "%.5f"
    return ticks, tick_format


PLOT_COLORS = {"Earthquake": "#C62828", "Typhoon": "#1565C0", "Coupled": "#7B1FA2"}
FIGURE_SIZE = (5.73 / 2.54, 3.80 / 2.54)


def write_plot(
    values: np.ndarray,
    destination: Path,
    label: str,
    exchange_rate: float,
) -> None:
    """Reproduce v12's probability-histogram/CDF loss figure exactly."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    loss_musd = np.nan_to_num(values, nan=0.0) * 100.0 / exchange_rate
    mean_loss = float(loss_musd.mean())
    std_loss = float(loss_musd.std())
    n_samples = len(loss_musd)
    if mean_loss < 1e-10:
        loss_musd = np.zeros(n_samples)
        mean_loss = 0.0
        std_loss = 0.0

    unique_count = len(np.unique(np.round(loss_musd, 6)))
    has_variance = std_loss > max(mean_loss * 1e-6, 1e-10)
    del has_variance  # retained as an explicit v12 diagnostic condition
    if mean_loss < 1e-10:
        lower, upper = 0.0, 0.01
        bins = 60
        single_value = False
    else:
        data_range = float(loss_musd.max() - loss_musd.min())
        minimum_width = max(mean_loss * 0.002, 0.002)
        if data_range >= minimum_width:
            padding = data_range * 0.15
            lower = max(0.0, float(loss_musd.min()) - padding)
            upper = float(loss_musd.max()) + padding
            single_value = False
        else:
            half_width = minimum_width / 2.0
            lower = max(0.0, mean_loss - half_width)
            upper = mean_loss + half_width
            single_value = unique_count <= 5
        bins = 60 if not single_value else 1

    if single_value:
        ticks, tick_format = [mean_loss], "%.2f"
    else:
        ticks, tick_format = nice_ticks(lower, upper, max_ticks=7)

    if not single_value:
        counts, bin_edges = np.histogram(loss_musd, bins=bins, range=(lower, upper))
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
        probability = counts.astype(float) / n_samples
        bar_width = bin_edges[1] - bin_edges[0]
    else:
        bin_centers = np.array([mean_loss])
        probability = np.array([1.0])
        bar_width = (upper - lower) * 0.6

    sorted_loss = np.sort(loss_musd)
    cumulative = np.arange(1, n_samples + 1) / n_samples * 100.0
    cumulative_at_mean = 100.0 if std_loss < 1e-10 else float(
        np.interp(mean_loss, sorted_loss, cumulative)
    )
    color = PLOT_COLORS[label]
    plt.rcParams["font.family"] = "serif"
    plt.rcParams["font.serif"] = ["Times New Roman", "Times", "DejaVu Serif"]
    plt.rcParams["mathtext.fontset"] = "stix"
    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis2 = axis.twinx()
    if single_value and unique_count <= 1:
        axis.bar(
            [mean_loss], [100.0], width=bar_width, color=color, alpha=0.55,
            edgecolor="white", linewidth=0.3, zorder=2,
        )
    else:
        axis.bar(
            bin_centers, probability * 100.0, width=bar_width * 0.92,
            color=color, alpha=0.55, edgecolor="white", linewidth=0.3, zorder=2,
        )
    axis2.plot(sorted_loss, cumulative, "-", color="#212121", linewidth=1.2, alpha=0.9, zorder=4)
    axis2.axvline(mean_loss, color="#FF6F00", linestyle="--", linewidth=1.0, alpha=0.85, zorder=3)
    axis2.plot(
        mean_loss, cumulative_at_mean, "o", color="#FF6F00", markersize=4.5,
        markeredgecolor="white", markeredgewidth=0.5, zorder=6,
    )
    axis2.annotate(
        f"({mean_loss:.2f}, {cumulative_at_mean:.1f}%)",
        xy=(mean_loss, cumulative_at_mean), xytext=(8, 0), textcoords="offset points",
        fontsize=5.5, fontweight="bold", color="#BF360C", ha="left", va="center",
        fontfamily="serif", annotation_clip=True, zorder=7,
    )
    axis.set_xlabel("Building Loss (M USD)", fontsize=7, labelpad=1, fontfamily="serif")
    axis.set_xlim(lower, upper)
    axis.xaxis.set_major_locator(mticker.FixedLocator(ticks))
    axis.xaxis.set_major_formatter(mticker.FormatStrFormatter(tick_format))
    axis.tick_params(axis="x", labelsize=6, pad=1)
    for tick_label in axis.get_xticklabels():
        tick_label.set_fontfamily("serif")
    if len(ticks) > 6:
        axis.tick_params(axis="x", rotation=30)
    axis.set_ylabel("Probability (%)", fontsize=7, color=color, labelpad=1, fontfamily="serif")
    axis.tick_params(axis="y", labelsize=6, labelcolor=color, pad=1)
    for tick_label in axis.get_yticklabels():
        tick_label.set_fontfamily("serif")
    axis.yaxis.set_major_locator(mticker.MaxNLocator(5))
    axis2.set_ylabel(
        "Cumulative Probability (%)", fontsize=7, color="#212121", labelpad=1,
        fontfamily="serif",
    )
    axis2.set_ylim(0, 105)
    axis2.tick_params(axis="y", labelsize=6, labelcolor="#212121", pad=1)
    for tick_label in axis2.get_yticklabels():
        tick_label.set_fontfamily("serif")
    axis2.yaxis.set_major_locator(mticker.MaxNLocator(5))
    axis.grid(axis="y", alpha=0.15, linestyle="--", linewidth=0.3)
    axis.set_axisbelow(True)
    figure.subplots_adjust(left=0.20, right=0.80, top=0.88, bottom=0.24)
    figure.savefig(destination, dpi=300, facecolor="white", edgecolor="none")
    plt.close(figure)


def write_legend(destination: Path, public_dir: Path | None) -> None:
    """Write the common v12 legend used beside the three loss figures."""
    figure, axis = plt.subplots(figsize=(10.0 / 2.54, 1.5 / 2.54))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    sw, sh, line_width, gap, font_size = 0.05, 0.22, 0.06, 0.025, 5
    for (color, text), x in zip(
        [(PLOT_COLORS["Earthquake"], "Earthquake loss"),
         (PLOT_COLORS["Typhoon"], "Typhoon loss"),
         (PLOT_COLORS["Coupled"], "Coupled loss")],
        [0.14, 0.46, 0.78],
    ):
        text_x = x + sw / 2 + gap
        patch = FancyBboxPatch(
            (x - sw / 2, 0.72 - sh / 2), sw, sh, boxstyle="round,pad=.02",
            facecolor=color, alpha=0.55, edgecolor="white", linewidth=0.5,
            transform=axis.transAxes, clip_on=False,
        )
        axis.add_patch(patch)
        axis.text(text_x, 0.72, text, transform=axis.transAxes, fontsize=font_size,
                  va="center", ha="left", fontfamily="serif")
    for style, color, text, x in [
        ("solid", "#212121", "Cumulative probability", 0.22),
        ("dashed", "#FF6F00", "Mean", 0.66),
    ]:
        text_x = x + line_width / 2 + gap
        axis.plot(
            [x - line_width / 2, x + line_width / 2], [0.28, 0.28],
            color=color, linestyle=style, linewidth=1.2 if style == "solid" else 1.0,
            transform=axis.transAxes, clip_on=False,
        )
        axis.text(text_x, 0.28, text, transform=axis.transAxes, fontsize=font_size,
                  va="center", ha="left", fontfamily="serif")
    output = destination / "Legend.png"
    figure.savefig(output, dpi=300, facecolor="white", edgecolor="none",
                   bbox_inches="tight", pad_inches=0.05)
    plt.close(figure)
    copy_result(output, public_dir)


def copy_result(source: Path, public_dir: Path | None) -> None:
    if public_dir is None:
        return
    public_dir.mkdir(parents=True, exist_ok=True)
    target = public_dir / source.name
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)


def portable_path(path: Path) -> str:
    """Keep manifests portable when an input is inside this repository."""
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="2005", help="Case key in cases.json")
    parser.add_argument("--case-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--grid-file", type=Path)
    parser.add_argument("--exposure-file", type=Path, default=DEFAULT_EXPOSURE)
    parser.add_argument("--output-stem")
    parser.add_argument("--wind-column")
    parser.add_argument("--pga-column", default="PGA")
    parser.add_argument("--sequence")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--public-dir", type=Path)
    parser.add_argument("--model-pickle", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--model-module-dir", type=Path, default=DEFAULT_MODEL_MODULE)
    parser.add_argument("--vulnerability-csv", type=Path, default=DEFAULT_VULNERABILITY)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-copula-grids", type=int, default=DEFAULT_MC_GRIDS)
    parser.add_argument(
        "--skip-with-other-rng",
        action="store_true",
        help="Do not consume the hidden with_Other v12 random stream before without_Other.",
    )
    args = parser.parse_args()
    if args.samples <= 0:
        raise ValueError("--samples must be positive")

    case = load_case(args.case_config, args.case)
    grid_file = args.grid_file or (HERE / case["grid_file"])
    output_stem = args.output_stem or case["output_stem"]
    wind_column = args.wind_column or case["wind_column"]
    sequence = args.sequence or case.get("sequence", "simultaneous")
    if sequence not in {"simultaneous", "eq_then_wind", "wind_then_eq"}:
        raise ValueError(f"Unsupported sequence: {sequence}")
    for required in (grid_file, args.exposure_file, args.model_pickle, args.vulnerability_csv):
        if not required.is_file():
            raise FileNotFoundError(required)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[loss] case={case.get('name', args.case)}")
    print(f"[loss] grid={grid_file}")
    print(f"[loss] exposure={args.exposure_file}")
    print(f"[loss] samples={args.samples} seed={args.seed} exposure=without_Other")

    grid = pd.read_csv(grid_file, usecols=["Unique_ID", "longitude", "latitude", wind_column, args.pga_column])
    grid = grid.rename(columns={wind_column: "wind_v", args.pga_column: "pga_gal"})
    grid["Unique_ID"] = pd.to_numeric(grid["Unique_ID"], errors="coerce").astype("Int64")
    grid["wind_v"] = pd.to_numeric(grid["wind_v"], errors="coerce").fillna(0.0)
    grid["pga_gal"] = pd.to_numeric(grid["pga_gal"], errors="coerce").fillna(0.0)
    grid = grid.dropna(subset=["Unique_ID"]).copy()
    grid["Unique_ID"] = grid["Unique_ID"].astype(int)
    grid["pga_g"] = grid["pga_gal"] / GAL

    exposure = pd.read_csv(
        args.exposure_file,
        usecols=["Unique_ID", "Vulner_ID_y", "value_split"],
        encoding="utf-8-sig",
    )
    exposure["Unique_ID"] = pd.to_numeric(exposure["Unique_ID"], errors="coerce")
    exposure["Vulner_ID_y"] = pd.to_numeric(exposure["Vulner_ID_y"], errors="coerce")
    exposure["value_split"] = pd.to_numeric(exposure["value_split"], errors="coerce").fillna(0.0)
    exposure = exposure.dropna(subset=["Unique_ID", "Vulner_ID_y"])
    exposure["Unique_ID"] = exposure["Unique_ID"].astype(int)
    exposure["Vulner_ID_y"] = exposure["Vulner_ID_y"].astype(int)

    model = load_model(args.model_pickle, args.model_module_dir)
    mean_interpolators, std_interpolators, thresholds = build_vulnerability_interpolators(args.vulnerability_csv)
    non_other = set(model.WOOD_IDS) | set(model.STEEL_IDS) | set(model.RC_IDS) | set(model.MASONRY_IDS)
    all_ids = non_other | set(model.OTHER_IDS)
    exposure = exposure[exposure["Vulner_ID_y"].isin(all_ids) & (exposure["value_split"] > 0)]
    hazard = grid[["Unique_ID", "longitude", "latitude", "pga_gal", "pga_g", "wind_v"]]
    merged_all = exposure.merge(hazard, on="Unique_ID", how="inner").reset_index(drop=True)
    if merged_all.empty:
        raise ValueError("No exposure cells overlap the supplied grid Unique_ID values")

    earthquake_mean = np.zeros(len(merged_all), dtype=float)
    earthquake_std = np.zeros(len(merged_all), dtype=float)
    for vulnerability_id, group_index in merged_all.groupby("Vulner_ID_y").groups.items():
        positions = group_index.to_numpy()
        pga = merged_all.loc[group_index, "pga_gal"].to_numpy(dtype=float)
        if vulnerability_id not in mean_interpolators:
            continue
        mean = np.clip(mean_interpolators[vulnerability_id](pga), 0.0, 1.0)
        threshold = thresholds.get(vulnerability_id, 0.0)
        if threshold > 0:
            mean[pga <= threshold] = 0.0
        earthquake_mean[positions] = mean
        earthquake_std[positions] = np.clip(std_interpolators[vulnerability_id](pga), 0.0, 1.0)
    merged_all["earthquake_mean"] = earthquake_mean
    merged_all["earthquake_std"] = earthquake_std

    rng = np.random.default_rng(args.seed)
    frames = []
    if not args.skip_with_other_rng:
        frames.append(("with_Other", merged_all))
    frames.append((
        "without_Other",
        merged_all[merged_all["Vulner_ID_y"].isin(non_other)].reset_index(drop=True).copy(),
    ))
    exchange_rate = float(case.get("exchange_rate", 110.4))
    for exposure_label, frame in frames:
        print(f"[loss] exposure={exposure_label} rows={len(frame):,}")
        for mode, label in (("earthquake", "Earthquake"), ("typhoon", "Typhoon"), ("coupled", "Coupled")):
            print(f"[loss] calculating {exposure_label} {label}")
            values = evaluate_mode(
                frame,
                mode,
                model,
                sequence,
                mean_interpolators,
                std_interpolators,
                thresholds,
                args.samples,
                rng,
                args.max_copula_grids,
            )
            if exposure_label == "with_Other":
                print(f"[loss] discarded with_Other {label}: mean={values.mean():.6f} loss_oku")
                continue
            csv_path = output_dir / f"{output_stem}_{label}_loss.csv"
            png_path = output_dir / f"{output_stem}_{label}_loss.png"
            pd.DataFrame({"loss_oku": values}).to_csv(csv_path, index=False, encoding="utf-8-sig")
            write_plot(values, png_path, label, exchange_rate)
            copy_result(csv_path, args.public_dir)
            copy_result(png_path, args.public_dir)
            print(f"[loss] {label}: mean={values.mean():.6f} loss_oku")
    write_legend(output_dir, args.public_dir)

    manifest = {
        "case": args.case,
        "name": case.get("name", output_stem),
        "loss_file_stem": output_stem,
        "exposure": "without_Other",
        "samples": args.samples,
        "seed": args.seed,
        "sequence": sequence,
        "exchange_rate_jpy_per_usd": exchange_rate,
        "v12_rng_order": "with_Other_then_without_Other" if not args.skip_with_other_rng else "without_Other_only",
        "grid_file": portable_path(grid_file),
        "exposure_file": portable_path(args.exposure_file),
        "calculation": "repository-local extraction of visualization-loss-value-12",
        "outputs": [f"{output_stem}_{label}_loss.csv" for label in ("Earthquake", "Typhoon", "Coupled")],
    }
    manifest_path = output_dir / f"{output_stem}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    copy_result(manifest_path, args.public_dir)
    print(json.dumps({"ok": True, **manifest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
