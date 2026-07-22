"""Data access for authentication.

Password hashes are selected only where they are actually needed to verify a
login. Every other query lists columns explicitly so a hash can never leak into
an API response by accident.
"""

from _shared.db import execute, query_one

PUBLIC_COLUMNS = """
    u.id, u.email, u.full_name, u.role, u.is_active,
    u.department_id, d.name AS department_name, u.created_at
"""


def find_by_email_for_login(email):
    """Includes password_hash. Used only by the login path."""
    return query_one(
        """
        SELECT u.id, u.email, u.full_name, u.role, u.is_active, u.password_hash
          FROM users u
         WHERE lower(u.email) = lower(%s)
        """,
        (email,),
    )


def find_by_id(user_id):
    return query_one(
        f"""
        SELECT {PUBLIC_COLUMNS}
          FROM users u
          LEFT JOIN departments d ON d.id = u.department_id
         WHERE u.id = %s
        """,
        (user_id,),
    )


def touch_last_login(user_id):
    """Best-effort audit trail; never blocks a successful login."""
    try:
        execute(
            "UPDATE users SET last_login_at = now() WHERE id = %s RETURNING id",
            (user_id,),
        )
    except Exception:  # noqa: BLE001
        pass
