"""directory-service — read-only reference data for frontend pickers.

    GET /api/directory-service/departments   id + name of every department
    GET /api/directory-service/users         id, full_name, email of active users

Exists because teams-service and projects-service both take a department_id
and a manager_id foreign key, and neither departments nor users otherwise has
a list endpoint a form dropdown can call. Read-only by design: departments
and users are managed by migration-service (seeding) and auth-service
(accounts) respectively, not created or edited here.
"""

import logging

import repository

from _shared.auth import authorize
from _shared.http import ApiError, http_method, resource_id, response, with_http_errors

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "directory-service"

# Every authenticated role may read; there is nothing here to write.
PERMISSIONS = {
    "GET": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
    "OPTIONS": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
}


@with_http_errors
def handler(event=None, context=None):
    event = event or {}
    method = http_method(event)

    if method == "OPTIONS":
        return response(204)

    authorize(event, PERMISSIONS)

    resource = resource_id(event, SERVICE_NAME)

    if method == "GET" and resource == "departments":
        return response(200, repository.list_departments())
    if method == "GET" and resource == "users":
        return response(200, repository.list_active_users())

    raise ApiError(
        f"Unknown route: {method} /{resource or ''}",
        status=404,
        code="route_not_found",
        details={"available": ["GET /departments", "GET /users"]},
    )


if __name__ == "__main__":
    print(handler())
