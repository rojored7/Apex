# api

Backend de APEX: FastAPI, SQLAlchemy 2 async, Alembic, worker con APScheduler. Gestionado con `uv`.

```
cd api && uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest
```

El arranque completo del stack (Docker Compose, variables de entorno) está en el `README.md` de la raíz. Las reglas del código están en `CLAUDE.md`.
