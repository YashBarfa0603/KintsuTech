
from copy import deepcopy
from typing import Any


def apply_compatibility_adapter(
    response: dict[str, Any],
    source_field: str,
    target_field: str,
) -> dict[str, Any]:
    """
    Copy a source field to a legacy field name.

    Does not overwrite an existing target field.
    Does not modify the original response.
    """
    if not source_field or not target_field:
        raise ValueError("Source and target fields are required.")

    if source_field == target_field:
        raise ValueError("Source and target fields must differ.")

    if source_field not in response:
        raise ValueError(f"Source field '{source_field}' is missing.")

    if target_field in response:
        raise ValueError(
            f"Target field '{target_field}' already exists."
        )

    adapted = deepcopy(response)
    adapted[target_field] = response[source_field]

    return adapted


def validate_repair(
    proposal: dict[str, Any],
    test_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Validate a restricted field-copy adapter.

    Expected proposal:
    {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True
    }

    Each test case must contain:
    {
        "input": {...},
        "expected": {...}
    }

    Expected outputs must come from a trusted contract or reviewer,
    not from the repair model itself.
    """
    errors: list[str] = []

    if proposal.get("operation") != "copy_field":
        return {
            "eligible_for_activation": False,
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": ["Unsupported adapter operation."],
        }

    source_field = proposal.get("source_field")
    target_field = proposal.get("target_field")

    if not isinstance(source_field, str) or not source_field:
        errors.append("A valid source_field is required.")

    if not isinstance(target_field, str) or not target_field:
        errors.append("A valid target_field is required.")

    if (
        isinstance(source_field, str)
        and isinstance(target_field, str)
        and source_field == target_field
    ):
        errors.append("Source and target fields must differ.")

    if proposal.get("semantics_confirmed") is not True:
        errors.append(
            "Field semantics and units must be confirmed "
            "before testing this mapping."
        )

    if not test_cases:
        errors.append("At least one independent test case is required.")

    if errors:
        return {
            "eligible_for_activation": False,
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": errors,
        }

    passed = 0
    failed = 0

    for index, case in enumerate(test_cases, start=1):
        try:
            actual = apply_compatibility_adapter(
                response=case["input"],
                source_field=source_field,
                target_field=target_field,
            )

            if actual != case["expected"]:
                failed += 1
                errors.append(
                    f"Test {index}: output did not match expected output."
                )
            else:
                passed += 1

        except (KeyError, TypeError, ValueError) as exc:
            failed += 1
            errors.append(f"Test {index}: {exc}")

    return {
        "eligible_for_activation": failed == 0 and passed > 0,
        "tests_passed": passed,
        "tests_failed": failed,
        "errors": errors,
    }


if __name__ == "__main__":
    proposal = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": False,
    }

    test_cases = [
        {
            "input": {"temp_c": 28},
            "expected": {"temp_c": 28, "temperature": 28},
        }
    ]

    result = validate_repair(proposal, test_cases)
    print(result)
