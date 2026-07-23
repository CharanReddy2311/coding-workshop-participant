"""Direct unit tests for backend/_shared/validation.py — the declarative
Field/validate() engine every service's schema.py builds on.

Pure logic, no I/O at all, so these are the fastest and most exhaustive
tests in the suite. Parametrized across every service in scope so both
vendored copies of this file get real execution credit (see
test_shared_db.py's `shared` fixture for why that matters).
"""

import datetime
import decimal

import pytest


@pytest.fixture(params=["teams-service", "allocations-service"])
def shared(request, load_service):
    return load_service(request.param)


@pytest.fixture
def val(shared):
    """The _shared.validation module itself, imported the same way every
    service imports it."""
    import sys

    return sys.modules["_shared.validation"]


class TestFieldTypeString:
    def test_strips_whitespace(self, val):
        field = val.Field("string")
        assert val._coerce("  hi  ", field) == "hi"

    def test_rejects_non_string(self, val):
        with pytest.raises(ValueError):
            val._coerce(123, val.Field("string"))

    def test_enforces_min_length(self, val):
        with pytest.raises(ValueError):
            val._coerce("a", val.Field("string", min_length=2))

    def test_enforces_max_length(self, val):
        with pytest.raises(ValueError):
            val._coerce("abcdef", val.Field("string", max_length=5))


class TestFieldTypeEmail:
    def test_accepts_and_lowercases_valid_email(self, val):
        assert val._coerce("User@Example.com", val.Field("email")) == "user@example.com"

    @pytest.mark.parametrize("bad", ["not-an-email", "missing-at.com", "no-domain@", "@no-local.com"])
    def test_rejects_malformed_email(self, val, bad):
        with pytest.raises(ValueError):
            val._coerce(bad, val.Field("email"))


class TestFieldTypeInteger:
    def test_accepts_real_int(self, val):
        assert val._coerce(5, val.Field("integer")) == 5

    def test_coerces_numeric_string(self, val):
        assert val._coerce("5", val.Field("integer")) == 5

    def test_rejects_non_numeric_string(self, val):
        with pytest.raises(ValueError):
            val._coerce("abc", val.Field("integer"))

    def test_rejects_bool_even_though_bool_is_an_int_subclass(self, val):
        with pytest.raises(ValueError):
            val._coerce(True, val.Field("integer"))

    def test_enforces_minimum_and_maximum(self, val):
        field = val.Field("integer", minimum=1, maximum=100)
        assert val._coerce(1, field) == 1
        assert val._coerce(100, field) == 100
        with pytest.raises(ValueError):
            val._coerce(0, field)
        with pytest.raises(ValueError):
            val._coerce(101, field)


class TestFieldTypeDecimal:
    def test_coerces_to_decimal(self, val):
        result = val._coerce("19.99", val.Field("decimal"))
        assert result == decimal.Decimal("19.99")

    def test_rejects_non_numeric(self, val):
        with pytest.raises(ValueError):
            val._coerce("free", val.Field("decimal"))

    def test_enforces_minimum(self, val):
        with pytest.raises(ValueError):
            val._coerce("-1", val.Field("decimal", minimum=0))


class TestFieldTypeBoolean:
    @pytest.mark.parametrize("raw,expected", [(True, True), (False, False), ("true", True), ("1", True), ("false", False), ("0", False)])
    def test_accepts_common_truthy_falsy_forms(self, val, raw, expected):
        assert val._coerce(raw, val.Field("boolean")) == expected

    def test_rejects_unrecognised_value(self, val):
        with pytest.raises(ValueError):
            val._coerce("maybe", val.Field("boolean"))


class TestFieldTypeDate:
    def test_parses_iso_date_string(self, val):
        assert val._coerce("2027-01-15", val.Field("date")) == datetime.date(2027, 1, 15)

    def test_passes_through_real_date_object(self, val):
        d = datetime.date(2027, 1, 15)
        assert val._coerce(d, val.Field("date")) is d

    def test_rejects_malformed_date(self, val):
        with pytest.raises(ValueError):
            val._coerce("15/01/2027", val.Field("date"))


class TestFieldTypeUuid:
    def test_normalises_a_valid_uuid(self, val):
        result = val._coerce("11111111-1111-1111-1111-111111111111", val.Field("uuid"))
        assert result == "11111111-1111-1111-1111-111111111111"

    def test_rejects_malformed_uuid(self, val):
        with pytest.raises(ValueError):
            val._coerce("not-a-uuid", val.Field("uuid"))


class TestValidateWholePayload:
    def test_rejects_non_dict_payload(self, val):
        with pytest.raises(val.ValidationError):
            val.validate(["not", "a", "dict"], {"name": val.Field("string")})

    def test_rejects_unknown_fields(self, val):
        schema = {"name": val.Field("string")}
        with pytest.raises(val.ValidationError) as excinfo:
            val.validate({"name": "x", "extra": "y"}, schema)
        assert "extra" in excinfo.value.details

    def test_required_field_missing_is_an_error(self, val):
        schema = {"name": val.Field("string", required=True)}
        with pytest.raises(val.ValidationError) as excinfo:
            val.validate({}, schema)
        assert excinfo.value.details["name"] == "is required"

    def test_optional_field_missing_uses_default(self, val):
        schema = {"status": val.Field("string", default="ACTIVE")}
        assert val.validate({}, schema) == {"status": "ACTIVE"}

    def test_optional_field_missing_with_no_default_is_simply_absent(self, val):
        schema = {"nickname": val.Field("string")}
        assert val.validate({}, schema) == {}

    def test_empty_string_on_required_field_is_an_error(self, val):
        schema = {"name": val.Field("string", required=True)}
        with pytest.raises(val.ValidationError) as excinfo:
            val.validate({"name": ""}, schema)
        assert excinfo.value.details["name"] == "is required"

    def test_none_on_nullable_field_is_accepted_as_none(self, val):
        schema = {"description": val.Field("string", nullable=True)}
        assert val.validate({"description": None}, schema) == {"description": None}

    def test_empty_string_on_non_required_non_nullable_field_is_an_error(self, val):
        schema = {"code": val.Field("string")}
        with pytest.raises(val.ValidationError) as excinfo:
            val.validate({"code": ""}, schema)
        assert excinfo.value.details["code"] == "may not be empty"

    def test_choices_constraint(self, val):
        schema = {"status": val.Field("string", choices=("OPEN", "CLOSED"))}
        assert val.validate({"status": "OPEN"}, schema) == {"status": "OPEN"}
        with pytest.raises(val.ValidationError) as excinfo:
            val.validate({"status": "PENDING"}, schema)
        assert "must be one of" in excinfo.value.details["status"]

    def test_collects_every_field_error_in_one_exception(self, val):
        schema = {
            "name": val.Field("string", required=True),
            "age": val.Field("integer", minimum=0),
        }
        with pytest.raises(val.ValidationError) as excinfo:
            val.validate({"age": -5}, schema)
        assert set(excinfo.value.details) == {"name", "age"}

    def test_partial_skips_absent_required_fields(self, val):
        schema = {"name": val.Field("string", required=True)}
        assert val.validate({"name": "New Name"}, schema, partial=True) == {"name": "New Name"}

    def test_partial_with_nothing_updatable_is_still_an_error(self, val):
        schema = {"name": val.Field("string", required=True)}
        with pytest.raises(val.ValidationError):
            val.validate({}, schema, partial=True)

    def test_returns_only_cleaned_fields_not_the_raw_payload(self, val):
        schema = {"name": val.Field("string", required=True), "weight": val.Field("decimal", default=1)}
        result = val.validate({"name": "  Padded  "}, schema)
        assert result == {"name": "Padded", "weight": 1}
