import pytest
from app.storage import StorageRegistry


def test_service_registration_and_baselines():
    registry = StorageRegistry()
    registry.register_service("weather", name="Weather Service")

    b1 = registry.save_baseline("weather", {"temp": 25})
    assert b1["version"] == 1
    assert "checksum" in b1

    b2 = registry.save_baseline("weather", {"temp": 28, "unit": "celsius"})
    assert b2["version"] == 2

    latest = registry.get_latest_baseline("weather")
    assert latest["version"] == 2
    assert latest["data"]["temp"] == 28


def test_incident_lifecycle_and_guarded_activation():
    registry = StorageRegistry()
    registry.register_service("products", name="Product API")

    # Create incident
    inc = registry.create_incident(
        "products",
        title="Field removed: price",
        severity="high",
        differences=[{"kind": "field_removed", "path": "price"}],
    )
    inc_id = inc["id"]
    assert inc["status"] == "open"

    # Attempting to activate before validation MUST fail
    with pytest.raises(ValueError, match="independent validation"):
        registry.activate_repair(
            inc_id,
            {"operation": "copy_field", "source": "cost", "target": "price"},
        )

    # Record passing validation
    registry.record_validation(
        inc_id,
        {
            "eligible_for_activation": True,
            "tests_passed": 2,
            "tests_failed": 0,
            "errors": [],
        },
    )

    # Now activation should succeed
    activation = registry.activate_repair(
        inc_id,
        {"operation": "copy_field", "source": "cost", "target": "price"},
        authorizer="lead_engineer",
    )
    assert activation["authorizer"] == "lead_engineer"

    svc = registry.get_service("products")
    assert svc["active_adapter"] is not None

    # Rollback
    rollback = registry.rollback_repair("products", authorizer="incident_commander", reason="Testing rollback")
    assert rollback["authorizer"] == "incident_commander"

    svc_after = registry.get_service("products")
    assert svc_after["active_adapter"] is None

    # Audit log
    audit = registry.get_audit_log()
    assert len(audit) == 3  # validation, activation, rollback
    assert audit[0]["event"] == "repair_rolled_back"
