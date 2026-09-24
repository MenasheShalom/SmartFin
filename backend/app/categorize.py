"""Rule-based categorization: the first matching rule decides a transaction's category.

Rules are tried by priority (highest first), then longest pattern first so a specific rule
("PAYPAL *SPOTIFY") beats a broad one ("PAYPAL"), then oldest first. Plain patterns match
anywhere in the text, ignoring case and extra spaces; regex patterns ignore case.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CategorizationRule, Transaction


def normalize(text: str) -> str:
    return " ".join(text.split())


def rule_order(rule: CategorizationRule) -> tuple[int, int, int]:
    return (-rule.priority, -len(rule.match_pattern), rule.id)


@dataclass(frozen=True)
class CompiledRule:
    category_id: int
    regex: re.Pattern[str] | None
    needle: str

    def matches(self, text: str, folded: str) -> bool:
        if self.regex is not None:
            return self.regex.search(text) is not None
        return self.needle in folded


class Categorizer:
    def __init__(self, rules: Iterable[CategorizationRule]):
        self.rules = [
            CompiledRule(
                category_id=rule.category_id,
                regex=re.compile(rule.match_pattern, re.IGNORECASE) if rule.is_regex else None,
                needle=normalize(rule.match_pattern).casefold(),
            )
            for rule in sorted(rules, key=rule_order)
        ]

    @classmethod
    def load(cls, session: Session) -> "Categorizer":
        return cls(session.scalars(select(CategorizationRule)))

    def category_for(self, description: str, memo: str | None = None) -> int | None:
        text = normalize(f"{description} {memo or ''}")
        folded = text.casefold()
        for rule in self.rules:
            if rule.matches(text, folded):
                return rule.category_id
        return None


def apply_rules(session: Session) -> int:
    """Re-run the rules over every transaction not categorized by hand.

    Returns how many transactions changed category. The caller commits.
    """
    categorizer = Categorizer.load(session)
    changed = 0
    automatic = select(Transaction).where(Transaction.category_manual.is_(False))
    for txn in session.scalars(automatic):
        category_id = categorizer.category_for(txn.raw_description, txn.memo)
        if txn.category_id != category_id:
            txn.category_id = category_id
            changed += 1
    session.flush()
    return changed
