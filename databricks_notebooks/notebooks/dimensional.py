# Databricks notebook source
# ruff: noqa: E402, F821
import sys
from pathlib import Path

_UPLOAD_ROOT = next(
    (
        directory
        for directory in (Path.cwd(), *Path.cwd().parents)
        if (directory / "src" / "gds_workbench_notebooks" / "__init__.py").is_file()
    ),
    None,
)
if _UPLOAD_ROOT is None:
    raise RuntimeError("Uploaded root with src/gds_workbench_notebooks was not found.")
_SOURCE_ROOT = str(_UPLOAD_ROOT / "src")
if _SOURCE_ROOT not in sys.path:
    sys.path.insert(0, _SOURCE_ROOT)

from gds_workbench_notebooks.notebook import run_notebook

run_notebook("dimensional", dbutils=dbutils, uploaded_root=_UPLOAD_ROOT)
