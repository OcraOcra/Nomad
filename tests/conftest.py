"""Configuración de pytest para Nomad CR."""

import sys
from pathlib import Path

# Asegurar que src está en el path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
