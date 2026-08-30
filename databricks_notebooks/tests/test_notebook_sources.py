import ast
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_EXPECTED = {
    "profiling.py": "profiling",
    "analysis_inference.py": "analysis_inference",
    "analysis_validation.py": "analysis_validation",
    "conceptual.py": "conceptual",
    "logical.py": "logical",
    "dimensional.py": "dimensional",
    "mapping.py": "mapping",
    "code_generation.py": "code_generation",
}


def test_all_workflow_notebooks_are_source_importable_and_thin() -> None:
    sources = {path.name: path for path in (_ROOT / "notebooks").glob("*.py")}
    assert set(sources) == {
        *_EXPECTED,
        "00_tenant_lock.py",
        "01_runtime_preflight.py",
        "90_review_workflow_draft.py",
        "91_apply_workflow_draft.py",
    }

    for name, workflow in _EXPECTED.items():
        text = sources[name].read_text()
        assert text.startswith("# Databricks notebook source\n")
        ast.parse(text)
        assert text.count("# COMMAND ----------") == 1
        setup = (
            f'create_workflow_widgets("{workflow}", dbutils=dbutils, uploaded_root=_UPLOAD_ROOT)'
        )
        execute = f'run_notebook("{workflow}", dbutils=dbutils, uploaded_root=_UPLOAD_ROOT)'
        assert text.index(setup) < text.index("# COMMAND ----------") < text.index(execute)
        assert text.count("run_notebook(") == 1
        assert "sys.path.insert" in text
        assert "psycopg" not in text
        assert "dbutils.secrets" not in text
        assert "DATABRICKS_TOKEN" not in text
        assert "DATABASE_URL" not in text


def test_tenant_lock_notebook_uses_the_source_tree_and_independent_entry_point() -> None:
    text = (_ROOT / "notebooks" / "00_tenant_lock.py").read_text()

    assert text.startswith("# Databricks notebook source\n")
    ast.parse(text)
    assert 'directory / "src" / "gds_workbench_notebooks"' in text
    assert 'str(_UPLOAD_ROOT / "src")' in text
    assert "sys.path.insert(0, _SOURCE_ROOT)" in text
    assert text.count("# COMMAND ----------") == 1
    assert (
        text.index("create_tenant_lock_widgets(dbutils=dbutils)")
        < text.index("# COMMAND ----------")
        < text.index("run_tenant_lock_notebook(dbutils=dbutils, uploaded_root=_UPLOAD_ROOT)")
    )
    assert text.count("run_tenant_lock_notebook(") == 1
    assert "AppName" not in text
    assert "ModelID" not in text
    assert "Principal" not in text
    assert "force" not in text.lower()


def test_preflight_has_no_user_inputs_or_widgets() -> None:
    text = (_ROOT / "notebooks" / "01_runtime_preflight.py").read_text()

    assert "dbutils.widgets" not in text
    assert "create_" not in text
    assert text.count("run_notebook_preflight(") == 1


def test_notebook_runtime_dependencies_are_explicit_and_pinned() -> None:
    requirements = (_ROOT / "requirements.txt").read_text().splitlines()
    assert requirements == [
        "azure-identity==1.25.3",
        "databricks-sdk==0.133.0",
        "databricks-sql-connector==4.4.0",
        "fastapi==0.141.1",
        "langchain==1.3.15",
        "langchain-openai==1.5.1",
        "mcp==2.0.0",
        "openai-agents==0.22.0",
        "openpyxl==3.1.5",
        "psycopg[binary]==3.3.4",
        "psycopg-pool==3.3.1",
        "pydantic==2.13.4",
        "sqlglot==30.13.0",
    ]


def test_notebook_control_has_no_app_http_client_surface() -> None:
    source_root = _ROOT / "src" / "gds_workbench_notebooks"
    source = "\n".join(path.read_text() for path in source_root.glob("*.py"))

    assert not (source_root / "app_client.py").exists()
    for forbidden in (
        "AppName",
        "WaitTimeoutSeconds",
        "databricks.sdk",
        "requests",
        "oidc/v1/token",
        "apiToken()",
    ):
        assert forbidden not in source


def test_readme_documents_independent_source_runtime_and_fixed_identity() -> None:
    readme = (_ROOT / "README.md").read_text()
    normalized_readme = " ".join(readme.split())
    for required_text in (
        "Azure Databricks Runtime 16.4 LTS",
        "`<root>/src`",
        "sys.path",
        "root `.env`",
        "`gds_notebook_runtime`",
        "fixed Super Admin workload identity",
        "no App configuration or App authorization",
        "None of these notebook entry points starts an MCP server",
        "No wheel or other distribution",
        "high-trust shared workload design",
        "Databricks unified authentication",
        "IdempotencyKey",
    ):
        assert required_text in normalized_readme
    for workflow in _EXPECTED.values():
        assert f"`{workflow}`" in readme


def test_readme_documents_ordered_workflow_and_manual_apply_gates() -> None:
    normalized_readme = " ".join((_ROOT / "README.md").read_text().split())

    assert (
        "profiling -> analysis_inference -> review/apply -> analysis_validation "
        "-> conceptual -> review/apply -> logical -> review/apply "
        "-> logical mapping -> review/apply -> optional logical code_generation "
        "-> optional dimensional -> review/apply -> dimensional mapping "
        "-> review/apply -> dimensional code_generation"
    ) in normalized_readme
    for required_text in (
        "Run `01_runtime_preflight.py`",
        "Run `00_tenant_lock.py` with `Action=check`",
        "`90_review_workflow_draft.py`",
        "`91_apply_workflow_draft.py`",
        "`ExpectedModelRevision`",
        "`ExpectedDraftRevision`",
        "`ExpectedCandidateDigest`",
        "`Confirmation=APPLY`",
        "Apply revalidates all fences",
        "Drafts are durable PostgreSQL data",
        "There is no force unlock action",
    ):
        assert required_text in normalized_readme
