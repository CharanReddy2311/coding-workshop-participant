"""Validation schema and business rules for deliverables and their
dependency edges."""

from _shared.http import ValidationError
from _shared.validation import Field

STATUSES = ("NOT_STARTED", "IN_PROGRESS", "BLOCKED", "COMPLETED", "CANCELLED")
DEP_TYPES = ("FINISH_TO_START", "START_TO_START", "FINISH_TO_FINISH")

DELIVERABLE_SCHEMA = {
    "project_id": Field("uuid", required=True),
    "owner_id": Field("uuid", nullable=True),
    "name": Field("string", required=True, min_length=2, max_length=200),
    "description": Field("string", max_length=2000, nullable=True),
    "status": Field("string", choices=STATUSES, default="NOT_STARTED"),
    "percent_complete": Field("integer", minimum=0, maximum=100, default=0),
    # DB check is `weight > 0`; 0.01 is the smallest value the column's
    # numeric(6,2) precision can actually represent, so it's the tightest
    # inclusive lower bound Field's minimum can express for that constraint.
    "weight": Field("decimal", minimum=0.01, default=1),
    "due_date": Field("date", required=True),
    "completed_at": Field("date", nullable=True),
}

DEPENDENCY_SCHEMA = {
    "predecessor_id": Field("uuid", required=True),
    "dep_type": Field("string", choices=DEP_TYPES, default="FINISH_TO_START"),
}

SORTABLE = ("name", "status", "due_date", "weight", "percent_complete", "created_at")


def check_business_rules(data, existing=None):
    """Validate cross-field rules for a deliverable payload.

    `existing` is the current row on update, so a partial payload is checked
    against the values it will actually end up combined with.
    """
    merged = dict(existing or {})
    merged.update(data)
    errors = {}

    status = merged.get("status")
    completed_at = merged.get("completed_at")

    if status == "COMPLETED" and not completed_at:
        errors["completed_at"] = "is required when a deliverable is marked completed"

    if completed_at and status not in ("COMPLETED", "CANCELLED"):
        errors["status"] = "must be COMPLETED or CANCELLED when completed_at is set"

    if errors:
        raise ValidationError("One or more fields are invalid", details=errors)

    return data
