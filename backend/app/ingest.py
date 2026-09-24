"""Turn a scraper result into accounts, transactions and a scrape_runs row."""

import hashlib
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountType, ScrapeRun, ScrapeStatus, Transaction

# israeli-bank-scrapers company ids that are card issuers rather than banks
CARD_COMPANIES = {"amex", "behatsdaa", "beyahadBishvilha", "isracard", "max", "visaCal"}

CENT = Decimal("0.01")


class Installments(BaseModel):
    number: int
    total: int


class ScrapedTransaction(BaseModel):
    """One transaction as israeli-bank-scrapers returns it."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    identifier: str | int | None = None
    date: datetime
    charged_amount: Decimal = Field(alias="chargedAmount")
    charged_currency: str | None = Field(default=None, alias="chargedCurrency")
    description: str
    memo: str | None = None
    status: str = "completed"
    installments: Installments | None = None


class ScrapedAccount(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    account_number: str = Field(alias="accountNumber")
    balance: Decimal | None = None
    txns: list[ScrapedTransaction] = []


class ScrapeResult(BaseModel):
    """What the scraper posts after one login attempt."""

    institution: str
    started_at: datetime
    finished_at: datetime
    success: bool
    error_type: str | None = None
    error_message: str | None = None
    accounts: list[ScrapedAccount] = []


class IngestSummary(BaseModel):
    run_id: int
    status: ScrapeStatus
    accounts: int = 0
    added: int = 0
    duplicates: int = 0
    pending_skipped: int = 0


def local_date(value: datetime, tz: ZoneInfo) -> date:
    """Scrapers report local midnight as a UTC timestamp; recover the local calendar date."""
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(tz).date()


def clean_description(text: str) -> str:
    return " ".join(text.split())


def external_ids(txns: list[ScrapedTransaction], tz: ZoneInfo) -> list[str]:
    """Stable ids for a batch of one account's transactions.

    Identical rows (two equal coffees on the same day) get an occurrence number so both are kept.
    That stays stable across re-scrapes because every scrape covers whole days.
    """
    seen: Counter[str] = Counter()
    ids = []
    for txn in txns:
        base = "\x1f".join(
            [
                local_date(txn.date, tz).isoformat(),
                str(txn.charged_amount.quantize(CENT)),
                txn.charged_currency or "ILS",
                clean_description(txn.description),
                clean_description(txn.memo or ""),
                str(txn.identifier or ""),
                str(txn.installments.number) if txn.installments else "",
            ]
        )
        occurrence = seen[base]
        seen[base] += 1
        ids.append(hashlib.sha256(f"{base}\x1f{occurrence}".encode()).hexdigest())
    return ids


def get_or_create_account(session: Session, institution: str, account_number: str) -> Account:
    account = session.scalars(
        select(Account).where(
            Account.institution == institution, Account.account_number == account_number
        )
    ).one_or_none()
    if account is None:
        account_type = (
            AccountType.CREDIT_CARD if institution in CARD_COMPANIES else AccountType.BANK
        )
        account = Account(
            institution=institution, account_number=account_number, account_type=account_type
        )
        session.add(account)
        session.flush()
    return account


def ingest(session: Session, result: ScrapeResult, tz: ZoneInfo) -> IngestSummary:
    run = ScrapeRun(
        institution=result.institution,
        started_at=result.started_at,
        finished_at=result.finished_at,
    )
    session.add(run)

    if not result.success:
        run.status = ScrapeStatus.FAILED
        run.error_message = ": ".join(
            part for part in (result.error_type, result.error_message) if part
        ) or "unknown error"
        session.commit()
        return IngestSummary(run_id=run.id, status=run.status)

    summary = IngestSummary(run_id=0, status=ScrapeStatus.SUCCESS, accounts=len(result.accounts))
    for scraped in result.accounts:
        account = get_or_create_account(session, result.institution, scraped.account_number)
        if scraped.balance is not None:
            account.balance = scraped.balance
        account.last_synced_at = result.finished_at

        # Pending charges can still change amount or date, so only settled ones are stored.
        completed = [t for t in scraped.txns if t.status != "pending"]
        summary.pending_skipped += len(scraped.txns) - len(completed)

        ids = external_ids(completed, tz)
        existing = set(
            session.scalars(
                select(Transaction.external_id).where(
                    Transaction.account_id == account.id, Transaction.external_id.in_(ids)
                )
            )
        )
        for txn, external_id in zip(completed, ids, strict=True):
            if external_id in existing:
                summary.duplicates += 1
                continue
            session.add(
                Transaction(
                    account_id=account.id,
                    external_id=external_id,
                    date=local_date(txn.date, tz),
                    amount=txn.charged_amount.quantize(CENT),
                    currency=txn.charged_currency or "ILS",
                    description=clean_description(txn.description),
                    raw_description=txn.description,
                )
            )
            summary.added += 1

    run.status = ScrapeStatus.SUCCESS
    run.transactions_added = summary.added
    session.commit()
    summary.run_id = run.id
    return summary
