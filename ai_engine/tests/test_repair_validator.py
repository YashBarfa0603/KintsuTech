
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repair_validator import (
    apply_compatibility_adapter,
    validate_repair,
)


def valid_proposal():
    return {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }


def test_adapter_copies_field_without_removing_source():
    result = apply_compatibility_adapter(
        {"temp_c": 28},
        "temp_c",
        "temperature",
    )

    assert result == {"temp_c": 28, "temperature": 28}


def test_adapter_does_not_modify_original_response():
    original = {"temp_c": 28}

    apply_compatibility_adapter(
        original,
        "temp_c",
        "temperature",
    )

    assert original == {"temp_c": 28}


def test_missing_source_field_is_rejected():
    with pytest.raises(ValueError):
        apply_compatibility_adapter(
            {"humidity": 60},
            "temp_c",
            "temperature",
        )


def test_existing_target_field_is_not_overwritten():
    with pytest.raises(ValueError):
        apply_compatibility_adapter(
            {"temp_c": 28, "temperature": 30},
            "temp_c",
            "temperature",
        )


def test_unconfirmed_semantics_are_rejected():
    proposal = valid_proposal()
    proposal["semantics_confirmed"] = False

    result = validate_repair(
        proposal,
        [
            {
                "input": {"temp_c": 28},
                "expected": {
                    "temp_c": 28,
                    "temperature": 28,
                },
            }
        ],
    )

    assert result["eligible_for_activation"] is False
    assert result["tests_passed"] == 0


def test_passing_confirmed_adapter_is_eligible():
    result = validate_repair(
        valid_proposal(),
        [
            {
                "input": {"temp_c": 28},
                "expected": {
                    "temp_c": 28,
                    "temperature": 28,
                },
            },
            {
                "input": {"temp_c": 15},
                "expected": {
                    "temp_c": 15,
                    "temperature": 15,
                },
            },
        ],
    )

    assert result["eligible_for_activation"] is True
    assert result["tests_passed"] == 2
    assert result["tests_failed"] == 0


def test_incorrect_expected_output_fails():
    result = validate_repair(
        valid_proposal(),
        [
            {
                "input": {"temp_c": 28},
                "expected": {
                    "temp_c": 28,
                    "temperature": 99,
                },
            }
        ],
    )

    assert result["eligible_for_activation"] is False
    assert result["tests_failed"] == 1


def test_unsupported_operation_is_rejected():
    proposal = valid_proposal()
    proposal["operation"] = "execute_python"

    result = validate_repair(proposal, [])

    assert result["eligible_for_activation"] is False
    assert result["tests_failed"] == 0
    assert "Unsupported adapter operation." in result["errors"]


def test_empty_test_cases_are_rejected():
    result = validate_repair(valid_proposal(), [])

    assert result["eligible_for_activation"] is False
    assert result["tests_passed"] == 0
