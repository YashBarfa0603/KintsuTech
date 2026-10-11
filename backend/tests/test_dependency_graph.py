import pytest
from app.dependency_graph import DependencyGraph, create_default_dependency_graph


def test_add_service_and_dependency():
    graph = DependencyGraph()
    graph.add_service("auth", description="Auth Service", is_critical=True)
    graph.add_service("api_gateway", description="API Gateway")
    graph.add_dependency("auth", "api_gateway")

    assert graph.get_direct_dependents("auth") == ["api_gateway"]
    assert graph.get_all_downstream_dependents("auth") == ["api_gateway"]


def test_transitive_downstream_dependencies():
    graph = DependencyGraph()
    graph.add_service("db")
    graph.add_service("backend")
    graph.add_service("frontend")

    graph.add_dependency("db", "backend")
    graph.add_dependency("backend", "frontend")

    assert graph.get_direct_dependents("db") == ["backend"]
    assert graph.get_all_downstream_dependents("db") == ["backend", "frontend"]


def test_calculate_impact_levels():
    graph = DependencyGraph()
    graph.add_service("svc_none")
    assert graph.calculate_impact("svc_none")["impact_level"] == "none"

    graph.add_service("svc_critical_child", is_critical=True)
    graph.add_dependency("svc_none", "svc_critical_child")
    assert graph.calculate_impact("svc_none")["impact_level"] == "critical"


def test_default_graph_structure():
    graph = create_default_dependency_graph()
    impact = graph.calculate_impact("weather")

    assert impact["exists_in_graph"] is True
    assert "alert_service" in impact["all_downstream_dependents"]
    assert "mobile_app" in impact["all_downstream_dependents"]
    assert "trip_planner" in impact["all_downstream_dependents"]
    # alert_service is critical, so impact should be critical
    assert impact["impact_level"] == "critical"
    assert "alert_service" in impact["critical_services_affected"]


def test_invalid_service_names():
    graph = DependencyGraph()
    with pytest.raises(ValueError):
        graph.add_service("")

    with pytest.raises(ValueError):
        graph.add_dependency("same", "same")


def test_to_dict_serialization():
    graph = create_default_dependency_graph()
    data = graph.to_dict()

    assert "nodes" in data
    assert "edges" in data
    assert data["node_count"] > 0
    assert data["edge_count"] > 0
