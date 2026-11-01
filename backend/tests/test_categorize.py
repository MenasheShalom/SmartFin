import re
from datetime import date

from app.categorize import CARD_BILL_PATTERNS, CardBills, Categorizer, SyncedCard
from app.models import AccountType, CategorizationRule


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


def bills(*institutions, first=date(2026, 1, 1), last_synced=date(2026, 9, 30), category_id=99):
    return CardBills(
        category_id,
        [
            SyncedCard(re.compile(CARD_BILL_PATTERNS[i], re.IGNORECASE), first, last_synced)
            for i in institutions
        ],
    )


def test_card_bill_for_a_synced_card_is_a_transfer():
    categorizer = Categorizer([rule(1, "ישראכרט", 7)], bills("isracard", "leumiCards"))
    on = {"account_type": AccountType.BANK, "day": date(2026, 9, 2)}
    assert categorizer.category_for('ישראכרט בע"מ-י', **on) == 99
    assert categorizer.category_for("לאומי מאסטרקרד", **on) == 99
    assert categorizer.category_for("לאומי  ויזה", **on) == 99
    # Not on a card's own statement, and not without the date
    assert categorizer.category_for('ישראכרט בע"מ-י', account_type=AccountType.CREDIT_CARD) == 7
    assert categorizer.category_for('ישראכרט בע"מ-י') == 7


def test_bill_for_a_card_that_isnt_synced_stays_with_the_rules():
    categorizer = Categorizer([rule(1, "כאל", 7)], bills("isracard"))
    assert categorizer.category_for("כאל", account_type=AccountType.BANK, day=date(2026, 9, 2)) == 7
    # Max's old name isn't a Leumi card
    leumi = Categorizer([], bills("leumiCards"))
    on = {"account_type": AccountType.BANK, "day": date(2026, 9, 2)}
    assert leumi.category_for("לאומי קארד", **on) is None


def test_card_bill_only_while_the_card_is_synced():
    synced = bills("isracard", first=date(2026, 3, 5), last_synced=date(2026, 9, 30))
    categorizer = Categorizer([], synced)

    def bill(day):
        return categorizer.category_for("ישראכרט", account_type=AccountType.BANK, day=day)

    assert bill(date(2026, 3, 2)) is None
    assert bill(date(2026, 3, 5)) == 99
    assert bill(date(2026, 10, 1)) == 99  # the sync time is UTC
    assert bill(date(2026, 10, 2)) is None


def test_card_bill_names_need_whole_words():
    categorizer = Categorizer([], bills("visaCal", "max"))
    on = {"account_type": AccountType.BANK, "day": date(2026, 9, 2)}
    assert categorizer.category_for("ויזה כאל", **on) == 99
    assert categorizer.category_for("מקס איט פיננ", **on) == 99
    assert categorizer.category_for("העברה", memo="העברה אל: מיכאל כהן", **on) is None
    assert categorizer.category_for("מקסימום", **on) is None


def test_no_transfers_category_turns_card_bills_off():
    categorizer = Categorizer([], bills("isracard", category_id=None))
    on = {"account_type": AccountType.BANK, "day": date(2026, 9, 2)}
    assert categorizer.category_for("ישראכרט", **on) is None
