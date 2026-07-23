"""Validation schema and business rules for allocations.

`period` (a daterange) is never exposed directly over the API — payloads use
plain start_date/end_date, matching how every other date range in this
codebase (e.g. projects' start_date/planned_end) is represented. The
repository layer is what turns the pair into a daterange and back.
"""

from _shared.http import ValidationError
from _shared.validation import Field

ALLOCATION_SCHEMA = {
    "user_id": Field("uuid", required=True),
    "project_id": Field("uuid", required=True),
    "role_on_project": Field("string", max_length=120, nullable=True),
    "allocation_pct": Field("integer", required=True, minimum=1, maximum=100),
    "start_date": Field("date", required=True),
    "end_date": Field("date", required=True),
}

SORTABLE = ("allocation_pct", "created_at", "start_date", "end_date")

# start_date/end_date aren't real columns — they're derived from `period` —
# so sorting by them needs the SQL expression that actually produces them.
SORT_EXPRESSIONS = {
    "allocation_pct": "a.allocation_pct",
    "created_at": "a.created_at",
    "start_date": "lower(a.period)",
    "end_date": "upper(a.period)",
}


def check_business_rules(data, existing=None):
    """Validate rules that span more than one field.

    Over-allocation against a user's other allocations is checked
    separately in function.py, since it requires a database query rather
    than pure field comparison — mirrors how _check_references works for
    every other service in this codebase.
    """
    merged = dict(existing or {})
    merged.update(data)
    errors = {}

    start = merged.get("start_date")
    end = merged.get("end_date")

    if start and end and end < start:
        errors["end_date"] = "must be on or after the start date"

    if errors:
        raise ValidationError("One or more fields are invalid", details=errors)

    return data
