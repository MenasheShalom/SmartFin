from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.labels import institution_label, masked
from app.models import Account, AccountType, ScrapeRun, ScrapeStatus
from app.routers.common import SessionDep

router = APIRouter(prefix="/api", tags=["accounts"])


class AccountOut(BaseModel):
    id: int
    institution: str
    institution_label: str
    account_number: str
    account_type: AccountType
    balance: Decimal | None
    last_synced_at: datetime | None


class SyncStatus(BaseModel):
    institution: str
    institution_label: str
    status: ScrapeStatus
    finished_at: datetime | None
    error_message: str | None
    # The latest successful sync, which may be older than the latest attempt
    last_success_at: datetime | None


@router.get("/accounts")
def list_accounts(session: SessionDep) -> list[AccountOut]:
    accounts = session.scalars(select(Account).order_by(Account.account_type, Account.institution))
    return [
        AccountOut(
            id=a.id,
            institution=a.institution,
            institution_label=institution_label(a.institution),
            account_number=masked(a.account_number),
            account_type=a.account_type,
            balance=a.balance,
            last_synced_at=a.last_synced_at,
        )
        for a in accounts
    ]


@router.get("/sync-status")
def sync_status(session: SessionDep) -> list[SyncStatus]:
    """The latest login attempt for each institution."""
    latest_ids = select(func.max(ScrapeRun.id)).group_by(ScrapeRun.institution)
    runs = session.scalars(select(ScrapeRun).where(ScrapeRun.id.in_(latest_ids)))
    last_success = dict(
        session.execute(
            select(ScrapeRun.institution, func.max(ScrapeRun.finished_at))
            .where(ScrapeRun.status == ScrapeStatus.SUCCESS)
            .group_by(ScrapeRun.institution)
        ).all()
    )
    return sorted(
        (
            SyncStatus(
                institution=r.institution,
                institution_label=institution_label(r.institution),
                status=r.status,
                finished_at=r.finished_at,
                error_message=r.error_message,
                last_success_at=last_success.get(r.institution),
            )
            for r in runs
        ),
        key=lambda s: s.institution_label,
    )
