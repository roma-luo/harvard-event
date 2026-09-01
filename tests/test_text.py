from harvard_events.core.text import (
    clean,
    extract_markers,
    is_all_caps,
    normalize_title,
    split_series_prefix,
)


def test_clean_unescapes_double_encoded_entities():
    # double-encoded apostrophe: &amp;#x27; -> &#x27; -> '
    assert clean("it&amp;#x27;s") == "it's"
    assert clean("a&nbsp;b") == "a b"
    assert clean("<p>Hello <b>world</b></p>") == "Hello world"


def test_clean_folds_full_width_punctuation():
    assert clean("讲座：建筑") == "讲座:建筑"


def test_extract_markers():
    title, marker = extract_markers("CANCELLED: Kenzō Tange Lecture")
    assert marker == "CANCELLED"
    assert "CANCELLED" not in title
    assert "Tange" in title
    assert extract_markers("A normal title") == ("A normal title", None)


def test_split_series_prefix():
    title, series = split_series_prefix("CSAIL Seminar Series | Dataset Distillation")
    assert series == "CSAIL Seminar Series"
    assert title == "Dataset Distillation"


def test_split_series_prefix_keeps_real_colon_titles():
    # "Dataset Distillation" has no series hint word, so no split.
    title, series = split_series_prefix("Dataset Distillation: Fundamentals")
    assert series is None
    assert title == "Dataset Distillation: Fundamentals"


def test_is_all_caps():
    assert is_all_caps("THE FUTURE OF HOUSING")
    assert not is_all_caps("The Future of Housing")
    assert not is_all_caps("AI")  # too short to judge


def test_normalize_title_strips_series_and_punctuation():
    a = normalize_title("CSAIL Seminar Series | Dataset Distillation!")
    b = normalize_title("dataset distillation")
    assert a == b
