"""Read-only data access for reference/lookup data."""

from _shared.db import query_all


def list_departments():
    return query_all("SELECT id, name FROM departments ORDER BY name")


def list_active_users():
    return query_all(
        "SELECT id, full_name, email FROM users WHERE is_active = true ORDER BY full_name"
    )
