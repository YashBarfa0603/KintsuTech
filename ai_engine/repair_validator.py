import hashlib
import json
import math
from copy import deepcopy
from typing import Any

from consumer_contracts import (
    contract_registry,
    validate_payload_against_contract,
)


def compute_adapter_hash(adapter_config: dict[str, Any]) -> str:
    """Compute a canonical SHA-256 hash of an adapter configuration."""
    canonical_json = json.dumps(
        adapter_config,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def apply_compatibility_adapter(
    response: dict[str, Any],
    source_field: str | dict[str, Any] | None = None,
    target_field: str | None = None,
    *,
    adapter_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Apply a restricted compatibility adapter (copy_field or convert_units).
    Does not overwrite an existing target field (unless target equals source).
    Does not modify the original response.
    """
    # Normalize input: support either (resp, "src", "tgt") or (resp, adapter_dict)
    if isinstance(source_field, dict) and adapter_config is None:
        cfg = source_field
    elif adapter_config is not None:
        cfg = adapter_config
    else:
        cfg = {
            "operation": "copy_field",
            "source_field": source_field,
            "target_field": target_field,
        }

    operation = cfg.get("operation", "copy_field")
    src = cfg.get("source_field")
    tgt = cfg.get("target_field")

    if not src or not isinstance(src, str):
        raise ValueError("A valid source_field is required.")
    if not tgt or not isinstance(tgt, str):
        raise ValueError("A valid target_field is required.")
    if src == tgt:
        raise ValueError("Source and target fields must differ.")

    if src not in response:
        raise ValueError(f"Source field '{src}' is missing.")

    if tgt in response and tgt != src:
        raise ValueError(f"Target field '{tgt}' already exists.")

    src_val = response[src]

    if operation == "copy_field":
        adapted = deepcopy(response)
        adapted[tgt] = src_val
        return adapted

    elif operation == "convert_units":
        scale = cfg.get("scale")
        offset = cfg.get("offset")

        # Scale and offset must be explicit, finite numbers (not booleans or None)
        if scale is None or isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale):
            raise ValueError("Unit conversion requires an explicit finite numeric 'scale' parameter.")
        if offset is None or isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset):
            raise ValueError("Unit conversion requires an explicit finite numeric 'offset' parameter.")

        # Source value must be a valid, finite number (no booleans, nulls, strings)
        if src_val is None:
            raise ValueError(f"Source field '{src}' cannot be null for unit conversion.")
        if isinstance(src_val, bool) or not isinstance(src_val, (int, float)) or not math.isfinite(src_val):
            val_desc = type(src_val).__name__ if (isinstance(src_val, bool) or not isinstance(src_val, (int, float))) else str(src_val)
            raise ValueError(f"Source field '{src}' must be a finite number for unit conversion, got {val_desc}.")

        # Optional source range constraints on the adapter
        if "input_min" in cfg and cfg["input_min"] is not None and src_val < cfg["input_min"]:
            raise ValueError(f"Source value {src_val} is below required input_min {cfg['input_min']}.")
        if "input_max" in cfg and cfg["input_max"] is not None and src_val > cfg["input_max"]:
            raise ValueError(f"Source value {src_val} exceeds required input_max {cfg['input_max']}.")

        raw_output = src_val * scale + offset
        if not math.isfinite(raw_output):
            raise ValueError("Unit conversion produced a non-finite result.")

        # Optional target range constraints on the adapter
        if "output_min" in cfg and cfg["output_min"] is not None and raw_output < cfg["output_min"]:
            raise ValueError(f"Converted output {raw_output} is below required output_min {cfg['output_min']}.")
        if "output_max" in cfg and cfg["output_max"] is not None and raw_output > cfg["output_max"]:
            raise ValueError(f"Converted output {raw_output} exceeds required output_max {cfg['output_max']}.")

        adapted = deepcopy(response)
        # Use round to eliminate float precision artifacts like 68.00000000000001
        adapted[tgt] = round(raw_output, 6) if isinstance(raw_output, float) else raw_output
        return adapted

    else:
        raise ValueError(f"Unsupported adapter operation: '{operation}'.")


def validate_repair(
    proposal: dict[str, Any],
    test_cases: list[dict[str, Any]],
    consumer_contracts: list[dict[str, Any]] | None = None,
    *,
    service_id: str | None = None,
    required_consumers: list[str] | None = None,
) -> dict[str, Any]:
    """
    Validate a proposed compatibility adapter (copy_field or convert_units).
    Evaluates adapter execution against test cases and verifies adapted outputs
    against all applicable downstream consumer contracts.
    """
    errors: list[str] = []
    adapter_hash = compute_adapter_hash(proposal) if isinstance(proposal, dict) else None

    if not isinstance(proposal, dict):
        return {
            "eligible_for_activation": False,
            "tests_passed": 0,
            "tests_failed": 0,
            "contract_results": [],
            "contracts_passed": 0,
            "contracts_failed": 0,
            "errors": ["Proposal must be a dictionary."],
            "adapter_hash": None,
            "contract_version": None,
        }

    operation = proposal.get("operation")
    if operation not in ("copy_field", "convert_units"):
        return {
            "eligible_for_activation": False,
            "tests_passed": 0,
            "tests_failed": 0,
            "contract_results": [],
            "contracts_passed": 0,
            "contracts_failed": 0,
            "errors": ["Unsupported adapter operation."],
            "adapter_hash": adapter_hash,
            "contract_version": None,
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

    if operation == "convert_units":
        scale = proposal.get("scale")
        offset = proposal.get("offset")
        if scale is None or isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale):
            errors.append("Explicit numeric 'scale' parameter is required for unit conversion.")
        if offset is None or isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset):
            errors.append("Explicit numeric 'offset' parameter is required for unit conversion.")

    if proposal.get("semantics_confirmed") is not True:
        errors.append(
            "Field semantics and units must be confirmed before testing this mapping."
        )

    if not test_cases:
        errors.append("At least one independent test case is required.")

    if errors:
        return {
            "eligible_for_activation": False,
            "tests_passed": 0,
            "tests_failed": 0,
            "contract_results": [],
            "contracts_passed": 0,
            "contracts_failed": 0,
            "errors": errors,
            "adapter_hash": adapter_hash,
            "contract_version": None,
        }

    # Resolve consumer contracts
    effective_contracts: list[dict[str, Any]] = []
    if consumer_contracts is not None:
        effective_contracts = list(consumer_contracts)
    elif service_id:
        effective_contracts = contract_registry.get_for_service(service_id)
    elif proposal.get("service_id"):
        effective_contracts = contract_registry.get_for_service(proposal["service_id"])
    elif proposal.get("consumer_contracts"):
        effective_contracts = list(proposal["consumer_contracts"])

    # Check for required consumers
    if required_consumers:
        present_consumers = {c.get("consumer_id") for c in effective_contracts}
        for req_cid in required_consumers:
            if req_cid not in present_consumers:
                errors.append(f"Missing required consumer contract for '{req_cid}'.")

    # Initialize contract results map
    contract_results_map: dict[str, dict[str, Any]] = {}
    for c in effective_contracts:
        cid = c.get("consumer_id", "unknown")
        contract_results_map[cid] = {
            "consumer_id": cid,
            "service_id": c.get("service_id", ""),
            "version": c.get("version", "1.0"),
            "mandatory": bool(c.get("mandatory", True)),
            "passed": True,
            "errors": [],
        }

    passed_tests = 0
    failed_tests = 0

    for index, case in enumerate(test_cases, start=1):
        try:
            actual = apply_compatibility_adapter(
                response=case["input"],
                adapter_config=proposal,
            )

            if actual != case["expected"]:
                failed_tests += 1
                errors.append(
                    f"Test {index}: output did not match expected output."
                )
            else:
                passed_tests += 1

            # Validate the adapted output payload against each applicable consumer contract
            for c in effective_contracts:
                cid = c.get("consumer_id", "unknown")
                c_val = validate_payload_against_contract(actual, c)
                if not c_val["passed"]:
                    contract_results_map[cid]["passed"] = False
                    for cerr in c_val["errors"]:
                        if cerr not in contract_results_map[cid]["errors"]:
                            contract_results_map[cid]["errors"].append(cerr)

        except Exception as exc:
            failed_tests += 1
            errors.append(f"Test {index}: {exc}")

    # Evaluate contract pass/fail outcomes
    contract_results = list(contract_results_map.values())
    contracts_passed = len([c for c in contract_results if c["passed"]])
    contracts_failed = len([c for c in contract_results if not c["passed"]])

    mandatory_failure = False
    for c in contract_results:
        if not c["passed"] and c["mandatory"]:
            mandatory_failure = True
            errors.append(
                f"Mandatory consumer contract '{c['consumer_id']}' failed: {'; '.join(c['errors'])}"
            )

    has_missing_contracts = any("Missing required consumer contract" in e for e in errors)
    eligible = (
        failed_tests == 0
        and passed_tests > 0
        and not mandatory_failure
        and not has_missing_contracts
        and len(errors) == 0
    )

    contract_version_str: str | None = None
    if effective_contracts:
        versions = sorted(list({str(c.get("version", "1.0")) for c in effective_contracts}))
        contract_version_str = ",".join(versions)
    elif proposal.get("contract_version"):
        contract_version_str = str(proposal["contract_version"])

    return {
        "eligible_for_activation": eligible,
        "tests_passed": passed_tests,
        "tests_failed": failed_tests,
        "contract_results": contract_results,
        "contracts_passed": contracts_passed,
        "contracts_failed": contracts_failed,
        "contract_version": contract_version_str,
        "adapter_hash": adapter_hash,
        "errors": errors,
    }
