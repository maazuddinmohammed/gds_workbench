"""Parent-before-child ordering for modeled loads and Mapping preparation."""

from __future__ import annotations

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
