"""Validation schema and business rules for teams."""

from _shared.http import ValidationError
from _shared.validation import Field

TEAM_SCHEMA = {
    "name": Field("string", required=True, min_length=2, max_length=120),
    "description": Field("string", max_length=2000, nullable=True),
    "department_id": Field("uuid", required=True),
    "manager_id": Field("uuid", required=True),
    "is_active": Field("boolean", default=True),
}

SORTABLE = ("name", "department_id", "manager_id", "is_active", "created_at")


def check_business_rules(data, existing=None):
    """Validate cross-field rules for team payloads."""
    merged = dict(existing or {})
    merged.update(data)
    errors = {}

    if merged.get("name") and not str(merged["name"]).strip():
        errors["name"] = "may not be empty"

    if errors:
        raise ValidationError("One or more fields are invalid", details=errors)

    return data
