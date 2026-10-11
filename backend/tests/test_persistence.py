import pytest

from app.storage import StorageRegistry


def test_service_and_baseline_persistence_across_restart(tmp_path):
    """
    Test Phase 2 requirement:
    - Service and versioned baseline persistence across separate registry instances.
    """
    db_file = tmp_path / "persistence_test_1.db"
    db_url = f"sqlite:///{db_file}"

    # 1. First process / instance creates data
    reg1 = StorageRegistry(db_url=db_url)
    reg1.register_service(
        "orders",
        name="Orders Microservice",
        base_url="http://127.0.0.1:9001/orders",
        description="Handles customer orders",
        is_critical=True,
    )
    b1 = reg1.save_baseline("orders", {"order_id": 100, "status": "pending"})
    assert b1["version"] == 1

    b2 = reg1.save_baseline("orders", {"order_id": 100, "status": "pending", "currency": "INR"})
    assert b2["version"] == 2

    del reg1

    # 2. Simulate application restart: second instance opens the same SQLite file
    reg2 = StorageRegistry(db_url=db_url)
    svc = reg2.get_service("orders")
    assert svc is not None
    assert svc["name"] == "Orders Microservice"
    assert svc["is_critical"] is True
    assert svc["baseline_versions_count"] == 2
    assert svc["current_baseline_version"] == 2

    latest_b = reg2.get_latest_baseline("orders")
    assert latest_b is not None
    assert latest_b["version"] == 2
    assert latest_b["data"]["currency"] == "INR"
    assert latest_b["checksum"] == b2["checksum"]


def test_incident_and_validation_persistence_across_restart(tmp_path):
    """
    Test Phase 2 requirement:
    - Incident and validation outcome persistence across restarts.
    """
    db_file = tmp_path / "persistence_test_2.db"
    db_url = f"sqlite:///{db_file}"

    # First instance
    reg1 = StorageRegistry(db_url=db_url)
    reg1.register_service("payments", name="Payment Gateway")
    inc = reg1.create_incident(
        "payments",
        title="Field removed: txn_fee",
        severity="high",
        differences=[{"kind": "field_removed", "path": "txn_fee"}],
        evidence={"schema_diff": "txn_fee missing"},
        impact={"affected_services": 2},
        repair_proposal={"operation": "copy_field", "source": "fee", "target": "txn_fee"},
    )
    inc_id = inc["id"]
    assert inc_id == "INC-001"
    assert inc["status"] == "open"

    # Record validation
    reg1.record_validation(
        inc_id,
        {
            "eligible_for_activation": True,
            "tests_passed": 3,
            "tests_failed": 0,
            "errors": [],
        },
    )
    del reg1

    # Second instance (after restart)
    reg2 = StorageRegistry(db_url=db_url)
    persisted_inc = reg2.get_incident(inc_id)
    assert persisted_inc is not None
    assert persisted_inc["id"] == inc_id
    assert persisted_inc["service_id"] == "payments"
    assert persisted_inc["status"] == "repair_validated"
    assert persisted_inc["differences"] == [{"kind": "field_removed", "path": "txn_fee"}]
    assert persisted_inc["evidence"] == {"schema_diff": "txn_fee missing"}

    persisted_val = reg2.get_validation(inc_id)
    assert persisted_val is not None
    assert persisted_val["eligible_for_activation"] is True
    assert persisted_val["tests_passed"] == 3


def test_active_adapter_persistence_across_restart(tmp_path):
    """
    Test Phase 2 requirement:
    - Active adapter state survives application restart.
    """
    db_file = tmp_path / "persistence_test_3.db"
    db_url = f"sqlite:///{db_file}"

    # First instance: validate & activate repair
    reg1 = StorageRegistry(db_url=db_url)
    reg1.register_service("weather", name="Weather API")
    inc = reg1.create_incident("weather", title="temp_c migration", severity="medium", differences=[])
    reg1.record_validation(inc["id"], {"eligible_for_activation": True, "tests_passed": 1})

    adapter_config = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }
    activation = reg1.activate_repair(
        inc["id"],
        adapter_config,
        authorizer="lead_architect",
        note="Approved for production adaptation",
    )
    assert activation["authorizer"] == "lead_architect"
    del reg1

    # Second instance (restarted)
    reg2 = StorageRegistry(db_url=db_url)
    svc = reg2.get_service("weather")
    assert svc is not None
    assert svc["has_active_adapter"] is True
    assert svc["active_adapter"] is not None

    active = svc["active_adapter"]
    assert active["incident_id"] == inc["id"]
    assert active["service_id"] == "weather"
    assert active["authorizer"] == "lead_architect"
    assert active["note"] == "Approved for production adaptation"
    assert active["adapter_config"]["target_field"] == "temperature"

    # Incident status reflects activation in restarted registry
    inc_restarted = reg2.get_incident(inc["id"])
    assert inc_restarted["status"] == "repair_activated"


def test_rollback_works_after_reopening_database(tmp_path):
    """
    Test Phase 2 requirement:
    - Rollback still works after reopening the database from a new process.
    """
    db_file = tmp_path / "persistence_test_4.db"
    db_url = f"sqlite:///{db_file}"

    # Step 1: Set up active adapter in instance 1
    reg1 = StorageRegistry(db_url=db_url)
    reg1.register_service("shipping", name="Shipping API")
    inc = reg1.create_incident("shipping", title="Carrier rename", severity="high", differences=[])
    reg1.record_validation(inc["id"], {"eligible_for_activation": True})
    reg1.activate_repair(
        inc["id"],
        {"operation": "copy_field", "source_field": "carrier_code", "target_field": "carrier"},
        authorizer="ops_lead",
    )
    del reg1

    # Step 2: Open instance 2 and perform rollback
    reg2 = StorageRegistry(db_url=db_url)
    rollback_result = reg2.rollback_repair(
        "shipping",
        authorizer="incident_commander",
        reason="Post-restart recovery rollback verification",
    )
    assert rollback_result["service_id"] == "shipping"
    assert rollback_result["authorizer"] == "incident_commander"
    assert rollback_result["reason"] == "Post-restart recovery rollback verification"
    assert rollback_result["previous_adapter"]["adapter_config"]["target_field"] == "carrier"

    svc_rechecked = reg2.get_service("shipping")
    assert svc_rechecked["active_adapter"] is None
    del reg2

    # Step 3: Open instance 3 and confirm rollback state is permanently persisted
    reg3 = StorageRegistry(db_url=db_url)
    assert reg3.get_service("shipping")["active_adapter"] is None
    inc_rechecked = reg3.get_incident(inc["id"])
    assert inc_rechecked["status"] == "rolled_back"


def test_audit_history_persistence_across_restart(tmp_path):
    """
    Test Phase 2 requirement:
    - Audit history is preserved in correct order across restarts.
    """
    db_file = tmp_path / "persistence_test_5.db"
    db_url = f"sqlite:///{db_file}"

    reg1 = StorageRegistry(db_url=db_url)
    reg1.register_service("auth", name="Auth Service")
    inc = reg1.create_incident("auth", title="Token update", severity="low", differences=[])
    reg1.record_validation(inc["id"], {"eligible_for_activation": True, "tests_passed": 2})
    reg1.activate_repair(
        inc["id"],
        {"operation": "copy_field", "source_field": "auth_token", "target_field": "token"},
        authorizer="security_auditor",
    )
    del reg1

    # Second instance queries audit log
    reg2 = StorageRegistry(db_url=db_url)
    audit = reg2.get_audit_log()
    assert len(audit) == 2  # validated, activated
    assert audit[0]["event"] == "repair_activated"
    assert audit[0]["authorizer"] == "security_auditor"
    assert audit[1]["event"] == "repair_validated"


def test_incident_ids_do_not_collide_after_restart(tmp_path):
    """
    Test Phase 2 requirement:
    - Incident IDs remain strictly unique and monotonic across restarts.
    """
    db_file = tmp_path / "persistence_test_6.db"
    db_url = f"sqlite:///{db_file}"

    # Instance 1 creates INC-001 and INC-002
    reg1 = StorageRegistry(db_url=db_url)
    reg1.register_service("metrics", name="Metrics API")
    inc1 = reg1.create_incident("metrics", title="Issue 1", severity="low", differences=[])
    inc2 = reg1.create_incident("metrics", title="Issue 2", severity="low", differences=[])
    assert inc1["id"] == "INC-001"
    assert inc2["id"] == "INC-002"
    del reg1

    # Instance 2 (restart) creates INC-003 and INC-004
    reg2 = StorageRegistry(db_url=db_url)
    inc3 = reg2.create_incident("metrics", title="Issue 3", severity="medium", differences=[])
    inc4 = reg2.create_incident("metrics", title="Issue 4", severity="high", differences=[])
    assert inc3["id"] == "INC-003"
    assert inc4["id"] == "INC-004"

    # All 4 incidents exist uniquely
    all_incidents = reg2.list_incidents()
    all_ids = {i["id"] for i in all_incidents}
    assert all_ids == {"INC-001", "INC-002", "INC-003", "INC-004"}
    assert len(all_incidents) == 4


def test_idempotent_weather_service_seeding(tmp_path):
    """
    Test Phase 2 requirement:
    - Repeated application restarts do not duplicate baseline records.
    """
    db_file = tmp_path / "persistence_test_7.db"
    db_url = f"sqlite:///{db_file}"

    # First start: register and seed baseline
    reg1 = StorageRegistry(db_url=db_url)
    reg1.register_service("weather", name="Mock Weather Service")
    if not reg1.get_latest_baseline("weather"):
        reg1.save_baseline("weather", {"temperature": 25.0})
    del reg1

    # Second start: simulate module re-import
    reg2 = StorageRegistry(db_url=db_url)
    reg2.register_service("weather", name="Mock Weather Service")
    if not reg2.get_latest_baseline("weather"):
        reg2.save_baseline("weather", {"temperature": 25.0})
    del reg2

    # Third start
    reg3 = StorageRegistry(db_url=db_url)
    svc = reg3.get_service("weather")
    assert svc["baseline_versions_count"] == 1
    assert svc["current_baseline_version"] == 1
