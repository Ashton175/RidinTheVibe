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

Create a PostgreSQL database named `asset_risk` (or update `DATABASE_URL`), then copy `.env.example` to `.env`. On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Update `DATABASE_URL` and set a private `JWT_SECRET_KEY` in `.env`. To enable AI explanations, add your OpenAI key as `OPENAI_API_KEY=...` in this local file. Do not commit `.env`.

Apply the database migrations before starting the API:

```bash
alembic upgrade head
```

Start the development server:

```bash
uvicorn app.main:app --reload
```

The API is at <http://127.0.0.1:8000>; interactive docs are at <http://127.0.0.1:8000/docs>. Check `GET /health`, which returns `{"status":"ok"}`.

## Authentication and role scoping

`POST /auth/register` is available for hackathon test-user seeding and does not require email verification. Create the organization and site first, then send JSON like:

```json
{
  "email": "manager@example.com",
  "password": "change-this-password",
  "role": "site_management",
  "organization_id": 1,
  "site_id": 1
}
```

Use `POST /auth/login` with `{"email":"manager@example.com","password":"change-this-password"}` to receive a bearer access token. Send it on protected requests as `Authorization: Bearer <access_token>`. Tokens include the user ID, role, organization ID, and site ID, and expire after `ACCESS_TOKEN_EXPIRE_MINUTES`. Passwords are stored as bcrypt hashes.

Authenticated routes use `get_current_user`; role-restricted routes can use `require_role(...)`. Missing or invalid credentials return **401**. A valid user with a disallowed role receives **403**. Technician routes can opt into the `technician` role and currently return **501 Not Implemented**.

For data access, inject `get_site_scope` and apply `apply_site_scope(statement, Model, scope)` to site-owned queries. `upper_management` users have `site_id = null` and are scoped to all sites whose `organization_id` matches theirs. `site_management` users have one required `site_id` and are scoped only to that site. The scope helper also filters records linked through `asset_id` (such as inspections and risk assessments) through assets at the allowed sites. The database is checked when loading the current user, so role or scope changes invalidate older tokens and require a fresh login.

Registration accepts a role for convenience while seeding test accounts. Restrict or remove public registration before deploying outside the hackathon.

## Site data uploads

Authenticated `upper_management` and `site_management` users can upload CSV or XLSX files to:

- `POST /sites/{site_id}/upload/assets`
- `POST /sites/{site_id}/upload/inspections`
- `POST /sites/{site_id}/upload/maintenance`

Send a multipart form field named `file`. Headers are normalized to lowercase underscore names before required-column checks; extra columns are retained in asset `metadata` or the record's `raw_data`. Uploads are limited to 20 MB. Upper management can target sites in their organization, while site management can target only their assigned site. Inspection and maintenance rows with unknown asset tags are skipped and returned in `unmatched_rows`; row-level validation problems appear in `errors`. Assets are upserted by site and asset tag; inspections and maintenance records by asset and their respective date.

## Database migrations

Alembic is configured to use `DATABASE_URL` and the SQLAlchemy metadata in `app.db.base`. Create a revision after adding models, then apply migrations:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Configuration and CORS

Settings load from environment variables and `.env` via `python-dotenv`. CORS currently permits all origins, methods, and headers for hackathon development; restrict these before production. Use a strong, private `JWT_SECRET_KEY` outside local development.

AI-generated risk explanations use the official OpenAI Python SDK. Add your API key to `.env` as `OPENAI_API_KEY=...`; never commit the key. `OPENAI_MODEL` defaults to `gpt-4.1-mini` and `OPENAI_TIMEOUT_SECONDS` defaults to `8`. If the key is absent or the API call fails, the analysis still completes with a logged, templated explanation.

## Maintenance schedule

Management users can read a site's calendar with `GET /sites/{site_id}/schedule?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`, create manual events with `POST /sites/{site_id}/schedule`, or create risk-linked follow-ups with `POST /risk-assessments/{risk_assessment_id}/schedule`. Events can be edited with `PATCH /schedule/{event_id}`, have their status changed with `PATCH /schedule/{event_id}/status`, or be deleted with `DELETE /schedule/{event_id}`. Site managers are limited to their assigned site; upper management can select any site in their organization. Calendar responses include nested asset and triggering risk details.
