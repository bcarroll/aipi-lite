@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "HELPER=%SCRIPT_DIR%tools\windows_installer.py"

if not exist "%HELPER%" goto helper_missing

where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 "%HELPER%" install %*
exit /b %ERRORLEVEL%

:try_python
where python >nul 2>&1
if errorlevel 1 goto python_missing
python "%HELPER%" install %*
exit /b %ERRORLEVEL%

:helper_missing
echo error: Windows installer helper not found: "%HELPER%" 1>&2
exit /b 1

:python_missing
echo error: Python 3 is required. Install Python for Windows, then rerun install.cmd. 1>&2
exit /b 1
