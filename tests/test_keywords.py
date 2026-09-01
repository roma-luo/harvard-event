from harvard_events.core.keywords import DESCRIPTION_WINDOW, KeywordEngine

SPEC = {
    "groups": [
        {
            "name": "machine_learning",
            "weight": 6,
            "terms": ["machine learning", "deep learning"],
            "acronyms": ["ML", "AI"],
        },
        {
            "name": "hci",
            "weight": 4,
            "terms": ["human-computer interaction"],
            "acronyms": ["HCI"],
        },
    ],
    "negative": [
        {"name": "recruiting", "weight": -10, "terms": ["info session"], "acronyms": []}
    ],
}


def engine():
    return KeywordEngine(SPEC)


def test_acronym_respects_word_boundaries():
    # "AI" must not fire inside Chair / Thai / Retail / Sustainability.
    total, hits = engine().evaluate(
        "The Chair of Thai Retail Sustainability", None, None, ""
    )
    assert total == 0
    assert hits == []


def test_acronym_is_case_sensitive():
    total, _ = engine().evaluate("Designing with ai in mind", None, None, "")
    assert total == 0
    total, _ = engine().evaluate("Designing with AI in mind", None, None, "")
    assert total == 6


def test_all_caps_title_downgrades_acronym_case():
    # An all-caps title carries no case information; AI matches case-insensitively.
    total, hits = engine().evaluate("DESIGNING WITH AI IN MIND", None, None, "")
    assert total == 6
    assert hits[0].group == "machine_learning"


def test_synonym_group_scores_once():
    total, hits = engine().evaluate(
        "Machine learning and deep learning: an ML tutorial", None, None, ""
    )
    assert total == 6
    assert len(hits) == 1


def test_hyphen_and_space_variants():
    total, _ = engine().evaluate("A talk on human computer interaction", None, None, "")
    assert total == 4


def test_negative_group():
    total, hits = engine().evaluate("Employer info session", None, None, "")
    assert total == -10


def test_match_window_covers_series_and_speaker():
    total, _ = engine().evaluate(
        "Weekly talk", "Machine Learning Seminar", None, ""
    )
    assert total == 6
    total, _ = engine().evaluate("Weekly talk", None, "Prof. ML Expert", "")
    assert total == 6


def test_description_window_is_capped():
    far_away = "x " * (DESCRIPTION_WINDOW + 50) + "machine learning"
    total, _ = engine().evaluate("Weekly talk", None, None, far_away)
    assert total == 0
    near = "machine learning " + "x " * (DESCRIPTION_WINDOW + 50)
    total, _ = engine().evaluate("Weekly talk", None, None, near)
    assert total == 6
