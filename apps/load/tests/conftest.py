"""Pytest-Config: app/ ins sys.path legen, damit `import main` etc. ohne
Installation des Pakets funktioniert (cd apps/load && pytest tests)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
