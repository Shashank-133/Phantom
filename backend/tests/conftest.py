"""Shared test fixtures + path setup.

Adds `backend/` to sys.path so tests can `from services.x import y` the same
way the running application does, regardless of where pytest is invoked from.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
