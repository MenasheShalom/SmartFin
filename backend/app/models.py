"""Data model from the SmartFin architecture doc."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Money = Numeric(12, 2)


class AccountType(StrEnum):
    BANK = "bank"
    CREDIT_CARD = "credit_card"


class CategoryKind(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    # Money moving between your own accounts, e.g. paying the card bill from the bank.
    # Kept out of spending so a card purchase isn't counted twice.
    TRANSFER = "transfer"


class AlertType(StrEnum):
    OVERSPEND = "overspend"
    LOW_BALANCE = "low_balance"
    UNUSUAL_TRANSACTION = "unusual_transaction"
    SCRAPE_FAILURE = "scrape_failure"


class ScrapeStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class Account(Base):
    """One bank or card connection that gets scraped."""

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("institution", "account_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # israeli-bank-scrapers company id, e.g. "leumi", "visaCal"
    institution: Mapped[str] = mapped_column(String(50))
    # As the scraper reports it; one login can return several accounts
    account_number: Mapped[str] = mapped_column(String(64))
    account_type: Mapped[AccountType] = mapped_column(String(20))
    balance: Mapped[Decimal | None] = mapped_column(Money)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("parent_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # Self-reference for subcategories, e.g. Food -> Groceries
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    # Subcategories share their parent's kind
    kind: Mapped[CategoryKind] = mapped_column(
        String(20), default=CategoryKind.EXPENSE, server_default=CategoryKind.EXPENSE
    )

    parent: Mapped["Category | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Category"]] = relationship(back_populates="parent")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("account_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    # Stable hash of the scraped fields; re-scraping the same transaction yields the same id
    external_id: Mapped[str] = mapped_column(String(64))
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="ILS")
    description: Mapped[str] = mapped_column(Text)
    # The scraper's original text, kept so rules can re-categorize later
    raw_description: Mapped[str] = mapped_column(Text)
    # Extra detail some banks put here, e.g. who a transfer went to
    memo: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    # Set by hand: rules never overwrite it
    category_manual: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)

    account: Mapped[Account] = relationship(back_populates="transactions")
    category: Mapped[Category | None] = relationship()


class CategorizationRule(Base):
    """String/regex match against raw_description and memo, applied on ingest."""

    __tablename__ = "categorization_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_pattern: Mapped[str] = mapped_column(String(255))
    # Plain patterns match anywhere in the text, ignoring case and extra spaces
    is_regex: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # Higher priority wins when several rules match
    priority: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category] = relationship()


class Budget(Base):
    """One row per category per month."""

    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("category_id", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # First day of the month
    month: Mapped[date] = mapped_column(Date)
    limit_amount: Mapped[Decimal] = mapped_column(Money)

    category: Mapped[Category] = relationship()


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[AlertType] = mapped_column(String(30))
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    message: Mapped[str] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    # Identifies what the alert is about, so the same thing never alerts twice,
    # e.g. "budget:2026-09:5:100" or "low_balance:3:2026-W39"
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    # When Telegram/email delivery succeeded; unset alerts are retried after the next sync
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScrapeRun(Base):
    """Audit trail for debugging scraper breakage: one row per login attempt."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution: Mapped[str] = mapped_column(String(50), index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ScrapeStatus] = mapped_column(String(20), default=ScrapeStatus.RUNNING)
    transactions_added: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
