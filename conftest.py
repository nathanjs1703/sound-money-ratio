"""Make the shared core and the CLI importable in tests without packaging.

Adds the repo root (for sound_money_core) and cli/ (for project) to sys.path.
This is the lightweight monorepo approach: no pyproject, no install step, the
two front doors and the shared core just resolve as local modules.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "cli"))
