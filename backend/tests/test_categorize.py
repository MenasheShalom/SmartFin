from app.categorize import Categorizer
from app.models import CategorizationRule


def rule(id_, pattern, category_id, priority=0, is_regex=False):
    return CategorizationRule(
        id=id_,
        match_pattern=pattern,
        category_id=category_id,
        priority=priority,
        is_regex=is_regex,
    )


def test_plain_pattern_ignores_case_and_spacing():
    categorizer = Categorizer([rule(1, "super  pharm", 7)])
    assert categorizer.category_for("SUPER   PHARM  TLV") == 7
    assert categorizer.category_for("SUPERPHARM") is None


def test_hebrew_description():
    assert Categorizer([rule(1, "שופרסל", 3)]).category_for("שופרסל דיל  רמת גן") == 3


def test_memo_is_matched_too():
    categorizer = Categorizer([rule(1, "שכר דירה", 4)])
    assert categorizer.category_for("העברה", memo="שכר דירה ספטמבר") == 4
    assert categorizer.category_for("העברה") is None


def test_regex_pattern():
    categorizer = Categorizer([rule(1, r"^(paz|delek)\b", 5, is_regex=True)])
    assert categorizer.category_for("PAZ YELLOW HERZLIYA") == 5
    assert categorizer.category_for("SPAZIO CAFE") is None


def test_longer_pattern_wins_a_priority_tie():
    categorizer = Categorizer([rule(1, "PAYPAL", 1), rule(2, "PAYPAL *SPOTIFY", 2)])
    assert categorizer.category_for("PAYPAL *SPOTIFY 4029357733") == 2
    assert categorizer.category_for("PAYPAL *EBAY") == 1


def test_priority_beats_pattern_length():
    categorizer = Categorizer([rule(1, "PAYPAL", 1, priority=5), rule(2, "PAYPAL *SPOTIFY", 2)])
    assert categorizer.category_for("PAYPAL *SPOTIFY 4029357733") == 1


def test_older_rule_wins_an_exact_tie():
    categorizer = Categorizer([rule(2, "aroma", 2), rule(1, "AROMA", 1)])
    assert categorizer.category_for("Aroma Tel Aviv") == 1
