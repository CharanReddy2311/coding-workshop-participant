"""deliverables-service — CRUD for deliverables, plus their dependency edges.

    POST   /api/deliverables-service                                    create
    GET    /api/deliverables-service                                    list, with search and filters
    GET    /api/deliverables-service/{id}                                read one
    PUT    /api/deliverables-service/{id}                                update
    DELETE /api/deliverables-service/{id}                                delete
    GET    /api/deliverables-service/{id}/dependencies                   list predecessors + successors
    POST   /api/deliverables-service/{id}/dependencies                   add a predecessor edge
    DELETE /api/deliverables-service/{id}/dependencies/{predecessor_id}  remove a predecessor edge

The dependency sub-resource is deliberately lightweight: it manages edges in
deliverable_dependencies (with cycle prevention) but doesn't compute a
critical path — that's a separate, larger feature and not part of this pass.
"""

import logging

import repository
from schema import DELIVERABLE_SCHEMA, DEPENDENCY_SCHEMA, check_business_rules

from _shared.auth import authorize
from _shared.db import exists
from _shared.http import (
    ApiError,
    ConflictError,
    NotFoundError,
    ValidationError,
    http_method,
    parse_body,
    path_segments,
    query_params,
    response,
    with_http_errors,
)
from _shared.validation import validate

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "deliverables-service"
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
    if data.get("project_id") and not exists("projects", data["project_id"]):
        errors["project_id"] = "no project exists with this id"
    if data.get("owner_id") and not exists("users", data["owner_id"]):
        errors["owner_id"] = "no user exists with this id"
    if errors:
        raise ValidationError("One or more references are invalid", details=errors)


def list_deliverables(event):
    rows, meta = repository.list_deliverables(query_params(event))
    return response(200, rows, meta)


def get_deliverable(deliverable_id):
    deliverable = repository.get_deliverable(deliverable_id)
    if not deliverable:
        raise NotFoundError(f"No deliverable found with id {deliverable_id}")
    return response(200, deliverable)


def create_deliverable(event):
    data = validate(parse_body(event), DELIVERABLE_SCHEMA)
    check_business_rules(data)
    _check_references(data)

    created = repository.create_deliverable(data)
    logger.info("Created deliverable %s", created["id"])
    return response(201, repository.get_deliverable(created["id"]))


def update_deliverable(event, deliverable_id):
    existing = repository.get_deliverable(deliverable_id)
    if not existing:
        raise NotFoundError(f"No deliverable found with id {deliverable_id}")

    data = validate(parse_body(event), DELIVERABLE_SCHEMA, partial=True)
    check_business_rules(data, existing=existing)
    _check_references(data)

    repository.update_deliverable(deliverable_id, data)
    logger.info("Updated deliverable %s (fields: %s)", deliverable_id, ", ".join(data))
    return response(200, repository.get_deliverable(deliverable_id))


def delete_deliverable(deliverable_id):
    if not repository.get_deliverable(deliverable_id):
        raise NotFoundError(f"No deliverable found with id {deliverable_id}")
    repository.delete_deliverable(deliverable_id)
    logger.info("Deleted deliverable %s", deliverable_id)
    return response(204)


def list_dependencies(deliverable_id):
    if not repository.get_deliverable(deliverable_id):
        raise NotFoundError(f"No deliverable found with id {deliverable_id}")
    return response(200, repository.list_dependencies(deliverable_id))


def add_dependency(event, deliverable_id):
    if not repository.get_deliverable(deliverable_id):
        raise NotFoundError(f"No deliverable found with id {deliverable_id}")

    data = validate(parse_body(event), DEPENDENCY_SCHEMA)
    predecessor_id = data["predecessor_id"]

    if predecessor_id == deliverable_id:
        raise ValidationError(
            "One or more fields are invalid",
            details={"predecessor_id": "a deliverable cannot depend on itself"},
        )
    if not exists("deliverables", predecessor_id):
        raise ValidationError(
            "One or more fields are invalid",
            details={"predecessor_id": "no deliverable exists with this id"},
        )
    if repository.would_create_cycle(predecessor_id, deliverable_id):
        raise ConflictError(
            "This dependency would create a cycle in the dependency graph",
            details={"predecessor_id": predecessor_id, "successor_id": deliverable_id},
        )

    repository.add_dependency(predecessor_id, deliverable_id, data["dep_type"])
    logger.info("Added dependency %s -> %s", predecessor_id, deliverable_id)
    return response(201, repository.list_dependencies(deliverable_id))


def remove_dependency(deliverable_id, predecessor_id):
    repository.remove_dependency(predecessor_id, deliverable_id)
    logger.info("Removed dependency %s -> %s", predecessor_id, deliverable_id)
    return response(204)


@with_http_errors
def handler(event=None, context=None):
    event = event or {}
    method = http_method(event)

    if method == "OPTIONS":
        return response(204)

    if method not in SUPPORTED_METHODS:
        raise ApiError(f"Method {method} is not supported", status=405, code="method_not_allowed")

    user = authorize(event, PERMISSIONS)
    segments = path_segments(event, SERVICE_NAME)
    deliverable_id = segments[0] if segments else None
    sub_resource = segments[1] if len(segments) > 1 else None
    edge_predecessor_id = segments[2] if len(segments) > 2 else None

    logger.info("%s %s by %s (%s)", method, "/".join(segments) or "-", user["email"], user["role"])

    if sub_resource == "dependencies":
        if not deliverable_id:
            raise ValidationError("A deliverable id is required in the path")
        if method == "GET":
            return list_dependencies(deliverable_id)
        if method == "POST":
            return add_dependency(event, deliverable_id)
        if method == "DELETE":
            if not edge_predecessor_id:
                raise ValidationError("A predecessor id is required in the path")
            return remove_dependency(deliverable_id, edge_predecessor_id)
        raise ApiError(
            f"Method {method} is not supported on /dependencies",
            status=405,
            code="method_not_allowed",
        )

    if method == "GET":
        return get_deliverable(deliverable_id) if deliverable_id else list_deliverables(event)
    if method == "POST":
        return create_deliverable(event)
    if method == "PUT":
        if not deliverable_id:
            raise ValidationError("A deliverable id is required in the path")
        return update_deliverable(event, deliverable_id)
    if method == "DELETE":
        if not deliverable_id:
            raise ValidationError("A deliverable id is required in the path")
        return delete_deliverable(deliverable_id)

    raise ApiError(f"Method {method} is not supported", status=405, code="method_not_allowed")


if __name__ == "__main__":
    print(handler())
