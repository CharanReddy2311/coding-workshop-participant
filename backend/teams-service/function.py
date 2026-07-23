"""teams-service — CRUD for teams.

    POST   /api/teams-service        create
    GET    /api/teams-service        list, with search and filters
    GET    /api/teams-service/{id}   read one
    PUT    /api/teams-service/{id}   update
    DELETE /api/teams-service/{id}   delete
"""

import logging

import repository
from schema import TEAM_SCHEMA, check_business_rules

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

SERVICE_NAME = "teams-service"
SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "OPTIONS")

PERMISSIONS = {
    "GET": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
    "OPTIONS": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
    "POST": ("MANAGER", "ADMIN"),
    "PUT": ("CONTRIBUTOR", "MANAGER", "ADMIN"),
    "DELETE": ("MANAGER", "ADMIN"),
}


def _check_references(data: dict) -> None:
    """Verify foreign keys up front so invalid IDs fail with a 400 instead of a 500."""
    errors = {}
    if data.get("department_id") and not exists("departments", data["department_id"]):
        errors["department_id"] = "no department exists with this id"
    if data.get("manager_id") and not exists("users", data["manager_id"]):
        errors["manager_id"] = "no user exists with this id"
    if errors:
        raise ValidationError("One or more references are invalid", details=errors)


def list_teams(event):
    rows, meta = repository.list_teams(query_params(event))
    return response(200, rows, meta)


def get_team(team_id):
    team = repository.get_team(team_id)
    if not team:
        raise NotFoundError(f"No team found with id {team_id}")
    return response(200, team)


def create_team(event):
    data = validate(parse_body(event), TEAM_SCHEMA)
    check_business_rules(data)
    _check_references(data)

    if repository.name_taken(data["name"]):
        raise ValidationError(
            "One or more fields are invalid",
            details={"name": "is already used by another team"},
        )

    created = repository.create_team(data)
    logger.info("Created team %s", created["id"])
    return response(201, repository.get_team(created["id"]))


def update_team(event, team_id):
    existing = repository.get_team(team_id)
    if not existing:
        raise NotFoundError(f"No team found with id {team_id}")

    data = validate(parse_body(event), TEAM_SCHEMA, partial=True)
    check_business_rules(data, existing=existing)
    _check_references(data)

    if "name" in data and repository.name_taken(data["name"], exclude_id=team_id):
        raise ValidationError(
            "One or more fields are invalid",
            details={"name": "is already used by another team"},
        )

    repository.update_team(team_id, data)
    logger.info("Updated team %s (fields: %s)", team_id, ", ".join(data))
    return response(200, repository.get_team(team_id))


def delete_team(team_id):
    if not repository.get_team(team_id):
        raise NotFoundError(f"No team found with id {team_id}")
    repository.delete_team(team_id)
    logger.info("Deleted team %s", team_id)
    return response(204)


@with_http_errors
def handler(event=None, context=None):
    event = event or {}
    method = http_method(event)
    team_id = resource_id(event, SERVICE_NAME)

    if method == "OPTIONS":
        return response(204)

    if method not in SUPPORTED_METHODS:
        raise ApiError(
            f"Method {method} is not supported",
            status=405,
            code="method_not_allowed",
        )

    user = authorize(event, PERMISSIONS)
    logger.info("%s %s by %s (%s)", method, team_id or "-", user["email"], user["role"])

    if method == "GET":
        return get_team(team_id) if team_id else list_teams(event)
    if method == "POST":
        return create_team(event)
    if method == "PUT":
        if not team_id:
            raise ValidationError("A team id is required in the path")
        return update_team(event, team_id)
    if method == "DELETE":
        if not team_id:
            raise ValidationError("A team id is required in the path")
        return delete_team(team_id)

    raise ApiError(
        f"Method {method} is not supported",
        status=405,
        code="method_not_allowed",
    )


if __name__ == "__main__":
    print(handler())
