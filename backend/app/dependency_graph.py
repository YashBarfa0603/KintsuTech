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
    ) -> None:
        """Register a service node."""
        if not service or not isinstance(service, str):
            raise ValueError("Service name must be a non-empty string.")

        self._graph.add_node(
            service,
            description=description,
            is_critical=is_critical,
        )
        if is_critical:
            self._critical_services.add(service)

    def add_dependency(
        self,
        upstream: str,
        downstream: str,
        *,
        interaction_type: str = "api_call",
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

        self._graph.add_edge(upstream, downstream, interaction=interaction_type)

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
        nodes = [
            {
                "id": node,
                "description": self._graph.nodes[node].get("description", ""),
                "is_critical": self._graph.nodes[node].get("is_critical", False),
            }
            for node in self._graph.nodes
        ]
        edges = [
            {
                "source": u,
                "target": v,
                "interaction": data.get("interaction", "api_call"),
            }
            for u, v, data in self._graph.edges(data=True)
        ]
        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": sorted(nodes, key=lambda n: n["id"]),
            "edges": sorted(edges, key=lambda e: (e["source"], e["target"])),
        }


def create_default_dependency_graph() -> DependencyGraph:
    """Pre-populate default service dependencies for KintsuTech platform."""
    graph = DependencyGraph()

    # Weather ecosystem
    graph.add_service("weather", description="Mock weather provider", is_critical=False)
    graph.add_service("mobile_app", description="Client mobile app", is_critical=False)
    graph.add_service("trip_planner", description="Itinerary engine", is_critical=False)
    graph.add_service("alert_service", description="Severe weather alerts", is_critical=True)

    graph.add_dependency("weather", "trip_planner")
    graph.add_dependency("weather", "mobile_app")
    graph.add_dependency("weather", "alert_service")

    # E-commerce ecosystem
    graph.add_service("products", description="Product catalog API", is_critical=False)
    graph.add_service("catalog_service", description="Storefront search & display", is_critical=False)
    graph.add_service("checkout_service", description="Order checkout workflow", is_critical=True)
    graph.add_service("inventory", description="Warehouse inventory", is_critical=True)

    graph.add_dependency("products", "catalog_service")
    graph.add_dependency("products", "checkout_service")
    graph.add_dependency("inventory", "checkout_service")

    return graph
