from datetime import date
from decimal import Decimal
from itertools import count

from app.models import Account, AccountType, Category, CategoryKind, Transaction

_ids = count(1)


def make_account(session, institution="leumi") -> Account:
    account = Account(
        institution=institution,
        account_number=f"acct-{next(_ids)}",
        account_type=AccountType.BANK,
    )
    session.add(account)
    session.flush()
    return account


def make_category(session, name, parent=None, kind=CategoryKind.EXPENSE) -> Category:
    category = Category(
        name=name,
        parent_id=parent.id if parent else None,
        kind=parent.kind if parent else kind,
    )
    session.add(category)
    session.flush()
    return category


def make_txn(
    session,
    account,
    description,
    amount,
    day=date(2026, 9, 5),
    memo=None,
    category=None,
    manual=False,
) -> Transaction:
    txn = Transaction(
        account_id=account.id,
        external_id=f"ext-{next(_ids)}",
        date=day,
        amount=Decimal(str(amount)),
        description=" ".join(description.split()),
        raw_description=description,
        memo=memo,
        category_id=category.id if category else None,
        category_manual=manual,
    )
    session.add(txn)
    session.flush()
    return txn
