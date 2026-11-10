"""Exact-coverage SQL-only agent candidate validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Self, cast

from atlas_mcp.domain.errors import InvalidRequestError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlglot import exp, parse
from sqlglot.errors import ErrorLevel, ParseError
from sqlglot.expressions.ddl import DDL, Command, Set, Transaction, Use
from sqlglot.expressions.dml import DML
from sqlglot.expressions.query import Query
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.scope import Scope, traverse_scope

from atlas_platform.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
    pydantic_validation_issues,
)

_UNSAFE_SQL_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class CodeGenerationTargetReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    modeled_entity_id: int = Field(gt=0, repr=False)
    source_system_codes: tuple[str, ...] = Field(min_length=1, max_length=200)

    # Schema/table, registered batch column (null means unbatched). Scoped to this Run.
    batch_sources: tuple[tuple[str, str, str | None], ...] = ()
    lookup_system_codes: tuple[str, ...] | None = None

    file_layout: Literal["combined", "per_system"] | None = "combined"
    preserved_artifact_names: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_source_systems(self) -> Self:
        if self.file_layout is None:
            object.__setattr__(self, "file_layout", "combined")
        normalized = tuple(value.strip().casefold() for value in self.source_system_codes)
        if any(not value for value in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("Target source System Codes must be unique and nonblank")
        return self


class GeneratedSqlArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    modeled_entity_id: int = Field(gt=0)
    artifact_name: str = Field(min_length=1, max_length=400)
    artifact_role: Literal["target_transformation", "support"]
    source_system_codes: tuple[str, ...] = Field(max_length=200)
    generated_sql: str = Field(min_length=1, repr=False)

    @field_validator("artifact_name")
    @classmethod
    def validate_artifact_name(cls, value: str) -> str:
        if value != value.strip() or value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("Artifact name must be a file name, not a path")
        return value

    @field_validator("generated_sql")
    @classmethod
    def validate_sql(cls, value: str) -> str:
        if not _is_valid_sql(value):
            raise ValueError("Generated SQL must be bounded SQL-only text")
        return value


class _AgentSqlArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(
        pattern=r"^[a-z][a-z0-9_]{0,99}$",
        description="Copy the exact opaque target reference from frozen authoring context.",
    )
    artifact_name: str = Field(
        min_length=1,
        max_length=400,
        description="File name only, without a directory path.",
    )
    artifact_role: Literal["target_transformation", "support"] = Field(
        description=(
            "target_transformation returns target rows from assigned source Systems; "
            "support is standalone read-only or temporary-view SQL with no System assignment."
        )
    )
    source_system_codes: list[str] = Field(
        max_length=200,
        description=(
            "Exact frozen source System Codes covered by this transformation artifact. "
            "Use an empty list only for support artifacts."
        ),
    )
    generated_sql: str = Field(
        min_length=1,
        repr=False,
        description=(
            "Complete SQL-only artifact as plain text with no Markdown fences. Separate "
            "multiple statements with semicolons; an earlier temporary view may be used by "
            "later statements in the same file. Never depend on another file's temporary state."
        ),
    )

    @field_validator("artifact_name")
    @classmethod
    def validate_artifact_name(cls, value: str) -> str:
        if value != value.strip() or value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("Artifact name must be a file name, not a path")
        return value


class _AgentSqlBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    issues: list[Literal["missing_requirement_evidence", "conflicting_requirement"]] = Field(
        default=[],
        description=(
            "Report missing_requirement_evidence alongside covered reviewable SQL with typed "
            "NULL placeholders. Conflicting requirements block authoring; return no artifacts "
            "with conflicting_requirement."
        ),
    )
    artifacts: list[_AgentSqlArtifact] = Field(
        min_length=0,
        max_length=50_000,
        description=(
            "Complete artifact ledger assigning each frozen source System exactly once "
            "per target across transformation artifacts; support artifacts assign none."
        ),
    )


class CodeGenerationCandidateValidator:
    """Validate the exact opaque target references selected by the backend."""

    def __init__(self, *, targets: tuple[CodeGenerationTargetReference, ...]) -> None:
        if not targets or len(targets) > 50_000:
            raise ValueError("Code Generation targets must be bounded and nonempty")
        refs = [target.target_ref for target in targets]
        identities = [target.modeled_entity_id for target in targets]
        if len(refs) != len(set(refs)) or len(identities) != len(set(identities)):
            raise ValueError("Code Generation targets must be unique")
        self._targets = targets
        self._by_ref = {target.target_ref: target for target in targets}

    def output_schema(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], _AgentSqlBatch.model_json_schema())

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        batch, issues = _parse_batch(candidate)
        if issues:
            return AgentCandidateValidation(issues=issues)
        if batch is None:
            raise AssertionError("validated SQL batch is missing")
        if "conflicting_requirement" in batch.issues or (batch.issues and not batch.artifacts):
            return AgentCandidateValidation(
                issues=tuple(
                    AgentValidationIssue(
                        code=f"code_generation.{code}",
                        path=("issues",),
                        message=(
                            "A business requirement has missing inputs or conflicts with applied "
                            "Mapping. Resolve the requirement and Mapping before generating SQL."
                        ),
                    )
                    for code in dict.fromkeys(batch.issues)
                    if code == "conflicting_requirement" or not batch.artifacts
                )
            )

        issue = self._coverage_issue(batch)
        if issue is not None:
            return issue
        for index, artifact in enumerate(batch.artifacts):
            if not _is_valid_sql(artifact.generated_sql):
                return AgentCandidateValidation(
                    issues=(
                        AgentValidationIssue(
                            code="candidate.sql_invalid",
                            path=("artifacts", index, "generated_sql"),
                            message="Generated SQL must be bounded SQL-only text.",
                        ),
                    )
                )
            if not _is_generation_sql(
                artifact.generated_sql,
                transformation=artifact.artifact_role == "target_transformation",
                target=self._by_ref[artifact.target_ref],
            ):
                return AgentCandidateValidation(
                    issues=(
                        AgentValidationIssue(
                            code="candidate.transformation_sql_contract"
                            if artifact.artifact_role == "target_transformation"
                            else "candidate.support_sql_contract",
                            path=("artifacts", index, "generated_sql"),
                            message=(
                                "Use only read-only queries and unqualified temporary views. "
                                "Transformations finish with one explicit-column SELECT. "
                                "Filter a batched driver with its registered batch column = "
                                "'wid_gdsbatchid'. Never select the latest source batch. "
                                "Use schema.table and LEFT JOIN meta.system on SystemCode alone. "
                                "Catalog qualifiers and SQL parameter bindings "
                                "are unsupported. "
                                "No persistent DDL, DML, commands, SELECT * or comments."
                            ),
                        ),
                    )
                )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> tuple[GeneratedSqlArtifact, ...]:
        batch, issues = _parse_batch(candidate)
        if issues or batch is None or "conflicting_requirement" in batch.issues:
            raise InvalidRequestError("The Code Generation candidate is invalid.")
        if self._coverage_issue(batch) is not None:
            raise InvalidRequestError("The Code Generation candidate is invalid.")
        artifacts: list[GeneratedSqlArtifact] = []
        for candidate_artifact in batch.artifacts:
            target = self._by_ref[candidate_artifact.target_ref]
            if not _is_generation_sql(
                candidate_artifact.generated_sql,
                transformation=candidate_artifact.artifact_role == "target_transformation",
                target=target,
            ):
                raise InvalidRequestError("The SQL does not follow the artifact delivery contract.")
            try:
                artifacts.append(
                    GeneratedSqlArtifact(
                        target_ref=target.target_ref,
                        modeled_entity_id=target.modeled_entity_id,
                        artifact_name=candidate_artifact.artifact_name,
                        artifact_role=candidate_artifact.artifact_role,
                        source_system_codes=tuple(
                            _canonical_system_codes(
                                candidate_artifact.source_system_codes,
                                target.source_system_codes,
                            )
                        ),
                        generated_sql=candidate_artifact.generated_sql,
                    )
                )
            except ValidationError:
                raise InvalidRequestError("The Code Generation candidate is invalid.") from None
        return tuple(artifacts)

    def warning_codes(self, candidate: JsonValue) -> tuple[str, ...]:
        """Keep review warnings outside SQL and independent of provider disclosure."""
        batch, issues = _parse_batch(candidate)
        if issues or batch is None:
            raise InvalidRequestError("The Code Generation candidate is invalid.")
        warnings: list[str] = []
        if "missing_requirement_evidence" in batch.issues:
            warnings.append("code_generation.missing_requirement_evidence")
        if any(
            isinstance(node.this, exp.Null)
            for artifact in batch.artifacts
            for statement in parse(
                artifact.generated_sql, read="databricks", error_level=ErrorLevel.RAISE
            )
            if statement is not None
            for node in statement.find_all(exp.Cast)
        ):
            warnings.append("code_generation.typed_null_placeholder")
        return tuple(warnings)

    def _coverage_issue(
        self,
        batch: _AgentSqlBatch,
    ) -> AgentCandidateValidation | None:
        artifacts_by_target: dict[str, list[_AgentSqlArtifact]] = {}
        for artifact in batch.artifacts:
            if artifact.target_ref not in self._by_ref:
                return _validation(
                    "candidate.target_coverage",
                    "Artifacts may reference only frozen targets.",
                )
            artifacts_by_target.setdefault(artifact.target_ref, []).append(artifact)
        if set(artifacts_by_target) != set(self._by_ref):
            return _validation(
                "candidate.target_coverage",
                "The candidate must cover every selected target.",
            )

        for target_ref, artifacts in artifacts_by_target.items():
            target = self._by_ref[target_ref]
            names = tuple(item.artifact_name.strip().casefold() for item in artifacts)
            if len(names) != len(set(names)):
                return _validation(
                    "candidate.artifact_name_duplicate",
                    "Artifact names must be unique within each target.",
                )
            if set(names) & {name.strip().casefold() for name in target.preserved_artifact_names}:
                return _validation(
                    "candidate.preserved_artifact",
                    "Do not overwrite SQL files outside the selected scope.",
                )
            transformations = [
                item for item in artifacts if item.artifact_role == "target_transformation"
            ]
            if (target.file_layout == "combined" and len(transformations) != 1) or (
                target.file_layout == "per_system"
                and any(len(item.source_system_codes) != 1 for item in transformations)
            ):
                return _validation(
                    "candidate.file_layout",
                    "Follow the requested combined or per-System file layout exactly.",
                )
            assigned: list[str] = []
            transformation_count = 0
            for artifact in artifacts:
                codes = [value.strip().casefold() for value in artifact.source_system_codes]
                if any(not value for value in codes) or len(codes) != len(set(codes)):
                    return _validation(
                        "candidate.source_system_coverage",
                        "Artifact source System Codes must be unique and nonblank.",
                    )
                if artifact.artifact_role == "support":
                    if codes:
                        return _validation(
                            "candidate.support_system_assignment",
                            "Support artifacts cannot own source System assignments.",
                        )
                    continue
                transformation_count += 1
                if not codes:
                    return _validation(
                        "candidate.source_system_coverage",
                        "Transformation artifacts require source System assignments.",
                    )
                assigned.extend(codes)
            expected = {value.strip().casefold() for value in target.source_system_codes}
            if (
                transformation_count == 0
                or len(assigned) != len(set(assigned))
                or set(assigned) != expected
            ):
                return _validation(
                    "candidate.source_system_coverage",
                    "Transformation artifacts must assign every frozen source System exactly once.",
                )
        return None


def _parse_batch(
    candidate: JsonValue,
) -> tuple[_AgentSqlBatch | None, tuple[AgentValidationIssue, ...]]:
    try:
        return _AgentSqlBatch.model_validate(candidate, strict=True), ()
    except ValidationError as error:
        return None, pydantic_validation_issues(error)


def _validation(code: str, message: str) -> AgentCandidateValidation:
    return AgentCandidateValidation(
        issues=(AgentValidationIssue(code=code, path=("artifacts",), message=message),)
    )


def _canonical_system_codes(
    candidate_codes: list[str],
    frozen_codes: tuple[str, ...],
) -> tuple[str, ...]:
    canonical = {value.strip().casefold(): value for value in frozen_codes}
    try:
        return tuple(canonical[value.strip().casefold()] for value in candidate_codes)
    except KeyError:
        raise InvalidRequestError("The Code Generation candidate is invalid.") from None


def _is_valid_sql(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "```" in value
        or _UNSAFE_SQL_CONTROL.search(value) is not None
    ):
        return False
    try:
        statements = parse(
            value,
            read="databricks",
            error_level=ErrorLevel.RAISE,
        )
    except ParseError:
        return False
    executable_statement_types = (
        Query,
        DDL,
        DML,
        Command,
        Use,
        Set,
        Transaction,
    )
    return bool(statements) and all(
        isinstance(statement, executable_statement_types) for statement in statements
    )


def _is_generation_sql(
    value: str, *, transformation: bool, target: CodeGenerationTargetReference
) -> bool:
    try:
        statements = parse(value, read="databricks", error_level=ErrorLevel.RAISE)
    except ParseError:
        return False
    if not statements or (transformation and not isinstance(statements[-1], Query)):
        return False
    for index, statement in enumerate(statements):
        if isinstance(statement, Query):
            if transformation and index != len(statements) - 1:
                return False
            continue
        if not isinstance(statement, exp.Create) or statement.kind != "VIEW":
            return False
        properties = statement.args.get("properties")
        if not isinstance(properties, exp.Properties) or not any(
            isinstance(item, exp.TemporaryProperty) for item in properties.expressions
        ):
            return False
        view_name = statement.this
        if (
            not isinstance(view_name, exp.Table)
            or view_name.db
            or view_name.catalog
            or not isinstance(statement.expression, Query)
        ):
            return False
    for statement in statements:
        assert statement is not None
        relations = tuple(statement.find_all(exp.Table))
        if not _valid_runtime_references(
            statement,
            target,
            final_projection=transformation and statement is statements[-1],
        ):
            return False
        if any(relation.catalog for relation in relations):
            return False
        relation_keys = {
            (relation.db.casefold(), relation.name.casefold()) for relation in relations
        }
        aliases = {relation.alias_or_name.casefold() for relation in relations}
        if any(
            column.catalog
            and column.catalog.casefold() not in aliases
            and (column.db.casefold(), column.table.casefold()) in relation_keys
            for column in statement.find_all(exp.Column)
        ):
            # SQLGlot also parses deep struct paths as four-part Columns. Only
            # reject a catalog-qualified relation column, not alias.struct.a.b.
            return False
    if any(
        node.comments or isinstance(node, (exp.Placeholder, exp.Parameter))
        for statement in statements
        if statement is not None
        for node in statement.walk()
    ):
        return False
    if not _valid_batch_queries(statements, value, target, transformation=transformation):
        return False
    return not any(
        isinstance(column, exp.Star) or isinstance(column, exp.Column) and column.is_star
        for statement in statements
        if statement is not None
        for select in statement.find_all(exp.Select)
        for column in select.expressions
    )


def _valid_runtime_references(
    statement: exp.Expr, target: CodeGenerationTargetReference, *, final_projection: bool
) -> bool:
    """Check registry joins and literal provenance."""
    for table in statement.find_all(exp.Table):
        if (table.db.casefold(), table.name.casefold()) != ("meta", "system"):
            continue
        join = table.parent
        if not isinstance(join, exp.Join) or join.side != "LEFT":
            return False
        match = join.args.get("on")
        if isinstance(match, exp.Paren):
            match = match.unnest()
        if not isinstance(match, exp.EQ):
            return False
        column, code = match.this.unnest(), match.expression.unnest()
        if isinstance(column, exp.Literal):
            column, code = code, column
        if (
            not isinstance(column, exp.Column)
            or column.table.casefold() != table.alias_or_name.casefold()
            or column.name.casefold() != "systemcode"
            or not isinstance(code, exp.Literal)
            or not code.is_string
            or (
                target.lookup_system_codes is not None
                and code.this not in (*target.source_system_codes, *target.lookup_system_codes)
            )
        ):
            return False

    # Reject direct numeric provenance, including quoted IDs and casts. Constants in
    # unrelated business fields and comparisons between two provenance columns are valid.
    def numeric_id(value: exp.Expr) -> bool:
        while isinstance(value, (exp.Paren, exp.Cast, exp.Neg)):
            value = value.this
        if isinstance(value, exp.Coalesce):
            return any(numeric_id(option) for option in (value.this, *value.expressions))
        return isinstance(value, exp.Literal) and (
            not value.is_string or re.fullmatch(r"[+-]?[0-9]+", value.this.strip()) is not None
        )

    for select in statement.find_all(exp.Select):
        base_tables = {
            table.alias_or_name.casefold(): table
            for table in select.find_all(exp.Table)
            if table.db and table.find_ancestor(exp.Select) is select
        }
        for output in select.selects:
            if output.alias_or_name.casefold() != "sourcesystemid":
                continue
            value = output.this if isinstance(output, exp.Alias) else output
            if numeric_id(value):
                return False
            # Within helper views/CTEs a parent's existing provenance may be
            # carried into a later match. Only a direct final assignment is definitive.
            if not final_projection or select.find_ancestor(exp.CTE, exp.Subquery):
                continue
            while isinstance(value, (exp.Cast, exp.Paren)):
                value = value.this
            if (
                isinstance(value, exp.Column)
                and (source := base_tables.get(value.table.casefold()))
                and (source.db.casefold(), source.name.casefold(), value.name.casefold())
                != ("meta", "system", "systemid")
            ):
                return False
    for predicate in statement.find_all(exp.Predicate):
        if isinstance(predicate, exp.Binary):
            pairs = ((predicate.this, predicate.expression), (predicate.expression, predicate.this))
        elif isinstance(predicate, exp.In):
            pairs = tuple((predicate.this, value) for value in predicate.expressions)
        else:
            continue
        for operand, value in pairs:
            while isinstance(operand, (exp.Cast, exp.Paren)):
                operand = operand.this
            if (
                isinstance(operand, exp.Column)
                and operand.name.casefold() == "sourcesystemid"
                and numeric_id(value)
            ):
                return False

    return True


@dataclass(frozen=True)
class _BatchRowset:
    # A direct projection of a registered batch column keeps its lineage across query stages.
    batch_columns: frozenset[str] = frozenset()
    driver_columns: frozenset[str] = frozenset()
    needs_filter: bool = False
    unknown_registration: bool = False
    latest_columns: frozenset[str] = frozenset()


def _batch_operand(value: exp.Expr) -> exp.Expr:
    while isinstance(value, (exp.Cast, exp.Paren)):
        value = value.this
    return value


def _valid_batch_queries(
    statements: list[exp.Expr | None],
    sql: str,
    target: CodeGenerationTargetReference,
    *,
    transformation: bool,
) -> bool:
    registered: dict[tuple[str, str], set[str]] = {}
    for schema, table, column in target.batch_sources:
        names = registered.setdefault((schema.casefold(), table.casefold()), set())
        if column:
            names.add(column.casefold())

    physical = {
        key: _BatchRowset(frozenset(columns), frozenset(columns), bool(columns))
        for key, columns in registered.items()
    }
    views: dict[str, _BatchRowset] = {}
    for statement in statements:
        assert statement is not None
        token_comparisons: dict[int, exp.Column] = {}
        for token in statement.find_all(exp.Literal):
            if not token.is_string or token.this.casefold() != "wid_gdsbatchid":
                continue
            if sql[token.meta["start"] : token.meta["end"] + 1] != "'wid_gdsbatchid'":
                return False
            operand: exp.Expr = token
            while isinstance(operand.parent, (exp.Cast, exp.Paren)):
                operand = operand.parent
            equality = operand.parent
            if not isinstance(equality, exp.EQ):
                return False
            other = equality.this if operand is equality.expression else equality.expression
            column = _batch_operand(other)
            if not isinstance(column, exp.Column):
                return False
            token_comparisons[id(equality)] = column
        if any(c.name.casefold() == "wid_gdsbatchid" for c in statement.find_all(exp.Column)):
            return False
        if not registered:
            continue  # Older snapshots do not declare which physical sources are batched.

        query = statement.expression if isinstance(statement, exp.Create) else statement
        result = _query_batch_rowset(query, physical, views, token_comparisons)
        if result is None:
            return False
        if isinstance(statement, exp.Create):
            views[statement.this.name.casefold()] = result
        elif transformation and result.needs_filter:
            return False
    return True


def _query_batch_rowset(
    query: exp.Expr,
    physical: dict[tuple[str, str], _BatchRowset],
    views: dict[str, _BatchRowset],
    token_comparisons: dict[int, exp.Column],
) -> _BatchRowset | None:
    """Trace the driving FROM and registered batch columns through each SELECT."""
    unknown = _BatchRowset(unknown_registration=True)
    # Databricks resolves table aliases and CTE names without regard to case.
    scopes = traverse_scope(normalize_identifiers(query.unnest(), dialect="databricks"))
    outputs: dict[Scope, _BatchRowset] = {}
    # references includes the right side of SEMI/ANTI joins; their ON
    # conditions can also compare a batch to a derived maximum.
    sources = {
        scope: {name: scope.sources[name] for name, _ in scope.references if name in scope.sources}
        for scope in scopes
    }

    def rowset(source: exp.Table | Scope | None) -> _BatchRowset:
        if isinstance(source, Scope):
            return outputs.get(source, unknown)
        if isinstance(source, exp.Table):
            if source.db:
                return physical.get((source.db.casefold(), source.name.casefold()), unknown)
            return views.get(source.name.casefold(), unknown)
        return unknown

    def column_sources(scope: Scope, column: exp.Column) -> list[tuple[str, _BatchRowset]]:
        current: Scope | None = scope
        while current is not None:
            inputs = sources[current]
            if column.table in inputs:
                return [(column.table, rowset(inputs[column.table]))]
            if not column.table and inputs:
                return [(alias, rowset(source)) for alias, source in inputs.items()]
            if not current.can_be_correlated:
                break
            current = current.parent
        return []

    def output_names(scope: Scope) -> list[str]:
        # SQLGlot carries a CTE's explicit column list into each UNION branch.
        projections = cast(exp.Selectable, scope.expression).selects
        return [
            scope.outer_columns[pos] if pos < len(scope.outer_columns) else output.alias_or_name
            for pos, output in enumerate(projections)
        ]

    for scope in scopes:
        select = scope.expression
        if isinstance(select, exp.SetOperation):
            # UNION matches columns by position, including renamed CTE outputs.
            branches = [(output_names(branch), outputs[branch]) for branch in scope.union_scopes]
            batch_names: set[str] = set()
            driver_names: set[str] = set()
            latest_names: set[str] = set()
            for pos, name in enumerate(output_names(scope)):
                if any(pos >= len(names) for names, _ in branches):
                    return None
                if any(names[pos] in flow.batch_columns for names, flow in branches):
                    batch_names.add(name)
                if any(names[pos] in flow.latest_columns for names, flow in branches):
                    latest_names.add(name)
                if all(names[pos] in flow.driver_columns for names, flow in branches):
                    driver_names.add(name)
            outputs[scope] = _BatchRowset(
                frozenset(batch_names),
                frozenset(driver_names),
                any(flow.needs_filter for _, flow in branches),
                any(flow.unknown_registration for _, flow in branches),
                frozenset(latest_names),
            )
            continue
        if not isinstance(select, exp.Select):
            outputs[scope] = unknown
            continue

        driver = select.args.get("from_")
        alias = driver.this.alias_or_name if isinstance(driver, exp.From) else ""
        driver_flow = rowset(sources[scope].get(alias))
        needs_filter = driver_flow.needs_filter
        batch_names = set()
        driver_names = set()
        projections = {
            id(output): name
            for output, name in zip(select.selects, output_names(scope), strict=True)
        }
        for output in select.selects:
            column = _batch_operand(output.unalias())
            if not isinstance(column, exp.Column):
                continue
            name = projections[id(output)]
            for source_alias, flow in column_sources(scope, column):
                if column.name in flow.batch_columns:
                    batch_names.add(name)
                if source_alias == alias and column.name in flow.driver_columns:
                    driver_names.add(name)

        predicates: list[exp.Expr] = []
        where = select.args.get("where")
        if isinstance(where, exp.Where):
            predicates.append(where.this)
        for join in scope.find_all(exp.Join):
            on = join.args.get("on")
            if not join.side and join.kind in {"", "INNER"} and isinstance(on, exp.Expr):
                predicates.append(on)
        mandatory: set[int] = set()
        while predicates:
            term = predicates.pop().unnest()
            if isinstance(term, exp.And):
                predicates.extend((term.this, term.expression))
            else:
                if isinstance(term, exp.Boolean) and not term.this:
                    needs_filter = False  # The documented zero-row placeholder.
                mandatory.add(id(term))

        for equality in scope.find_all(exp.EQ):
            compared = token_comparisons.get(id(equality))
            runtime_token = compared is not None
            if compared is None:
                if id(equality) not in mandatory:
                    continue
                column, literal = _batch_operand(equality.this), _batch_operand(equality.expression)
                if isinstance(literal, exp.Column):
                    column, literal = literal, column
                if isinstance(literal, exp.Neg):
                    literal = literal.this
                if not isinstance(column, exp.Column) or not isinstance(literal, exp.Literal):
                    continue
                compared = column
            bindings = column_sources(scope, compared)
            if (
                runtime_token
                and bindings
                and not any(
                    compared.name in flow.batch_columns or flow.unknown_registration
                    for _, flow in bindings
                )
            ):
                return None
            if id(equality) in mandatory and any(
                source_alias == alias and compared.name in flow.driver_columns
                for source_alias, flow in bindings
            ):
                if not runtime_token:
                    return None  # A fixed second batch would exclude other requested runs.
                needs_filter = False

        # Track a batch maximum or rank as an ordinary projected value until
        # it is used to select rows. A diagnostic MAX in the output is valid.
        latest_values: list[exp.Expr] = [
            child.expression for child in scope.subquery_scopes if outputs[child].latest_columns
        ]
        for column in scope.find_all(exp.Column):
            if any(column.name in flow.latest_columns for _, flow in column_sources(scope, column)):
                latest_values.append(column)

        selectors: list[tuple[exp.Expr, exp.Expr]] = [
            (node.this, node) for node in scope.find_all(exp.Max, exp.Min)
        ]
        for window in scope.find_all(exp.Window):
            if isinstance(window.this, (exp.Rank, exp.DenseRank, exp.RowNumber)) and (
                order := window.args.get("order")
            ):
                selectors.extend((item.this, window) for item in order.expressions)
        if select.args.get("limit") and (order := select.args.get("order")):
            selectors.append((order.expressions[0].this, order))
        for operand, marker in selectors:
            # DISTINCT and scalar expressions such as COALESCE may wrap the
            # value being maximized. Nested queries resolve their own columns.
            for node in operand.walk(prune=lambda n: isinstance(n, (exp.Query, exp.Predicate))):
                if isinstance(node, exp.Column) and (
                    any(node.name in flow.batch_columns for _, flow in column_sources(scope, node))
                    or (
                        not node.table
                        and node.name in batch_names
                        and isinstance(operand.parent, exp.Ordered)
                    )
                ):
                    latest_values.append(marker)
                    break

        latest_names = set()
        for value in latest_values:
            cursor: exp.Expr | None = value
            while cursor is not None and cursor is not select:
                if id(cursor) in projections:
                    latest_names.add(projections[id(cursor)])
                    break
                if isinstance(cursor, (exp.Where, exp.Having, exp.Qualify, exp.Join)) or (
                    isinstance(cursor, exp.Order) and select.args.get("limit")
                ):
                    return None
                cursor = cursor.parent
        # Databricks also permits HAVING, QUALIFY and ORDER BY to reference
        # an aggregate or window output by its alias in the same SELECT.
        for clause in ("having", "qualify", "order"):
            condition = select.args.get(clause)
            if (
                isinstance(condition, exp.Expr)
                and (clause != "order" or select.args.get("limit"))
                and any(
                    not col.table and col.name in latest_names
                    for col in condition.find_all(exp.Column)
                )
            ):
                return None

        outputs[scope] = _BatchRowset(
            frozenset(batch_names),
            frozenset(driver_names),
            needs_filter,
            any(rowset(source).unknown_registration for source in sources[scope].values()),
            frozenset(latest_names),
        )
    return outputs[scopes[-1]] if scopes else unknown
