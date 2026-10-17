from pipeline.decisions import decide

BASE = dict(score=8, is_urgent=False, is_sensitive=False, has_official_source=False, verified_ok=True,
            verifier_confidence=0.95, issues=[], insufficient_facts=False, auto_publish_enabled=True,
            auto_publish_min_score=7, min_confidence=0.8)


def d(**kw):
    return decide(**{**BASE, **kw})


def test_high_score_clean_check_publishes():
    assert d().publish


def test_sensitive_always_goes_to_review():
    assert not d(is_sensitive=True, is_urgent=True, has_official_source=True, score=10).publish


def test_verifier_doubt_goes_to_review():
    decision = d(verified_ok=False, issues=["Цифра 40 миль не совпадает с источником"])
    assert not decision.publish and "40 миль" in decision.reason


def test_issues_even_with_ok_go_to_review():
    assert not d(issues=["имя частного лица"]).publish


def test_low_confidence_goes_to_review():
    assert not d(verifier_confidence=0.6).publish


def test_low_score_goes_to_review():
    assert not d(score=6).publish


def test_urgent_official_publishes_even_with_lower_score():
    assert d(score=5, is_urgent=True, has_official_source=True).publish


def test_urgent_without_official_source_follows_score():
    assert not d(score=5, is_urgent=True, has_official_source=False).publish


def test_auto_publish_switch():
    assert not d(auto_publish_enabled=False).publish


def test_insufficient_facts_goes_to_review():
    assert not d(insufficient_facts=True).publish


def test_publish_without_review_overrides_review():
    decision = d(is_sensitive=True, verified_ok=False, issues=["x"], publish_without_review=True)
    assert decision.publish and "Чувствительная" in decision.reason


def test_publish_without_review_keeps_normal_publish_reason():
    assert d(publish_without_review=True).reason.startswith("Важность")
