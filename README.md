# Asset Risk Platform

A starter FastAPI backend using PostgreSQL, SQLAlchemy 2, Alembic, and JWT helpers.

## Requirements

- Python 3.10+
- PostgreSQL

## Local setup

From the project root, create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a PostgreSQL database named `asset_risk` (or update `DATABASE_URL`), then copy `.env.example` to `.env` and adjust the connection string and JWT secret:

```bash
cp .env.example .env
```

Start the development server:

```bash
uvicorn app.main:app --reload
```

The API is at <http://127.0.0.1:8000>; interactive docs are at <http://127.0.0.1:8000/docs>. Check `GET /health`, which returns `{"status":"ok"}`.

## Database migrations

Alembic is configured to use `DATABASE_URL` and the SQLAlchemy metadata in `app.db.base`. Create a revision after adding models, then apply migrations:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Configuration and CORS

Settings load from environment variables and `.env` via `python-dotenv`. CORS currently permits all origins, methods, and headers for hackathon development; restrict these before production. Use a strong, private `JWT_SECRET_KEY` outside local development.
