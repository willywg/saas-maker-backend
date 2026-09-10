# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
make dev              # Run dev server with auto-reload (port 8090)
make migrate          # Apply Alembic migrations
make makemigrations m="message"  # Create new migration
make test             # Run pytest
make install          # Install dependencies via uv (incluye ruff/pytest)
make lint             # ruff check + format check
make format           # ruff auto-fix + format
make audit            # Security audit of uv.lock (uv-secure)
make upgrade          # uv lock --upgrade + sync + audit
```

Requires Python 3.14 (see `.python-version`); `uv` downloads it automatically.

## Environment Setup

Copy `.env.example` to `.env` and configure. Generate JWT secret with:
```bash
openssl rand -hex 32
```

## Architecture

### Tech Stack
- FastAPI + Uvicorn (async)
- SQLModel (SQLAlchemy + Pydantic)
- PostgreSQL with asyncpg
- Alembic for migrations
- PyJWT for JWT
- bcrypt for password hashing

### Directory Structure
```
app/
├── core/           # Config, security, dependencies
├── models/         # SQLModel database models (tenant.py)
├── schemas/        # Pydantic request/response schemas
├── controllers/    # FastAPI route handlers
├── services/       # Business logic layer
├── db/             # Database session management
└── main.py         # FastAPI app initialization
```

### Multi-Tenancy Model
- **Organization**: Tenant entity with slug
- **User**: Can belong to multiple organizations
- **OrganizationMember**: Many-to-many with role (owner/admin/member)
- **InviteToken**: Single-use invitation tokens with expiration

### Authentication Flow
- JWT tokens with user context (user_id, email, org_id, role)
- Access token (30 min, stateless) + Refresh token (7 days, persisted in `refresh_tokens`)
- Refresh tokens rotate on every `/auth/refresh`; they can be revoked (logout, logout-all,
  password change/reset). Logic in `app/services/session_service.py`
- Login expects form-data with `username` field (email value)
- A session is scoped to one organization; `/auth/switch-organization` issues tokens for another
  org the user belongs to, and refresh keeps that org
- Email verification: `users.email_verified`; register sends a link, `/auth/verify-email`
  confirms it. `REQUIRE_EMAIL_VERIFICATION=true` blocks login until verified (default false)
- Rate limiting (slowapi, per IP, in-memory) on auth endpoints: `RATE_LIMIT_AUTH` (default 10/minute)
- Role hierarchy: owner > admin > member
- Admin panel tokens stay stateless (no revocation table)

### Key Dependencies (in `app/core/dependencies.py`)
```python
get_current_user()      # Validates JWT, returns AuthUser
require_role("admin")   # Factory for role-based authorization
CurrentUser             # Type alias for dependency injection
```

### API Endpoints
- `POST /auth/register` - Create user + organization
- `POST /auth/login` - Authenticate (form-data)
- `POST /auth/refresh` - Rotate tokens (old refresh token is revoked)
- `POST /auth/logout` - Revoke a refresh token
- `POST /auth/logout-all` - Revoke all sessions of the current user
- `GET /auth/me` - Current user info (includes `email_verified`)
- `PUT /auth/me` - Update profile
- `POST /auth/change-password` - Change password (revokes other sessions)
- `POST /auth/forgot-password`, `GET/POST /auth/reset-password` - Password recovery
- `POST /auth/verify-email`, `POST /auth/resend-verification` - Email verification
- `GET /auth/organizations` - Organizations the user belongs to
- `POST /auth/switch-organization` - Tokens scoped to another organization
- `GET /auth/invite/{token}` - Get invitation details (public)
- `POST /auth/accept-invite` - Accept invitation
- `GET /organizations/me` - Current organization
- `PUT /organizations/me` - Update organization (owner only)
- `GET /organizations/members` - List members (admin+)
- `POST /organizations/members/invite` - Create invitation (admin+)
- `PUT /organizations/members/{user_id}/role` - Change role (owner)
- `DELETE /organizations/members/{user_id}` - Remove member (owner)
- `GET/POST /projects`, `GET/PUT/DELETE /projects/{id}` - Reference tenant-scoped resource
  (read: any member; write: admin+; other orgs get 404). Paginated list with `q`, `status`,
  `page`, `page_size`.

### Tests (`tests/`)
- Run with `make test`. Needs a local Postgres; uses (and creates) `saas_template_test`.
- `conftest.py` resets the schema and runs the real Alembic migrations once per session,
  truncates tables between tests, stubs SMTP, and exposes `client`, `owner_tokens`,
  `register()` and `auth_headers()` helpers.
- Every new endpoint gets a test next to the existing ones (`test_auth.py`,
  `test_organizations.py`, `test_admin.py`, `test_password_reset.py`).

### Adding New Features
Copy the `projects` module (`app/models/project.py`, `app/schemas/project.py`,
`app/services/project_service.py`, `app/controllers/projects.py`, `tests/test_projects.py`).
Non-negotiable: every service function takes `organization_id` and filters by it; a resource
from another organization answers 404. Insert registrations at the `# generator:*` anchors.
1. Create model in `app/models/`
2. Create schemas in `app/schemas/`
3. Create service in `app/services/`
4. Create controller in `app/controllers/`
5. Register router in `app/main.py`
6. Run `make makemigrations m="description"` then `make migrate`
7. Add tests in `tests/` and run `make test` + `make lint`
