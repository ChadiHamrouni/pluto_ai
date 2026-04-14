.PHONY: dev build test lint desktop daemon

dev: daemon
	docker compose up --build

build:
	docker compose build

test:
	cd backend && python -m pytest

lint:
	cd backend && ruff check . && cd ../frontend && npm run lint

desktop:
	cd frontend && npm run tauri build

# Register + start the reminder daemon (idempotent — safe to run repeatedly).
# Uses cmd.exe directly so schtasks works correctly on Windows.
daemon:
	@cmd /c "schtasks /Query /TN PlutoReminderDaemon >nul 2>&1 || install_reminder_daemon.bat"
	@cmd /c "schtasks /Query /TN PlutoReminderDaemon /FO LIST 2>nul | find \"Running\" >nul || schtasks /Run /TN PlutoReminderDaemon"
	@echo [daemon] Reminder daemon registered and running.
