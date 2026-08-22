# SYLO — AI Carpooling Platform

A full-stack carpooling application for universities and workplaces, built as a final year project at Bahria University, Islamabad (2026).

**Team:** M. Shayan Khan, M. Mobeen Shoukat Ch
**My contribution:** backend and frontend development, and the ML matching and clustering engine.


---

## The Problem

Carpool matching is harder than it looks. Riders have different origins, destinations, and departure windows, so naive "nearest driver" matching sends drivers on long detours and produces routes nobody wants to take. The matching problem is the interesting part of the system, and most of the engineering here goes into it.

There's a second problem specific to carpooling with strangers: trust. A rider needs some assurance the driver is who they claim to be, which is why the platform includes an identity verification pipeline.

---

## Architecture

```
┌─────────────┐        ┌──────────────────────────┐        ┌──────────────┐
│  Flutter    │  HTTP  │   FastAPI backend        │        │  PostgreSQL  │
│  client     │───────▶│   (modular monolith)     │───────▶│  + PostGIS   │
│  (Android,  │  WS    │                          │        └──────────────┘
│   Web)      │◀──────▶│  auth · rides · matching │
└─────────────┘        │  payments · verification │        ┌──────────────┐
       │               │  notifications · admin   │───────▶│    Redis     │
       │               └──────────────────────────┘        │  cache/queue │
       │                          │                        └──────────────┘
       │                          │                               ▲
       ▼                          ▼                               │
┌─────────────┐        ┌──────────────────────────┐        ┌──────────────┐
│  Firebase   │        │  Local ML models         │        │    Celery    │
│  Auth + FCM │        │  FaceNet · Tesseract     │        │  background  │
└─────────────┘        └──────────────────────────┘        └──────────────┘
```

The backend is a modular monolith: each domain (`auth`, `rides`, `matching`, `payments`, `verification`, `notifications`, `telemetry`, `ratings`, `analytics`, `admin`) is a self-contained package with its own routers, schemas, service layer, and CRUD.

---

## Matching Engine

The core of the system. Located in `backend/app/modules/matching/`.

### Two-stage pipeline

**Stage 1 — spatial prefilter.** Narrow thousands of candidate rides down to a manageable set using a geographic query:

- PostGIS `ST_DWithin` against a GIST index on ride start points
- Automatic fallback to bounding-box queries on plain btree indexes when the PostGIS extension isn't available
- Additional filters on departure time window and available seats

The fallback path matters — it means the system degrades rather than breaking on a Postgres instance without PostGIS.

**Stage 2 — weighted ranking.** Score each surviving candidate:

```python
match_score = (1 - detour_cost)   * 0.5   # minimise added travel time
            + driver_score        * 0.3   # rating and available seats
            + preference_score    * 0.2   # rider's stated constraints
```

Each component is computed from route geometry: estimated detour minutes, ETA to pickup, and percentage overlap between the rider's route and the driver's existing route. Weights are configurable via environment variables rather than hardcoded.

An `explain` flag on the request returns the score breakdown per candidate, which made the ranking logic debuggable during development.

### Clustering

Driver locations are clustered in the background so that regional groupings are precomputed rather than recalculated per request.

- Pluggable adapter interface (`ml_adapter.py`) with KMeans and DBSCAN implementations
- KMeans for known regions with a fixed cluster count; DBSCAN where cluster count is unknown and outliers need handling
- Refreshed periodically by a Celery beat task
- Results cached in Redis, with an in-memory fallback when Redis is unavailable

---

## Identity Verification

Located in `backend/app/modules/verification/`. Two locally-run models behind a common service layer.

| Component | Purpose |
|---|---|
| **FaceNet** (`face_match_adapter.py`) | Generates face embeddings and compares a submitted selfie against the photo on the uploaded ID document |
| **Tesseract OCR** (`ocr_adapter.py`) | Extracts text fields from CNIC and driving licence images |
| **Decision engine** (`decision_engine.py`) | Combines both signals into an accept / reject / manual-review outcome |

Both models run locally rather than via a third-party verification API. The adapter pattern means either could be swapped for a hosted service without touching the service layer.

Development notebooks documenting both pipelines are in `backend/app/modules/verification/machine_learning/`:

- `01_FaceNet_Verification_Pipeline.ipynb`
- `02_Tesseract_Identity_Verification_Pipeline.ipynb`

> No user-submitted identity documents are included in this repository.

---

## Other Modules

**Dynamic fare calculation** — `dynamic_fare.py`, `fuel_price_engine.py`, and `pickup_time_estimator.py` compute fares from route distance, estimated duration, and current fuel prices rather than a flat per-kilometre rate.

**Payments** — adapter-based integration layer for JazzCash, EasyPaisa, and card payments, with idempotency key handling and a reconciliation module.

**Notifications** — multi-channel dispatch (FCM push, email, SMS) behind a common adapter interface, plus WebSocket delivery for in-app notifications.

**Telemetry** — trip location streaming with anomaly detection and replay.

**Admin** — moderation, audit logging, payouts, and SOS incident handling.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Mobile / web client | Flutter (Dart) |
| API | FastAPI (Python), async SQLAlchemy |
| Database | PostgreSQL, PostGIS extension |
| Migrations | Alembic |
| Cache / queue | Redis |
| Background tasks | Celery (worker + beat) |
| Auth & push | Firebase Auth, Firebase Cloud Messaging |
| Maps & routing | Google Maps Platform |
| ML | scikit-learn (KMeans, DBSCAN), FaceNet, Tesseract OCR |
| Tooling | pre-commit, Black, Ruff, isort, pytest |

---

## Running Locally

The application cannot currently be run end-to-end — see the note at the top. These steps are documented for reference.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # fill in your own credentials
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Interactive API docs at `http://localhost:8000/docs`.

Optional services — the app runs without them, with reduced functionality:

```bash
redis-server                     # enables Redis caching and WebSocket pub/sub
celery -A app.tasks worker       # background clustering and scheduled tasks
celery -A app.tasks beat
```

### Frontend

```bash
cd frontend
flutter pub get
flutter run
```

Requires your own `firebase_options.dart` and a Google Maps API key.

### Tests

```bash
cd backend
pytest tests/ -v
```

19 test modules covering auth, rides, matching, payments, verification, notifications, telemetry, ratings, and analytics.

---

## Limitations & What I'd Do Differently

Being specific about what doesn't work:

- **Never deployed.** The application runs locally only. No containerisation, no CI/CD, no hosted environment. This is the single biggest gap and the first thing I'd fix.
- **Safety AI module is disabled.** 13 endpoints are commented out in `main.py` because `calculate_safety_score` was never implemented. The surrounding rule engine, escalation logic, and models exist; the scoring function does not. See `backend/NON_WORKING_ENDPOINTS.md`.
- **Foreign key bug.** `match_records.driver_id` references a `drivers` table that doesn't exist — the actual table is `driver_profiles`. Non-blocking, but the constraint isn't enforced.
- **No load testing.** Latency and throughput under concurrent load were never measured, so I make no claims about either.
- **Duplicate module versions.** Several modules carry `service.py`, `service_new.py`, and `service_v2.py` side by side, left over from iterative development. These should have been consolidated.
- **Degraded mode without Redis.** Notification delivery falls back to database polling and cluster caching to in-memory storage. Functional, but inefficient.
- **Matching evaluated on simulated data.** The `/simulate` endpoint generates synthetic driver distributions for testing. The engine was never validated against real ride data or live traffic conditions.
- **AI-assisted development.** Substantial portions of this codebase were written with AI coding tools, which is reflected in the repo's structure and some duplication.

---

## Repository Structure

```
backend/
  app/
    core/          # config, auth utils, fare calculation, Maps client
    models/        # SQLAlchemy models
    modules/       # domain packages (routers, schemas, service, crud)
    tasks/         # Celery tasks
  alembic/         # database migrations
  tests/           # pytest suite
frontend/
  lib/
    core/          # models, API services, theme
    features/      # screens by domain
scripts/           # local development helpers
```

---

**License:** MIT
