import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).parents[2]
_SOURCE_ROOTS = (
    _REPOSITORY_ROOT / "databricks_notebooks" / "src",
    _REPOSITORY_ROOT / "web_app" / "backend",
    _REPOSITORY_ROOT / "mcp_server",
    _REPOSITORY_ROOT,
)
for source_root in reversed(_SOURCE_ROOTS):
    source = str(source_root)
    if source in sys.path:
        sys.path.remove(source)
    sys.path.insert(0, source)
