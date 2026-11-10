"""Parent-before-child ordering for modeled loads and Mapping preparation."""

from __future__ import annotations

from collections import deque
from collections.abc import Hashable, Iterable, Mapping


def resolve_dependency_orders[Key: Hashable](
    orders: Mapping[Key, int],
    edges: Iterable[tuple[Key, Key]],
    *,
    targets: set[Key],
    include_dependents: bool = False,
) -> tuple[dict[Key, int], set[Key]]:
    """Raise required orders only; return nodes blocked by a cycle separately.

    Edges are (child, parent). Ancestors always participate. Model edits also
    include dependents so raising a parent cannot leave its saved children behind.
    Unrelated components and deliberate gaps in saved orders remain untouched.
    """
    parents: dict[Key, set[Key]] = {}
    children: dict[Key, set[Key]] = {}
    for child, parent in edges:
        if child in orders and parent in orders:
            parents.setdefault(child, set()).add(parent)
            children.setdefault(parent, set()).add(child)
    relevant = targets & orders.keys()
    pending = list(relevant)
    while pending:
        key = pending.pop()
        neighbors = parents.get(key, set())
        if include_dependents:
            neighbors = neighbors | children.get(key, set())
        for neighbor in neighbors:
            if neighbor not in relevant:
                relevant.add(neighbor)
                pending.append(neighbor)
    waiting = {key: len(parents.get(key, ())) for key in relevant}
    ready = [key for key, count in waiting.items() if count == 0]
    resolved: dict[Key, int] = {}
    while ready:
        key = ready.pop()
        resolved[key] = max(
            orders[key],
            1 + max((resolved[parent] for parent in parents.get(key, ())), default=-1),
        )
        for child in children.get(key, ()):
            if child in waiting:
                waiting[child] -= 1
                if waiting[child] == 0:
                    ready.append(child)
    return resolved, relevant - resolved.keys()


def resolve_mapping_dependency_order(
    orders: Mapping[int, int], edges: set[tuple[int, int]], target: int
) -> tuple[int, set[tuple[int, int]], tuple[int, ...]]:
    """Order the first load, identify its deferred edges and return one actual cycle."""
    resolved, blocked = resolve_dependency_orders(orders, edges, targets={target})
    if not blocked:
        return resolved[target], set(), ()

    # 'blocked' includes descendants of cycles. Two iterative depth-first passes
    # identify strongly connected components: only edges within one component
    # require a later load. Keep dependencies entering or leaving a component.
    parents: dict[int, set[int]] = {node: set() for node in blocked}
    children: dict[int, set[int]] = {node: set() for node in blocked}
    for child, parent in edges:
        if child in blocked and parent in blocked:
            parents[child].add(parent)
            children[parent].add(child)
    visited: set[int] = set()
    finished: list[int] = []
    for root in blocked:
        stack = [(root, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                finished.append(node)
            elif node not in visited:
                visited.add(node)
                stack.append((node, True))
                stack.extend((parent, False) for parent in parents[node])
    component: dict[int, int] = {}
    for root in reversed(finished):
        if root in component:
            continue
        pending = [root]
        while pending:
            node = pending.pop()
            if node not in component:
                component[node] = root
                pending.extend(children[node])
    deferred = {
        (child, parent)
        for child in blocked
        for parent in parents[child]
        if component[child] == component[parent]
    }
    first_pass, _ = resolve_dependency_orders(orders, edges - deferred, targets={target})

    # Report a shortest cycle through the target when possible. Otherwise show
    # a cycle from its ancestry. IDs break ties independently of SQL row order.
    cyclic_nodes = {child for child, _ in deferred}
    start = target if target in cyclic_nodes else min(cyclic_nodes)
    prior = {start: start}
    queue = deque([start])
    while queue:
        child = queue.popleft()
        for parent in sorted(parents[child]):
            if (child, parent) not in deferred:
                continue
            if parent == start:
                path = [start, child]
                while path[-1] != start:
                    path.append(prior[path[-1]])
                return first_pass[target], deferred, tuple(reversed(path))
            if parent not in prior:
                prior[parent] = child
                queue.append(parent)
    raise AssertionError("A cyclic component must contain a return path.")
