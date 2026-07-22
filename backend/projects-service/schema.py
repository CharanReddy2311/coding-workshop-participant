"""Validation schema and cross-field business rules for projects."""

from _shared.http import ValidationError
from _shared.validation import Field

STATUSES = ("PLANNING", "ACTIVE", "ON_HOLD", "COMPLETED", "CANCELLED")
PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

PROJECT_SCHEMA = {
    "code": Field("string", required=True, min_length=2, max_length=20),
    "name": Field("string", required=True, min_length=3, max_length=200),
    "description": Field("string", max_length=2000, nullable=True),
    "department_id": Field("uuid", required=True),
    "manager_id": Field("uuid", required=True),
    "status": Field("string", choices=STATUSES, default="PLANNING"),
    "priority": Field("string", choices=PRIORITIES, default="MEDIUM"),
    "start_date": Field("date", required=True),
    "planned_end": Field("date", required=True),
    "actual_end": Field("date", nullable=True),
    "planned_budget": Field("decimal", minimum=0, default=0),
}

# Columns a client may sort by. Anything else is ignored rather than
# interpolated into SQL.
SORTABLE = ("code", "name", "status", "priority", "start_date",
            "planned_end", "planned_budget", "created_at")


def check_business_rules(data, existing=None):
    """Validate rules that span more than one field.

    `existing` is the current row on update, so a partial payload is checked
    against the values it will actually end up combined with — otherwise a
    one-field update could quietly create an invalid row.
    """
    merged = dict(existing or {})
    merged.update(data)
    errors = {}

    start = merged.get("start_date")
    planned_end = merged.get("planned_end")
    actual_end = merged.get("actual_end")

    if start and planned_end and planned_end < start:
        errors["planned_end"] = "must be on or after the start date"

    if start and actual_end and actual_end < start:
        errors["actual_end"] = "must be on or after the start date"

    if merged.get("status") == "COMPLETED" and not actual_end:
        errors["actual_end"] = "is required when a project is marked completed"

    if actual_end and merged.get("status") not in ("COMPLETED", "CANCELLED"):
        errors["status"] = "must be COMPLETED or CANCELLED when an end date is set"

    if errors:
        raise ValidationError("One or more fields are invalid", details=errors)

    return data
