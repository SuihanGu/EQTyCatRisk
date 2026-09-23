#!/usr/bin/env python3
"""Backward-compatible entry point for the real repository-local calculator.

Older launch commands can continue to call this filename.  The implementation
now lives in ``run_v12_loss_calculation.py`` and performs the loss calculation;
it no longer copies a precomputed result.
"""

from run_v12_loss_calculation import main


if __name__ == "__main__":
    main()
