# IPO Lens

Understand an IPO beyond the hype. A free research tool that shows what is inside an Indian IPO
prospectus (DRHP/RHP), with every figure linked to its source page.

**Research aid, not investment advice.** IPO Lens does not predict listing gains or GMP and gives
no buy or sell advice.

The full product brief and rules are in [CLAUDE.md](CLAUDE.md). Design choices are logged in
[docs/decisions.md](docs/decisions.md).

## Layout

```
backend/        FastAPI app, models, Alembic migrations, tests
frontend/       Next.js app (App Router, TypeScript, Tailwind)
data/samples/   sample prospectus PDFs (git-ignored)
data/golden/    hand-verified figures (CSV)
docs/           decisions, data-source notes, rule references
.claude/skills/ custom Claude Code skills
```

## Setup on Windows

You need these installed (all free):

- [Docker Desktop](https://www.docker.com/products/docker-desktop/), running
- Python 3.11 or newer
- Node.js 22
- Git

Commands below are for PowerShell. Run them from the repo folder
(`C:\Users\aniru\code\ipo-lens`).

### 1. Environment file

```powershell
Copy-Item .env.example .env
```

The defaults work for local development. Postgres is exposed on host port **54329**, because
5432-5434 are often taken by other Postgres installs. To change it, edit `POSTGRES_PORT` and
`DATABASE_URL` together in `.env`.

### 2. Database (Postgres + pgvector)

```powershell
docker compose up -d db
docker compose ps
```

Wait until the status shows `healthy`.

### 3. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

If PowerShell refuses to run `Activate.ps1`, run this once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Check it: open <http://localhost:8000/health>. You should see
`{"status":"ok","database":"ok"}`. API docs are at <http://localhost:8000/docs>.

### 4. Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>.

## Ingesting a prospectus

Put the PDF in `data\samples\` (git-ignored), then from `backend/` with the venv active:

```powershell
python -m app.cli ingest ..\data\samples\bcssl_RHP_2026.pdf --company "Bombay Coated and Special Steels Limited" --doc-type RHP --filing-date 2026-10-21
```

`--doc-type` is one of `DRHP`, `RHP`, `addendum`, `corrigendum`, `prospectus`. Running it
again on the same file does nothing (files are matched by their SHA-256).

With the API running, read any page back at
`http://localhost:8000/documents/1/pages/42`. Page numbers are the PDF viewer's page
numbers, starting at 1.

## Checks

Backend (from `backend/`, with the venv active and the database running):

```powershell
ruff check .
ruff format --check .
mypy app tests
pytest
```

Database tests use a separate `ipolens_test` database (created automatically), so they never
touch ingested documents. They are skipped, not failed, when Postgres is not running.

Frontend (from `frontend/`):

```powershell
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

GitHub Actions runs all of these on every push and pull request
([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Migrations

After changing `backend/app/models.py`:

```powershell
alembic revision --autogenerate -m "describe the change"
```

Review the generated file before running `alembic upgrade head`. A test fails if the
migrations and models drift apart.

## Stopping

```powershell
docker compose down      # keeps data
docker compose down -v   # deletes the database volume
```
