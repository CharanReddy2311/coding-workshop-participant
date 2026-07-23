"""allocations-service — CRUD for project resource allocations.

    POST   /api/allocations-service        create
    GET    /api/allocations-service        list, filterable by user_id/project_id
    GET    /api/allocations-service/{id}   read one
    PUT    /api/allocations-service/{id}   update
    DELETE /api/allocations-service/{id}   delete

Over-allocation is enforced on every create and update: a user's peak
*concurrent* allocation_pct on any single day can never exceed 100. That peak
is a sweep line over the overlapping allocations (repository.peak_existing_pct),
not a naive sum of every overlapping row — two allocations that overlap the new
window but not each other are never counted together. The authoritative check
runs inside the write transaction behind a per-user advisory lock, so two
concurrent writers for the same user cannot both pass and then both write.
The idx_allocations_user_period GiST index (see schema.sql) keeps the overlap
lookup cheap.
"""

import logging

import repository
from schema import ALLOCATION_SCHEMA, check_business_rules

from _shared.auth import authorize
from _shared.db import exists
from _shared.http import (
    ApiError,
    ConflictError,
    NotFoundError,
    ValidationError,
    http_method,
    parse_body,
    query_params,
    resource_id,
    response,
    with_http_errors,
)
from _shared.validation import validate

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "allocations-service"
SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "OPTIONS")

# Viewers read; Contributors and Managers create/edit; Managers and Admins delete.
PERMISSIONS = {
    "GET": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
    "OPTIONS": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
    "POST": ("CONTRIBUTOR", "MANAGER", "ADMIN"),
    "PUT": ("CONTRIBUTOR", "MANAGER", "ADMIN"),
    "DELETE": ("MANAGER", "ADMIN"),
}


def _check_references(data):
    """Verify foreign keys up front so the client gets a 400, not a 500."""
    errors = {}
    if data.get("user_id") and not exists("users", data["user_id"]):
        errors["user_id"] = "no user exists with this id"
    if data.get("project_id") and not exists("projects", data["project_id"]):
        errors["project_id"] = "no project exists with this id"
    if errors:
        raise ValidationError("One or more references are invalid", details=errors)


def _check_overlap(merged, exclude_id=None):
    """Reject if this allocation would push the user over 100% for any single
    day the new/updated period covers.

    This is a fail-fast, friendly pre-check using the peak *concurrent* load
    (not a naive sum of every overlapping row). The authoritative, race-free
    enforcement runs inside the write transaction in repository.py behind a
    per-user advisory lock; this pre-check just lets the common case fail with
    a clear message before a transaction is opened.
    """
    existing_pct = repository.peak_existing_pct(
        merged["user_id"], merged["start_date"], merged["end_date"], exclude_id=exclude_id
    )
    projected = existing_pct + merged["allocation_pct"]
    if projected > 100:
        raise ConflictError(
            "This allocation would over-allocate the user for the overlapping dates",
            details={
                "existing_pct": existing_pct,
                "requested_pct": merged["allocation_pct"],
                "projected_pct": projected,
                "max_pct": 100,
            },
        )


def list_allocations(event):
    rows, meta = repository.list_allocations(query_params(event))
    return response(200, rows, meta)


def get_allocation(allocation_id):
    allocation = repository.get_allocation(allocation_id)
    if not allocation:
        raise NotFoundError(f"No allocation found with id {allocation_id}")
    return response(200, allocation)


def create_allocation(event):
    data = validate(parse_body(event), ALLOCATION_SCHEMA)
    check_business_rules(data)
    _check_references(data)
    _check_overlap(data)

    created = repository.create_allocation(data)
    logger.info("Created allocation %s", created["id"])
    return response(201, repository.get_allocation(created["id"]))


def update_allocation(event, allocation_id):
    existing = repository.get_allocation(allocation_id)
    if not existing:
        raise NotFoundError(f"No allocation found with id {allocation_id}")

    data = validate(parse_body(event), ALLOCATION_SCHEMA, partial=True)
    check_business_rules(data, existing=existing)
    _check_references(data)

    merged = dict(existing)
    merged.update(data)
    _check_overlap(merged, exclude_id=allocation_id)

    repository.update_allocation(allocation_id, data, merged)
    logger.info("Updated allocation %s (fields: %s)", allocation_id, ", ".join(data))
    return response(200, repository.get_allocation(allocation_id))


def delete_allocation(allocation_id):
    if not repository.get_allocation(allocation_id):
        raise NotFoundError(f"No allocation found with id {allocation_id}")
    repository.delete_allocation(allocation_id)
    logger.info("Deleted allocation %s", allocation_id)
    return response(204)


@with_http_errors
def handler(event=None, context=None):
    event = event or {}
    method = http_method(event)
    allocation_id = resource_id(event, SERVICE_NAME)

    if method == "OPTIONS":
        return response(204)

    if method not in SUPPORTED_METHODS:
        raise ApiError(f"Method {method} is not supported", status=405, code="method_not_allowed")

    user = authorize(event, PERMISSIONS)
    logger.info("%s %s by %s (%s)", method, allocation_id or "-", user["email"], user["role"])

    if method == "GET":
        return get_allocation(allocation_id) if allocation_id else list_allocations(event)
    if method == "POST":
        return create_allocation(event)
    if method == "PUT":
        if not allocation_id:
            raise ValidationError("An allocation id is required in the path")
        return update_allocation(event, allocation_id)
    if method == "DELETE":
        if not allocation_id:
            raise ValidationError("An allocation id is required in the path")
        return delete_allocation(allocation_id)

    raise ApiError(f"Method {method} is not supported", status=405, code="method_not_allowed")


if __name__ == "__main__":
    print(handler())
