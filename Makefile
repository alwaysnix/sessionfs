.PHONY: install test lint build clean server server-down

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --tb=short

lint:
	ruff check src/
	mypy src/sessionfs/ --ignore-missing-imports

build:
	python -m build

clean:
	rm -rf dist/ build/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +

server:
	docker compose up -d

server-down:
	docker compose down
