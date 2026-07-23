"""Validation schema and business rules for users.

`password` is a write-only field: it is accepted on the way in, hashed by the
handler before it ever reaches the database, and never selected back out (see
repository.py, which lists columns explicitly so password_hash cannot leak).
"""

from _shared.auth import ROLES
from _shared.http import ValidationError
from _shared.validation import Field

USER_SCHEMA = {
    "email": Field("email", required=True),
    "full_name": Field("string", required=True, min_length=2, max_length=200),
    # Required on create; on a partial update an absent password simply leaves
    # the existing hash untouched. Minimum length is a floor, not a policy —
    # the real strength requirement would live here if the brief demanded one.
    "password": Field("string", required=True, min_length=8, max_length=256),
    "role": Field("string", choices=ROLES, default="VIEWER"),
    "department_id": Field("uuid", nullable=True),
    "is_active": Field("boolean", default=True),
}

SORTABLE = ("email", "full_name", "role", "is_active", "created_at")


def check_business_rules(data, existing=None):
    """Validate rules that span more than one field.

    Kept for symmetry with the other services and as the obvious home for
    future cross-field policy (e.g. password complexity tied to role).
    """
    merged = dict(existing or {})
    merged.update(data)
    errors = {}

    if merged.get("full_name") is not None and not str(merged["full_name"]).strip():
        errors["full_name"] = "may not be empty"

    if errors:
        raise ValidationError("One or more fields are invalid", details=errors)

    return data
