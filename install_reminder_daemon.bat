@echo off
:: Registers the Pluto reminder daemon as a Windows Task Scheduler task
:: that runs at user logon. Run this once as Administrator (or just as your user).

SET SCRIPT_DIR=%~dp0
SET VBS_PATH=%SCRIPT_DIR%start_reminder_daemon.vbs

echo Installing Pluto reminder daemon...

:: Delete existing task if present (ignore error if not found)
schtasks /Delete /TN "PlutoReminderDaemon" /F >nul 2>&1

:: Create the task: run at logon, for current user, no password required
schtasks /Create ^
  /TN "PlutoReminderDaemon" ^
  /TR "wscript.exe \"%VBS_PATH%\"" ^
  /SC ONLOGON ^
  /RU "%USERNAME%" ^
  /RL HIGHEST ^
  /F

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Daemon registered. It will start automatically at next login.
    echo      To start it now without rebooting, run:
    echo      schtasks /Run /TN PlutoReminderDaemon
) ELSE (
    echo.
    echo [ERROR] Task Scheduler registration failed.
    echo         Try running this script as Administrator.
)

pause
