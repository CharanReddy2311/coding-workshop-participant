"""Declarative payload validation shared by every service.

A service declares a schema as a dict of field name -> Field and calls
`validate()`. Errors come back as a single ValidationError carrying a
per-field details map, so the frontend can render a message next to the right
input instead of showing one generic banner.
"""

import datetime
import decimal
import re
import uuid

from .http import ValidationError

_MISSING = object()
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Field:
    def __init__(self, type="string", required=False, choices=None,
                 min_length=None, max_length=None, minimum=None, maximum=None,
                 default=_MISSING, nullable=False):
        self.type = type
        self.required = required
        self.choices = choices
        self.min_length = min_length
        self.max_length = max_length
        self.minimum = minimum
        self.maximum = maximum
        self.default = default
        self.nullable = nullable


def _check_range(value, field):
    if field.minimum is not None and value < field.minimum:
        raise ValueError(f"must be at least {field.minimum}")
    if field.maximum is not None and value > field.maximum:
        raise ValueError(f"must be at most {field.maximum}")


def _coerce(value, field):
    kind = field.type

    if kind == "string":
        if not isinstance(value, str):
            raise ValueError("must be a string")
        value = value.strip()
        if field.min_length is not None and len(value) < field.min_length:
            raise ValueError(f"must be at least {field.min_length} characters")
        if field.max_length is not None and len(value) > field.max_length:
            raise ValueError(f"must be at most {field.max_length} characters")
        return value

    if kind == "email":
        if not isinstance(value, str) or not _EMAIL_RE.match(value.strip()):
            raise ValueError("must be a valid email address")
        return value.strip().lower()

    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            try:
                value = int(str(value))
            except (TypeError, ValueError):
                raise ValueError("must be a whole number")
        _check_range(value, field)
        return value

    if kind == "decimal":
        try:
            value = decimal.Decimal(str(value))
        except (decimal.InvalidOperation, TypeError, ValueError):
            raise ValueError("must be a number")
        _check_range(value, field)
        return value

    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if str(value).lower() in ("true", "1"):
            return True
        if str(value).lower() in ("false", "0"):
            return False
        raise ValueError("must be true or false")

    if kind == "date":
        if isinstance(value, datetime.date):
            return value
        try:
            return datetime.date.fromisoformat(str(value))
        except ValueError:
            raise ValueError("must be a date in YYYY-MM-DD format")

    if kind == "uuid":
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("must be a valid identifier")

    raise ValueError(f"unsupported field type {kind}")


def validate(payload, schema, partial=False):
    """Validate `payload` against `schema`.

    partial=True is for updates: absent fields are skipped rather than failing
    the required check, but an empty payload is still rejected.
    """
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object")

    unknown = set(payload) - set(schema)
    if unknown:
        raise ValidationError(
            "Unknown fields in request body",
            details={name: "is not a recognised field" for name in sorted(unknown)},
        )

    cleaned, errors = {}, {}

    for name, field in schema.items():
        if name not in payload:
            if partial:
                continue
            if field.required:
                errors[name] = "is required"
            elif field.default is not _MISSING:
                cleaned[name] = field.default
            continue

        value = payload[name]

        if value is None or value == "":
            if field.required:
                errors[name] = "is required"
            elif field.nullable or value is None:
                cleaned[name] = None
            else:
                errors[name] = "may not be empty"
            continue

        try:
            coerced = _coerce(value, field)
        except ValueError as exc:
            errors[name] = str(exc)
            continue

        if field.choices and coerced not in field.choices:
            errors[name] = f"must be one of: {', '.join(field.choices)}"
            continue

        cleaned[name] = coerced

    if errors:
        raise ValidationError("One or more fields are invalid", details=errors)

    if partial and not cleaned:
        raise ValidationError("No updatable fields were supplied")

    return cleaned
