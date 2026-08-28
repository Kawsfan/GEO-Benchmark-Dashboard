"""Regressietest voor een bug waarbij de scan-detailpagina volledig
onopgemaakt rendere: `render_report_body()` levert alleen het
`.geo-report`-fragment, de bijbehorende CSS (`render_report_css()`) werd
alleen in de PDF-export ingesloten en nooit op de webpagina zelf."""

from app.report_html import render_report_css, render_report_body
from app.scoring import compute_score


def _sample_report():
    return compute_score(
        criterion_scores={"c1_structured_data": 7.0},
        crawler_ok=True,
        ssr_ok=True,
    )


def test_report_css_defines_custom_properties_scoped_to_geo_report_not_root():
    css = render_report_css(_sample_report())

    # Geen echte :root-selector (alleen de comment mag ":root" noemen).
    assert ":root {" not in css
    assert ".geo-report {" in css
    assert "--bg:" in css
    assert "--accent:" in css


def test_report_css_contains_a_style_tag():
    css = render_report_css(_sample_report())
    assert css.startswith("<style>")
    assert css.endswith("</style>")


def test_report_body_alone_has_no_style_tag():
    # render_report_body() is een fragment zonder eigen <style> — de caller
    # (scan_detail.html, of render_full_report_html() voor de PDF) moet
    # render_report_css() er zelf naast zetten.
    body = render_report_body(_sample_report(), "Voorbeeld BV", "voorbeeld.nl", "26-08-2026 11:31")
    assert "<style>" not in body
    assert 'class="geo-report"' in body
