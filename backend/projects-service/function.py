"""projects-service — CRUD for projects.

    POST   /api/projects-service        create
    GET    /api/projects-service        list, with search and filters
    GET    /api/projects-service/{id}   read one
    PUT    /api/projects-service/{id}   update
    DELETE /api/projects-service/{id}   delete

The entry point must be named `handler`: infra/locals.tf pins every Python
Lambda to "function.handler".
"""

import logging

import repository
from schema import PROJECT_SCHEMA, check_business_rules

from _shared.auth import authorize
from _shared.db import exists
from _shared.http import (
    ApiError,
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

SERVICE_NAME = "projects-service"
SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "OPTIONS")

# Stricter than the shared default: a Contributor may update a project but not
# create or delete one.
PERMISSIONS = {
    "GET": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
    "OPTIONS": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
    "POST": ("MANAGER", "ADMIN"),
    "PUT": ("CONTRIBUTOR", "MANAGER", "ADMIN"),
    "DELETE": ("ADMIN",),
}


def _check_references(data):
    """Verify foreign keys up front so the client gets a 400, not a 500."""
    errors = {}
    if data.get("department_id") and not exists("departments", data["department_id"]):
        errors["department_id"] = "no department exists with this id"
    if data.get("manager_id") and not exists("users", data["manager_id"]):
        errors["manager_id"] = "no user exists with this id"
    if errors:
        raise ValidationError("One or more references are invalid", details=errors)


def list_projects(event):
    rows, meta = repository.list_projects(query_params(event))
    return response(200, rows, meta)


def get_project(project_id):
    project = repository.get_project(project_id)
    if not project:
        raise NotFoundError(f"No project found with id {project_id}")
    return response(200, project)


def create_project(event):
    data = validate(parse_body(event), PROJECT_SCHEMA)
    check_business_rules(data)
    _check_references(data)

    if repository.code_taken(data["code"]):
        raise ValidationError(
            "One or more fields are invalid",
            details={"code": "is already used by another project"},
        )

    created = repository.create_project(data)
    logger.info("Created project %s", created["id"])
    return response(201, repository.get_project(created["id"]))


def update_project(event, project_id):
    existing = repository.get_project(project_id)
    if not existing:
        raise NotFoundError(f"No project found with id {project_id}")

    data = validate(parse_body(event), PROJECT_SCHEMA, partial=True)
    check_business_rules(data, existing=existing)
    _check_references(data)

    if "code" in data and repository.code_taken(data["code"], exclude_id=project_id):
        raise ValidationError(
            "One or more fields are invalid",
            details={"code": "is already used by another project"},
        )

    repository.update_project(project_id, data)
    logger.info("Updated project %s (fields: %s)", project_id, ", ".join(data))
    return response(200, repository.get_project(project_id))


def delete_project(project_id):
    if not repository.get_project(project_id):
        raise NotFoundError(f"No project found with id {project_id}")
    repository.delete_project(project_id)
    logger.info("Deleted project %s", project_id)
    return response(204)


@with_http_errors
def handler(event=None, context=None):
    event = event or {}
    method = http_method(event)
    project_id = resource_id(event, SERVICE_NAME)

    if method == "OPTIONS":
        return response(204)

    # Method support is a property of the route, not of the caller's role,
    # so it is checked before RBAC. Otherwise an unsupported verb returns a
    # misleading 403 about permissions no role could satisfy.
    if method not in SUPPORTED_METHODS:
        raise ApiError(f"Method {method} is not supported",
                       status=405, code="method_not_allowed")

    user = authorize(event, PERMISSIONS)
    logger.info("%s %s by %s (%s)", method, project_id or "-",
                user["email"], user["role"])

    if method == "GET":
        return get_project(project_id) if project_id else list_projects(event)
    if method == "POST":
        return create_project(event)
    if method == "PUT":
        if not project_id:
            raise ValidationError("A project id is required in the path")
        return update_project(event, project_id)
    if method == "DELETE":
        if not project_id:
            raise ValidationError("A project id is required in the path")
        return delete_project(project_id)

    raise ApiError(f"Method {method} is not supported",
                   status=405, code="method_not_allowed")


if __name__ == "__main__":
    print(handler())
