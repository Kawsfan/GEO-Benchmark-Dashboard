"""PDF-export per scan.

Het bestaande `geo_report_generator.py`-recept ging uit van wkhtmltopdf.
Dit dashboard gebruikt WeasyPrint (pure-Python, geen extern binary nodig)
zodat de PDF-export overal werkt zonder systeemafhankelijkheid — zie
ARCHITECTURE.md. De HTML/CSS is identiek aan de schermweergave
(`render_full_report_html`), dus het PDF-recept is nog steeds "hetzelfde
rapport, ander uitvoerformaat".
"""

from __future__ import annotations

from app.models import Organization, Scan
from app.report_html import render_full_report_html
from app.report_view import build_report_from_scan


def render_scan_pdf(scan: Scan, organization: Organization) -> bytes:
    from weasyprint import HTML  # lazy import: zwaar, alleen nodig bij PDF-export

    report = build_report_from_scan(scan)
    generated_at = scan.created_at.strftime("%d-%m-%Y %H:%M")
    html = render_full_report_html(report, organization.name, organization.domain, generated_at)
    return HTML(string=html).write_pdf()
