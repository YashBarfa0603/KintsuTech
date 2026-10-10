
from typing import Literal, TypedDict


Operation = Literal["equal", "delete", "insert"]


class DiffOperation(TypedDict):
    operation: Operation
    value: str


def myers_diff(
    old_lines: list[str],
    new_lines: list[str],
) -> list[DiffOperation]:
    """
    Return a shortest edit script using Myers' diff algorithm.

    Each operation is:
    - equal: a line exists in both sequences
    - delete: a line exists only in the old sequence
    - insert: a line exists only in the new sequence
    """
    n = len(old_lines)
    m = len(new_lines)
    max_distance = n + m

    # V maps a diagonal to the furthest reachable x coordinate.
    frontier = {1: 0}
    trace: list[dict[int, int]] = []

    for distance in range(max_distance + 1):
        trace.append(frontier.copy())

        for diagonal in range(-distance, distance + 1, 2):
            if (
                diagonal == -distance
                or (
                    diagonal != distance
                    and frontier.get(diagonal - 1, -1)
                    < frontier.get(diagonal + 1, -1)
                )
            ):
                x = frontier.get(diagonal + 1, 0)
            else:
                x = frontier.get(diagonal - 1, 0) + 1

            y = x - diagonal

            # Follow the diagonal while lines match.
            while (
                x < n
                and y < m
                and old_lines[x] == new_lines[y]
            ):
                x += 1
                y += 1

            frontier[diagonal] = x

            if x >= n and y >= m:
                return _backtrack(
                    old_lines,
                    new_lines,
                    trace,
                    distance,
                )

    return []


def _backtrack(
    old_lines: list[str],
    new_lines: list[str],
    trace: list[dict[int, int]],
    distance: int,
) -> list[DiffOperation]:
    """Reconstruct the shortest edit script from the saved frontiers."""
    x = len(old_lines)
    y = len(new_lines)
    reversed_operations: list[DiffOperation] = []

    for d in range(distance, -1, -1):
        frontier = trace[d]
        diagonal = x - y

        if (
            diagonal == -d
            or (
                diagonal != d
                and frontier.get(diagonal - 1, -1)
                < frontier.get(diagonal + 1, -1)
            )
        ):
            previous_diagonal = diagonal + 1
        else:
            previous_diagonal = diagonal - 1

        previous_x = frontier.get(previous_diagonal, 0)
        previous_y = previous_x - previous_diagonal

        while x > previous_x and y > previous_y:
            reversed_operations.append({
                "operation": "equal",
                "value": old_lines[x - 1],
            })
            x -= 1
            y -= 1

        if d == 0:
            break

        if x == previous_x:
            reversed_operations.append({
                "operation": "insert",
                "value": new_lines[y - 1],
            })
            y -= 1
        else:
            reversed_operations.append({
                "operation": "delete",
                "value": old_lines[x - 1],
            })
            x -= 1

    while x > 0 and y > 0:
        reversed_operations.append({
            "operation": "equal",
            "value": old_lines[x - 1],
        })
        x -= 1
        y -= 1

    while x > 0:
        reversed_operations.append({
            "operation": "delete",
            "value": old_lines[x - 1],
        })
        x -= 1

    while y > 0:
        reversed_operations.append({
            "operation": "insert",
            "value": new_lines[y - 1],
        })
        y -= 1

    reversed_operations.reverse()
    return reversed_operations
