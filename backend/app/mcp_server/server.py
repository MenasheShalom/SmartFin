"""SmartFin's MCP server: lets Claude read your cash flow, transactions, budgets and history.

Read-only: on Postgres every query runs in a read-only transaction, and there are no tools that
change anything. Run it with  python -m app.mcp_server  (the "mcp" service in docker-compose).
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.budgeting import BudgetSummary, money, summarize
from app.cashflow import CashFlow, compute
from app.config import Settings
from app.history import MonthHistory, monthly_history
from app.labels import institution_label, masked
from app.mcp_server.oauth import SCOPE, SmartFinOAuthProvider
from app.models import Account, Category, CategoryKind, Transaction
from app.months import MONTH_PATTERN, get_today, next_month, parse_month
from app.routers.accounts import AccountOut, SyncStatus, list_accounts, sync_status
from app.routers.categories import tree_order
from app.routers.transactions import query_transactions

INSTRUCTIONS = """\
SmartFin is the user's personal cash-flow app for their Israeli bank and credit-card accounts.
Amounts are in ILS (₪). On transactions, negative amounts are money out and positive are money in.
Category and account names are in Hebrew; answer in the user's language.
Categories have a kind: expense (fixed bills or day-to-day spending), income, or transfer (money
between the user's own accounts, such as paying the card bill from the bank; never spending).
Uncategorized transactions are left out of the cash-flow and budget numbers and counted separately.
Weeks run Sunday to Saturday. Months are written YYYY-MM. Start with get_cash_flow for questions
about this month, and get_history for trends."""

Month = Annotated[str | None, Field(pattern=MONTH_PATTERN, description="YYYY-MM; default: this month")]


class CategoryInfo(BaseModel):
    id: int
    name: str
    parent: str | None
    kind: CategoryKind
    is_fixed: bool


class TransactionInfo(BaseModel):
    id: int
    date: date
    amount: Decimal
    currency: str
    description: str
    memo: str | None
    category: str | None
    account: str


class CategoryTotal(BaseModel):
    category_id: int | None
    name: str
    kind: CategoryKind | None
    # Money out is positive for expenses; for income and transfers, the net amount
    total: Decimal
    count: int


class Accounts(BaseModel):
    accounts: list[AccountOut]
    sync: list[SyncStatus]


def build_server(engine: Engine, settings: Settings) -> MCPServer:
    if not settings.mcp_public_url:
        raise SystemExit("Set MCP_PUBLIC_URL to the HTTPS address Claude will reach this server at")
    public_url = settings.mcp_public_url.rstrip("/")
    provider = SmartFinOAuthProvider(
        sessionmaker(bind=engine, expire_on_commit=False), public_url, settings.mcp_redirect_uri_list
    )
    # The data tools can only read
    reader = sessionmaker(bind=engine.execution_options(postgresql_readonly=True))

    server = MCPServer(
        name="SmartFin",
        instructions=INSTRUCTIONS,
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=public_url,
            resource_server_url=f"{public_url}/mcp",
            validate_token_resource=True,
            required_scopes=[SCOPE],
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]
            ),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )

    def today() -> date:
        return get_today(settings)

    def first_of(month: str | None) -> date:
        return parse_month(month) if month else today().replace(day=1)

    @server.tool(annotations={"readOnlyHint": True})
    def get_cash_flow(month: Month = None) -> CashFlow:
        """The month's cash-flow plan and where it stands: expected and received income, fixed
        bills (paid or expected), the savings goal, the budget left for day-to-day spending,
        the end-of-month forecast, and each week's allowance and spending."""
        with reader() as session:
            return compute(session, first_of(month), today())

    @server.tool(annotations={"readOnlyHint": True})
    def get_history() -> list[MonthHistory]:
        """Income, expenses, net and end-of-month bank balance for every month, oldest first.
        The current month is partial."""
        with reader() as session:
            return monthly_history(session, today())

    @server.tool(annotations={"readOnlyHint": True})
    def get_budgets(month: Month = None) -> BudgetSummary:
        """Spending against each category's monthly budget, month to date."""
        with reader() as session:
            return summarize(session, first_of(month), today())

    @server.tool(annotations={"readOnlyHint": True})
    def spending_by_category(
        month: Month = None,
        date_from: Annotated[date | None, Field(description="Instead of month: first day")] = None,
        date_to: Annotated[date | None, Field(description="Instead of month: last day")] = None,
    ) -> list[CategoryTotal]:
        """Totals per category (subcategories separately) for a month or a date range, largest
        spending first. Uncategorized transactions are one line with no category id."""
        if date_from or date_to:
            first, last = date_from or date.min, date_to or date.max
        else:
            first = first_of(month)
            last = date.fromordinal(next_month(first).toordinal() - 1)
        with reader() as session:
            categories = {c.id: c for c in session.scalars(select(Category))}
            rows = session.execute(
                select(Transaction.category_id, func.sum(Transaction.amount), func.count())
                .where(Transaction.date >= first, Transaction.date <= last)
                .group_by(Transaction.category_id)
            )
            totals = []
            for category_id, total, count in rows:
                category = categories.get(category_id)
                kind = category.kind if category else None
                net = money(total)
                totals.append(
                    CategoryTotal(
                        category_id=category_id,
                        name=category.name if category else "לא מסווג",
                        kind=kind,
                        total=-net if kind == CategoryKind.EXPENSE else net,
                        count=count,
                    )
                )
        order = {CategoryKind.EXPENSE: 0, None: 1, CategoryKind.INCOME: 2, CategoryKind.TRANSFER: 3}
        return sorted(totals, key=lambda t: (order[t.kind], -t.total))

    @server.tool(annotations={"readOnlyHint": True})
    def search_transactions(
        query: Annotated[
            str | None, Field(max_length=100, description="Text in the description or memo")
        ] = None,
        month: Annotated[str | None, Field(pattern=MONTH_PATTERN, description="YYYY-MM")] = None,
        date_from: date | None = None,
        date_to: date | None = None,
        category_id: Annotated[
            int | None, Field(description="From list_categories; includes subcategories")
        ] = None,
        account_id: Annotated[int | None, Field(description="From list_accounts")] = None,
        uncategorized: bool = False,
        limit: Annotated[int, Field(ge=1, le=500)] = 50,
        offset: Annotated[int, Field(ge=0)] = 0,
    ) -> list[TransactionInfo]:
        """Transactions, newest first, filtered by any combination of text, month or dates,
        category and account."""
        with reader() as session:
            categories = {c.id: c.name for c in session.scalars(select(Category))}
            accounts = {
                a.id: f"{institution_label(a.institution)} {masked(a.account_number)}"
                for a in session.scalars(select(Account))
            }
            found = query_transactions(
                session,
                month=month,
                account_id=account_id,
                category_id=category_id,
                uncategorized=uncategorized,
                date_from=date_from,
                date_to=date_to,
                q=query,
                limit=limit,
                offset=offset,
            )
            return [
                TransactionInfo(
                    id=t.id,
                    date=t.date,
                    amount=money(t.amount),
                    currency=t.currency,
                    description=t.description,
                    memo=t.memo,
                    category=categories.get(t.category_id) if t.category_id else None,
                    account=accounts[t.account_id],
                )
                for t in found
            ]

    @server.tool(annotations={"readOnlyHint": True})
    def list_categories() -> list[CategoryInfo]:
        """Every category, each parent followed by its subcategories."""
        with reader() as session:
            categories = list(session.scalars(select(Category)))
            names = {c.id: c.name for c in categories}
            return [
                CategoryInfo(
                    id=c.id,
                    name=c.name,
                    parent=names.get(c.parent_id) if c.parent_id else None,
                    kind=c.kind,
                    is_fixed=c.is_fixed,
                )
                for c in tree_order(categories)
            ]

    @server.tool(annotations={"readOnlyHint": True})
    def list_accounts_and_sync() -> Accounts:
        """The bank and card accounts with their balances, and how each one's last sync went."""
        with reader() as session:
            return Accounts(accounts=list_accounts(session), sync=sync_status(session))

    server.custom_route("/login", methods=["GET", "POST"])(provider.login_page)

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok"})

    return server


def build_app(engine: Engine, settings: Settings) -> Starlette:
    # Behind a tunnel or proxy the Host header is the public name, so allow any host; the
    # bearer token is what protects /mcp.
    return build_server(engine, settings).streamable_http_app(host="0.0.0.0")
