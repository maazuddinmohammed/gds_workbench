from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID

import pytest
from openpyxl import Workbook

import loader


class _YamlModule(Protocol):
    def safe_dump(self, data: object, *, sort_keys: bool) -> str: ...


yaml = cast(_YamlModule, importlib.import_module("yaml"))

OPAQUE_DSN = "test-connection-input"
VALID_CONNECTION_PARTS = {
    "host": "test-host",
    "dbname": "test-database",
    "user": "test-loader",
    "sslmode": "verify-full",
}
LOCK_ACTOR = loader.LockActor(
    principal_id=7,
    entra_tenant_id=UUID(int=1),
    entra_object_id=UUID(int=2),
    principal_type="user",
)


def _definition(
    *,
    table: str = "environment",
    sheet: str = "Environment",
    order: int = 10,
    deferred: bool = False,
) -> loader.LoadDefinition:
    immediate = (
        f"MERGE INTO reference.{table} AS target "
        f"USING {{staging_table}} AS source ON FALSE WHEN NOT MATCHED THEN DO NOTHING"
    )
    deferred_sql = (
        f"MERGE INTO reference.{table} AS target "
        f"USING {{staging_table}} AS source ON TRUE WHEN MATCHED THEN DO NOTHING"
    )
    return loader.LoadDefinition(
        workbook="reference.xlsx",
        sheet=sheet,
        schema="reference",
        table=table,
        dependency_order=order,
        columns=("code", "name"),
        required_columns=("code", "name"),
        source_key=("code",),
        merge_statements=(immediate,),
        deferred_statements=(deferred_sql,) if deferred else (),
    )


def _write_config(path: Path, statement: str) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "loads": [
                    {
                        "workbook": "reference.xlsx",
                        "sheet": "Environment",
                        "schema": "reference",
                        "table": "environment",
                        "dependency_order": 10,
                        "columns": ["environment_code", "environment_name"],
                        "required_columns": ["environment_code"],
                        "source_key": ["environment_code"],
                        "merge_statements": [statement],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_lock_workbook(path: Path, rows: list[tuple[Any, ...]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = loader.LOCK_SHEET
    sheet.append(loader.LOCK_COLUMNS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()


class FakeCursor:
    def __init__(
        self,
        *,
        merge_rowcount: int = 1,
        update_rowcount: int = 1,
        dedicated_allowed: bool = True,
        maintenance_lock: bool = True,
        bootstrap_allowed: bool = True,
        target_rows: tuple[tuple[Any, ...], ...] = (),
    ) -> None:
        self.events: list[tuple[str, str, Any]] = []
        self.rowcount = -1
        self.merge_rowcount = merge_rowcount
        self.update_rowcount = update_rowcount
        self.dedicated_allowed = dedicated_allowed
        self.maintenance_lock = maintenance_lock
        self.bootstrap_allowed = bootstrap_allowed
        self.target_rows = target_rows
        self.last_statement = ""

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: str, parameters: Any = None) -> None:
        self.events.append(("execute", statement, parameters))
        self.last_statement = statement
        if statement.startswith("MERGE"):
            self.rowcount = self.merge_rowcount
        elif statement.startswith("UPDATE"):
            self.rowcount = self.update_rowcount

    def executemany(self, statement: str, rows: Any) -> None:
        self.events.append(("executemany", statement, tuple(rows)))

    def fetchone(self) -> tuple[bool]:
        if "is_dedicated" in self.last_statement:
            return (self.dedicated_allowed,)
        if "maintenance_lock" in self.last_statement:
            return (self.maintenance_lock,)
        return (self.bootstrap_allowed,)

    def fetchall(self) -> tuple[tuple[Any, ...], ...]:
        return self.target_rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor, *, autocommit: bool = False) -> None:
        self.fake_cursor = cursor
        self.autocommit = autocommit

    def cursor(self) -> FakeCursor:
        return self.fake_cursor


def test_settings_are_validated_and_connection_input_is_not_in_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader, "conninfo_to_dict", lambda value: VALID_CONNECTION_PARTS)
    settings = loader.LoaderSettings.from_environment(
        {
            "GDS_LOADER_DSN": OPAQUE_DSN,
            "GDS_LOADER_WRITE_ACK": loader.WRITE_ACKNOWLEDGEMENT,
        }
    )

    rendered = repr(settings)
    assert OPAQUE_DSN not in rendered
    assert "test-host" not in rendered


@pytest.mark.parametrize(
    ("dsn", "acknowledgement", "parts", "message"),
    [
        ("", loader.WRITE_ACKNOWLEDGEMENT, VALID_CONNECTION_PARTS, "GDS_LOADER_DSN is required"),
        (OPAQUE_DSN, "", VALID_CONNECTION_PARTS, "must explicitly acknowledge"),
        (
            OPAQUE_DSN,
            loader.WRITE_ACKNOWLEDGEMENT,
            {**VALID_CONNECTION_PARTS, "sslmode": "require"},
            "sslmode=verify-full",
        ),
        (
            OPAQUE_DSN,
            loader.WRITE_ACKNOWLEDGEMENT,
            {**VALID_CONNECTION_PARTS, "user": "gds_mcp_runtime"},
            "runtime account",
        ),
    ],
)
def test_settings_reject_unsafe_connection_configuration(
    monkeypatch: pytest.MonkeyPatch,
    dsn: str,
    acknowledgement: str,
    parts: dict[str, str],
    message: str,
) -> None:
    monkeypatch.setattr(loader, "conninfo_to_dict", lambda value: parts)
    with pytest.raises(loader.LoaderError, match=message):
        loader.LoaderSettings.from_environment(
            {"GDS_LOADER_DSN": dsn, "GDS_LOADER_WRITE_ACK": acknowledgement}
        )


def test_read_config_accepts_one_allowlisted_merge(tmp_path: Path) -> None:
    config = tmp_path / "load_config.yaml"
    statement = (
        "MERGE INTO reference.environment AS target "
        "USING {staging_table} AS source ON FALSE WHEN NOT MATCHED THEN DO NOTHING;"
    )
    _write_config(config, statement)

    definitions = loader.read_config(config, require_complete=False)

    assert len(definitions) == 1
    assert definitions[0].target == "reference.environment"


def test_complete_config_uses_approved_workbook_split() -> None:
    definitions = loader.read_config()
    sheets_by_workbook = {
        workbook: {
            definition.sheet for definition in definitions if definition.workbook == workbook
        }
        for workbook in loader._ALLOWED_WORKBOOKS
    }

    assert sheets_by_workbook == {
        "reference.xlsx": {
            "Environment",
            "SystemType",
            "Zone",
            "ConnectionType",
            "ObjectType",
            "ConnectionParameter",
            "PurgePolicy",
            "SystemNotebook",
            "LocationType",
            "FileType",
            "Domain",
            "DataOperation",
            "ChunkType",
            "Pipeline",
            "ProcessType",
            "Currency",
            "JobType",
            "Lane",
        },
        "foundational.xlsx": {
            "Project",
            "System",
            "SystemNotebookPath",
            "Tenant",
            "Connection",
        },
        "users_security.xlsx": {
            "Principal",
            "EntraPrincipalIdentity",
            "TenantPrincipalAccess",
        },
        "operational.xlsx": {
            "TenantMetadataDiscoveryScope",
            "ConnectionLocation",
            "ConnectionValue",
            "Object",
            "Attribute",
            "IngestionObjectMapping",
            "IngestionAttributeMapping",
            "CopyGroup",
            "MemberGroup",
            "CopyGroupControl",
            "Copy",
            "ProcessGroup",
            "Process",
        },
        "model.xlsx": {"Model", "ModelScope"},
    }


def test_model_sheet_uses_canonical_policy_columns() -> None:
    definitions = loader.read_config()
    definition = next(value for value in definitions if value.selection == ("model.xlsx", "Model"))

    assert definition.target == "model.model"
    assert definition.columns == (
        "tenant_code",
        "model_name",
        "model_description",
        "silver_model_naming_instructions",
        "silver_model_audit_columns_template",
        "gold_model_naming_instructions",
        "gold_model_technical_columns_template",
        "gold_model_audit_columns_template",
        "is_active",
    )
    assert definition.required_columns == ("tenant_code", "model_name")
    assert definition.source_key == ("tenant_code", "model_name")
    assert loader.prepare_selected_loads((definition,)) == (
        loader.PreparedLoad(definition=definition, rows=()),
    )

    merge_sql = definition.merge_statements[0]
    assert "silver_model_naming_template" not in merge_sql
    assert "gold_model_naming_template" not in merge_sql
    assert (
        "NULLIF(btrim(staged.silver_model_naming_instructions::text), '') "
        "AS silver_model_naming_instructions"
    ) in merge_sql
    assert (
        "NULLIF(btrim(staged.gold_model_naming_instructions::text), '') "
        "AS gold_model_naming_instructions"
    ) in merge_sql
    for column in (
        "silver_model_audit_columns_template",
        "gold_model_technical_columns_template",
        "gold_model_audit_columns_template",
    ):
        assert f"NULLIF(btrim(staged.{column}::text), '')::jsonb AS {column}" in merge_sql
    for column in definition.columns[2:]:
        assert f"{column} = source.{column}" in merge_sql


@pytest.mark.parametrize(
    ("statement", "message"),
    [
        (
            "MERGE INTO core.project USING {staging_table} AS source "
            "ON FALSE WHEN NOT MATCHED THEN DO NOTHING",
            "wrong configured table",
        ),
        (
            "MERGE INTO reference.environment USING {staging_table} AS source "
            "ON TRUE WHEN MATCHED THEN DELETE",
            "forbidden SQL operation",
        ),
        (
            "MERGE INTO reference.environment USING source ON TRUE WHEN MATCHED THEN DO NOTHING",
            "must use \u007bstaging_table\u007d",
        ),
    ],
)
def test_read_config_rejects_unsafe_merge_sql(tmp_path: Path, statement: str, message: str) -> None:
    config = tmp_path / "load_config.yaml"
    _write_config(config, statement)

    with pytest.raises(loader.LoaderError, match=message):
        loader.read_config(config, require_complete=False)


def test_selection_is_deduplicated_and_sorted_before_locks() -> None:
    earlier = _definition(order=10)
    later = _definition(table="system_type", sheet="SystemType", order=20)

    selected = loader.select_loads(
        (later, earlier),
        (
            later.selection,
            (loader.LOCK_WORKBOOK, loader.LOCK_SHEET),
            earlier.selection,
            later.selection,
        ),
    )

    assert selected == (earlier, later, "lock")


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (((None, "Name"),), "required value is blank"),
        ((("CODE", "First"), (" code ", "Second")), "duplicate source key"),
    ],
)
def test_rows_reject_missing_required_values_and_normalized_duplicates(
    rows: tuple[tuple[str | None, ...], ...], message: str
) -> None:
    with pytest.raises(loader.LoaderError, match=message):
        loader._validate_rows(_definition(), rows)


def test_case_sensitive_source_key_columns_remain_distinct() -> None:
    definition = replace(
        _definition(),
        source_key=("code", "name"),
        case_sensitive_key_columns=("name",),
    )

    loader._validate_rows(definition, (("CODE", "Run"), ("CODE", "run")))


def test_case_sensitive_source_key_columns_preserve_whitespace() -> None:
    definition = replace(
        _definition(),
        source_key=("code", "name"),
        case_sensitive_key_columns=("name",),
    )

    loader._validate_rows(definition, (("CODE", "Run"), ("CODE", " Run ")))


def test_lock_control_accepts_allowlisted_targets_and_boolean_forms(tmp_path: Path) -> None:
    workbook = tmp_path / loader.LOCK_WORKBOOK
    _write_lock_workbook(
        workbook,
        [
            ("core", "object", "object_id", 5, 1, None),
            ("model", "model_scope", "model_scope_id", 6, "false", 7),
        ],
    )

    assert loader._read_lock_rows(workbook) == (
        ("core", "object", "object_id", 5, True, None),
        ("model", "model_scope", "model_scope_id", 6, False, 7),
    )


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (("core", "project", "project_id", 5, 1, None), "non-allowlisted target"),
        (("core", "object", "object_id", 5, "yes", None), "must be 1 or 0"),
        (
            ("model", "model_scope", "model_scope_id", 5, 1, None),
            "require expected_model_revision",
        ),
    ],
)
def test_lock_control_rejects_unknown_targets_and_boolean_values(
    tmp_path: Path, row: tuple[Any, ...], message: str
) -> None:
    workbook = tmp_path / loader.LOCK_WORKBOOK
    _write_lock_workbook(workbook, [row])

    with pytest.raises(loader.LoaderError, match=message):
        loader._read_lock_rows(workbook)


def test_execute_uses_temp_staging_and_runs_deferred_merges_last() -> None:
    first = _definition(deferred=True)
    second = _definition(table="system_type", sheet="SystemType", order=20)
    cursor = FakeCursor()

    loader.execute_prepared_loads(
        FakeConnection(cursor),
        (
            loader.PreparedLoad(first, (("A", "First"),)),
            loader.PreparedLoad(second, (("B", "Second"),)),
        ),
    )

    executed = [event[1] for event in cursor.events if event[0] == "execute"]
    assert executed[0] == "SET LOCAL lock_timeout = '5s'"
    assert executed[1] == "SET LOCAL statement_timeout = '5min'"
    assert any("is_dedicated" in statement for statement in executed)
    assert any("maintenance_lock" in statement for statement in executed)
    assert any(statement.startswith("LOCK TABLE") for statement in executed)
    assert any(statement.startswith("SET CONSTRAINTS") for statement in executed)
    immediate = [statement for statement in executed if statement.startswith("MERGE")]
    assert "reference.environment" in immediate[-1]
    assert "reference.system_type" in immediate[-2]
    assert 'pg_temp."staging_reference_environment"' in immediate[0]
    assert all("DROP " not in statement and "TRUNCATE " not in statement for statement in executed)


def test_execute_rejects_database_after_runtime_activity() -> None:
    cursor = FakeCursor(bootstrap_allowed=False)
    definition = _definition()

    with pytest.raises(loader.LoaderError, match="before governed runtime activity"):
        loader.execute_prepared_loads(
            FakeConnection(cursor),
            (loader.PreparedLoad(definition, (("A", "First"),)),),
        )


def test_execute_rejects_owner_or_superuser_session() -> None:
    cursor = FakeCursor(dedicated_allowed=False)
    definition = _definition()

    with pytest.raises(loader.LoaderError, match="dedicated non-owner"):
        loader.execute_prepared_loads(
            FakeConnection(cursor),
            (loader.PreparedLoad(definition, (("A", "First"),)),),
        )


def test_execute_rejects_autocommit_connection() -> None:
    definition = _definition()

    with pytest.raises(loader.LoaderError, match="non-autocommit"):
        loader.execute_prepared_loads(
            FakeConnection(FakeCursor(), autocommit=True),
            (loader.PreparedLoad(definition, (("A", "First"),)),),
        )


def test_execute_fails_when_merge_drops_a_staged_row() -> None:
    definition = _definition()
    cursor = FakeCursor(merge_rowcount=0)

    with pytest.raises(loader.LoaderError, match="did not resolve every row"):
        loader.execute_prepared_loads(
            FakeConnection(cursor),
            (loader.PreparedLoad(definition, (("A", "First"),)),),
        )


def test_lock_update_fails_when_any_requested_id_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor(update_rowcount=0)
    load = loader.PreparedLockLoad(rows=(("core", "object", "object_id", 5, True, None),))
    monkeypatch.setattr(loader, "_resolve_lock_actor", lambda value: LOCK_ACTOR)

    with pytest.raises(loader.LoaderError, match="ID that does not exist"):
        loader._execute_lock_load(cursor, load)


def test_lock_update_rejects_stale_model_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor(target_rows=((6, 9, True, 3, 8, 7),))
    load = loader.PreparedLockLoad(rows=(("model", "model_scope", "model_scope_id", 6, True, 7),))
    monkeypatch.setattr(loader, "_resolve_lock_actor", lambda value: LOCK_ACTOR)

    with pytest.raises(loader.LoaderError, match="revision is stale"):
        loader._execute_lock_load(cursor, load)


def test_main_dry_run_never_loads_dotenv_or_calls_connector(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    definition = _definition()
    prepared = loader.PreparedLoad(definition, (("A", "First"),))
    connector_called = False

    def forbidden_connector(*args: Any, **kwargs: Any) -> Any:
        nonlocal connector_called
        connector_called = True
        raise AssertionError("dry run opened a database connection")

    monkeypatch.setattr(loader, "read_config", lambda: (definition,))
    monkeypatch.setattr(loader, "prepare_selected_loads", lambda selected: (prepared,))
    monkeypatch.setitem(loader.sys.modules, "dotenv", None)

    result = loader.main(
        ["--workbook", definition.workbook, "--sheet", definition.sheet],
        connector=forbidden_connector,
    )

    assert result == 0
    assert connector_called is False
    assert "no database connection was opened" in capsys.readouterr().out


def test_main_rejects_mixed_data_and_locks_before_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = _definition()
    connector_called = False

    def forbidden_connector(*args: Any, **kwargs: Any) -> Any:
        nonlocal connector_called
        connector_called = True
        raise AssertionError("mixed selection opened a database connection")

    monkeypatch.setattr(loader, "read_config", lambda: (definition,))
    monkeypatch.setattr(
        loader,
        "MANUAL_LOAD_SELECTIONS",
        [definition.selection, (loader.LOCK_WORKBOOK, loader.LOCK_SHEET)],
    )

    assert loader.main([], connector=forbidden_connector) == 2
    assert connector_called is False
