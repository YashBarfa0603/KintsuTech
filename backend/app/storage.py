from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    Text,
    create_engine,
    delete,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


from app.security import compute_adapter_hash


# Base model for SQLAlchemy ORM
class Base(DeclarativeBase):
    pass


class ServiceModel(Base):
    __tablename__ = "services"

    id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    base_url = Column(String(500), default="")
    description = Column(Text, default="")
    is_critical = Column(Boolean, default=False)
    created_at = Column(String(50), nullable=False)


class BaselineModel(Base):
    __tablename__ = "baselines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_id = Column(String(100), index=True, nullable=False)
    version = Column(Integer, nullable=False)
    data_json = Column(Text, nullable=False)
    checksum = Column(String(64), nullable=False)
    description = Column(Text, default="")
    created_at = Column(String(50), nullable=False)


class IncidentModel(Base):
    __tablename__ = "incidents"

    id = Column(String(50), primary_key=True)
    sequence_num = Column(Integer, index=True, nullable=False)
    service_id = Column(String(100), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    severity = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="open")
    baseline_version = Column(Integer, default=0)
    differences_json = Column(Text, nullable=False)
    evidence_json = Column(Text, nullable=False)
    impact_json = Column(Text, nullable=False)
    repair_proposal_json = Column(Text, nullable=True)
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)


class ValidationModel(Base):
    __tablename__ = "validations"

    incident_id = Column(String(50), primary_key=True)
    validation_json = Column(Text, nullable=False)
    eligible_for_activation = Column(Boolean, nullable=False)
    tests_passed = Column(Integer, default=0)
    adapter_hash = Column(String(64), nullable=True)
    created_at = Column(String(50), nullable=False)


class ActiveAdapterModel(Base):
    __tablename__ = "active_adapters"

    service_id = Column(String(100), primary_key=True)
    incident_id = Column(String(50), nullable=False)
    adapter_config_json = Column(Text, nullable=False)
    authorizer = Column(String(100), nullable=False)
    note = Column(Text, default="")
    activated_at = Column(String(50), nullable=False)


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event = Column(String(100), nullable=False)
    service_id = Column(String(100), nullable=False)
    incident_id = Column(String(50), nullable=True)
    authorizer = Column(String(100), nullable=True)
    reason = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=False)
    timestamp = Column(String(50), nullable=False)


# Default persistent file location outside source code
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_DB_FILE = DEFAULT_DATA_DIR / "kintsutech.db"


def get_default_db_url() -> str:
    """Resolve database URL from environment or fallback to local SQLite file."""
    env_url = os.environ.get("KINTSUTECH_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_FILE}"


class StorageRegistry:
    """
    Persistent, thread-safe registry for services, versioned baselines,
    incidents, repair validations, active adapters, and audit trails.
    Backed by SQLite with SQLAlchemy.
    """

    def __init__(self, db_url: str | None = None) -> None:
        self._lock = Lock()
        if db_url is None:
            # When instantiated directly with no arguments and no explicit URL,
            # use an isolated in-memory SQLite database (ideal for tests).
            self._db_url = "sqlite:///:memory:"
            self._engine = create_engine(
                self._db_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            if db_url.startswith("sqlite://") or "://" in db_url:
                self._db_url = db_url
            else:
                self._db_url = f"sqlite:///{Path(db_url).resolve()}"

            if self._db_url.startswith("sqlite:///:memory:"):
                self._engine = create_engine(
                    self._db_url,
                    connect_args={"check_same_thread": False},
                    poolclass=StaticPool,
                )
            else:
                self._engine = create_engine(
                    self._db_url,
                    connect_args={"check_same_thread": False},
                )

        Base.metadata.create_all(self._engine)
        self._migrate_schema()
        self._session_factory = sessionmaker(bind=self._engine)

    def _migrate_schema(self) -> None:
        """Ensure schema compatibility for existing SQLite databases."""
        with self._engine.begin() as conn:
            try:
                result = conn.exec_driver_sql("PRAGMA table_info(validations)")
                existing_cols = [row[1] for row in result.fetchall()]
                if existing_cols and "adapter_hash" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE validations ADD COLUMN adapter_hash VARCHAR(64)")
            except Exception:
                pass

    def _get_session(self) -> Session:
        return self._session_factory()

    def register_service(
        self,
        service_id: str,
        *,
        name: str,
        base_url: str = "",
        description: str = "",
        is_critical: bool = False,
    ) -> dict[str, Any]:
        """Register or update a monitored service."""
        if not service_id or not isinstance(service_id, str) or not service_id.strip():
            raise ValueError("service_id must be a non-empty string.")

        with self._lock:
            with self._get_session() as session:
                svc = session.get(ServiceModel, service_id)
                now_str = datetime.now(timezone.utc).isoformat()
                if not svc:
                    svc = ServiceModel(
                        id=service_id,
                        name=name,
                        base_url=base_url,
                        description=description,
                        is_critical=is_critical,
                        created_at=now_str,
                    )
                    session.add(svc)
                else:
                    svc.name = name
                    svc.base_url = base_url
                    svc.description = description
                    svc.is_critical = is_critical
                session.commit()

                return {
                    "id": svc.id,
                    "name": svc.name,
                    "base_url": svc.base_url,
                    "description": svc.description,
                    "is_critical": svc.is_critical,
                    "created_at": svc.created_at,
                }

    def list_services(self) -> list[dict[str, Any]]:
        """List all registered services with current baseline version and adapter status."""
        with self._lock:
            with self._get_session() as session:
                services = session.scalars(select(ServiceModel).order_by(ServiceModel.id)).all()
                results = []
                for svc in services:
                    baselines_count = session.scalar(
                        select(func.count(BaselineModel.id)).where(BaselineModel.service_id == svc.id)
                    ) or 0
                    adapter_model = session.get(ActiveAdapterModel, svc.id)
                    active_adapter = None
                    if adapter_model:
                        active_adapter = {
                            "incident_id": adapter_model.incident_id,
                            "service_id": adapter_model.service_id,
                            "adapter_config": json.loads(adapter_model.adapter_config_json),
                            "authorizer": adapter_model.authorizer,
                            "note": adapter_model.note,
                            "activated_at": adapter_model.activated_at,
                        }

                    results.append({
                        "id": svc.id,
                        "name": svc.name,
                        "base_url": svc.base_url,
                        "description": svc.description,
                        "is_critical": svc.is_critical,
                        "created_at": svc.created_at,
                        "baseline_versions_count": baselines_count,
                        "current_baseline_version": baselines_count,
                        "has_active_adapter": active_adapter is not None,
                        "active_adapter": active_adapter,
                    })
                return results

    def get_service(self, service_id: str) -> dict[str, Any] | None:
        """Get service details."""
        with self._lock:
            with self._get_session() as session:
                svc = session.get(ServiceModel, service_id)
                if not svc:
                    return None

                baselines_count = session.scalar(
                    select(func.count(BaselineModel.id)).where(BaselineModel.service_id == service_id)
                ) or 0
                adapter_model = session.get(ActiveAdapterModel, service_id)
                active_adapter = None
                if adapter_model:
                    active_adapter = {
                        "incident_id": adapter_model.incident_id,
                        "service_id": adapter_model.service_id,
                        "adapter_config": json.loads(adapter_model.adapter_config_json),
                        "authorizer": adapter_model.authorizer,
                        "note": adapter_model.note,
                        "activated_at": adapter_model.activated_at,
                    }

                return {
                    "id": svc.id,
                    "name": svc.name,
                    "base_url": svc.base_url,
                    "description": svc.description,
                    "is_critical": svc.is_critical,
                    "created_at": svc.created_at,
                    "baseline_versions_count": baselines_count,
                    "current_baseline_version": baselines_count,
                    "has_active_adapter": active_adapter is not None,
                    "active_adapter": active_adapter,
                }

    def save_baseline(
        self,
        service_id: str,
        data: dict[str, Any],
        *,
        description: str = "",
    ) -> dict[str, Any]:
        """Save a new versioned baseline for a service."""
        if not isinstance(data, dict):
            raise ValueError("Baseline data must be a dictionary.")

        with self._lock:
            with self._get_session() as session:
                svc = session.get(ServiceModel, service_id)
                now_str = datetime.now(timezone.utc).isoformat()
                if not svc:
                    svc = ServiceModel(
                        id=service_id,
                        name=service_id.capitalize(),
                        base_url="",
                        description="",
                        is_critical=False,
                        created_at=now_str,
                    )
                    session.add(svc)
                    session.flush()

                current_max = session.scalar(
                    select(func.max(BaselineModel.version)).where(BaselineModel.service_id == service_id)
                ) or 0
                new_version = current_max + 1

                content_str = json.dumps(data, sort_keys=True)
                checksum = hashlib.sha256(content_str.encode("utf-8")).hexdigest()

                baseline_row = BaselineModel(
                    service_id=service_id,
                    version=new_version,
                    data_json=content_str,
                    checksum=checksum,
                    description=description,
                    created_at=now_str,
                )
                session.add(baseline_row)
                session.commit()

                return {
                    "service_id": service_id,
                    "version": new_version,
                    "data": deepcopy(data),
                    "checksum": checksum,
                    "description": description,
                    "created_at": now_str,
                }

    def get_latest_baseline(self, service_id: str) -> dict[str, Any] | None:
        """Get the most recent baseline for a service."""
        with self._lock:
            with self._get_session() as session:
                latest = session.scalars(
                    select(BaselineModel)
                    .where(BaselineModel.service_id == service_id)
                    .order_by(BaselineModel.version.desc())
                    .limit(1)
                ).first()
                if not latest:
                    return None

                return {
                    "service_id": latest.service_id,
                    "version": latest.version,
                    "data": json.loads(latest.data_json),
                    "checksum": latest.checksum,
                    "description": latest.description,
                    "created_at": latest.created_at,
                }

    def create_incident(
        self,
        service_id: str,
        *,
        title: str,
        severity: str,
        differences: list[dict[str, Any]],
        evidence: dict[str, Any] | None = None,
        impact: dict[str, Any] | None = None,
        repair_proposal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create and store an incident with detailed evidence."""
        with self._lock:
            with self._get_session() as session:
                svc = session.get(ServiceModel, service_id)
                now_str = datetime.now(timezone.utc).isoformat()
                if not svc:
                    svc = ServiceModel(
                        id=service_id,
                        name=service_id.capitalize(),
                        base_url="",
                        description="",
                        is_critical=False,
                        created_at=now_str,
                    )
                    session.add(svc)
                    session.flush()

                # Derive globally unique monotonic sequence number
                max_seq = session.scalar(select(func.max(IncidentModel.sequence_num))) or 0
                next_seq = max_seq + 1
                incident_id = f"INC-{next_seq:03d}"

                latest_baseline_version = session.scalar(
                    select(func.max(BaselineModel.version)).where(BaselineModel.service_id == service_id)
                ) or 0

                incident_row = IncidentModel(
                    id=incident_id,
                    sequence_num=next_seq,
                    service_id=service_id,
                    title=title,
                    severity=severity,
                    status="open",
                    baseline_version=latest_baseline_version,
                    differences_json=json.dumps(differences),
                    evidence_json=json.dumps(evidence or {}),
                    impact_json=json.dumps(impact or {}),
                    repair_proposal_json=json.dumps(repair_proposal) if repair_proposal else None,
                    created_at=now_str,
                    updated_at=now_str,
                )
                session.add(incident_row)
                session.commit()

                return {
                    "id": incident_id,
                    "service_id": service_id,
                    "title": title,
                    "severity": severity,
                    "status": "open",
                    "baseline_version": latest_baseline_version,
                    "differences": deepcopy(differences),
                    "evidence": deepcopy(evidence or {}),
                    "impact": deepcopy(impact or {}),
                    "repair_proposal": deepcopy(repair_proposal),
                    "created_at": now_str,
                    "updated_at": now_str,
                }

    def list_incidents(
        self,
        *,
        service_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List incidents with optional filtering."""
        with self._lock:
            with self._get_session() as session:
                stmt = select(IncidentModel)
                if service_id:
                    stmt = stmt.where(IncidentModel.service_id == service_id)
                if status:
                    stmt = stmt.where(IncidentModel.status == status)
                stmt = stmt.order_by(IncidentModel.created_at.desc())

                rows = session.scalars(stmt).all()
                results = []
                for r in rows:
                    results.append({
                        "id": r.id,
                        "service_id": r.service_id,
                        "title": r.title,
                        "severity": r.severity,
                        "status": r.status,
                        "baseline_version": r.baseline_version,
                        "differences": json.loads(r.differences_json),
                        "evidence": json.loads(r.evidence_json),
                        "impact": json.loads(r.impact_json),
                        "repair_proposal": json.loads(r.repair_proposal_json) if r.repair_proposal_json else None,
                        "created_at": r.created_at,
                        "updated_at": r.updated_at,
                    })
                return results

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        """Retrieve single incident."""
        with self._lock:
            with self._get_session() as session:
                r = session.get(IncidentModel, incident_id)
                if not r:
                    return None
                return {
                    "id": r.id,
                    "service_id": r.service_id,
                    "title": r.title,
                    "severity": r.severity,
                    "status": r.status,
                    "baseline_version": r.baseline_version,
                    "differences": json.loads(r.differences_json),
                    "evidence": json.loads(r.evidence_json),
                    "impact": json.loads(r.impact_json),
                    "repair_proposal": json.loads(r.repair_proposal_json) if r.repair_proposal_json else None,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }

    def record_validation(
        self,
        incident_id: str,
        validation_result: dict[str, Any],
        adapter_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record validation outcome for an incident's proposed repair."""
        with self._lock:
            with self._get_session() as session:
                incident = session.get(IncidentModel, incident_id)
                if not incident:
                    raise ValueError(f"Incident {incident_id} not found.")

                now_str = datetime.now(timezone.utc).isoformat()
                eligible = bool(validation_result.get("eligible_for_activation", False))
                incident.status = "repair_validated" if eligible else "validation_rejected"
                incident.updated_at = now_str

                adapter_hash = None
                if adapter_config:
                    adapter_hash = compute_adapter_hash(adapter_config)
                elif "adapter_hash" in validation_result:
                    adapter_hash = validation_result["adapter_hash"]

                if adapter_hash:
                    validation_result["adapter_hash"] = adapter_hash

                val_record = session.get(ValidationModel, incident_id)
                if not val_record:
                    val_record = ValidationModel(
                        incident_id=incident_id,
                        validation_json=json.dumps(validation_result),
                        eligible_for_activation=eligible,
                        tests_passed=int(validation_result.get("tests_passed", 0)),
                        adapter_hash=adapter_hash,
                        created_at=now_str,
                    )
                    session.add(val_record)
                else:
                    val_record.validation_json = json.dumps(validation_result)
                    val_record.eligible_for_activation = eligible
                    val_record.tests_passed = int(validation_result.get("tests_passed", 0))
                    val_record.adapter_hash = adapter_hash

                audit_event = {
                    "event": "repair_validated",
                    "incident_id": incident_id,
                    "service_id": incident.service_id,
                    "eligible": eligible,
                    "tests_passed": validation_result.get("tests_passed", 0),
                    "adapter_hash": adapter_hash,
                    "timestamp": now_str,
                }
                session.add(
                    AuditLogModel(
                        event="repair_validated",
                        service_id=incident.service_id,
                        incident_id=incident_id,
                        authorizer=None,
                        reason=None,
                        payload_json=json.dumps(audit_event),
                        timestamp=now_str,
                    )
                )

                session.commit()
                return deepcopy(validation_result)

    def get_validation(self, incident_id: str) -> dict[str, Any] | None:
        """Get latest validation result for an incident."""
        with self._lock:
            with self._get_session() as session:
                val = session.get(ValidationModel, incident_id)
                if not val:
                    return None
                return json.loads(val.validation_json)

    def activate_repair(
        self,
        incident_id: str,
        adapter_config: dict[str, Any],
        *,
        authorizer: str = "system",
        note: str = "",
    ) -> dict[str, Any]:
        """
        Guarded repair activation.
        Requires that the proposed adapter was verified via validation and
        matches the exact validated adapter configuration hash.
        """
        with self._lock:
            if not incident_id or not isinstance(incident_id, str) or not incident_id.strip():
                raise ValueError("incident_id must be a non-empty string.")

            with self._get_session() as session:
                incident = session.get(IncidentModel, incident_id)
                if not incident:
                    raise ValueError(f"Incident '{incident_id}' not found.")

                val = session.get(ValidationModel, incident_id)
                if not val or not val.eligible_for_activation:
                    raise ValueError(
                        f"Cannot activate repair for {incident_id}: "
                        "Repair has not passed independent validation."
                    )

                # Recompute requested adapter hash and verify binding to validated adapter
                requested_hash = compute_adapter_hash(adapter_config)
                if val.adapter_hash and val.adapter_hash != requested_hash:
                    raise ValueError(
                        f"Cannot activate repair for {incident_id}: "
                        f"Requested adapter configuration does not match validated adapter. "
                        f"Validated hash: '{val.adapter_hash}', requested hash: '{requested_hash}'."
                    )

                now_str = datetime.now(timezone.utc).isoformat()
                service_id = incident.service_id

                active_adapter = session.get(ActiveAdapterModel, service_id)
                if not active_adapter:
                    active_adapter = ActiveAdapterModel(
                        service_id=service_id,
                        incident_id=incident_id,
                        adapter_config_json=json.dumps(adapter_config),
                        authorizer=authorizer,
                        note=note,
                        activated_at=now_str,
                    )
                    session.add(active_adapter)
                else:
                    active_adapter.incident_id = incident_id
                    active_adapter.adapter_config_json = json.dumps(adapter_config)
                    active_adapter.authorizer = authorizer
                    active_adapter.note = note
                    active_adapter.activated_at = now_str

                incident.status = "repair_activated"
                incident.updated_at = now_str

                audit_event = {
                    "event": "repair_activated",
                    "incident_id": incident_id,
                    "service_id": service_id,
                    "authorizer": authorizer,
                    "adapter": adapter_config,
                    "timestamp": now_str,
                }
                session.add(
                    AuditLogModel(
                        event="repair_activated",
                        service_id=service_id,
                        incident_id=incident_id,
                        authorizer=authorizer,
                        reason=None,
                        payload_json=json.dumps(audit_event),
                        timestamp=now_str,
                    )
                )

                session.commit()

                return {
                    "incident_id": incident_id,
                    "service_id": service_id,
                    "adapter_config": deepcopy(adapter_config),
                    "authorizer": authorizer,
                    "note": note,
                    "activated_at": now_str,
                }

    def rollback_repair(
        self,
        service_id: str,
        *,
        authorizer: str = "system",
        reason: str = "",
    ) -> dict[str, Any]:
        """
        Deactivate active adapter and restore to un-adapted baseline state.
        """
        with self._lock:
            if not service_id or not isinstance(service_id, str) or not service_id.strip():
                raise ValueError("service_id must be a non-empty string.")

            with self._get_session() as session:
                svc = session.get(ServiceModel, service_id)
                if not svc:
                    raise ValueError(f"Service '{service_id}' not found.")

                active_adapter = session.get(ActiveAdapterModel, service_id)
                if not active_adapter:
                    raise ValueError(f"Service '{service_id}' has no active adapter to roll back.")

                previous_adapter = {
                    "incident_id": active_adapter.incident_id,
                    "service_id": active_adapter.service_id,
                    "adapter_config": json.loads(active_adapter.adapter_config_json),
                    "authorizer": active_adapter.authorizer,
                    "note": active_adapter.note,
                    "activated_at": active_adapter.activated_at,
                }

                session.delete(active_adapter)

                now_str = datetime.now(timezone.utc).isoformat()
                # Mark associated incidents
                incidents = session.scalars(
                    select(IncidentModel).where(
                        IncidentModel.service_id == service_id,
                        IncidentModel.status == "repair_activated",
                    )
                ).all()
                for inc in incidents:
                    inc.status = "rolled_back"
                    inc.updated_at = now_str

                audit_event = {
                    "event": "repair_rolled_back",
                    "service_id": service_id,
                    "authorizer": authorizer,
                    "reason": reason,
                    "timestamp": now_str,
                }
                session.add(
                    AuditLogModel(
                        event="repair_rolled_back",
                        service_id=service_id,
                        incident_id=None,
                        authorizer=authorizer,
                        reason=reason,
                        payload_json=json.dumps(audit_event),
                        timestamp=now_str,
                    )
                )

                session.commit()

                return {
                    "service_id": service_id,
                    "previous_adapter": previous_adapter,
                    "authorizer": authorizer,
                    "reason": reason,
                    "rolled_back_at": now_str,
                }

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return audit history in reverse chronological order."""
        with self._lock:
            with self._get_session() as session:
                rows = session.scalars(select(AuditLogModel).order_by(AuditLogModel.id.desc())).all()
                return [json.loads(r.payload_json) for r in rows]

    def reset(self) -> None:
        """Utility to wipe all storage tables (useful for isolated tests)."""
        with self._lock:
            with self._get_session() as session:
                session.execute(delete(ActiveAdapterModel))
                session.execute(delete(ValidationModel))
                session.execute(delete(IncidentModel))
                session.execute(delete(BaselineModel))
                session.execute(delete(ServiceModel))
                session.execute(delete(AuditLogModel))
                session.commit()


# Singleton instance for backend use
storage_registry = StorageRegistry(db_url=get_default_db_url())
