
from myers_diff import myers_diff


def test_identical_sequences():
    assert myers_diff(["a", "b"], ["a", "b"]) == [
        {"operation": "equal", "value": "a"},
        {"operation": "equal", "value": "b"},
    ]


def test_detects_replacement():
    result = myers_diff(["limit=20"], ["limit=10"])

    assert result == [
        {"operation": "delete", "value": "limit=20"},
        {"operation": "insert", "value": "limit=10"},
    ]


def test_detects_added_line():
    assert myers_diff(["a"], ["a", "b"]) == [
        {"operation": "equal", "value": "a"},
        {"operation": "insert", "value": "b"},
    ]


def test_detects_removed_line():
    assert myers_diff(["a", "b"], ["a"]) == [
        {"operation": "equal", "value": "a"},
        {"operation": "delete", "value": "b"},
    ]


def test_handles_empty_sequences():
    assert myers_diff([], ["a"]) == [
        {"operation": "insert", "value": "a"},
    ]
    assert myers_diff(["a"], []) == [
        {"operation": "delete", "value": "a"},
    ]


def test_handles_completely_different_sequences():
    result = myers_diff(["a"], ["b"])

    assert result == [
        {"operation": "delete", "value": "a"},
        {"operation": "insert", "value": "b"},
    ]
