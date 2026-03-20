.PHONY: dev build test lint desktop

dev:
	docker compose up --build

build:
	docker compose build

test:
	cd backend && python -m pytest

lint:
	cd backend && ruff check . && cd ../frontend && npm run lint

desktop:
	cd frontend && npm run tauri build
