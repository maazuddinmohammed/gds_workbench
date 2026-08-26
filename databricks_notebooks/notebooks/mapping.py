# Databricks notebook source
# ruff: noqa: E402, F821
import sys
from pathlib import Path

_SOURCE_ROOT = str(Path.cwd().parent)
if _SOURCE_ROOT not in sys.path:
    sys.path.insert(0, _SOURCE_ROOT)

from gds_workbench_notebooks import run_notebook

run_notebook("mapping", dbutils=dbutils)
