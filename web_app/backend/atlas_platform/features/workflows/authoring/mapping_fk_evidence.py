"""Role-specific evidence shared by inline Mapping and its frozen FK reader."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from .context_inputs import OBJECT_FIELDS, natural_key


def mapping_fk_evidence(
    cards: list[dict[str, Any]],
    sources: Sequence[dict[str, Any]],
    relationships: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Connect only saved operands and eligible endpoints. A candidate link is never a join rule."""
    target = next(card["record"] for card in cards if card["kind"] == "target")
    layer = target["entity_type"].removesuffix("_entity")
    entity_fields = (f"{layer}_entity_schema_name", f"{layer}_entity_name")
    child_fields = tuple(f"from_{field}" for field in entity_fields)
    parent_fields = tuple(f"to_{field}" for field in entity_fields)
    target_key = natural_key(target, ("entity_schema_name", "entity_name"))
    roles = [
        card["record"]
        for card in cards
        if card["kind"] == "target_relationship"
        and natural_key(card["record"], child_fields) == target_key
    ]
    if not roles:
        return []

    child_attributes = {
        card["record"]["attribute_name"].casefold(): card["record"]
        for card in cards
        if card["kind"] == "field"
    }
    parent_attributes: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        row = card["record"]
        if card["kind"] == f"source_{layer}_attribute":
            parent_attributes[natural_key(row, entity_fields)].append(row)
    # Foreign-System parent lineage can explain the lookup but cannot authorize Bronze
    # reads. Match both endpoints to this branch's frozen eligible Objects and columns.
    columns: dict[tuple[Any, ...], dict[str, Any]] = {}
    batch_fields: dict[tuple[Any, ...], str | None] = {}
    for source in sources:
        obj = source["object"]
        if "object_schema" not in obj:
            continue
        key = natural_key(obj)
        batch_fields[key] = obj.get("batch_attribute_name")
        for attr in obj["attributes"]:
            if attr.get("is_active", True):
                columns[(*key, attr["attribute_name"].casefold())] = attr

    links: list[tuple[list[tuple[Any, ...]], dict[str, Any]]] = []
    for row in relationships:
        endpoints = [
            {field: row[f"{side}_{field}"] for field in (*OBJECT_FIELDS, "attribute_name")}
            for side in ("from", "to")
            if all(f"{side}_{field}" in row for field in (*OBJECT_FIELDS, "attribute_name"))
        ]
        if len(endpoints) != 2:
            continue
        keys = [natural_key(endpoint, (*OBJECT_FIELDS, "attribute_name")) for endpoint in endpoints]
        if any(key not in columns for key in keys):
            continue
        for endpoint, key in zip(endpoints, keys, strict=True):
            col = columns[key]
            endpoint.update(
                {
                    name: col[name]
                    for name in ("attribute_data_type", "attribute_description", "is_natural_key")
                    if col.get(name) is not None
                }
            )
            endpoint["batch_attribute_name"] = batch_fields[key[:-1]]
        links.append(
            (
                keys,
                {
                    "from": endpoints[0],
                    "to": endpoints[1],
                    **{
                        name: row[name]
                        for name in (
                            "relationship_kind",
                            "inferred_cardinality",
                            "validation_result",
                            "validation_source_missing_target_count",
                            "validation_duplicate_target_key_count",
                        )
                        if name in row
                    },
                },
            )
        )

    result: list[dict[str, Any]] = []
    for role in roles:
        name = role[f"from_{layer}_attribute_name"]
        field = child_attributes.get(name.casefold())
        if field is None:
            continue
        parent = natural_key(role, parent_fields)
        returned = role[f"to_{layer}_attribute_name"]
        identity = {
            "target_attribute_name": name,
            "parent_schema": role[parent_fields[0]],
            "parent_entity": role[parent_fields[1]],
            "returned_attribute": returned,
        }
        child_sources = field.get("sources", [])
        role_header: dict[str, Any] = {**identity, "parent_key_names": []}
        result.append({"kind": "fk_role", "record": role_header})
        child_columns = {
            natural_key(source["source_attribute"], (*OBJECT_FIELDS, "attribute_name"))
            for source in child_sources
            if source.get("source_attribute")
        }
        parent_columns: set[tuple[Any, ...]] = set()
        for attribute in parent_attributes[parent]:
            key_name = attribute[f"{layer}_attribute_name"]
            is_natural = attribute.get(f"{layer}_attribute_is_natural_key", False)
            if not (is_natural or key_name.casefold() in (returned.casefold(), "sourcesystemid")):
                continue
            lineage = attribute.get("sources", [])
            role_header["parent_key_names"].append(key_name)
            parent_columns.update(
                natural_key(source["source_attribute"], (*OBJECT_FIELDS, "attribute_name"))
                for source in lineage
                if source.get("source_attribute") and is_natural
            )
        # Only follow links on this role's actual operands. A second FK on the
        # same table may use a different bridge to reach the very same parent.
        adjacent = {
            opposite[:-1]
            for (first, second), _ in links
            for operand, opposite in ((first, second), (second, first))
            if operand in child_columns
        } - {key[:-1] for key in child_columns | parent_columns}
        for (first, second), link in links:
            if (
                first in child_columns
                or second in child_columns
                or (first in parent_columns and second[:-1] in adjacent)
                or (second in parent_columns and first[:-1] in adjacent)
            ):
                result.append({"kind": "fk_source_link", "record": {**identity, **link}})
    return result


def select_fk_evidence(
    cards: list[dict[str, Any]], roles: list[dict[str, Any]], *, core: bool
) -> list[dict[str, Any]]:
    """Move existing evidence to the selected FK and return shared parent rules once."""
    if not roles:
        return cards if core else []
    target = next(card["record"] for card in cards if card["kind"] == "target")
    layer = target["entity_type"].removesuffix("_entity")
    fields = (f"{layer}_entity_schema_name", f"{layer}_entity_name")
    names = {role["target_attribute_name"].casefold() for role in roles}
    parent_keys: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    for role in roles:
        parent_keys[natural_key(role, ("parent_schema", "parent_entity"))].update(
            name.casefold() for name in (*role["parent_key_names"], role["returned_attribute"])
        )

    result: list[dict[str, Any]] = []
    for card in cards:
        kind, row = card["kind"], card["record"]
        if kind == "fk_role":
            if core or row["target_attribute_name"].casefold() in names:
                result.append(card)
            continue
        detail = False
        if kind == "field" and row["attribute_name"].casefold() in names:
            # Keep field ordering, type and authoring action on the first page.
            if core:
                result.append(
                    {
                        "kind": kind,
                        "record": {
                            key: value
                            for key, value in row.items()
                            if key not in ("sources", "saved")
                        },
                    }
                )
                continue
            detail = True
        elif kind == "fk_source_link":
            detail = row["target_attribute_name"].casefold() in names
        elif kind == "target_relationship":
            detail = (
                natural_key(row, tuple(f"from_{key}" for key in fields))
                == natural_key(target, ("entity_schema_name", "entity_name"))
                and row[f"from_{layer}_attribute_name"].casefold() in names
            )
        elif kind == f"source_{layer}_entity":
            detail = natural_key(row, fields) in parent_keys
        elif kind == f"source_{layer}_attribute":
            detail = row[f"{layer}_attribute_name"].casefold() in parent_keys.get(
                natural_key(row, fields), ()
            )
        elif (
            kind in ("source_object_mapping", "source_attribute_mapping")
            and row["modeled_entity_type"] == target["entity_type"]
        ):
            parent = natural_key(row, ("modeled_entity_schema_name", "modeled_entity_name"))
            detail = parent in parent_keys and (
                kind == "source_object_mapping"
                or row["modeled_attribute_name"].casefold() in parent_keys[parent]
            )
        if core != detail:
            result.append(card)
    return result
