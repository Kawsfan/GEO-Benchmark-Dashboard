#!/usr/bin/env python3
"""Handmatige/cron-fallback voor de maandelijkse Fase 4-citatiecheck, buiten
de in-process APScheduler om.

Gebruik:
    python scripts/run_monthly_citation_check.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scheduler import run_monthly_citation_checks  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_monthly_citation_checks()
