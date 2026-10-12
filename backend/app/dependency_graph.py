from typing import Any
import networkx as nx


class DependencyGraph:
    """
    Service dependency graph and downstream blast radius analyzer.
    Uses NetworkX directed graphs (DiGraph).
    Edges represent data flow from provider (upstream) to consumer (downstream).
    """

    def __init__(self) -> None:
        self._graph = nx.DiGraph()
        self._critical_services: set[str] = set()

    def add_service(
        self,
        service: str,
        *,
        description: str = "",
        is_critical: bool = False,
        **extra: Any,
    ) -> None:
        """Register a service node with optional rich metadata."""
        if not service or not isinstance(service, str):
            raise ValueError("Service name must be a non-empty string.")

        node_data = {
            "description": description,
            "is_critical": is_critical,
            **extra,
        }
        self._graph.add_node(
            service,
            **node_data,
        )
        if is_critical:
            self._critical_services.add(service)

    def add_dependency(
        self,
        upstream: str,
        downstream: str,
        *,
        interaction_type: str = "api_call",
        **extra: Any,
    ) -> None:
        """
        Record a dependency: downstream depends on upstream.
        Edge is oriented upstream -> downstream.
        """
        if not upstream or not downstream:
            raise ValueError("Both upstream and downstream services are required.")
        if upstream == downstream:
            raise ValueError("A service cannot depend on itself.")

        if upstream not in self._graph:
            self.add_service(upstream)
        if downstream not in self._graph:
            self.add_service(downstream)

        edge_data = {
            "interaction": interaction_type,
            **extra,
        }
        self._graph.add_edge(upstream, downstream, **edge_data)

    def get_direct_dependents(self, service: str) -> list[str]:
        """Return immediate consumers of a service."""
        if service not in self._graph:
            return []
        return sorted(list(self._graph.successors(service)))

    def get_all_downstream_dependents(self, service: str) -> list[str]:
        """Return all transitive consumers affected by a change in this service."""
        if service not in self._graph:
            return []
        try:
            descendants = nx.descendants(self._graph, service)
            return sorted(list(descendants))
        except Exception:
            return []

    def calculate_impact(self, service: str) -> dict[str, Any]:
        """
        Calculate blast radius and impact level for a service change.
        """
        if service not in self._graph:
            return {
                "service": service,
                "exists_in_graph": False,
                "direct_dependents": [],
                "all_downstream_dependents": [],
                "total_affected": 0,
                "impact_level": "unknown",
                "critical_services_affected": [],
            }

        direct = self.get_direct_dependents(service)
        all_downstream = self.get_all_downstream_dependents(service)
        critical_affected = [
            svc for svc in all_downstream if svc in self._critical_services
        ]

        # Determine impact level
        count = len(all_downstream)
        if critical_affected:
            impact_level = "critical"
        elif count >= 4:
            impact_level = "high"
        elif count >= 2:
            impact_level = "medium"
        elif count == 1:
            impact_level = "low"
        else:
            impact_level = "none"

        return {
            "service": service,
            "exists_in_graph": True,
            "direct_dependents": direct,
            "all_downstream_dependents": all_downstream,
            "total_affected": count,
            "impact_level": impact_level,
            "critical_services_affected": critical_affected,
        }

    def detect_cycles(self) -> list[list[str]]:
        """Return any cycles detected in the dependency graph."""
        try:
            return list(nx.simple_cycles(self._graph))
        except Exception:
            return []

    def to_dict(self) -> dict[str, Any]:
        """Serialize nodes and edges for visualization or API responses."""
        nodes = []
        for node in self._graph.nodes:
            d = dict(self._graph.nodes[node])
            nodes.append({
                "id": node,
                "name": d.get("name", node.replace("_", " ").title()),
                "kind": d.get("kind", "dependency"),
                "subtype": d.get("subtype", "Service"),
                "description": d.get("description", ""),
                "detail": d.get("detail", d.get("description", "")),
                "endpoint": d.get("endpoint", ""),
                "protocol": d.get("protocol", "HTTP/REST"),
                "provider": d.get("provider", "Kintsu Core"),
                "status": d.get("status", "healthy"),
                "is_critical": d.get("is_critical", False),
                "project": d.get("project", "Pulse API"),
                "environment": d.get("environment", "Production"),
                "evidence": d.get("evidence", "Registered service"),
                "source": d.get("source", "inventory"),
                **{
                    k: v
                    for k, v in d.items()
                    if k not in (
                        "name", "kind", "subtype", "description", "detail",
                        "endpoint", "protocol", "provider", "status",
                        "is_critical", "project", "environment", "evidence", "source"
                    )
                },
            })

        edges = []
        for u, v, d in self._graph.edges(data=True):
            d_dict = dict(d)
            edges.append({
                "id": f"edge-{u}-{v}",
                "source": u,
                "target": v,
                "from": u,
                "to": v,
                "label": d_dict.get("label", d_dict.get("interaction", "api_call")),
                "interaction": d_dict.get("interaction", "api_call"),
                "status": d_dict.get("status", "healthy"),
                "evidence": d_dict.get("evidence", "confirmed"),
                "confidence": d_dict.get("confidence", 95),
            })

        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": sorted(nodes, key=lambda n: n["id"]),
            "edges": sorted(edges, key=lambda e: (e["source"], e["target"])),
        }


def create_default_dependency_graph() -> DependencyGraph:
    """Pre-populate real service dependencies for KintsuTech platform."""
    graph = DependencyGraph()

    # 1. Weather Intelligence Ecosystem (Real API: GET /api/v1/mock/weather)
    graph.add_service(
        "weather",
        name="Weather Intelligence API",
        kind="api",
        subtype="External REST API",
        description="Mock weather provider with temperature schema drift",
        detail="GET /api/v1/mock/weather",
        endpoint="/api/v1/mock/weather",
        protocol="HTTP/REST",
        provider="OpenWeather Mock Service",
        status="affected",
        evidence="Myers schema drift detected: temperature (removed) -> temp_c (added)",
        is_critical=False,
    )
    graph.add_service(
        "mobile_app",
        name="Client Mobile Experience",
        kind="application",
        subtype="Mobile Client",
        description="iOS & Android travel and weather widgets",
        detail="apps/mobile/weather_widget.tsx",
        endpoint="mobile://weather/v2",
        protocol="React Native",
        provider="Kintsu Frontend",
        status="healthy",
        evidence="Observed 200 OK traffic",
        is_critical=False,
    )
    graph.add_service(
        "trip_planner",
        name="Trip Planner Engine",
        kind="dependency",
        subtype="Core Workflow",
        description="Travel pack condition & itinerary advisor",
        detail="services/weather.ts:42",
        endpoint="/workflows/travel/pack-advisory",
        protocol="TypeScript / Node",
        provider="Kintsu Core",
        status="affected",
        evidence="Direct consumer of weather.temperature; unhandled 412 in parser",
        is_critical=False,
    )
    graph.add_service(
        "alert_service",
        name="Severe Alert Service",
        kind="dependency",
        subtype="Incident Pipeline",
        description="Evaluates freeze alerts & triggers automated escalation",
        detail="backend/app/scheduler.py:78",
        endpoint="kintsu://events/severe-weather",
        protocol="Python Async Worker",
        provider="Kintsu Core",
        status="affected",
        evidence="Trigger threshold calculation failed on missing temperature float",
        is_critical=True,
    )

    graph.add_dependency(
        "weather", "trip_planner",
        interaction_type="api_call",
        label="GET /forecast (temp_c drift)",
        status="affected",
        evidence="confirmed",
    )
    graph.add_dependency(
        "weather", "mobile_app",
        interaction_type="api_call",
        label="GET /weather (cached widget)",
        status="healthy",
        evidence="confirmed",
    )
    graph.add_dependency(
        "weather", "alert_service",
        interaction_type="api_call",
        label="evaluates freeze thresholds",
        status="affected",
        evidence="confirmed",
    )

    # 2. Stripe Payments & Checkout (Real API: POST /v1/payment_intents/:id, POST /webhooks/stripe)
    graph.add_service(
        "stripe_gateway",
        name="Stripe Payment Gateway",
        kind="api",
        subtype="Payment & Webhooks",
        description="Stripe PaymentIntents & Webhook receiver",
        detail="POST /v1/payment_intents/:id · POST /webhooks/stripe",
        endpoint="https://api.stripe.com/v1/payment_intents",
        protocol="HTTPS REST + Webhook",
        provider="Stripe Inc.",
        status="affected",
        evidence="Incident KIN-2841: display_name -> name field mismatch",
        is_critical=False,
    )
    graph.add_service(
        "checkout_service",
        name="Checkout Order Service",
        kind="application",
        subtype="Core Business Service",
        description="Order checkout & payment settlement workflow",
        detail="backend/app/checkout_service.py",
        endpoint="/api/v1/checkout/process",
        protocol="REST & FastPay",
        provider="Kintsu Core",
        status="affected",
        evidence="412 Precondition Failed when reading paymentIntent.name",
        is_critical=True,
    )
    graph.add_service(
        "billing_ledger_sync",
        name="Billing Ledger Sync",
        kind="dependency",
        subtype="Accounting Pipeline",
        description="Double-entry invoice and ledger sync",
        detail="services/ledger_sync.ts",
        endpoint="ledger://sync/v1",
        protocol="PostgreSQL Batch Worker",
        provider="Kintsu Core",
        status="affected",
        evidence="Awaiting schema repair mapping proposal",
        is_critical=False,
    )

    graph.add_dependency(
        "stripe_gateway", "checkout_service",
        interaction_type="payment_intent",
        label="processes checkout (display_name)",
        status="affected",
        evidence="confirmed",
    )
    graph.add_dependency(
        "stripe_gateway", "billing_ledger_sync",
        interaction_type="webhook_event",
        label="payment.succeeded event",
        status="affected",
        evidence="confirmed",
    )

    # 3. Vapi Telephony & Escalation Voice Agent (Real API: POST https://api.vapi.ai/call/phone)
    graph.add_service(
        "vapi_telephony",
        name="Vapi Voice Agent Gateway",
        kind="api",
        subtype="Telephony & Voice AI",
        description="Outbound telephony escalation & conversational voice assistant",
        detail="POST https://api.vapi.ai/call/phone · POST /api/vapi/webhook",
        endpoint="https://api.vapi.ai/call/phone",
        protocol="HTTPS REST + SIP Webhook",
        provider="Vapi Voice Platform",
        status="healthy",
        evidence="Configured assistant asst_kintsu_voice_v1; caller +12025550199",
        is_critical=False,
    )
    graph.add_service(
        "alert_scheduler",
        name="Persistent Alert Scheduler",
        kind="application",
        subtype="Escalation Engine",
        description="Claims unacknowledged alerts & triggers outbound voice dispatch",
        detail="backend/app/scheduler.py",
        endpoint="scheduler://escalations/v1",
        protocol="Background Task Daemon",
        provider="Kintsu Core",
        status="healthy",
        evidence="Idempotent claim & quiet hours guard verified",
        is_critical=True,
    )
    graph.add_service(
        "call_delivery_logger",
        name="Telephony Audit Logger",
        kind="dependency",
        subtype="Audit & Compliance",
        description="Records call IDs, speech updates, and acknowledgement transcripts",
        detail="backend/app/storage.py (AlertDeliveryModel)",
        endpoint="sqlite:///kintsu_alerts.db",
        protocol="SQLite / SQLAlchemy",
        provider="Kintsu Storage",
        status="healthy",
        evidence="Verified webhook signature callbacks and delivery logs",
        is_critical=False,
    )

    graph.add_dependency(
        "vapi_telephony", "alert_scheduler",
        interaction_type="voice_escalation",
        label="outbound escalation dispatch",
        status="healthy",
        evidence="confirmed",
    )
    graph.add_dependency(
        "vapi_telephony", "call_delivery_logger",
        interaction_type="webhook_callback",
        label="call-report webhook callbacks",
        status="healthy",
        evidence="confirmed",
    )

    # 4. Supabase Identity & RBAC Gateway (Real API: https://djmgakxzxqyquvmkhkxo.supabase.co/auth/v1)
    graph.add_service(
        "supabase_auth",
        name="Supabase Identity Gateway",
        kind="api",
        subtype="Auth & GoTrue Gateway",
        description="User authentication, JWT token verification & RBAC",
        detail="https://djmgakxzxqyquvmkhkxo.supabase.co/auth/v1",
        endpoint="https://djmgakxzxqyquvmkhkxo.supabase.co/auth/v1",
        protocol="HTTPS REST + JWT HS256",
        provider="Supabase Cloud",
        status="healthy",
        evidence="Verified URL & anon key in frontend/.env.local",
        is_critical=False,
    )
    graph.add_service(
        "kintsu_console",
        name="Kintsu Admin Console",
        kind="application",
        subtype="SPA Web Dashboard",
        description="Incident commander and developer UI",
        detail="frontend/src/components/layout/AppShell.tsx",
        endpoint="http://localhost:3000",
        protocol="Next.js React Client",
        provider="Kintsu Frontend",
        status="healthy",
        evidence="Active operator session",
        is_critical=False,
    )
    graph.add_service(
        "jwt_rbac_guard",
        name="JWT RBAC Security Guard",
        kind="dependency",
        subtype="Security Middleware",
        description="FastAPI authorization and token validation",
        detail="backend/app/auth.py",
        endpoint="/api/v1/auth/verify",
        protocol="Python Middleware",
        provider="Kintsu Core",
        status="healthy",
        evidence="Validates HS256 JWT signatures on protected routes",
        is_critical=True,
    )

    graph.add_dependency(
        "supabase_auth", "kintsu_console",
        interaction_type="oauth_session",
        label="Bearer token auth session",
        status="healthy",
        evidence="confirmed",
    )
    graph.add_dependency(
        "supabase_auth", "jwt_rbac_guard",
        interaction_type="token_verify",
        label="HS256 JWT signature verification",
        status="healthy",
        evidence="confirmed",
    )

    # 5. Product Catalog & Warehouse Inventory (Real API: GET /api/v1/products, GET /api/v1/inventory)
    graph.add_service(
        "products",
        name="Product Catalog API",
        kind="api",
        subtype="Internal REST API",
        description="Product catalog and pricing endpoints",
        detail="GET /api/v1/products",
        endpoint="/api/v1/products",
        protocol="HTTP/REST",
        provider="Kintsu Catalog Service",
        status="healthy",
        evidence="OpenAPI 3.1 contract active",
        is_critical=False,
    )
    graph.add_service(
        "catalog_service",
        name="Catalog Search Service",
        kind="dependency",
        subtype="Search & Cache",
        description="Storefront search & item display",
        detail="backend/app/catalog_service.py",
        endpoint="/api/v1/catalog/search",
        protocol="Internal Microservice",
        provider="Kintsu Core",
        status="healthy",
        evidence="In-memory cache warmed",
        is_critical=False,
    )
    graph.add_service(
        "inventory",
        name="Warehouse Inventory",
        kind="dependency",
        subtype="Warehouse Datastore",
        description="Real-time stock reservation and SKU ledger",
        detail="GET /api/v1/inventory",
        endpoint="/api/v1/inventory",
        protocol="HTTP/REST",
        provider="Warehouse Ops",
        status="healthy",
        evidence="Stock synchronization active",
        is_critical=True,
    )

    graph.add_dependency(
        "products", "catalog_service",
        interaction_type="api_call",
        label="GET /api/v1/products",
        status="healthy",
        evidence="confirmed",
    )
    graph.add_dependency(
        "products", "checkout_service",
        interaction_type="api_call",
        label="validates product SKU pricing",
        status="healthy",
        evidence="confirmed",
    )
    graph.add_dependency(
        "inventory", "checkout_service",
        interaction_type="stock_check",
        label="reserves warehouse stock",
        status="healthy",
        evidence="confirmed",
    )

    return graph
