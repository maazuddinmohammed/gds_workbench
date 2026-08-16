"""Syntactic safety policy for submitted Databricks SQL."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import sqlglot
from sqlglot import Token, TokenType
from sqlglot import expressions as exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.expressions.core import Expression
from sqlglot.expressions.ddl import DDL
from sqlglot.expressions.dml import DML

from gds_etl_workbench.domain.errors import InvalidRequestError

# SQLGlot warnings include source SQL. Submitted SQL must never enter application logs.
_sqlglot_logger = logging.getLogger("sqlglot")
_sqlglot_logger.handlers.clear()
_sqlglot_logger.setLevel(logging.CRITICAL + 1)
_sqlglot_logger.propagate = False
_sqlglot_logger.disabled = True

_MAX_STATEMENTS = 25
_SECRET_FUNCTIONS = frozenset({"secret", "try_secret"})


class DatabricksStatementKind(StrEnum):
    READ = "read"
    TEMPORARY_DDL = "temporary_ddl"


@dataclass(frozen=True, slots=True)
class ValidatedDatabricksStatement:
    sql: str
    kind: DatabricksStatementKind


@dataclass(frozen=True, slots=True)
class ValidatedDatabricksSql:
    statements: tuple[ValidatedDatabricksStatement, ...]

    @property
    def final_returns_rows(self) -> bool:
        return self.statements[-1].kind is DatabricksStatementKind.READ


def validate_databricks_sql(sql: str) -> ValidatedDatabricksSql:
    """Split and validate one submitted Databricks SQL batch without rewriting it."""
    try:
        tokens = sqlglot.tokenize(sql, dialect="databricks")
    except TokenError as exc:
        raise InvalidRequestError("The Databricks SQL syntax is invalid.") from exc

    statements: list[str] = []
    statement_start = 0
    statement_has_tokens = False
    for token in tokens:
        if token.token_type is TokenType.SEMICOLON:
            if statement_has_tokens:
                statements.append(sql[statement_start : token.start].strip())
            statement_start = token.end + 1
            statement_has_tokens = False
        else:
            statement_has_tokens = True
    if statement_has_tokens:
        statements.append(sql[statement_start:].strip())

    if not statements:
        raise InvalidRequestError("Provide at least one SQL statement.")
    if len(statements) > _MAX_STATEMENTS:
        raise InvalidRequestError("Provide at most 25 SQL statements.")

    validated: list[ValidatedDatabricksStatement] = []
    for index, statement_sql in enumerate(statements, start=1):
        statement_tokens = _tokenize_statement(statement_sql, index)
        if statement_tokens[0].token_type is TokenType.SHOW:
            validated.append(
                ValidatedDatabricksStatement(
                    sql=statement_sql,
                    kind=DatabricksStatementKind.READ,
                )
            )
            continue
        if statement_tokens[0].token_type is TokenType.COMMAND:
            _raise_not_allowed(index)

        try:
            expression = sqlglot.parse_one(
                statement_sql,
                read="databricks",
                error_level=sqlglot.ErrorLevel.RAISE,
            )
        except ParseError as exc:
            line = exc.errors[0].get("line", 1) if exc.errors else 1
            column = exc.errors[0].get("col", 1) if exc.errors else 1
            raise InvalidRequestError(
                f"Statement {index} has invalid Databricks SQL syntax near "
                f"line {line}, column {column}."
            ) from exc

        if isinstance(expression, (exp.Query, exp.Values, exp.Subquery, exp.Describe)):
            if any(
                isinstance(node, (DDL, DML, exp.Into))
                or (
                    isinstance(node, exp.Anonymous)
                    and node.name.casefold() in _SECRET_FUNCTIONS
                )
                for node in expression.walk()
            ):
                _raise_not_allowed(index)
            validated.append(
                ValidatedDatabricksStatement(
                    sql=statement_sql,
                    kind=DatabricksStatementKind.READ,
                )
            )
            continue

        if not isinstance(expression, exp.Create):
            _raise_not_allowed(index)

        kind = expression.args.get("kind")
        properties = expression.args.get("properties")
        property_expressions = (
            cast(list[Expression], properties.expressions)
            if isinstance(properties, exp.Properties)
            else []
        )
        if (
            kind not in {"TABLE", "VIEW"}
            or not property_expressions
            or not all(
                isinstance(item, exp.TemporaryProperty)
                for item in property_expressions
            )
        ):
            _raise_not_allowed(index)

        target = expression.this
        if isinstance(target, exp.Schema):
            target = target.this
        if (
            not isinstance(target, exp.Table)
            or target.args.get("db")
            or target.args.get("catalog")
        ):
            raise InvalidRequestError(
                f"Statement {index} must use an unqualified temporary object name."
            )

        query = expression.args.get("expression")
        if kind == "VIEW" and not isinstance(
            query,
            (exp.Query, exp.Values, exp.Subquery),
        ):
            raise InvalidRequestError(
                f"Statement {index} must define the temporary view with a read query."
            )
        if query is not None and not isinstance(
            query,
            (exp.Query, exp.Values, exp.Subquery),
        ):
            _raise_not_allowed(index)
        if expression.args.get("clone") is not None or any(
            isinstance(node, (DDL, DML, exp.Into))
            or (
                isinstance(node, exp.Anonymous)
                and node.name.casefold() in _SECRET_FUNCTIONS
            )
            for node in expression.walk()
            if node is not expression
        ):
            _raise_not_allowed(index)

        validated.append(
            ValidatedDatabricksStatement(
                sql=statement_sql,
                kind=DatabricksStatementKind.TEMPORARY_DDL,
            )
        )

    return ValidatedDatabricksSql(statements=tuple(validated))


def _tokenize_statement(statement_sql: str, index: int) -> list[Token]:
    try:
        tokens = sqlglot.tokenize(statement_sql, dialect="databricks")
    except TokenError as exc:
        raise InvalidRequestError(
            f"Statement {index} has invalid Databricks SQL syntax."
        ) from exc
    if not tokens:
        raise InvalidRequestError(
            f"Statement {index} has invalid Databricks SQL syntax."
        )
    return tokens


def _raise_not_allowed(index: int) -> None:
    raise InvalidRequestError(
        f"Statement {index} is not allowed. Use read SQL or "
        "CREATE [OR REPLACE] TEMP VIEW/TABLE."
    )
