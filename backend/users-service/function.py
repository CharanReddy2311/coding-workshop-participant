"""users-service — CRUD for user accounts and their roles.

    POST   /api/users-service        create a user
    GET    /api/users-service        list, with search and filters
    GET    /api/users-service/{id}   read one
    PUT    /api/users-service/{id}   update (partial) — including role changes
    DELETE /api/users-service/{id}   delete

This is the ADMIN-only "manage users and roles" surface. Every method requires
ADMIN: exposing the full account list (with roles and activation state) and
being able to change a role is exactly the privilege the RBAC matrix reserves
for administrators. Non-admin screens read the safe subset of user data from
directory-service instead.

Passwords are accepted here but never returned: the handler hashes them before
they reach the repository, and the repository only ever reads the public
columns (see repository.PUBLIC_COLUMNS).
"""

import logging

import repository
from schema import USER_SCHEMA, check_business_rules

from _shared.auth import authorize, hash_password
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

SERVICE_NAME = "users-service"
SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "OPTIONS")

# Managing accounts and roles is an administrator-only capability.
PERMISSIONS = {
    "GET": ("ADMIN",),
    "OPTIONS": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
    "POST": ("ADMIN",),
    "PUT": ("ADMIN",),
    "DELETE": ("ADMIN",),
}


def _check_references(data):
    """Verify foreign keys up front so an invalid id fails with a 400, not a 500."""
    department_id = data.get("department_id")
    if department_id and not exists("departments", department_id):
        raise ValidationError(
            "One or more references are invalid",
            details={"department_id": "no department exists with this id"},
        )


def _guard_last_admin(existing, *, demoting=False, deactivating=False):
    """Refuse a change that would remove the final active administrator."""
    is_active_admin = existing["role"] == "ADMIN" and existing["is_active"]
    if is_active_admin and (demoting or deactivating):
        if repository.other_active_admins(existing["id"]) == 0:
            raise ConflictError(
                "Cannot remove the last active administrator",
                details={"hint": "Promote another user to ADMIN first"},
            )


def list_users(event):
    rows, meta = repository.list_users(query_params(event))
    return response(200, rows, meta)


def get_user(user_id):
    user = repository.get_user(user_id)
    if not user:
        raise NotFoundError(f"No user found with id {user_id}")
    return response(200, user)


def create_user(event):
    data = validate(parse_body(event), USER_SCHEMA)
    check_business_rules(data)
    _check_references(data)

    if repository.email_taken(data["email"]):
        raise ValidationError(
            "One or more fields are invalid",
            details={"email": "is already used by another user"},
        )

    # Never persist the raw password; store only its hash.
    data["password_hash"] = hash_password(data.pop("password"))

    created = repository.create_user(data)
    logger.info("Created user %s (%s)", created["id"], created["role"])
    return response(201, created)


def update_user(event, user_id):
    existing = repository.get_user(user_id)
    if not existing:
        raise NotFoundError(f"No user found with id {user_id}")

    data = validate(parse_body(event), USER_SCHEMA, partial=True)
    check_business_rules(data, existing=existing)
    _check_references(data)

    if "email" in data and repository.email_taken(data["email"], exclude_id=user_id):
        raise ValidationError(
            "One or more fields are invalid",
            details={"email": "is already used by another user"},
        )

    _guard_last_admin(
        existing,
        demoting="role" in data and data["role"] != "ADMIN",
        deactivating="is_active" in data and data["is_active"] is False,
    )

    if "password" in data:
        data["password_hash"] = hash_password(data.pop("password"))

    updated = repository.update_user(user_id, data)
    logger.info("Updated user %s (fields: %s)", user_id, ", ".join(data))
    return response(200, updated)


def delete_user(user_id, caller):
    existing = repository.get_user(user_id)
    if not existing:
        raise NotFoundError(f"No user found with id {user_id}")

    if str(user_id) == str(caller["id"]):
        raise ConflictError(
            "You cannot delete your own account",
            details={"hint": "Ask another administrator to remove this account"},
        )

    _guard_last_admin(existing, demoting=True)

    refs = repository.managed_reference_counts(user_id)
    if refs["teams"] or refs["projects"]:
        raise ConflictError(
            "User still manages teams or projects and cannot be deleted",
            details={
                "teams": refs["teams"],
                "projects": refs["projects"],
                "hint": "Reassign those teams and projects to another manager first",
            },
        )

    repository.delete_user(user_id)
    logger.info("Deleted user %s", user_id)
    return response(204)


@with_http_errors
def handler(event=None, context=None):
    event = event or {}
    method = http_method(event)
    user_id = resource_id(event, SERVICE_NAME)

    if method == "OPTIONS":
        return response(204)

    if method not in SUPPORTED_METHODS:
        raise ApiError(
            f"Method {method} is not supported",
            status=405,
            code="method_not_allowed",
        )

    caller = authorize(event, PERMISSIONS)
    logger.info("%s %s by %s (%s)", method, user_id or "-", caller["email"], caller["role"])

    if method == "GET":
        return get_user(user_id) if user_id else list_users(event)
    if method == "POST":
        return create_user(event)
    if method == "PUT":
        if not user_id:
            raise ValidationError("A user id is required in the path")
        return update_user(event, user_id)
    if method == "DELETE":
        if not user_id:
            raise ValidationError("A user id is required in the path")
        return delete_user(user_id, caller)

    raise ApiError(
        f"Method {method} is not supported",
        status=405,
        code="method_not_allowed",
    )


if __name__ == "__main__":
    print(handler())
