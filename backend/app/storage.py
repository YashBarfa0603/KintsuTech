from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    create_engine,
    delete,
    event,
    func,
    or_,
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
    contract_version = Column(String(50), nullable=True)
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


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String(100), primary_key=True)
    email = Column(String(255), nullable=True, index=True)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), default="authenticated")
    user_metadata_json = Column(Text, default="{}")
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)


class WebhookSubscriptionModel(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(String(50), primary_key=True)
    target_url = Column(String(500), nullable=False)
    events_json = Column(Text, nullable=False)
    secret = Column(String(255), nullable=False)
    description = Column(Text, default="")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(String(50), nullable=False)


class WebhookDeliveryModel(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(String(50), primary_key=True)
    event_id = Column(String(50), index=True, nullable=True)
    event_type = Column(String(100), nullable=False)
    subscription_id = Column(String(50), index=True, nullable=False)
    target_url = Column(String(500), nullable=False)
    attempts = Column(Integer, default=1, nullable=False)
    status = Column(String(50), nullable=False)
    status_code = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    timestamp = Column(String(50), nullable=False)


class WebhookIdempotencyModel(Base):
    __tablename__ = "webhook_idempotency"

    event_id = Column(String(100), primary_key=True)
    received_at = Column(String(50), nullable=False)


# --- Alert Models ---

VALID_ALERT_STATUSES = {
    "pending",
    "delivering",
    "delivered",
    "acknowledged",
    "escalated",
    "resolved",
    "failed",
    "cancelled",
}

VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"delivering", "delivered", "acknowledged", "resolved", "failed", "cancelled"},
    "delivering": {"delivered", "acknowledged", "resolved", "failed", "cancelled"},
    "delivered": {"acknowledged", "escalated", "resolved", "cancelled", "delivering"},
    "escalated": {"acknowledged", "resolved", "cancelled", "delivering"},
    "failed": {"delivering", "acknowledged", "resolved", "cancelled"},
    "acknowledged": {"resolved", "cancelled"},
    "resolved": set(),
    "cancelled": set(),
}


VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}

DEFAULT_ALERT_PREFERENCES: dict[str, Any] = {
    "channels": ["in_app"],
    "min_severity": "medium",
    "quiet_hours_enabled": False,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "08:00",
    "timezone": "UTC",
    "voice_enabled": True,
    "max_attempts": 3,
    "escalation_interval_seconds": 300,
    "ack_timeout_seconds": 600,
    "phone_consent": False,
    "phone_number": None,
}


def validate_alert_transition(current_status: str, target_status: str) -> None:
    """Validate that moving from current_status to target_status is allowed."""
    if target_status not in VALID_ALERT_STATUSES:
        raise ValueError(f"Unknown alert status: '{target_status}'")
    if current_status == target_status:
        return
    allowed = VALID_STATUS_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise ValueError(
            f"Invalid alert status transition from '{current_status}' to '{target_status}'"
        )


class AlertModel(Base):
    __tablename__ = "alerts"

    id = Column(String(50), primary_key=True)
    user_id = Column(String(100), index=True, nullable=False)
    incident_id = Column(String(50), index=True, nullable=True)
    source_event_id = Column(String(100), index=True, nullable=True)
    idempotency_key = Column(String(200), index=True, nullable=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(50), index=True, nullable=False, default="medium")
    status = Column(String(50), index=True, nullable=False, default="pending")
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)
    due_at = Column(String(50), index=True, nullable=True)
    acknowledged_at = Column(String(50), nullable=True)
    resolved_at = Column(String(50), nullable=True)
    escalation_level = Column(Integer, default=0, nullable=False)
    next_escalation_at = Column(String(50), index=True, nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(String(50), nullable=True)
    delivery_channel = Column(String(50), default="in_app", nullable=False)
    locked_until = Column(String(50), nullable=True)
    metadata_json = Column(Text, default="{}")

    __table_args__ = (
        UniqueConstraint("idempotency_key", "user_id", name="uq_alerts_idempotency_user"),
        Index("ix_alerts_user_status", "user_id", "status"),
    )


class AlertDeliveryModel(Base):
    __tablename__ = "alert_deliveries"

    id = Column(String(50), primary_key=True)
    alert_id = Column(String(50), index=True, nullable=False)
    channel = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    attempt_number = Column(Integer, default=1, nullable=False)
    escalation_level = Column(Integer, default=0, nullable=False)
    error = Column(Text, nullable=True)
    details_json = Column(Text, default="{}")
    timestamp = Column(String(50), nullable=False)


class AlertPreferenceModel(Base):
    __tablename__ = "alert_preferences"

    user_id = Column(String(100), primary_key=True)
    channels_json = Column(Text, default='["in_app"]')
    min_severity = Column(String(50), default="medium")
    quiet_hours_enabled = Column(Boolean, default=False)
    quiet_hours_start = Column(String(10), default="22:00")
    quiet_hours_end = Column(String(10), default="08:00")
    timezone = Column(String(50), default="UTC")
    voice_enabled = Column(Boolean, default=True)
    max_attempts = Column(Integer, default=3)
    escalation_interval_seconds = Column(Integer, default=300)
    ack_timeout_seconds = Column(Integer, default=600)
    phone_consent = Column(Boolean, default=False)
    phone_number = Column(String(50), nullable=True)
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)


def _format_alert(r: AlertModel) -> dict[str, Any]:
    meta = {}
    if r.metadata_json:
        try:
            meta = json.loads(r.metadata_json)
        except Exception:
            meta = {}
    return {
        "id": r.id,
        "user_id": r.user_id,
        "incident_id": r.incident_id,
        "source_event_id": r.source_event_id,
        "idempotency_key": r.idempotency_key,
        "title": r.title,
        "message": r.message,
        "severity": r.severity,
        "status": r.status,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "due_at": r.due_at,
        "acknowledged_at": r.acknowledged_at,
        "resolved_at": r.resolved_at,
        "escalation_level": r.escalation_level,
        "next_escalation_at": r.next_escalation_at,
        "attempt_count": r.attempt_count,
        "last_attempt_at": r.last_attempt_at,
        "delivery_channel": r.delivery_channel,
        "metadata": meta,
    }


def _format_delivery(r: AlertDeliveryModel) -> dict[str, Any]:
    details = {}
    if r.details_json:
        try:
            details = json.loads(r.details_json)
        except Exception:
            details = {}
    return {
        "id": r.id,
        "alert_id": r.alert_id,
        "channel": r.channel,
        "status": r.status,
        "attempt_number": r.attempt_number,
        "escalation_level": r.escalation_level,
        "error": r.error,
        "details": details,
        "timestamp": r.timestamp,
    }


def _format_preference(r: AlertPreferenceModel) -> dict[str, Any]:
    channels = ["in_app"]
    if r.channels_json:
        try:
            channels = json.loads(r.channels_json)
        except Exception:
            channels = ["in_app"]
    return {
        "user_id": r.user_id,
        "channels": channels,
        "min_severity": r.min_severity,
        "quiet_hours_enabled": r.quiet_hours_enabled,
        "quiet_hours_start": r.quiet_hours_start,
        "quiet_hours_end": r.quiet_hours_end,
        "timezone": r.timezone,
        "voice_enabled": r.voice_enabled,
        "max_attempts": r.max_attempts,
        "escalation_interval_seconds": r.escalation_interval_seconds,
        "ack_timeout_seconds": r.ack_timeout_seconds,
        "phone_consent": r.phone_consent,
        "phone_number": r.phone_number,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }



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
            if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:///:memory:"):
                raw_path = db_url.replace("sqlite:///", "", 1)
                p = Path(raw_path)
                if not p.is_absolute():
                    if raw_path.startswith("backend/") and not Path("backend").exists():
                        p = Path(raw_path[len("backend/"):])
                    p = p.resolve()
                p.parent.mkdir(parents=True, exist_ok=True)
                self._db_url = f"sqlite:///{p.as_posix()}"
            elif db_url.startswith("sqlite://") or "://" in db_url:
                self._db_url = db_url
            else:
                p = Path(db_url).resolve()
                p.parent.mkdir(parents=True, exist_ok=True)
                self._db_url = f"sqlite:///{p.as_posix()}"

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

        if "sqlite" in self._db_url:
            @event.listens_for(self._engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                except Exception:
                    pass
                try:
                    cursor.execute("PRAGMA busy_timeout=5000")
                except Exception:
                    pass
                cursor.close()

        Base.metadata.create_all(self._engine)
        self._migrate_schema()
        self._session_factory = sessionmaker(bind=self._engine)

    def _migrate_schema(self) -> None:
        """Ensure schema compatibility for existing SQLite databases."""
        Base.metadata.create_all(self._engine)
        with self._engine.begin() as conn:
            try:
                result = conn.exec_driver_sql("PRAGMA table_info(validations)")
                existing_cols = [row[1] for row in result.fetchall()]
                if existing_cols and "adapter_hash" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE validations ADD COLUMN adapter_hash VARCHAR(64)")
                if existing_cols and "contract_version" not in existing_cols:
                    conn.exec_driver_sql("ALTER TABLE validations ADD COLUMN contract_version VARCHAR(50)")
            except Exception:
                pass

            try:
                result = conn.exec_driver_sql("PRAGMA table_info(alerts)")
                columns_info = result.fetchall()
                incident_col = next((c for c in columns_info if c[1] == "incident_id"), None)
                if incident_col and incident_col[3] == 1:
                    count = conn.exec_driver_sql("SELECT count(*) FROM alerts").scalar() or 0
                    if count == 0:
                        conn.exec_driver_sql("DROP TABLE alerts")
                        Base.metadata.tables["alerts"].create(conn)
                    else:
                        conn.exec_driver_sql("ALTER TABLE alerts RENAME TO alerts_old")
                        Base.metadata.tables["alerts"].create(conn)
                        conn.exec_driver_sql(
                            "INSERT INTO alerts (id, incident_id, user_id, severity, status, title, message, created_at) "
                            "SELECT id, incident_id, recipient_id, severity, status, title, message, created_at FROM alerts_old"
                        )
                        conn.exec_driver_sql("DROP TABLE alerts_old")

                result = conn.exec_driver_sql("PRAGMA table_info(alerts)")
                existing_cols = [row[1] for row in result.fetchall()]

                if existing_cols:
                    if "user_id" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN user_id VARCHAR(100)")
                        if "recipient_id" in existing_cols:
                            conn.exec_driver_sql("UPDATE alerts SET user_id = recipient_id WHERE user_id IS NULL")
                    if "source_event_id" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN source_event_id VARCHAR(100)")
                    if "idempotency_key" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN idempotency_key VARCHAR(200)")
                    if "updated_at" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN updated_at VARCHAR(50)")
                        if "created_at" in existing_cols:
                            conn.exec_driver_sql("UPDATE alerts SET updated_at = created_at WHERE updated_at IS NULL")
                    if "due_at" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN due_at VARCHAR(50)")
                        if "escalation_due_at" in existing_cols:
                            conn.exec_driver_sql("UPDATE alerts SET due_at = escalation_due_at WHERE due_at IS NULL")
                    if "resolved_at" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN resolved_at VARCHAR(50)")
                    if "escalation_level" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN escalation_level INTEGER DEFAULT 0")
                    if "next_escalation_at" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN next_escalation_at VARCHAR(50)")
                    if "attempt_count" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN attempt_count INTEGER DEFAULT 0")
                    if "last_attempt_at" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN last_attempt_at VARCHAR(50)")
                    if "delivery_channel" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN delivery_channel VARCHAR(50) DEFAULT 'in_app'")
                    if "locked_until" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN locked_until VARCHAR(50)")
                    if "metadata_json" not in existing_cols:
                        conn.exec_driver_sql("ALTER TABLE alerts ADD COLUMN metadata_json TEXT DEFAULT '{}'")
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
        contract_version: str | None = None,
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

                resolved_contract_version = contract_version or validation_result.get("contract_version")
                if resolved_contract_version:
                    validation_result["contract_version"] = resolved_contract_version

                val_record = session.get(ValidationModel, incident_id)
                if not val_record:
                    val_record = ValidationModel(
                        incident_id=incident_id,
                        validation_json=json.dumps(validation_result),
                        eligible_for_activation=eligible,
                        tests_passed=int(validation_result.get("tests_passed", 0)),
                        adapter_hash=adapter_hash,
                        contract_version=resolved_contract_version,
                        created_at=now_str,
                    )
                    session.add(val_record)
                else:
                    val_record.validation_json = json.dumps(validation_result)
                    val_record.eligible_for_activation = eligible
                    val_record.tests_passed = int(validation_result.get("tests_passed", 0))
                    val_record.adapter_hash = adapter_hash
                    val_record.contract_version = resolved_contract_version

                audit_event = {
                    "event": "repair_validated",
                    "incident_id": incident_id,
                    "service_id": incident.service_id,
                    "eligible": eligible,
                    "tests_passed": validation_result.get("tests_passed", 0),
                    "adapter_hash": adapter_hash,
                    "contract_version": resolved_contract_version,
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
        contract_version: str | None = None,
    ) -> dict[str, Any]:
        """
        Guarded repair activation.
        Requires that the proposed adapter was verified via validation,
        matches the exact validated adapter configuration hash,
        and matches the validated contract version.
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

                # Recheck contract version if provided
                if contract_version and val.contract_version and val.contract_version != contract_version:
                    raise ValueError(
                        f"Cannot activate repair for {incident_id}: "
                        f"Requested contract version '{contract_version}' does not match validated contract version '{val.contract_version}'."
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

    def sync_user(
        self,
        user_id: str,
        email: str | None = None,
        full_name: str | None = None,
        role: str = "authenticated",
        user_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Persist or update an authenticated user profile in the local SQLite database.
        Returns the saved user record.
        """
        now = datetime.now(timezone.utc).isoformat()
        metadata_clean = user_metadata or {}
        metadata_str = json.dumps(metadata_clean)

        with self._lock:
            with self._get_session() as session:
                existing = session.get(UserModel, user_id)
                if existing:
                    if email is not None:
                        existing.email = email
                    if full_name is not None:
                        existing.full_name = full_name
                    existing.role = role
                    existing.user_metadata_json = metadata_str
                    existing.updated_at = now
                    session.commit()
                    return {
                        "id": existing.id,
                        "email": existing.email,
                        "full_name": existing.full_name,
                        "role": existing.role,
                        "user_metadata": json.loads(existing.user_metadata_json),
                        "created_at": existing.created_at,
                        "updated_at": existing.updated_at,
                    }
                else:
                    new_user = UserModel(
                        id=user_id,
                        email=email,
                        full_name=full_name,
                        role=role,
                        user_metadata_json=metadata_str,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(new_user)
                    session.commit()
                    return {
                        "id": new_user.id,
                        "email": new_user.email,
                        "full_name": new_user.full_name,
                        "role": new_user.role,
                        "user_metadata": metadata_clean,
                        "created_at": now,
                        "updated_at": now,
                    }

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve a user by ID from the local SQLite database."""
        with self._lock:
            with self._get_session() as session:
                user = session.get(UserModel, user_id)
                if not user:
                    return None
                return {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "user_metadata": json.loads(user.user_metadata_json),
                    "created_at": user.created_at,
                    "updated_at": user.updated_at,
                }

    def list_users(self) -> list[dict[str, Any]]:
        """List all users saved in the local SQLite database."""
        with self._lock:
            with self._get_session() as session:
                users = session.scalars(select(UserModel).order_by(UserModel.created_at.desc())).all()
                return [
                    {
                        "id": u.id,
                        "email": u.email,
                        "full_name": u.full_name,
                        "role": u.role,
                        "user_metadata": json.loads(u.user_metadata_json),
                        "created_at": u.created_at,
                        "updated_at": u.updated_at,
                    }
                    for u in users
                ]

    def create_webhook_subscription(
        self,
        sub: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist a new or updated webhook subscription to SQLite."""
        with self._lock:
            with self._get_session() as session:
                sub_id = sub["id"]
                row = WebhookSubscriptionModel(
                    id=sub_id,
                    target_url=sub["target_url"],
                    events_json=json.dumps(sub.get("events", ["*"])),
                    secret=sub.get("secret", ""),
                    description=sub.get("description", ""),
                    is_active=sub.get("is_active", True),
                    created_at=sub.get("created_at") or datetime.now(timezone.utc).isoformat(),
                )
                session.merge(row)
                session.commit()
                return deepcopy(sub)

    def list_webhook_subscriptions(
        self,
        include_secret: bool = False,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """List persisted webhook subscriptions with optional secret redaction."""
        with self._lock:
            with self._get_session() as session:
                stmt = select(WebhookSubscriptionModel)
                if active_only:
                    stmt = stmt.where(WebhookSubscriptionModel.is_active.is_(True))
                stmt = stmt.order_by(WebhookSubscriptionModel.created_at.asc())
                rows = session.scalars(stmt).all()
                result = []
                for r in rows:
                    entry = {
                        "id": r.id,
                        "target_url": r.target_url,
                        "events": json.loads(r.events_json),
                        "description": r.description,
                        "is_active": r.is_active,
                        "created_at": r.created_at,
                    }
                    if include_secret:
                        entry["secret"] = r.secret
                    else:
                        entry["secret_configured"] = bool(r.secret)
                    result.append(entry)
                return result

    def get_webhook_subscription(
        self,
        sub_id: str,
        include_secret: bool = False,
    ) -> dict[str, Any] | None:
        """Retrieve a specific webhook subscription."""
        with self._lock:
            with self._get_session() as session:
                r = session.get(WebhookSubscriptionModel, sub_id)
                if not r:
                    return None
                entry = {
                    "id": r.id,
                    "target_url": r.target_url,
                    "events": json.loads(r.events_json),
                    "description": r.description,
                    "is_active": r.is_active,
                    "created_at": r.created_at,
                }
                if include_secret:
                    entry["secret"] = r.secret
                else:
                    entry["secret_configured"] = bool(r.secret)
                return entry

    def record_webhook_delivery(
        self,
        log_entry: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist a webhook delivery attempt and status record to SQLite."""
        with self._lock:
            with self._get_session() as session:
                del_id = log_entry.get("delivery_id") or f"del_{uuid.uuid4().hex[:12]}"
                log_entry["delivery_id"] = del_id
                now_str = log_entry.get("timestamp") or datetime.now(timezone.utc).isoformat()
                row = WebhookDeliveryModel(
                    id=del_id,
                    event_id=log_entry.get("event_id"),
                    event_type=log_entry.get("event_type", "unknown"),
                    subscription_id=log_entry.get("subscription_id", ""),
                    target_url=log_entry.get("target_url", ""),
                    attempts=int(log_entry.get("attempts", 1)),
                    status=log_entry.get("status", "unknown"),
                    status_code=log_entry.get("status_code"),
                    error=log_entry.get("error"),
                    timestamp=now_str,
                )
                session.add(row)
                session.commit()
                return deepcopy(log_entry)

    def list_webhook_deliveries(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve recent webhook delivery records in reverse chronological order."""
        with self._lock:
            with self._get_session() as session:
                stmt = (
                    select(WebhookDeliveryModel)
                    .order_by(WebhookDeliveryModel.timestamp.desc())
                    .limit(limit)
                )
                rows = session.scalars(stmt).all()
                return [
                    {
                        "delivery_id": r.id,
                        "event_id": r.event_id,
                        "event_type": r.event_type,
                        "subscription_id": r.subscription_id,
                        "target_url": r.target_url,
                        "attempts": r.attempts,
                        "status": r.status,
                        "status_code": r.status_code,
                        "error": r.error,
                        "timestamp": r.timestamp,
                    }
                    for r in rows
                ]

    def is_duplicate_webhook_event(
        self,
        event_id: str,
        max_retention: int = 1000,
    ) -> bool:
        """
        Check if an incoming webhook event has already been processed (idempotency).
        Enforces a bounded retention limit by purging oldest records when exceeded.
        """
        if not event_id:
            return False
        with self._lock:
            with self._get_session() as session:
                exists = session.get(WebhookIdempotencyModel, str(event_id))
                if exists:
                    return True
                now_str = datetime.now(timezone.utc).isoformat()
                session.add(WebhookIdempotencyModel(event_id=str(event_id), received_at=now_str))

                # Bounded retention policy: purge oldest if total entries exceed max_retention
                total_count = session.scalar(select(func.count(WebhookIdempotencyModel.event_id)))
                if total_count and total_count > max_retention:
                    excess = total_count - max_retention
                    subq = (
                        select(WebhookIdempotencyModel.event_id)
                        .order_by(WebhookIdempotencyModel.received_at.asc())
                        .limit(excess)
                    )
                    old_ids = session.scalars(subq).all()
                    if old_ids:
                        session.execute(
                            delete(WebhookIdempotencyModel).where(
                                WebhookIdempotencyModel.event_id.in_(old_ids)
                            )
                        )
                session.commit()
                return False

    # --- Alert Registry Operations ---

    def create_alert(
        self,
        user_id: str,
        *,
        title: str,
        message: str,
        severity: str = "medium",
        incident_id: str | None = None,
        source_event_id: str | None = None,
        idempotency_key: str | None = None,
        delivery_channel: str = "in_app",
        due_at: str | None = None,
        next_escalation_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create and store an alert with idempotency protection."""
        if not user_id or not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string.")
        if not title or not isinstance(title, str) or not title.strip():
            raise ValueError("title must be a non-empty string.")
        if not message or not isinstance(message, str):
            raise ValueError("message must be a string.")
        if severity not in VALID_SEVERITIES:
            severity = "medium"

        with self._lock:
            with self._get_session() as session:
                # Deduplication check
                if idempotency_key:
                    existing = session.scalar(
                        select(AlertModel).where(
                            AlertModel.idempotency_key == idempotency_key,
                            AlertModel.user_id == user_id,
                        )
                    )
                    if existing:
                        return _format_alert(existing)

                now = datetime.now(timezone.utc)
                now_str = now.isoformat()

                # Determine preferences for timeouts
                pref = session.get(AlertPreferenceModel, user_id)
                ack_timeout = pref.ack_timeout_seconds if pref else 600
                esc_interval = pref.escalation_interval_seconds if pref else 300

                if not due_at:
                    due_at = (now + timedelta(seconds=ack_timeout)).isoformat()
                if not next_escalation_at:
                    next_escalation_at = (now + timedelta(seconds=esc_interval)).isoformat()

                alert_id = f"alt_{uuid.uuid4().hex[:12]}"
                alert_row = AlertModel(
                    id=alert_id,
                    user_id=user_id,
                    incident_id=incident_id,
                    source_event_id=source_event_id,
                    idempotency_key=idempotency_key,
                    title=title,
                    message=message,
                    severity=severity,
                    status="pending",
                    created_at=now_str,
                    updated_at=now_str,
                    due_at=due_at,
                    acknowledged_at=None,
                    resolved_at=None,
                    escalation_level=0,
                    next_escalation_at=next_escalation_at,
                    attempt_count=0,
                    last_attempt_at=None,
                    delivery_channel=delivery_channel,
                    locked_until=None,
                    metadata_json=json.dumps(metadata or {}),
                )
                session.add(alert_row)
                session.commit()
                return _format_alert(alert_row)

    def get_alert(self, alert_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        """Retrieve an alert by ID, optionally verifying user ownership."""
        with self._lock:
            with self._get_session() as session:
                alert = session.get(AlertModel, alert_id)
                if not alert:
                    return None
                if user_id is not None and alert.user_id != user_id:
                    return None
                return _format_alert(alert)

    def list_alerts(
        self,
        user_id: str,
        *,
        status: str | None = None,
        severity: str | None = None,
        incident_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List alerts for the specified user with optional filtering."""
        with self._lock:
            with self._get_session() as session:
                stmt = select(AlertModel).where(AlertModel.user_id == user_id)
                if status:
                    stmt = stmt.where(AlertModel.status == status)
                if severity:
                    stmt = stmt.where(AlertModel.severity == severity)
                if incident_id:
                    stmt = stmt.where(AlertModel.incident_id == incident_id)
                stmt = stmt.order_by(AlertModel.created_at.desc()).offset(offset).limit(limit)
                rows = session.scalars(stmt).all()
                return [_format_alert(r) for r in rows]

    def acknowledge_alert(
        self,
        alert_id: str,
        user_id: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Acknowledge an alert idempotently and verify user ownership."""
        with self._lock:
            with self._get_session() as session:
                alert = session.get(AlertModel, alert_id)
                if not alert:
                    raise ValueError("Alert not found")
                if alert.user_id != user_id:
                    raise ValueError("Access denied: alert belongs to another user")

                if alert.status == "acknowledged":
                    return _format_alert(alert)

                if alert.status in ("resolved", "cancelled"):
                    raise ValueError(f"Cannot acknowledge alert in '{alert.status}' state")

                validate_alert_transition(alert.status, "acknowledged")
                now_str = datetime.now(timezone.utc).isoformat()
                alert.status = "acknowledged"
                alert.acknowledged_at = now_str
                alert.updated_at = now_str

                deliv = AlertDeliveryModel(
                    id=f"deliv_{uuid.uuid4().hex[:12]}",
                    alert_id=alert.id,
                    channel="in_app",
                    status="acknowledged",
                    attempt_number=alert.attempt_count,
                    escalation_level=alert.escalation_level,
                    details_json=json.dumps({"action": "acknowledge", "note": note or ""}),
                    timestamp=now_str,
                )
                session.add(deliv)
                session.commit()
                return _format_alert(alert)

    def resolve_alert(
        self,
        alert_id: str,
        user_id: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Resolve an alert and verify user ownership."""
        with self._lock:
            with self._get_session() as session:
                alert = session.get(AlertModel, alert_id)
                if not alert:
                    raise ValueError("Alert not found")
                if alert.user_id != user_id:
                    raise ValueError("Access denied: alert belongs to another user")

                if alert.status == "resolved":
                    return _format_alert(alert)

                if alert.status == "cancelled":
                    raise ValueError("Cannot resolve a cancelled alert")

                validate_alert_transition(alert.status, "resolved")
                now_str = datetime.now(timezone.utc).isoformat()
                alert.status = "resolved"
                alert.resolved_at = now_str
                alert.updated_at = now_str

                deliv = AlertDeliveryModel(
                    id=f"deliv_{uuid.uuid4().hex[:12]}",
                    alert_id=alert.id,
                    channel="in_app",
                    status="resolved",
                    attempt_number=alert.attempt_count,
                    escalation_level=alert.escalation_level,
                    details_json=json.dumps({"action": "resolve", "note": note or ""}),
                    timestamp=now_str,
                )
                session.add(deliv)
                session.commit()
                return _format_alert(alert)

    def cancel_alert(
        self,
        alert_id: str,
        user_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel an alert."""
        with self._lock:
            with self._get_session() as session:
                alert = session.get(AlertModel, alert_id)
                if not alert:
                    raise ValueError("Alert not found")
                if user_id is not None and alert.user_id != user_id:
                    raise ValueError("Access denied: alert belongs to another user")

                if alert.status == "cancelled":
                    return _format_alert(alert)

                if alert.status == "resolved":
                    raise ValueError("Cannot cancel an already resolved alert")

                validate_alert_transition(alert.status, "cancelled")
                now_str = datetime.now(timezone.utc).isoformat()
                alert.status = "cancelled"
                alert.updated_at = now_str

                deliv = AlertDeliveryModel(
                    id=f"deliv_{uuid.uuid4().hex[:12]}",
                    alert_id=alert.id,
                    channel="in_app",
                    status="cancelled",
                    attempt_number=alert.attempt_count,
                    escalation_level=alert.escalation_level,
                    details_json=json.dumps({"action": "cancel", "reason": reason or ""}),
                    timestamp=now_str,
                )
                session.add(deliv)
                session.commit()
                return _format_alert(alert)

    def record_delivery_attempt(
        self,
        alert_id: str,
        *,
        channel: str,
        status: str,
        error: str | None = None,
        details: dict[str, Any] | None = None,
        update_alert_status: bool = True,
    ) -> dict[str, Any]:
        """Record an alert delivery attempt and optionally update alert status."""
        with self._lock:
            with self._get_session() as session:
                alert = session.get(AlertModel, alert_id)
                if not alert:
                    raise ValueError("Alert not found")

                now_str = datetime.now(timezone.utc).isoformat()
                alert.attempt_count += 1
                alert.last_attempt_at = now_str
                alert.updated_at = now_str

                if update_alert_status:
                    if status == "success":
                        if alert.status in ("pending", "delivering"):
                            validate_alert_transition(alert.status, "delivered")
                            alert.status = "delivered"
                    elif status == "failed":
                        pref = session.get(AlertPreferenceModel, alert.user_id)
                        max_attempts = pref.max_attempts if pref else 3
                        if alert.attempt_count >= max_attempts and alert.status in ("pending", "delivering"):
                            validate_alert_transition(alert.status, "failed")
                            alert.status = "failed"

                deliv_id = f"deliv_{uuid.uuid4().hex[:12]}"
                deliv = AlertDeliveryModel(
                    id=deliv_id,
                    alert_id=alert.id,
                    channel=channel,
                    status=status,
                    attempt_number=alert.attempt_count,
                    escalation_level=alert.escalation_level,
                    error=error,
                    details_json=json.dumps(details or {}),
                    timestamp=now_str,
                )
                session.add(deliv)
                session.commit()
                return _format_delivery(deliv)

    def claim_due_alerts(
        self,
        lock_duration_seconds: int = 60,
        limit: int = 10,
        now_iso: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Safely claim due alerts by locking them against concurrent workers.
        Returns the claimed alerts.
        """
        with self._lock:
            with self._get_session() as session:
                now_dt = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
                now_str = now_dt.isoformat()
                locked_until_str = (now_dt + timedelta(seconds=lock_duration_seconds)).isoformat()

                stmt = (
                    select(AlertModel)
                    .where(
                        AlertModel.status.in_(["pending", "delivered", "escalated"]),
                        or_(
                            AlertModel.locked_until.is_(None),
                            AlertModel.locked_until < now_str,
                        ),
                        or_(
                            AlertModel.status == "pending",
                            and_(
                                AlertModel.next_escalation_at.is_not(None),
                                AlertModel.next_escalation_at <= now_str,
                            ),
                            and_(
                                AlertModel.due_at.is_not(None),
                                AlertModel.due_at <= now_str,
                            ),
                        ),
                    )
                    .order_by(AlertModel.created_at.asc())
                    .limit(limit)
                )
                rows = session.scalars(stmt).all()
                claimed = []
                for row in rows:
                    row.locked_until = locked_until_str
                    claimed.append(_format_alert(row))
                session.commit()
                return claimed

    def escalate_due_alerts(
        self,
        max_alerts: int = 50,
        now_iso: str | None = None,
    ) -> list[dict[str, Any]]:
        """Escalate alerts whose acknowledgment deadlines or escalation intervals have passed."""
        with self._lock:
            with self._get_session() as session:
                now_dt = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
                now_str = now_dt.isoformat()

                stmt = (
                    select(AlertModel)
                    .where(
                        AlertModel.status.in_(["pending", "delivering", "delivered", "escalated"]),
                        or_(
                            and_(
                                AlertModel.next_escalation_at.is_not(None),
                                AlertModel.next_escalation_at <= now_str,
                            ),
                            and_(
                                AlertModel.due_at.is_not(None),
                                AlertModel.due_at <= now_str,
                            ),
                        ),
                    )
                    .limit(max_alerts)
                )
                rows = session.scalars(stmt).all()
                escalated_list = []
                for row in rows:
                    if row.status in ("acknowledged", "resolved", "cancelled"):
                        continue
                    row.escalation_level += 1
                    try:
                        validate_alert_transition(row.status, "escalated")
                        row.status = "escalated"
                    except ValueError:
                        pass
                    row.updated_at = now_str

                    pref = session.get(AlertPreferenceModel, row.user_id)
                    interval = pref.escalation_interval_seconds if pref else 300
                    row.next_escalation_at = (now_dt + timedelta(seconds=interval)).isoformat()
                    row.locked_until = None

                    deliv = AlertDeliveryModel(
                        id=f"deliv_{uuid.uuid4().hex[:12]}",
                        alert_id=row.id,
                        channel=row.delivery_channel,
                        status="escalated",
                        attempt_number=row.attempt_count,
                        escalation_level=row.escalation_level,
                        details_json=json.dumps({"action": "escalate", "level": row.escalation_level}),
                        timestamp=now_str,
                    )
                    session.add(deliv)
                    escalated_list.append(_format_alert(row))

                session.commit()
                return escalated_list

    def get_alert_history(self, alert_id: str, user_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve delivery and escalation history for an alert."""
        with self._lock:
            with self._get_session() as session:
                if user_id is not None:
                    alert = session.get(AlertModel, alert_id)
                    if not alert or alert.user_id != user_id:
                        raise ValueError("Alert not found or access denied")

                stmt = (
                    select(AlertDeliveryModel)
                    .where(AlertDeliveryModel.alert_id == alert_id)
                    .order_by(AlertDeliveryModel.timestamp.asc())
                )
                rows = session.scalars(stmt).all()
                return [_format_delivery(r) for r in rows]

    def get_alert_preferences(self, user_id: str) -> dict[str, Any]:
        """Retrieve alert preferences for a user, returning default values if not configured."""
        with self._lock:
            with self._get_session() as session:
                pref = session.get(AlertPreferenceModel, user_id)
                if not pref:
                    res = deepcopy(DEFAULT_ALERT_PREFERENCES)
                    res["user_id"] = user_id
                    return res
                return _format_preference(pref)

    def update_alert_preferences(
        self,
        user_id: str,
        preferences: dict[str, Any],
    ) -> dict[str, Any]:
        """Update or create user alert preferences."""
        if not user_id:
            raise ValueError("user_id is required")

        with self._lock:
            with self._get_session() as session:
                pref = session.get(AlertPreferenceModel, user_id)
                now_str = datetime.now(timezone.utc).isoformat()
                if not pref:
                    pref = AlertPreferenceModel(
                        user_id=user_id,
                        channels_json=json.dumps(preferences.get("channels", ["in_app"])),
                        min_severity=preferences.get("min_severity", "medium"),
                        quiet_hours_enabled=bool(preferences.get("quiet_hours_enabled", False)),
                        quiet_hours_start=preferences.get("quiet_hours_start", "22:00"),
                        quiet_hours_end=preferences.get("quiet_hours_end", "08:00"),
                        timezone=preferences.get("timezone", "UTC"),
                        voice_enabled=bool(preferences.get("voice_enabled", True)),
                        max_attempts=int(preferences.get("max_attempts", 3)),
                        escalation_interval_seconds=int(preferences.get("escalation_interval_seconds", 300)),
                        ack_timeout_seconds=int(preferences.get("ack_timeout_seconds", 600)),
                        phone_consent=bool(preferences.get("phone_consent", False)),
                        phone_number=preferences.get("phone_number"),
                        created_at=now_str,
                        updated_at=now_str,
                    )
                    session.add(pref)
                else:
                    if "channels" in preferences:
                        pref.channels_json = json.dumps(preferences["channels"])
                    if "min_severity" in preferences:
                        pref.min_severity = preferences["min_severity"]
                    if "quiet_hours_enabled" in preferences:
                        pref.quiet_hours_enabled = bool(preferences["quiet_hours_enabled"])
                    if "quiet_hours_start" in preferences:
                        pref.quiet_hours_start = preferences["quiet_hours_start"]
                    if "quiet_hours_end" in preferences:
                        pref.quiet_hours_end = preferences["quiet_hours_end"]
                    if "timezone" in preferences:
                        pref.timezone = preferences["timezone"]
                    if "voice_enabled" in preferences:
                        pref.voice_enabled = bool(preferences["voice_enabled"])
                    if "max_attempts" in preferences:
                        pref.max_attempts = int(preferences["max_attempts"])
                    if "escalation_interval_seconds" in preferences:
                        pref.escalation_interval_seconds = int(preferences["escalation_interval_seconds"])
                    if "ack_timeout_seconds" in preferences:
                        pref.ack_timeout_seconds = int(preferences["ack_timeout_seconds"])
                    if "phone_consent" in preferences:
                        pref.phone_consent = bool(preferences["phone_consent"])
                    if "phone_number" in preferences:
                        pref.phone_number = preferences["phone_number"]
                    pref.updated_at = now_str

                session.commit()
                return _format_preference(pref)

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
                session.execute(delete(UserModel))
                session.execute(delete(WebhookDeliveryModel))
                session.execute(delete(WebhookSubscriptionModel))
                session.execute(delete(WebhookIdempotencyModel))
                session.execute(delete(AlertDeliveryModel))
                session.execute(delete(AlertModel))
                session.execute(delete(AlertPreferenceModel))
                session.commit()

    def close(self) -> None:
        """Dispose database engine and close active connections."""
        with self._lock:
            if hasattr(self, "_engine") and self._engine:
                self._engine.dispose()



# Singleton instance for backend use
storage_registry = StorageRegistry(db_url=get_default_db_url())
