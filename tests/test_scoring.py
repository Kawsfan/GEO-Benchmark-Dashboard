from app.scoring import CRITERIA, SOURCE_AUTOMATED, SOURCE_MANUAL, classify, compute_score


def test_weights_sum_to_100():
    assert sum(c["weight"] for c in CRITERIA.values()) == 100


def test_knockout_fail_forces_zero_score():
    report = compute_score(
        criterion_scores={code: 10 for code in CRITERIA},
        crawler_ok=False,
        ssr_ok=True,
    )
    assert report.total_score == 0.0
    assert report.classification == "Onzichtbaar"
    assert report.knockout_pass is False


def test_full_scores_yield_perfect_total():
    report = compute_score(
        criterion_scores={code: 10 for code in CRITERIA},
        crawler_ok=True,
        ssr_ok=True,
    )
    assert report.total_score == 100.0
    assert report.classification == "AI Category Leader"


def test_missing_scores_default_to_zero():
    report = compute_score(criterion_scores={}, crawler_ok=True, ssr_ok=True)
    assert report.total_score == 0.0
    assert report.classification == "Onzichtbaar"


def test_classify_boundaries():
    assert classify(85)[0] == "AI Category Leader"
    assert classify(84.9)[0] == "Sterke AI-positie"
    assert classify(70)[0] == "Sterke AI-positie"
    assert classify(55)[0] == "Op de goede weg"
    assert classify(40)[0] == "Kwetsbaar"
    assert classify(0)[0] == "Onzichtbaar"


def test_gap_analysis_flags_low_scores():
    scores = {code: 9 for code in CRITERIA}
    scores["c1_structured_data"] = 3  # Technische basis & Structuur
    report = compute_score(scores, crawler_ok=True, ssr_ok=True)
    gap_items = report.gaps["Technical & Structural GAP"]
    assert any(r.code == "c1_structured_data" for r in gap_items)


def test_priorities_prefer_quick_wins():
    scores = {code: 9 for code in CRITERIA}
    scores["c1_structured_data"] = 2  # quick win, low pillar weight
    scores["c3_answerability"] = 2  # strategic, higher weight
    report = compute_score(scores, crawler_ok=True, ssr_ok=True)
    priority_codes = [r.code for r in report.priorities]
    assert "c1_structured_data" in priority_codes
    assert "c3_answerability" in priority_codes


def test_source_tracking_roundtrip():
    sources = {"c1_structured_data": SOURCE_AUTOMATED, "c3_answerability": SOURCE_MANUAL}
    report = compute_score(
        criterion_scores={"c1_structured_data": 7, "c3_answerability": 5},
        crawler_ok=True,
        ssr_ok=True,
        sources=sources,
    )
    by_code = {r.code: r for r in report.results}
    assert by_code["c1_structured_data"].source == SOURCE_AUTOMATED
    assert by_code["c3_answerability"].source == SOURCE_MANUAL
    # criteria zonder opgegeven bron vallen terug op handmatig
    assert by_code["c2_chunkability"].source == SOURCE_MANUAL
