import math
import pytest

from consumer_contracts import (
    ConsumerContractRegistry,
    contract_registry,
    validate_field_constraint,
    validate_payload_against_contract,
)
from repair_validator import (
    apply_compatibility_adapter,
    compute_adapter_hash,
    validate_repair,
)


# 1. Typed Field Constraints


def test_field_constraint_types():
    """Verify explicit typing for string, integer, number, boolean, object, and array."""
    # String
    assert validate_field_constraint("name", "Alice", {"type": "string"})[0] is True
    assert validate_field_constraint("name", 123, {"type": "string"})[0] is False

    # Integer
    assert validate_field_constraint("count", 42, {"type": "integer"})[0] is True
    assert validate_field_constraint("count", 42.5, {"type": "integer"})[0] is False
    assert validate_field_constraint("count", "42", {"type": "integer"})[0] is False

    # Number
    assert validate_field_constraint("temp", 25.5, {"type": "number"})[0] is True
    assert validate_field_constraint("temp", 25, {"type": "number"})[0] is True
    assert validate_field_constraint("temp", "25.5", {"type": "number"})[0] is False

    # Boolean
    assert validate_field_constraint("is_active", True, {"type": "boolean"})[0] is True
    assert validate_field_constraint("is_active", 1, {"type": "boolean"})[0] is False

    # Object
    assert validate_field_constraint("meta", {"env": "prod"}, {"type": "object"})[0] is True
    assert validate_field_constraint("meta", ["item"], {"type": "object"})[0] is False

    # Array
    assert validate_field_constraint("tags", ["prod", "us-east"], {"type": "array"})[0] is True
    assert validate_field_constraint("tags", "prod", {"type": "array"})[0] is False

    # Unsupported type declaration
    with pytest.raises(ValueError, match="Unsupported or missing type declaration"):
        validate_field_constraint("bad", "val", {"type": "invalid_type"})


def test_booleans_versus_numbers():
    """Verify booleans are strictly rejected where an integer or number is expected."""
    # In Python, isinstance(True, int) is True, so this test ensures strict guard
    assert validate_field_constraint("num_field", True, {"type": "number"})[0] is False
    assert validate_field_constraint("num_field", False, {"type": "number"})[0] is False
    assert validate_field_constraint("int_field", True, {"type": "integer"})[0] is False
    assert validate_field_constraint("int_field", False, {"type": "integer"})[0] is False


def test_missing_fields_and_nullability():
    """Verify required vs optional and nullable vs non-nullable field semantics."""
    # Required missing field
    assert validate_field_constraint("f", None, {"type": "string", "required": True}, is_present=False)[0] is False

    # Optional missing field
    assert validate_field_constraint("f", None, {"type": "string", "required": False}, is_present=False)[0] is True

    # Non-nullable null value
    assert validate_field_constraint("f", None, {"type": "string", "nullable": False}, is_present=True)[0] is False

    # Nullable null value
    assert validate_field_constraint("f", None, {"type": "string", "nullable": True}, is_present=True)[0] is True


def test_numeric_min_max_constraints():
    """Verify minimum and maximum range enforcement on numeric fields."""
    humidity_schema = {"type": "number", "minimum": 0.0, "maximum": 100.0}

    assert validate_field_constraint("humidity", 50.0, humidity_schema)[0] is True
    assert validate_field_constraint("humidity", 0.0, humidity_schema)[0] is True
    assert validate_field_constraint("humidity", 100.0, humidity_schema)[0] is True

    # Out of bounds
    passed, errors = validate_field_constraint("humidity", -0.1, humidity_schema)
    assert passed is False
    assert "below minimum" in errors[0]

    passed, errors = validate_field_constraint("humidity", 100.1, humidity_schema)
    assert passed is False
    assert "exceeds maximum" in errors[0]

    # Temperature Celsius (>= -273.15)
    temp_schema = {"type": "number", "minimum": -273.15}
    assert validate_field_constraint("temp_c", -273.15, temp_schema)[0] is True
    assert validate_field_constraint("temp_c", -300.0, temp_schema)[0] is False

    # Malformed range schema: minimum > maximum
    with pytest.raises(ValueError, match="cannot exceed maximum"):
        validate_field_constraint("val", 10, {"type": "number", "minimum": 50, "maximum": 20})


def test_non_finite_values_rejected():
    """Verify NaN and infinities are rejected for numeric fields and conversions."""
    schema = {"type": "number"}
    assert validate_field_constraint("temp", float("nan"), schema)[0] is False
    assert validate_field_constraint("temp", float("inf"), schema)[0] is False
    assert validate_field_constraint("temp", float("-inf"), schema)[0] is False


# 2. Adapter Operations (copy_field & convert_units)


def test_copy_field_compatibility():
    """Verify copy_field behavior is completely preserved."""
    payload = {"city": "Indore", "temp_c": 30.0}

    # Dict-based adapter_config
    adapted = apply_compatibility_adapter(
        payload,
        adapter_config={"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"},
    )
    assert adapted["temperature"] == 30.0
    assert adapted["temp_c"] == 30.0

    # Positional string-based call
    adapted2 = apply_compatibility_adapter(payload, "temp_c", "temperature")
    assert adapted2["temperature"] == 30.0


def test_convert_units_deterministic_transformations():
    """Verify explicit unit conversion formulas: output = input * scale + offset."""
    # 1. Identity conversion
    adapted = apply_compatibility_adapter(
        {"val": 42.0},
        adapter_config={"operation": "convert_units", "source_field": "val", "target_field": "out", "scale": 1.0, "offset": 0.0},
    )
    assert adapted["out"] == 42.0

    # 2. Scale-only (e.g. km to meters)
    adapted = apply_compatibility_adapter(
        {"dist_km": 5.5},
        adapter_config={"operation": "convert_units", "source_field": "dist_km", "target_field": "dist_m", "scale": 1000.0, "offset": 0.0},
    )
    assert adapted["dist_m"] == 5500.0

    # 3. Offset-only (e.g. Celsius to Kelvin)
    adapted = apply_compatibility_adapter(
        {"temp_c": 20.0},
        adapter_config={"operation": "convert_units", "source_field": "temp_c", "target_field": "temp_k", "scale": 1.0, "offset": 273.15},
    )
    assert adapted["temp_k"] == 293.15

    # 4. Scale and Offset (Celsius to Fahrenheit: F = C * 1.8 + 32)
    adapted = apply_compatibility_adapter(
        {"temp_c": 25.0},
        adapter_config={"operation": "convert_units", "source_field": "temp_c", "target_field": "temp_f", "scale": 1.8, "offset": 32.0},
    )
    assert adapted["temp_f"] == 77.0

    # 5. Negative values (-40 C is -40 F)
    adapted = apply_compatibility_adapter(
        {"temp_c": -40.0},
        adapter_config={"operation": "convert_units", "source_field": "temp_c", "target_field": "temp_f", "scale": 1.8, "offset": 32.0},
    )
    assert adapted["temp_f"] == -40.0


def test_convert_units_invalid_configurations_rejected():
    """Verify invalid unit conversion parameters and payloads raise ValueError."""
    # Missing scale
    with pytest.raises(ValueError, match="scale"):
        apply_compatibility_adapter(
            {"temp_c": 25.0},
            adapter_config={"operation": "convert_units", "source_field": "temp_c", "target_field": "out", "offset": 0.0},
        )

    # Boolean scale rejected
    with pytest.raises(ValueError, match="scale"):
        apply_compatibility_adapter(
            {"temp_c": 25.0},
            adapter_config={"operation": "convert_units", "source_field": "temp_c", "target_field": "out", "scale": True, "offset": 0.0},
        )

    # Missing source field
    with pytest.raises(ValueError, match="is missing"):
        apply_compatibility_adapter(
            {"other_field": 25.0},
            adapter_config={"operation": "convert_units", "source_field": "temp_c", "target_field": "out", "scale": 1.0, "offset": 0.0},
        )

    # Null source value
    with pytest.raises(ValueError, match="cannot be null"):
        apply_compatibility_adapter(
            {"temp_c": None},
            adapter_config={"operation": "convert_units", "source_field": "temp_c", "target_field": "out", "scale": 1.0, "offset": 0.0},
        )

    # Boolean source value rejected
    with pytest.raises(ValueError, match="must be a finite number"):
        apply_compatibility_adapter(
            {"temp_c": True},
            adapter_config={"operation": "convert_units", "source_field": "temp_c", "target_field": "out", "scale": 1.0, "offset": 0.0},
        )

    # NaN source value rejected
    with pytest.raises(ValueError, match="must be a finite number"):
        apply_compatibility_adapter(
            {"temp_c": float("nan")},
            adapter_config={"operation": "convert_units", "source_field": "temp_c", "target_field": "out", "scale": 1.0, "offset": 0.0},
        )


# 3. Downstream Consumer Contract Validation


def test_validate_repair_with_consumer_contracts_pass_and_fail():
    """Verify repair validation evaluates adapted outputs against consumer contracts."""
    contract = {
        "consumer_id": "mobile_app",
        "service_id": "weather",
        "version": "1.0",
        "mandatory": True,
        "fields": {
            "temperature": {
                "type": "number",
                "required": True,
                "nullable": False,
                "minimum": -273.15,
                "maximum": 60.0,
            },
        },
    }

    adapter = {
        "operation": "convert_units",
        "source_field": "temp_c",
        "target_field": "temperature",
        "scale": 1.0,
        "offset": 0.0,
        "semantics_confirmed": True,
    }

    # Case A: Valid adapter and output passes consumer contract
    test_cases_valid = [
        {"input": {"temp_c": 25.0}, "expected": {"temp_c": 25.0, "temperature": 25.0}},
    ]
    res_valid = validate_repair(
        proposal=adapter,
        test_cases=test_cases_valid,
        consumer_contracts=[contract],
    )
    assert res_valid["eligible_for_activation"] is True
    assert res_valid["tests_passed"] == 1
    assert res_valid["contracts_passed"] == 1
    assert res_valid["contracts_failed"] == 0
    assert res_valid["contract_results"][0]["passed"] is True

    # Case B: Output violates consumer contract range (temperature > 60.0)
    test_cases_range_violation = [
        {"input": {"temp_c": 75.0}, "expected": {"temp_c": 75.0, "temperature": 75.0}},
    ]
    res_range_fail = validate_repair(
        proposal=adapter,
        test_cases=test_cases_range_violation,
        consumer_contracts=[contract],
    )
    assert res_range_fail["eligible_for_activation"] is False
    assert res_range_fail["contracts_failed"] == 1
    assert res_range_fail["contract_results"][0]["passed"] is False
    assert any("exceeds maximum" in err for err in res_range_fail["errors"])

    # Case C: Output violates type requirement (returns string instead of number)
    bad_type_adapter = {
        "operation": "copy_field",
        "source_field": "temp_str",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }
    test_cases_type_fail = [
        {"input": {"temp_str": "hot"}, "expected": {"temp_str": "hot", "temperature": "hot"}},
    ]
    res_type_fail = validate_repair(
        proposal=bad_type_adapter,
        test_cases=test_cases_type_fail,
        consumer_contracts=[contract],
    )
    assert res_type_fail["eligible_for_activation"] is False
    assert res_type_fail["contracts_failed"] == 1
    assert any("expected finite number" in err for err in res_type_fail["errors"])


def test_missing_required_consumer_contract():
    """Verify validation rejects eligibility if a required consumer contract is missing."""
    adapter = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }
    test_cases = [
        {"input": {"temp_c": 20.0}, "expected": {"temp_c": 20.0, "temperature": 20.0}},
    ]

    # Provide contract only for 'mobile_app', but require 'alert_service'
    provided_contracts = [
        {
            "consumer_id": "mobile_app",
            "version": "1.0",
            "mandatory": True,
            "fields": {"temperature": "number"},
        }
    ]

    result = validate_repair(
        proposal=adapter,
        test_cases=test_cases,
        consumer_contracts=provided_contracts,
        required_consumers=["mobile_app", "alert_service"],
    )
    assert result["eligible_for_activation"] is False
    assert any("Missing required consumer contract for 'alert_service'" in e for e in result["errors"])
