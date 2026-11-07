"""Automatic categorization: card bills first, then the first matching rule.

Card bills: a bank-account transaction that pays a credit card SmartFin also syncs ("ישראכרט",
"לאומי מאסטרקרד") is marked as a card bill, which keeps it out of the cash flow: the card's own
purchases are already counted, and counting the bill too would count that spending twice. It is
also filed under the category earlier card bills are in. A bill for a card that isn't synced is
left to the rules and counts, since it is the only record of that spending. A card counts as
synced for bills dated from its first transaction to its last sync.

Rules are tried by priority (highest first), then longest pattern first so a specific rule
("PAYPAL *SPOTIFY") beats a broad one ("PAYPAL"), then oldest first. Plain patterns match
anywhere in the text, ignoring case and extra spaces; regex patterns ignore case.

A category set by hand is never changed by any of this.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    AccountType,
    CategorizationRule,
    Transaction,
)

# How each card company's bill reads in a bank account, by the scraper's institution id
CARD_BILL_PATTERNS = {
    "isracard": r"ישראכרט",
    "amex": r"אמריקן\s*אקספרס|\bamex\b",
    "visaCal": r"\bכאל\b|כ\.א\.ל",
    "max": r"מקס\s*איט|לאומי\s*קארד|\bmax\s*it\b",
    "leumiCards": r"לאומי\s*(ויזה|מאסטרקרד|מסטרקרד)",
}

# The bank's dates are Israel dates and the sync time is UTC: allow for the midnight gap
SYNC_DAY_SLACK = timedelta(days=1)


def normalize(text: str) -> str:
    return " ".join(text.split())


def rule_order(rule: CategorizationRule) -> tuple[int, int, int]:
    return (-rule.priority, -len(rule.match_pattern), rule.id)


def check_pattern(pattern: str, is_regex: bool) -> None:
    """Raise ValueError for a rule pattern that can't work."""
    if is_regex:
        try:
            re.compile(pattern)
        except re.error as err:
            raise ValueError(f"Invalid regular expression: {err}") from err
    elif not normalize(pattern):
        raise ValueError("Pattern is blank")


@dataclass(frozen=True)
class CompiledRule:
    category_id: int
    regex: re.Pattern[str] | None
    needle: str

    def matches(self, text: str, folded: str) -> bool:
        if self.regex is not None:
            return self.regex.search(text) is not None
        return self.needle in folded


@dataclass(frozen=True)
class SyncedCard:
    """A card company whose transactions SmartFin has, from `first` to `last_synced`."""

    bill: re.Pattern[str]
    first: date
    last_synced: date

    def paid_by(self, text: str, day: date) -> bool:
        return self.first <= day <= self.last_synced + SYNC_DAY_SLACK and bool(
            self.bill.search(text)
        )


class CardBills:
    def __init__(self, category_id: int | None, cards: Iterable[SyncedCard]):
        # Where card bills are filed (where the latest one is); None leaves them to the rules
        self.category_id = category_id
        self.cards = list(cards)

    @classmethod
    def load(cls, session: Session) -> "CardBills":
        category_id = session.scalar(
            select(Transaction.category_id)
            .where(
                Transaction.card_bill.is_(True),
                Transaction.category_manual.is_(False),
                Transaction.category_id.is_not(None),
            )
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(1)
        )
        first_txn, last_synced = func.min(Transaction.date), func.max(Account.last_synced_at)
        coverage = session.execute(
            select(Account.institution, first_txn, last_synced)
            .join(Transaction, Transaction.account_id == Account.id)
            .where(Account.account_type == AccountType.CREDIT_CARD)
            .group_by(Account.institution)
        )
        cards = [
            SyncedCard(
                re.compile(CARD_BILL_PATTERNS[institution], re.IGNORECASE), first, synced.date()
            )
            for institution, first, synced in coverage
            if institution in CARD_BILL_PATTERNS and synced is not None
        ]
        return cls(category_id, cards)

    def is_bill(self, text: str, day: date) -> bool:
        return any(card.paid_by(text, day) for card in self.cards)


class Categorizer:
    def __init__(
        self,
        rules: Iterable[CategorizationRule],
        card_bills: CardBills | None = None,
        account_types: dict[int, AccountType] | None = None,
    ):
        self.rules = [
            CompiledRule(
                category_id=rule.category_id,
                regex=re.compile(rule.match_pattern, re.IGNORECASE) if rule.is_regex else None,
                needle=normalize(rule.match_pattern).casefold(),
            )
            for rule in sorted(rules, key=rule_order)
        ]
        self.card_bills = card_bills
        self.account_types = account_types or {}

    @classmethod
    def load(cls, session: Session) -> "Categorizer":
        return cls(
            session.scalars(select(CategorizationRule)),
            CardBills.load(session),
            {id_: kind for id_, kind in session.execute(select(Account.id, Account.account_type))},
        )

    def category_for(
        self,
        description: str,
        memo: str | None = None,
        *,
        account_type: AccountType | None = None,
        day: date | None = None,
    ) -> int | None:
        """Card bills need the account type and date; without them only the rules apply."""
        text = normalize(f"{description} {memo or ''}")
        if self.card_bills and self.card_bills.category_id is not None:
            if self.is_card_bill(description, memo, account_type=account_type, day=day):
                return self.card_bills.category_id
        folded = text.casefold()
        for rule in self.rules:
            if rule.matches(text, folded):
                return rule.category_id
        return None

    def is_card_bill(
        self,
        description: str,
        memo: str | None = None,
        *,
        account_type: AccountType | None = None,
        day: date | None = None,
    ) -> bool:
        """A bank payment of a card SmartFin syncs: kept out of the cash flow"""
        if not self.card_bills or account_type != AccountType.BANK or day is None:
            return False
        return self.card_bills.is_bill(normalize(f"{description} {memo or ''}"), day)

    def card_bill_of(self, txn: Transaction) -> bool:
        return self.is_card_bill(
            txn.raw_description,
            txn.memo,
            account_type=self.account_types.get(txn.account_id),
            day=txn.date,
        )

    def category_of(self, txn: Transaction) -> int | None:
        """For a stored transaction."""
        return self.category_for(
            txn.raw_description,
            txn.memo,
            account_type=self.account_types.get(txn.account_id),
            day=txn.date,
        )


def apply_rules(session: Session) -> int:
    """Work out which transactions are card bills, then re-categorize every transaction not
    categorized by hand: card bills, then the rules.

    Returns how many transactions changed category. The caller commits.
    """
    session.flush()
    categorizer = Categorizer.load(session)
    for txn in session.scalars(select(Transaction)):
        txn.card_bill = categorizer.card_bill_of(txn)
    session.flush()
    # The card bills' category follows the marks just worked out
    categorizer = Categorizer.load(session)
    changed = 0
    automatic = select(Transaction).where(Transaction.category_manual.is_(False))
    for txn in session.scalars(automatic):
        category_id = categorizer.category_of(txn)
        if txn.category_id != category_id:
            txn.category_id = category_id
            changed += 1
    session.flush()
    return changed
