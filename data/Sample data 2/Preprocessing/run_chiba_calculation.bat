@echo off
setlocal
if not "%EQTY_PYTHON%"=="" (
  "%EQTY_PYTHON%" "%~dp0run_chiba_calculation.py" %*
) else (
  python "%~dp0run_chiba_calculation.py" %*
)
exit /b %errorlevel%
