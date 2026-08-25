"""Gedeelde HTTP-helpers voor de Fase 1-automatisering."""

from __future__ import annotations

import httpx

USER_AGENT = "GEO-Scan-Dashboard/1.0 (+https://github.com/kawsfan/geo-benchmark-dashboard)"

DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


def build_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    )


def normalize_domain(domain: str) -> str:
    domain = domain.strip()
    if not domain:
        return domain
    if not domain.startswith(("http://", "https://")):
        domain = f"https://{domain}"
    return domain.rstrip("/")
