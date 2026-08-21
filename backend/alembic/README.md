# Alembic Migrations

This directory contains database migrations for the SmartCarpoolingApp backend.

## Directory Structure

- `versions/` - Contains all migration files
- `env.py` - Alembic environment configuration
- `script.py.mako` - Template for generating new migration files
- `../alembic.ini` - Alembic configuration file

## Usage

### Generate a new migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Description of changes"

# Create empty migration (for manual changes)
alembic revision -m "Description of changes"
```

### Apply migrations

```bash
# Upgrade to latest version
alembic upgrade head

# Upgrade by one version
alembic upgrade +1

# Upgrade to specific revision
alembic upgrade <revision_id>
```

### Rollback migrations

```bash
# Downgrade by one version
alembic downgrade -1

# Downgrade to specific revision
alembic downgrade <revision_id>

# Downgrade all migrations
alembic downgrade base
```

### View migration history

```bash
# Show current revision
alembic current

# Show migration history
alembic history

# Show verbose history
alembic history --verbose
```

## Migration File Naming

Migration files follow this format:
```
YYYYMMDD_HHMM_<revision>_<slug>.py
```

Example: `20251108_1430_abc123def456_initial_database_schema.py`

## Best Practices

1. **Always review auto-generated migrations** - Alembic's autogenerate is not perfect
2. **Test migrations in development first** - Never run untested migrations in production
3. **Add manual data migrations if needed** - Alembic only handles schema changes
4. **Use descriptive migration messages** - Make it easy to understand what changed
5. **Never edit applied migrations** - Create a new migration to fix issues
6. **Backup database before migrations** - Always have a rollback plan

## Notes

- Migrations use async SQLAlchemy
- Database URL is read from `app.core.config.settings.DB_URL`
- All models are imported in `app/db/base.py` for autogeneration
- Supports PostgreSQL-specific features (UUID, ENUM, JSON, etc.)
