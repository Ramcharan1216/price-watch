up:
	docker compose up -d
down:
	docker compose down
reset:
	docker compose down -v && docker compose up -d
check:
	python scripts/check_db.py
