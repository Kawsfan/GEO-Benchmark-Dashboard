from app.automation import phase3_runner
from app.automation.entity_clarity import EntityClarityResult
from app.automation.external_mentions import ExternalMentionsResult
from app.automation.multimodal import MultimodalResult
from app.automation.phase3_runner import run_phase3_automation
from app.scoring import SOURCE_AUTOMATED, SOURCE_LLM_ESTIMATE

HTML = '<html><body><a href="https://www.youtube.com/@voorbeeld">YT</a></body></html>'


def test_all_three_criteria_merged_on_success(monkeypatch):
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_PHASE3", raising=False)
    monkeypatch.setattr(
        phase3_runner, "analyze_entity_clarity", lambda name, domain: EntityClarityResult(score=6.5, qid="Q1", detail="ok")
    )
    monkeypatch.setattr(
        phase3_runner,
        "assess_external_mentions",
        lambda name, domain, sector=None: ExternalMentionsResult(
            score=7.0, notable_sources=["nu.nl"], mentions_count_estimate=5, rationale="prima"
        ),
    )
    monkeypatch.setattr(phase3_runner, "analyze_multimodal_presence", lambda html: MultimodalResult(score=3.0, platforms_found=["YouTube"]))

    result = run_phase3_automation("Voorbeeld BV", "voorbeeld.nl", HTML)

    assert result.criterion_scores["c6_entity_clarity"] == 6.5
    assert result.criterion_sources["c6_entity_clarity"] == SOURCE_AUTOMATED
    assert result.criterion_scores["c7_external_mentions"] == 7.0
    assert result.criterion_sources["c7_external_mentions"] == SOURCE_LLM_ESTIMATE
    assert "nu.nl" in result.criterion_rationales["c7_external_mentions"]
    assert result.criterion_scores["c8_multimodal"] == 3.0
    assert result.criterion_sources["c8_multimodal"] == SOURCE_AUTOMATED
    assert result.errors == {}


def test_one_failure_does_not_block_the_others(monkeypatch):
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_PHASE3", raising=False)

    def raise_c6(name, domain):
        raise RuntimeError("wikidata down")

    monkeypatch.setattr(phase3_runner, "analyze_entity_clarity", raise_c6)
    monkeypatch.setattr(
        phase3_runner,
        "assess_external_mentions",
        lambda name, domain, sector=None: ExternalMentionsResult(error="geen credentials"),
    )
    monkeypatch.setattr(phase3_runner, "analyze_multimodal_presence", lambda html: MultimodalResult(score=1.5, platforms_found=["Instagram"]))

    result = run_phase3_automation("Voorbeeld BV", "voorbeeld.nl", HTML)

    assert "c6_entity_clarity" in result.errors
    assert "c7_external_mentions" in result.errors
    assert "c6_entity_clarity" not in result.criterion_scores
    assert "c7_external_mentions" not in result.criterion_scores
    # C8 bleef ongemoeid door de C6/C7-fouten.
    assert result.criterion_scores["c8_multimodal"] == 1.5


def test_no_html_skips_c8_only(monkeypatch):
    monkeypatch.delenv("GEO_DASHBOARD_DISABLE_PHASE3", raising=False)
    monkeypatch.setattr(phase3_runner, "analyze_entity_clarity", lambda name, domain: EntityClarityResult(score=4.0))
    monkeypatch.setattr(
        phase3_runner,
        "assess_external_mentions",
        lambda name, domain, sector=None: ExternalMentionsResult(score=2.0, rationale="weinig"),
    )

    result = run_phase3_automation("Voorbeeld BV", "voorbeeld.nl", None)

    assert "c8_multimodal" in result.errors
    assert result.criterion_scores["c6_entity_clarity"] == 4.0
    assert result.criterion_scores["c7_external_mentions"] == 2.0


def test_disable_phase3_env_var_skips_everything(monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_DISABLE_PHASE3", "1")

    def fail(*args, **kwargs):
        raise AssertionError("mag niet aangeroepen worden als Fase 3 is uitgeschakeld")

    monkeypatch.setattr(phase3_runner, "analyze_entity_clarity", fail)
    monkeypatch.setattr(phase3_runner, "assess_external_mentions", fail)
    monkeypatch.setattr(phase3_runner, "analyze_multimodal_presence", fail)

    result = run_phase3_automation("Voorbeeld BV", "voorbeeld.nl", HTML)

    assert result.criterion_scores == {}
    assert set(result.errors) == {"c6_entity_clarity", "c7_external_mentions", "c8_multimodal"}
