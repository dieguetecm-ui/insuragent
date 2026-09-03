#!/usr/bin/env python3
"""Wrapper de `insuragent.cli.index` para ejecutar sin instalar el paquete."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from insuragent.cli import index  # noqa: E402

if __name__ == "__main__":
    sys.exit(index(sys.argv[1:]))
