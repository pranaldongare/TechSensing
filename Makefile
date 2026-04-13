.PHONY: dev frontend test lint

dev:
	python backend.py

frontend:
	cd frontend && npm install && npm run dev

test:
	python -m pytest tests/ -v

lint:
	ruff check app/ core/ tests/
