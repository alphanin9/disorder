.PHONY: install dev up down logs test migrate demo frontend-install frontend-dev frontend-test frontend-build frontend-e2e

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

frontend-install:
	npm --prefix frontend install

frontend-dev:
	npm --prefix frontend run dev

frontend-test:
	npm --prefix frontend run test:run

frontend-build:
	npm --prefix frontend run build

frontend-e2e:
	npm --prefix frontend run test:e2e
