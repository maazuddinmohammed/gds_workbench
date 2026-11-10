"""Validate explicit batch selectors in the standard Object's SQL-like row instructions."""

import re
from collections import defaultdict

from atlas_mcp.domain.errors import InvalidRequestError
from pydantic import JsonValue
from sqlglot import exp, parse_one
from sqlglot.errors import SqlglotError

from .preparation_contracts import MappingPhysicalObject, MappingPreparation

_TOKEN = "'wid_gdsbatchid'"
_IDENT = r"(?:`(?:``|[^`])+`|[^\W\d]\w*)"
_COLUMN = rf"(?:(?P<owner>{_IDENT})\s*\.\s*)?(?P<column>{_IDENT})"
_CLAUSE = (
    r"left|right|inner|outer|full|cross|semi|anti|join|on|where|and|group|having|order|"
    r"qualify|limit|union|lateral"
)
_RELATION = re.compile(
    rf"\b(?:FROM|JOIN|READ)\s+(?P<schema>{_IDENT})\s*\.\s*(?P<table>{_IDENT})(?![.\w])"
    rf"(?:\s+(?:AS\s+)?(?!(?:{_CLAUSE})\b)(?P<alias>{_IDENT}))?",
    re.I,
)
_EQUALITY = (
    re.compile(rf"(?<![.\w]){_COLUMN}\s*=\s*{_TOKEN}(?!\s*[-+*/])", re.I),
    re.compile(rf"{_TOKEN}\s*=\s*{_COLUMN}(?!\w|\.[\w`]|\s*[-+*/])", re.I),
)
_RANK = (
    rf"\b(?:ROW_NUMBER|DENSE_RANK|RANK)\s*\(\s*\)\s+OVER\s*\([^()]*?"
    rf"\bORDER\s+BY\s+{_COLUMN}\s+(?:DESC|ASC)\s*\)"
)
_NAMED_RANK = re.compile(rf"{_RANK}\s+AS\s+(?P<rank>{_IDENT})", re.I)
_FIRST_ROW = re.compile(rf"(?<!\w){_COLUMN}\s*(?:=|<=)\s*1\b", re.I)
_EXTREME = r"\b(?:MAX|MIN)\s*\(\s*(?:DISTINCT\s+)?"
_REDUCTIONS = (
    re.compile(rf"{_EXTREME}{_COLUMN}\s*\)", re.I),
    re.compile(rf"{_EXTREME}COALESCE\s*\(\s*{_COLUMN}\s*,\s*(?:[-+]?\d+|NULL|'')\s*\)\s*\)", re.I),
    re.compile(rf"\bORDER\s+BY\s+{_COLUMN}\s+(?:DESC|ASC)\s+LIMIT\s+1\b", re.I),
    re.compile(rf"{_RANK}\s*(?:=|<=)\s*1\b", re.I),
    _NAMED_RANK,
    re.compile(rf"(?<![.\w]){_COLUMN}\s*=\s*(?:[-+]?\d+\b|'')", re.I),
    re.compile(rf"(?:\b\d+|'')\s*=\s*{_COLUMN}(?!\w|\.[\w`])", re.I),
)
_TOP_ONE = re.compile(r"\bSELECT\s+TOP\s+(?:1\b|\(\s*1\s*\))", re.I)
_BATCH_ORDER = re.compile(rf"\bORDER\s+BY\s+{_COLUMN}\s+(?:DESC|ASC)\b", re.I)

# These fields mix SQL, headings and prose. Keep parenthesized SELECTs in their own
# scope so a lookup reusing the driver's alias cannot establish its batch predicate.
_FRAGMENT = re.compile(
    r"--[^\n]*|/\*.*?(?:\*/|$)|(?<!\w)'(?:''|[^'\n])*'|\"(?:\"\"|[^\"\n])*\"|`(?:``|[^`])*`"
    r"|\bwid_gdsbatchid\b|(?P<subquery>\(\s*(?=(?:SELECT|WITH)\b))|[()]",
    re.I | re.S,
)


def _sql_scopes(text: str) -> list[str]:
    parts: list[list[str]] = [[]]
    scope: list[str] = parts[0]
    parents: list[list[str]] = []
    start = 0
    for match in _FRAGMENT.finditer(text):
        scope.append(text[start : match.start()])
        token = match.group()
        if token.strip("'\"`").casefold() == "wid_gdsbatchid" and token != _TOKEN:
            raise InvalidRequestError(
                "Use the exact single-quoted orchestration token 'wid_gdsbatchid' "
                "in the Object batch equality. Remove any latest-batch selection."
            )
        if token.startswith("("):
            parents.append(scope)
            if match["subquery"]:
                scope.append(" (subquery) ")
                scope = []
                parts.append(scope)
            else:
                scope.append(token)
        elif token == ")" and parents:
            previous = parents.pop()
            if previous is scope:
                scope.append(token)
            scope = previous
        elif token.startswith(("--", "/*")):
            scope.append(" ")
        elif token.startswith(("'", '"')) and token != _TOKEN:
            scope.append("''")
        else:
            scope.append(token)
        start = match.end()
    scope.append(text[start:])
    return ["".join(part) for part in parts]


def _name(value: str) -> str:
    return value.strip("`").replace("``", "`").casefold()


def _requires_batch(
    filters: str, alias: str, column_name: str, sole_alias: str | None
) -> bool | None:
    """For a SQL predicate, require the equality on every possible OR branch."""
    if _TOKEN not in filters:
        return None
    predicate = re.sub(rf"^\s*(?:Apply\s+to\s+{_IDENT}\s*:|WHERE\b)", "", filters, flags=re.I)
    try:
        condition = parse_one(
            predicate.strip().removesuffix("."), read="databricks", into=exp.Condition
        )
    except SqlglotError, RecursionError:
        return None  # The field may also contain explanatory prose.
    required: set[int] = set()
    for node in reversed(list(condition.walk())):
        if isinstance(node, exp.EQ):
            column, value = node.this.unnest(), node.expression.unnest()
            if isinstance(column, exp.Literal):
                column, value = value, column
            if (
                isinstance(column, exp.Column)
                and (column.table.casefold() or sole_alias) == alias
                and column.name.casefold() == column_name
                and isinstance(value, exp.Literal)
                and value.is_string
                and value.this == "wid_gdsbatchid"
            ):
                required.add(id(node))
        elif isinstance(node, (exp.Paren, exp.And, exp.Or)):
            left = id(node.this) in required
            right = id(node.expression) in required
            if (
                (isinstance(node, exp.Paren) and left)
                or (isinstance(node, exp.And) and (left or right))
                or (isinstance(node, exp.Or) and left and right)
            ):
                required.add(id(node))
    return id(condition) in required


def validate_object_batch_rules(
    preparation: MappingPreparation, document: dict[str, JsonValue]
) -> None:
    batch_columns: dict[tuple[str, str], set[str | None]] = defaultdict(set)
    for source in preparation.context.sources:
        table = source.object
        if isinstance(table, MappingPhysicalObject) and table.zone_code in {"source", "bronze"}:
            batch = table.batch_attribute_name
            batch_columns[table.object_schema.casefold(), table.object_name.casefold()].add(
                batch.strip().casefold() if batch else None
            )

    query, criteria = document.get("sample_query"), document.get("filter_criteria")
    plan, *plan_subqueries = _sql_scopes(query if isinstance(query, str) else "")
    filters, *filter_subqueries = _sql_scopes(criteria if isinstance(criteria, str) else "")
    # Row filters can name the aliases declared in the join plan. Scalar subqueries
    # bind their own sources. An unknown or ambiguous relation cannot prove a batch column.
    scopes = [plan + ";\n" + filters, *plan_subqueries, *filter_subqueries]
    first_row_columns = {
        _name(match["column"]) for sql in scopes for match in _FIRST_ROW.finditer(sql)
    }
    for index, sql in enumerate(scopes):
        aliases: dict[str, set[str | None]] = defaultdict(set)
        unknown_aliases: set[str] = set()
        for relation in _RELATION.finditer(sql):
            schema, table_name = _name(relation["schema"]), _name(relation["table"])
            alias = _name(relation["alias"] or table_name)
            if (schema, table_name) in batch_columns:
                aliases[alias].update(batch_columns[schema, table_name])
            else:
                unknown_aliases.add(alias)

        sole_alias = next(iter(aliases)) if len(aliases) == 1 and not unknown_aliases else None
        patterns = (*_REDUCTIONS, _BATCH_ORDER) if _TOP_ONE.search(sql) else _REDUCTIONS
        for pattern in patterns:
            for selector in pattern.finditer(sql):
                if pattern is _NAMED_RANK and _name(selector["rank"]) not in first_row_columns:
                    continue
                owner = _name(selector["owner"]) if selector["owner"] else sole_alias
                if owner and aliases.get(owner) == {_name(selector["column"])}:
                    raise InvalidRequestError(
                        "Remove the fixed batch or batch reduction from the Object rule. "
                        "Filter the registered driver batch column to 'wid_gdsbatchid'. "
                        "Keep same-load inputs aligned on their batch columns."
                    )

        batch_filtered: set[str] = set()
        plan_filtered: set[str] = set()
        for pattern in _EQUALITY:
            for eq in pattern.finditer(sql):
                alias = _name(eq["owner"]) if eq["owner"] else sole_alias
                if alias is None:
                    continue
                if alias in aliases and _name(eq["column"]) not in aliases[alias]:
                    raise InvalidRequestError(
                        "Use 'wid_gdsbatchid' only with that input's registered batch column. "
                        "Remove the batch predicate for an input without a registered batch column."
                    )
                batch_filtered.add(alias)
                if not index and eq.start() < len(plan):
                    plan_filtered.add(alias)

        # For a FROM plan or a simple legacy SELECT, the first relation names the
        # driver. A CTE or a derived driving relation may rename its inputs.
        if index or not re.match(r"\s*(?:SELECT|FROM)\b", plan, re.I):
            continue
        first_from = re.search(rf"\bFROM\s+(?P<input>{_IDENT})", plan, re.I)
        if first_from is None:
            continue
        driver = _RELATION.match(plan, first_from.start())
        if driver is None:
            # The standard plan can drive FROM a named step. Follow its definition
            # only when that same step explicitly starts by reading one physical table.
            steps = [
                step
                for step in re.finditer(rf"^\s*(?P<step>{_IDENT})\s*:\s*", plan, re.M)
                if _name(step["step"]) == _name(first_from["input"])
            ]
            if len(steps) == 1 and re.match(r"READ\b", plan[steps[0].end() :], re.I):
                driver = _RELATION.match(plan, steps[0].end())
        if driver is None:
            continue
        table_name = _name(driver["table"])
        alias = _name(driver["alias"] or table_name)
        registration = batch_columns.get((_name(driver["schema"]), table_name), set())
        if len(registration) != 1 or alias in plan_filtered:
            continue
        column_name = next(iter(registration))
        if column_name is None:
            continue
        required = _requires_batch(filters, alias, column_name, sole_alias)
        if required is False or (required is None and alias not in batch_filtered):
            raise InvalidRequestError(
                "In filter_criteria, compare the driver's registered batch column "
                "directly to the exact single-quoted token 'wid_gdsbatchid'."
            )
