.PHONY: install dev up down logs test migrate demo

install:
	pip install -e .[dev]

dev:
	uvicorn control_plane.app.main:app --reload --host 0.0.0.0 --port 8000

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f control_plane

migrate:
	alembic -c control_plane/alembic.ini upgrade head

test:
	pytest -q

demo:
	python scripts/demo_flow.py
