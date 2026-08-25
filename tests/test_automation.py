from app.automation.chunkability import analyze_chunkability
from app.automation.freshness import analyze_freshness
from app.automation.phase0_knockout import check_robots_txt
from app.automation.structured_data import analyze_structured_data

JSONLD_ORG = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Voorbeeld BV",
  "url": "https://voorbeeld.nl",
  "logo": "https://voorbeeld.nl/logo.png",
  "sameAs": ["https://linkedin.com/company/voorbeeld"]
}
</script>
<meta name="DCTERMS.modified" content="2026-06-01T10:00:00Z">
</head><body></body></html>
"""

NO_STRUCTURED_DATA_HTML = "<html><head></head><body><p>Geen markup hier.</p></body></html>"

CHUNKABLE_HTML = """
<html><body>
<h2>Titel een</h2>
<p>""" + " ".join(["woord"] * 180) + """</p>
<h3>Subtitel</h3>
<ul><li>Punt 1</li><li>Punt 2</li></ul>
<table><tr><td>Cel</td></tr></table>
</body></html>
"""

NOT_CHUNKABLE_HTML = "<html><body><p>Te kort.</p></body></html>"


def test_structured_data_detects_organization_and_dcterms():
    result = analyze_structured_data(JSONLD_ORG)
    assert "Organization" in result.types_found
    assert result.dcterms_fields
    assert result.score > 5


def test_structured_data_scores_zero_without_markup():
    result = analyze_structured_data(NO_STRUCTURED_DATA_HTML)
    assert result.score == 0.0
    assert not result.types_found


def test_chunkability_rewards_headings_and_lists():
    result = analyze_chunkability(CHUNKABLE_HTML)
    assert result.heading_count == 2
    assert result.list_count == 1
    assert result.table_count == 1
    assert result.score > 5


def test_chunkability_low_score_for_sparse_content():
    result = analyze_chunkability(NOT_CHUNKABLE_HTML)
    assert result.score < 5


def test_freshness_parses_dcterms_modified():
    result = analyze_freshness(JSONLD_ORG)
    assert result.modified_at is not None
    assert result.source_field == "meta:DCTERMS.modified"
    assert result.score >= 0


def test_freshness_zero_without_date():
    result = analyze_freshness(NO_STRUCTURED_DATA_HTML)
    assert result.score == 0.0
    assert result.modified_at is None


class _FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class _FakeClient:
    def __init__(self, text: str, status_code: int = 200):
        self._text = text
        self._status_code = status_code

    def get(self, url: str):
        return _FakeResponse(self._status_code, self._text)


def test_robots_txt_blocks_gptbot():
    robots = "User-agent: GPTBot\nDisallow: /\n"
    found, crawler_ok, disallowed = check_robots_txt(_FakeClient(robots), "https://voorbeeld.nl")
    assert found is True
    assert crawler_ok is False
    assert "GPTBot" in disallowed


def test_robots_txt_wildcard_disallow_blocks_all_ai_crawlers():
    robots = "User-agent: *\nDisallow: /\n"
    found, crawler_ok, disallowed = check_robots_txt(_FakeClient(robots), "https://voorbeeld.nl")
    assert crawler_ok is False
    assert set(disallowed) == {"GPTBot", "PerplexityBot", "ClaudeBot", "Google-Extended"}


def test_robots_txt_allows_when_no_disallow():
    robots = "User-agent: *\nDisallow: /admin\n"
    found, crawler_ok, disallowed = check_robots_txt(_FakeClient(robots), "https://voorbeeld.nl")
    assert crawler_ok is True
    assert disallowed == []


def test_robots_txt_missing_defaults_to_ok():
    found, crawler_ok, disallowed = check_robots_txt(_FakeClient("", status_code=404), "https://voorbeeld.nl")
    assert found is False
    assert crawler_ok is True


def test_robots_txt_specific_agent_overrides_wildcard_disallow():
    # Wildcard blokkeert alles, maar GPTBot krijgt een eigen groep zonder
    # Disallow: / -> moet als toegestaan gelden (specifieke groep wint).
    robots = "User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nDisallow: /admin\n"
    found, crawler_ok, disallowed = check_robots_txt(_FakeClient(robots), "https://voorbeeld.nl")
    assert "GPTBot" not in disallowed
    assert "PerplexityBot" in disallowed  # geen eigen groep -> valt terug op wildcard
    assert crawler_ok is False  # PerplexityBot etc. nog steeds geblokkeerd


def test_robots_txt_specific_agent_can_also_block_when_wildcard_allows():
    robots = "User-agent: *\nDisallow: /admin\n\nUser-agent: ClaudeBot\nDisallow: /\n"
    found, crawler_ok, disallowed = check_robots_txt(_FakeClient(robots), "https://voorbeeld.nl")
    assert disallowed == ["ClaudeBot"]
