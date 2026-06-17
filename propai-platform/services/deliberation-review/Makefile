.PHONY: test migrate downgrade lint scan up down

test:
	.venv/bin/python -m pytest -q

migrate:
	cd apps/api && ../../.venv/bin/alembic upgrade head

downgrade:
	cd apps/api && ../../.venv/bin/alembic downgrade base

lint:
	.venv/bin/ruff check . || true

scan:
	.venv/bin/python -c "from tools.static_scan import scan_for_numeric_legal_constants as s; print('static_scan ready')"

up:
	docker-compose up -d

down:
	docker-compose down
