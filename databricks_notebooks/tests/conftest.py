import sys
from pathlib import Path

_SOURCE_ROOT = str(Path(__file__).parents[1])
if _SOURCE_ROOT not in sys.path:
    sys.path.insert(0, _SOURCE_ROOT)
