"""Pytest-Config: app/ ins sys.path legen, damit `import k8s` etc. ohne
Installation des Pakets funktioniert (cd apps/metric && pytest tests)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
