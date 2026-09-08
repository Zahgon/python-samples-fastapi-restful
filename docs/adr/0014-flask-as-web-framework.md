# ADR-0014: Flask as Web Framework

Date: 2026-09-08

## Status

Accepted — supersedes ADR-0008

## Context

The service was built on FastAPI and Uvicorn: an ASGI stack in which every
request is handled inside an event loop, route handlers are `async def`, and the
per-request database session is supplied by `Depends(generate_async_session)`.
FastAPI also contributed request/response validation from the Pydantic models
and an OpenAPI document served as Swagger UI at `/docs` and ReDoc at `/redoc`.

The framework had to be changed to Flask. Flask is a WSGI framework: a request
is handled synchronously on a worker thread, there is no event loop, there is no
dependency-injection mechanism, error responses are HTML, and no OpenAPI
document is produced.

The rest of the stack is not tied to either framework. The services
(`services/player_service.py`), the ORM schema, the Pydantic models and the
Alembic environment are all asynchronous but framework-agnostic, and the
Argentina 2022 squad data is the same. The API contract — endpoints, status
codes, camelCase bodies, the `X-Cache` and `Location` headers — is an invariant
of this project and had to survive the change unchanged.

Two properties of the async libraries constrain how coroutines may be driven
from a synchronous request:

- SQLAlchemy's async engine holds pooled `aiosqlite` connections.
- `aiocache.SimpleMemoryCache` schedules TTL expiry with `loop.call_later()`, so
  a cached entry is only ever evicted by the loop that stored it.

Both bind state to the loop that created it, and both would be broken by a loop
that is created and discarded per request.

## Alternatives Considered

- **Rewrite the data layer synchronously**: drop `aiosqlite` and `aiocache` for
  their blocking equivalents, making the code idiomatic Flask throughout. Set
  aside because it would rewrite the services, the database module, the ORM
  session handling and the Alembic environment — far beyond a framework change —
  and would discard the async design the project exists to demonstrate.
- **Flask's built-in async views (`flask[async]`)**: keep `async def` handlers
  and let Flask bridge them through `asgiref`. Set aside because `asgiref`
  creates a fresh event loop per request: the `aiocache` TTL handles are then
  scheduled on a loop that is closed before they can fire, so cached entries
  would never expire, and the SQLAlchemy connection pool would be shared across
  short-lived loops.
- **A new event loop per request via `asyncio.run()`**: same defect as above,
  stated explicitly rather than hidden behind the framework.
- **An ASGI-to-WSGI adapter around a Flask app**: retains a server-side event
  loop but reintroduces the ASGI stack the migration was meant to remove.

## Decision

We will run the application as a Flask WSGI app served by Gunicorn's default
synchronous worker, and keep the service, database and cache layers
asynchronous exactly as they are.

Coroutines are driven by `async_runner.run_async()`, which submits them to a
single, process-wide event loop running on a dedicated daemon thread. One
long-lived loop satisfies both constraints above: the SQLAlchemy pool and the
`aiocache` TTL handles stay valid for the lifetime of the worker. The loop is
started lazily so that it is never created before Gunicorn forks its workers.

The three responsibilities FastAPI provided implicitly are now explicit:

- **Session lifetime** — `generate_async_session()` stores the `AsyncSession` on
  Flask's application context (`g`), giving it the same one-per-request lifetime
  the `Depends()` provider had; `close_async_session()` is registered as a
  `teardown_appcontext` callback.
- **Validation and errors** — request bodies are validated with
  `PlayerRequestModel.model_validate()` and path parameters with a Pydantic
  `TypeAdapter`, so a malformed value still yields `422 Unprocessable Entity`
  with the same payload. `read_request_body()` reproduces FastAPI's body
  extraction, including its media-type test, so an absent body, an unparsable
  one and a valid one that fails validation are still reported as three distinct
  errors. `routes/http_error.py` renders every aborted request as
  `{"detail": ...}`. The handler is registered for `HTTPException` only: a
  Pydantic failure is converted to 422 at the point of parsing, so a validation
  error raised anywhere else still surfaces as `500`.
- **Documentation** — `routes/docs_route.py` serves `/openapi.json`, `/docs` and
  `/redoc`, with the component schemas generated from the same Pydantic models.

## Consequences

- Every endpoint, status code and response body was compared request by request
  against the FastAPI implementation. The success paths, the `X-Cache` and
  `Location` headers, and the `422 Unprocessable Entity` payloads for both path
  parameters and request bodies are identical. Seven differences remain, none of
  which changes a documented endpoint:
  - `405 Method Not Allowed` advertises every method the path accepts in its
    `Allow` header; FastAPI advertised only one.
  - `HEAD` and `OPTIONS` return `200 OK` where FastAPI returned `405`. Werkzeug
    registers both for every rule, which is what RFC 9110 asks for; suppressing
    them would require a custom rule class and would make the service less
    correct, not more faithful.
  - `/health/` is served directly rather than redirected to `/health` with
    `307`, because Werkzeug only redirects towards a trailing slash, never away
    from one.
  - `/players` redirects to `/players/` with `308` rather than `307`; both
    preserve the request method.
  - `/players/squadnumber/` (a trailing slash with no value) returns `404`
    rather than `422`, because Werkzeug does not fall back to the shorter
    `/players/<player_id>` rule for an empty segment.
  - Response bodies end with a newline, which `flask.jsonify` appends.
  - An unhandled server error returns `{"detail": "Internal Server Error"}`
    rather than a plain-text body.
- The services, the ORM schema, the Pydantic models and the Alembic environment
  were not modified.
- Concurrency is now bounded by Gunicorn's worker count rather than by an event
  loop, because a synchronous worker blocks for the duration of a request. This
  is the cost of the WSGI model and is unrelated to the data layer remaining
  asynchronous.
- Every request pays a thread hand-off to the runner loop. It is negligible
  against SQLite access, but it is not free.
- The event loop is per process, so a forking server gets one loop per worker.
  Anything stored on it — including the in-memory cache — is per worker, exactly
  as it already was under Uvicorn workers.
- The OpenAPI document is now assembled by hand in `routes/docs_route.py`
  instead of being derived from the route signatures. Adding or changing an
  endpoint requires updating that module as well. The component schemas are
  generated from the Pydantic models, and `tests/test_docs.py` fails if the
  document and the URL map disagree in either direction, so the two cannot drift
  apart silently.
- `pydantic` and `greenlet` are now declared as direct dependencies. They were
  previously installed transitively through `fastapi[standard]` and SQLAlchemy's
  async extra.
- ADR-0008 described the same layering in terms of FastAPI's `Depends()`. The
  layering itself is retained; only the mechanism that supplies the session
  changed, which is why this record supersedes it rather than reversing it.
