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
    assert set(sources) == set(_EXPECTED)

    for name, workflow in _EXPECTED.items():
        text = sources[name].read_text()
        assert text.startswith("# Databricks notebook source\n")
        ast.parse(text)
        assert text.count("run_notebook(") == 1
        assert f'run_notebook("{workflow}", dbutils=dbutils)' in text
        assert "sys.path.insert" in text
        assert "psycopg" not in text
        assert "dbutils.secrets" not in text
        assert "DATABRICKS_TOKEN" not in text
        assert "DATABASE_URL" not in text


def test_notebook_runtime_dependencies_are_explicit_and_minimal() -> None:
    requirements = (_ROOT / "requirements.txt").read_text().splitlines()
    assert requirements == ["databricks-sdk==0.133.0", "requests==2.34.2"]


def test_readme_documents_source_import_auth_and_safe_retry_contract() -> None:
    readme = (_ROOT / "README.md").read_text()
    normalized_readme = " ".join(readme.split())
    for required_text in (
        "not a wheel",
        "Databricks CLI 0.294.0 or newer",
        "FastAPI",
        "same Workflow Run",
        "CAN USE",
        "all-apis",
        "sys.path",
        "IdempotencyKey",
        "remains queued",
        "never acquires, extends, or releases a Tenant Lock",
    ):
        assert required_text in normalized_readme
    for workflow in _EXPECTED.values():
        assert f"`{workflow}`" in readme


def test_readme_documents_ordered_workflow_and_manual_apply_gates() -> None:
    normalized_readme = " ".join((_ROOT / "README.md").read_text().split())

    assert (
        "`profiling` → `analysis_inference` → `analysis_validation` → "
        "`conceptual` → `logical` → logical `mapping` → optional logical "
        "`code_generation` → optional `dimensional` → dimensional `mapping` → "
        "dimensional `code_generation`"
    ) in normalized_readme
    for required_text in (
        "backend-validated draft",
        "Apply revalidates",
        "applied Mapping unlocks logical Code Generation",
        "required before Dimensional inputs become eligible",
        "refresh `ExpectedModelRevision`",
        "The notebooks never apply a draft",
        "Code Generation reads applied Mapping",
    ):
        assert required_text in normalized_readme
