from app.automation.multimodal import analyze_multimodal_presence

HTML_WITH_LINKS = """
<html><body>
<a href="https://www.youtube.com/@voorbeeld">YouTube</a>
<a href="https://www.instagram.com/voorbeeld/">Instagram</a>
<a href="https://nl.trustpilot.com/review/voorbeeld.nl">Trustpilot</a>
<a href="/over-ons">Over ons</a>
</body></html>
"""

HTML_WITHOUT_LINKS = "<html><body><p>Geen social links hier.</p></body></html>"


def test_detects_multiple_platforms_and_youtube_bonus():
    result = analyze_multimodal_presence(HTML_WITH_LINKS)
    assert set(result.platforms_found) == {"YouTube", "Instagram", "Trustpilot"}
    assert result.score > 3 * 1.5  # youtube-bonus telt mee


def test_no_links_scores_zero():
    result = analyze_multimodal_presence(HTML_WITHOUT_LINKS)
    assert result.platforms_found == []
    assert result.score == 0.0


def test_score_never_exceeds_ten():
    html = "<html><body>" + "".join(
        f'<a href="https://{host}">x</a>'
        for host in [
            "youtube.com/x", "youtu.be/x", "instagram.com/x", "tiktok.com/x",
            "facebook.com/x", "linkedin.com/company/x", "twitter.com/x", "trustpilot.com/review/x",
        ]
    ) + "</body></html>"
    result = analyze_multimodal_presence(html)
    assert result.score <= 10.0
