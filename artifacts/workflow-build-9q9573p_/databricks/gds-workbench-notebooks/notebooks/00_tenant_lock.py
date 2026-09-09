# Databricks notebook source
# ruff: noqa: E402, F821
import sys
from pathlib import Path


def _locate_uploaded_root(start: Path) -> Path:
    candidate = start.resolve(strict=False)
    for directory in (candidate, *candidate.parents):
        if (
            (directory / "src" / "gds_workbench_notebooks" / "__init__.py").is_file()
            and (directory / "notebooks").is_dir()
            and (directory / "requirements.txt").is_file()
        ):
            return directory
    raise RuntimeError("Uploaded root must contain src, notebooks, and requirements.txt.")


_UPLOAD_ROOT = _locate_uploaded_root(Path.cwd())
_SOURCE_ROOT = str(_UPLOAD_ROOT / "src")
if _SOURCE_ROOT not in sys.path:
    sys.path.insert(0, _SOURCE_ROOT)

from gds_workbench_notebooks.tenant_lock import (
    create_tenant_lock_widgets,
    run_tenant_lock_notebook,
)

# Run this cell first, then fill the Tenant Lock widgets above.
create_tenant_lock_widgets(dbutils=dbutils)

# COMMAND ----------

# Run this cell after filling TenantID and the action inputs.
run_tenant_lock_notebook(dbutils=dbutils, uploaded_root=_UPLOAD_ROOT)
