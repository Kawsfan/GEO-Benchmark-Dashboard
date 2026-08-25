"""Optionele HTTP Basic Auth voor het hele dashboard.

Dit dashboard heeft geen gebruikersbeheer — één gedeeld wachtwoord is
voldoende om te voorkomen dat een toevallige bezoeker van de link
organisaties kan toevoegen/verwijderen of scans kan starten (die geld
kosten via de Claude API). Ingeschakeld door zowel
`GEO_DASHBOARD_AUTH_USERNAME` als `GEO_DASHBOARD_AUTH_PASSWORD` te zetten;
zonder die twee draait het dashboard onbeveiligd (handig voor lokale
ontwikkeling), met een duidelijke waarschuwing bij het opstarten.
"""

from __future__ import annotations

import base64
import binascii
import logging
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("geo_dashboard.auth")

WWW_AUTHENTICATE = 'Basic realm="GEO Scan Dashboard"'


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, username: str, password: str):
        super().__init__(app)
        self._username = username
        self._password = password

    async def dispatch(self, request: Request, call_next):
        if self._credentials_valid(request.headers.get("authorization")):
            return await call_next(request)
        return Response(
            content="Authenticatie vereist.",
            status_code=401,
            headers={"WWW-Authenticate": WWW_AUTHENTICATE},
        )

    def _credentials_valid(self, header_value: str | None) -> bool:
        if not header_value:
            return False
        scheme, _, encoded = header_value.partition(" ")
        if scheme.lower() != "basic" or not encoded:
            return False
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return False
        username, _, password = decoded.partition(":")
        # secrets.compare_digest voorkomt timing-aanvallen op de vergelijking.
        return secrets.compare_digest(username, self._username) and secrets.compare_digest(
            password, self._password
        )


def configure_auth(app, username: str | None, password: str | None) -> bool:
    """Voegt de middleware toe als beide credentials gezet zijn.

    Retourneert of auth is ingeschakeld, zodat de caller dit kan loggen."""
    if username and password:
        app.add_middleware(BasicAuthMiddleware, username=username, password=password)
        return True

    logger.warning(
        "GEO_DASHBOARD_AUTH_USERNAME/GEO_DASHBOARD_AUTH_PASSWORD niet (volledig) gezet — "
        "dashboard draait ONBEVEILIGD. Zet beide env-vars voordat je de link deelt."
    )
    return False
