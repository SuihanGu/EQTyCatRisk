@echo off
setlocal
rem Repository-local launcher for the without_Other loss engine.
rem Set EQTY_PYTHON when Python is not on PATH, for example:
rem   set EQTY_PYTHON=D:\Anaconda\python.exe
if defined EQTY_PYTHON (
  "%EQTY_PYTHON%" "%~dp0run_v12_loss_calculation.py" %*
) else (
  python "%~dp0run_v12_loss_calculation.py" %*
)
exit /b %ERRORLEVEL%
