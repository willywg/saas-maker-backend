# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
make dev              # Run dev server with auto-reload (port 8090)
make migrate          # Apply Alembic migrations
make makemigrations m="message"  # Create new migration
make test             # Run pytest
make install          # Install dependencies via uv
```

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
- python-jose for JWT
- passlib + bcrypt for passwords

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
- Access token (30 min) + Refresh token (7 days)
- Login expects form-data with `username` field (email value)
- Role hierarchy: owner > admin > member

### Key Dependencies (in `app/core/dependencies.py`)
```python
get_current_user()      # Validates JWT, returns AuthUser
require_role("admin")   # Factory for role-based authorization
CurrentUser             # Type alias for dependency injection
```

### API Endpoints
- `POST /auth/register` - Create user + organization
- `POST /auth/login` - Authenticate (form-data)
- `POST /auth/refresh` - Refresh access token
- `GET /auth/me` - Current user info
- `GET /auth/invite/{token}` - Get invitation details (public)
- `POST /auth/accept-invite` - Accept invitation
- `GET /organizations/me` - Current organization
- `PUT /organizations/me` - Update organization (owner only)
- `GET /organizations/members` - List members (admin+)
- `POST /organizations/members/invite` - Create invitation (admin+)
- `PUT /organizations/members/{user_id}/role` - Change role (owner)
- `DELETE /organizations/members/{user_id}` - Remove member (owner)

### Adding New Features
1. Create model in `app/models/`
2. Create schemas in `app/schemas/`
3. Create service in `app/services/`
4. Create controller in `app/controllers/`
5. Register router in `app/main.py`
6. Run `make makemigrations m="description"` then `make migrate`
