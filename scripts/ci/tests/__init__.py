"""Unit tests for the CI helper scripts.

The scripts live one directory up and are executed as plain files (`python3 scripts/ci/check_pr.py`), so they
import each other by bare module name. Make that work under `unittest discover` too.
"""

import sys
from pathlib import Path

SCRIPTS_CI = Path(__file__).resolve().parent.parent
if str(SCRIPTS_CI) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_CI))
