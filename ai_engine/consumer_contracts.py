import math
from copy import deepcopy
from typing import Any


VALID_TYPES = {"string", "integer", "number", "boolean", "object", "array"}


def validate_field_constraint(
    field_name: str,
    value: Any,
    constraint: dict[str, Any] | str,
    *,
    is_present: bool = True,
) -> tuple[bool, list[str]]:
    """
    Validate a single field value against its schema constraint.
    Rejects malformed schemas and unsupported type declarations.
    Prevents silent coercion (e.g. strings to numbers or booleans to numbers).
    """
    if isinstance(constraint, str):
        constraint = {"type": constraint}
    elif not isinstance(constraint, dict):
        raise ValueError(f"Constraint for field '{field_name}' must be a dict or string, got {type(constraint).__name__}.")

    field_type = constraint.get("type")
    if not field_type or not isinstance(field_type, str) or field_type not in VALID_TYPES:
        raise ValueError(
            f"Unsupported or missing type declaration '{field_type}' for field '{field_name}'. "
            f"Supported types: {sorted(list(VALID_TYPES))}."
        )

    # Validate range parameters if provided
    has_min = "minimum" in constraint and constraint["minimum"] is not None
    has_max = "maximum" in constraint and constraint["maximum"] is not None

    if has_min or has_max:
        if field_type not in ("integer", "number"):
            raise ValueError(
                f"Minimum/maximum constraints are only supported on numeric fields ('integer' or 'number'), "
                f"but field '{field_name}' has type '{field_type}'."
            )
        if has_min:
            min_val = constraint["minimum"]
            if isinstance(min_val, bool) or not isinstance(min_val, (int, float)) or not math.isfinite(min_val):
                raise ValueError(f"Minimum constraint for field '{field_name}' must be a finite number.")
        if has_max:
            max_val = constraint["maximum"]
            if isinstance(max_val, bool) or not isinstance(max_val, (int, float)) or not math.isfinite(max_val):
                raise ValueError(f"Maximum constraint for field '{field_name}' must be a finite number.")
        if has_min and has_max and constraint["minimum"] > constraint["maximum"]:
            raise ValueError(
                f"Minimum ({constraint['minimum']}) cannot exceed maximum ({constraint['maximum']}) for field '{field_name}'."
            )

    # 1. Presence check
    required = constraint.get("required", True)
    if not is_present:
        if required:
            return False, [f"Field '{field_name}' is required but missing."]
        return True, []

    # 2. Nullability check
    nullable = constraint.get("nullable", False)
    if value is None:
        if nullable:
            return True, []
        return False, [f"Field '{field_name}' is non-nullable but received null."]

    # 3. Explicit Type check (rejecting silent coercion)
    errors: list[str] = []

    if field_type == "integer":
        # Python bool is a subclass of int, so reject booleans explicitly
        if isinstance(value, bool) or not isinstance(value, int):
            return False, [f"Field '{field_name}' expected integer, got {type(value).__name__}."]
    elif field_type == "number":
        # Python bool is a subclass of int/float, so reject booleans explicitly
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            type_desc = type(value).__name__ if (isinstance(value, bool) or not isinstance(value, (int, float))) else str(value)
            return False, [f"Field '{field_name}' expected finite number, got {type_desc}."]
    elif field_type == "string":
        if not isinstance(value, str):
            return False, [f"Field '{field_name}' expected string, got {type(value).__name__}."]
    elif field_type == "boolean":
        if not isinstance(value, bool):
            return False, [f"Field '{field_name}' expected boolean, got {type(value).__name__}."]
    elif field_type == "object":
        if not isinstance(value, dict):
            return False, [f"Field '{field_name}' expected object, got {type(value).__name__}."]
    elif field_type == "array":
        if not isinstance(value, list):
            return False, [f"Field '{field_name}' expected array, got {type(value).__name__}."]

    # 4. Range / Invariant constraints (for numeric fields)
    if field_type in ("integer", "number"):
        if has_min and value < constraint["minimum"]:
            errors.append(f"Field '{field_name}' value {value} is below minimum {constraint['minimum']}.")
        if has_max and value > constraint["maximum"]:
            errors.append(f"Field '{field_name}' value {value} exceeds maximum {constraint['maximum']}.")

    return len(errors) == 0, errors


def validate_payload_against_contract(
    payload: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate a single payload against an explicit downstream consumer contract.
    Returns structured pass/fail status and all validation errors.
    """
    if not isinstance(payload, dict):
        return {
            "consumer_id": contract.get("consumer_id", "unknown"),
            "service_id": contract.get("service_id", ""),
            "version": contract.get("version", "1.0"),
            "mandatory": bool(contract.get("mandatory", True)),
            "passed": False,
            "errors": [f"Payload must be an object/dict, got {type(payload).__name__}."],
        }

    consumer_id = contract.get("consumer_id", "unknown")
    fields = contract.get("fields", {})
    if not isinstance(fields, dict):
        raise ValueError(f"Contract for '{consumer_id}' must define a 'fields' dictionary.")

    all_errors: list[str] = []
    for field_name, constraint in fields.items():
        is_present = field_name in payload
        val = payload.get(field_name)
        passed, field_errors = validate_field_constraint(
            field_name,
            val,
            constraint,
            is_present=is_present,
        )
        if not passed:
            all_errors.extend(field_errors)

    return {
        "consumer_id": consumer_id,
        "service_id": contract.get("service_id", ""),
        "version": contract.get("version", "1.0"),
        "mandatory": bool(contract.get("mandatory", True)),
        "passed": len(all_errors) == 0,
        "errors": all_errors,
    }


class ConsumerContractRegistry:
    """
    In-memory registry for downstream consumer contracts.
    Stores and indexes consumer schemas by upstream service_id and consumer_id.
    """

    def __init__(self) -> None:
        self._contracts: dict[tuple[str, str], dict[str, Any]] = {}
        self._seed_default_contracts()

    def _seed_default_contracts(self) -> None:
        """Seed standard contracts for the KintsuTech weather service ecosystem."""
        self.register({
            "consumer_id": "mobile_app",
            "service_id": "weather",
            "version": "1.0",
            "mandatory": True,
            "description": "Mobile app weather screen contract",
            "fields": {
                "temperature": {
                    "type": "number",
                    "required": True,
                    "nullable": False,
                    "minimum": -273.15,
                },
                "city": {
                    "type": "string",
                    "required": False,
                    "nullable": False,
                },
            },
        })

        self.register({
            "consumer_id": "trip_planner",
            "service_id": "weather",
            "version": "1.0",
            "mandatory": True,
            "description": "Itinerary engine weather contract",
            "fields": {
                "temperature": {
                    "type": "number",
                    "required": True,
                    "nullable": False,
                },
            },
        })

        self.register({
            "consumer_id": "alert_service",
            "service_id": "weather",
            "version": "1.0",
            "mandatory": True,
            "description": "Critical severe weather alert contract",
            "fields": {
                "temperature": {
                    "type": "number",
                    "required": True,
                    "nullable": False,
                    "minimum": -273.15,
                },
            },
        })

    def register(self, contract: dict[str, Any]) -> dict[str, Any]:
        """Register or update a consumer contract."""
        consumer_id = contract.get("consumer_id")
        service_id = contract.get("service_id")
        if not consumer_id or not isinstance(consumer_id, str):
            raise ValueError("Consumer contract must have a non-empty 'consumer_id'.")
        if not service_id or not isinstance(service_id, str):
            raise ValueError("Consumer contract must have a non-empty 'service_id'.")

        fields = contract.get("fields", {})
        # Pre-validate field schemas
        for fname, fconstraint in fields.items():
            if isinstance(fconstraint, str):
                fconstraint = {"type": fconstraint}
            ftype = fconstraint.get("type")
            if not ftype or ftype not in VALID_TYPES:
                raise ValueError(f"Invalid type declaration '{ftype}' for field '{fname}'.")

        key = (service_id, consumer_id)
        stored = deepcopy(contract)
        stored.setdefault("version", "1.0")
        stored.setdefault("mandatory", True)
        self._contracts[key] = stored
        return stored

    def get_for_service(self, service_id: str) -> list[dict[str, Any]]:
        """Retrieve all consumer contracts registered for a given upstream service."""
        return [
            deepcopy(c)
            for (s_id, _), c in self._contracts.items()
            if s_id == service_id
        ]

    def get(self, consumer_id: str, service_id: str | None = None) -> dict[str, Any] | None:
        """Retrieve a specific consumer contract."""
        for (s_id, c_id), c in self._contracts.items():
            if c_id == consumer_id:
                if service_id is None or s_id == service_id:
                    return deepcopy(c)
        return None

    def list_all(self) -> list[dict[str, Any]]:
        """List all registered consumer contracts."""
        return [deepcopy(c) for c in self._contracts.values()]

    def reset(self) -> None:
        """Reset registry back to default contracts."""
        self._contracts.clear()
        self._seed_default_contracts()


# Global singleton contract registry
contract_registry = ConsumerContractRegistry()
