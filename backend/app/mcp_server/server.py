"""SmartFin's MCP server: lets Claude read your cash flow, transactions, budgets and history,
and categorize transactions.

The reading tools run in read-only transactions on Postgres. The only tools that change anything
are categorize_transactions and add_rule, and all they change is which category a transaction
has and the categorization rules. Run it with  python -m app.mcp_server  (the "mcp" service in
docker-compose).
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.budgeting import BudgetSummary, money, summarize
from app.cashflow import CashFlow, compute
from app.categorize import Categorizer, apply_rules, check_pattern, normalize, rule_order
from app.config import Settings
from app.history import MonthHistory, monthly_history
from app.labels import institution_label, masked
from app.mcp_server.oauth import SCOPE, SmartFinOAuthProvider
from app.models import Account, CategorizationRule, Category, CategoryKind, Transaction
from app.months import MONTH_PATTERN, get_today, next_month, parse_month
from app.routers.accounts import AccountOut, SyncStatus, list_accounts, sync_status
from app.routers.categories import tree_order
from app.routers.transactions import learn_rule, query_transactions

INSTRUCTIONS = """\
SmartFin is the user's personal cash-flow app for their Israeli bank and credit-card accounts.
Amounts are in ILS (₪). On transactions, negative amounts are money out and positive are money in.
Category and account names are in Hebrew; answer in the user's language.
Categories have a kind: expense (fixed bills or day-to-day spending), income, or transfer (money
between the user's own accounts, such as paying the card bill from the bank; never spending).
Uncategorized transactions are left out of the cash-flow and budget numbers and counted separately.
Weeks run Sunday to Saturday. Months are written YYYY-MM. Start with get_cash_flow for questions
about this month, and get_history for trends.

To categorize: find the transactions with search_transactions (uncategorized=true for the ones
with no category), pick categories from list_categories, and set them with
categorize_transactions. When a merchant will come back, also teach a rule (create_rule, or
add_rule for a pattern that covers its variants, after checking list_rules) so future syncs
categorize it on their own. Rules never change a category that was set by hand. Before changing
many transactions or adding a broad rule, show the user what you plan unless they already told
you to go ahead."""

Month = Annotated[str | None, Field(pattern=MONTH_PATTERN, description="YYYY-MM; default: this month")]
Pattern = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
# Changes a category or a rule, both of which can be changed back; never deletes anything
WRITES = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True}


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


class RuleInfo(BaseModel):
    id: int
    match_pattern: str
    is_regex: bool
    category_id: int
    category: str
    priority: int


class CategorizedTransaction(BaseModel):
    id: int
    date: date
    amount: Decimal
    description: str
    category: str | None
    # Set by hand, so rules leave it alone; false once handed back to the rules
    category_manual: bool


class Categorized(BaseModel):
    transactions: list[CategorizedTransaction]
    # Rules added, or existing ones pointed at the new category (create_rule)
    rules: list[RuleInfo]
    # Other transactions those rules moved
    recategorized: int


class RuleSaved(BaseModel):
    rule: RuleInfo
    # True when a rule with the same pattern existed and was changed instead of adding another
    replaced_existing: bool
    # Transactions the rules moved (never ones categorized by hand)
    recategorized: int


def rule_info(session: Session, rule: CategorizationRule) -> RuleInfo:
    return RuleInfo(
        id=rule.id,
        match_pattern=rule.match_pattern,
        is_regex=rule.is_regex,
        category_id=rule.category_id,
        category=session.get(Category, rule.category_id).name,
        priority=rule.priority,
    )


def known_category(session: Session, category_id: int) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise ToolError(f"No category with id {category_id}; see list_categories")
    return category


def same_rule(session: Session, pattern: str, is_regex: bool) -> CategorizationRule | None:
    """A rule that already matches exactly what this pattern would."""
    key = pattern if is_regex else normalize(pattern).casefold()
    for rule in session.scalars(
        select(CategorizationRule).where(CategorizationRule.is_regex.is_(is_regex))
    ):
        if (rule.match_pattern if is_regex else normalize(rule.match_pattern).casefold()) == key:
            return rule
    return None


def build_server(engine: Engine, settings: Settings) -> MCPServer:
    if not settings.mcp_public_url:
        raise SystemExit("Set MCP_PUBLIC_URL to the HTTPS address Claude will reach this server at")
    public_url = settings.mcp_public_url.rstrip("/")
    provider = SmartFinOAuthProvider(
        sessionmaker(bind=engine, expire_on_commit=False), public_url, settings.mcp_redirect_uri_list
    )
    # The reading tools can only read; only the categorizing tools use the writer
    reader = sessionmaker(bind=engine.execution_options(postgresql_readonly=True))
    writer = sessionmaker(bind=engine, expire_on_commit=False)

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

    @server.tool(annotations={"readOnlyHint": True})
    def list_rules() -> list[RuleInfo]:
        """The categorization rules, in the order they're tried: higher priority first, then
        the longer pattern. A plain pattern matches anywhere in a transaction's description or
        memo, ignoring case and extra spaces; the first rule that matches decides the
        category."""
        with reader() as session:
            rules = sorted(session.scalars(select(CategorizationRule)), key=rule_order)
            return [rule_info(session, rule) for rule in rules]

    @server.tool(annotations=WRITES)
    def categorize_transactions(
        transaction_ids: Annotated[
            list[int], Field(min_length=1, max_length=200, description="From search_transactions")
        ],
        category_id: Annotated[
            int | None,
            Field(
                description="From list_categories; null hands the transactions back to the rules"
            ),
        ],
        create_rule: Annotated[
            bool,
            Field(
                description="Also add a rule for each transaction's description, so other "
                "transactions with that description, past and future, get this category"
            ),
        ] = False,
    ) -> Categorized:
        """Set the category of one or more transactions by hand. Rules won't change a category
        set this way. All or nothing: if any id or the category doesn't exist, nothing
        changes."""
        ids = list(dict.fromkeys(transaction_ids))
        with writer() as session:
            txns = list(session.scalars(select(Transaction).where(Transaction.id.in_(ids))))
            missing = sorted(set(ids) - {t.id for t in txns})
            if missing:
                raise ToolError(f"No transaction with id {', '.join(map(str, missing))}")
            rules: dict[int, CategorizationRule] = {}
            recategorized = 0

            if category_id is None:
                if create_rule:
                    raise ToolError("create_rule needs a category_id")
                categorizer = Categorizer.load(session)
                for txn in txns:
                    txn.category_manual = False
                    txn.category_id = categorizer.category_for(txn.raw_description, txn.memo)
            else:
                known_category(session, category_id)
                for txn in txns:
                    txn.category_id = category_id
                    txn.category_manual = True
                if create_rule:
                    for txn in txns:
                        rule = learn_rule(session, txn.description, category_id)
                        rules[rule.id] = rule
                    recategorized = apply_rules(session)

            session.commit()
            names = {c.id: c.name for c in session.scalars(select(Category))}
            by_id = {t.id: t for t in txns}
            return Categorized(
                transactions=[
                    CategorizedTransaction(
                        id=t.id,
                        date=t.date,
                        amount=money(t.amount),
                        description=t.description,
                        category=names.get(t.category_id) if t.category_id else None,
                        category_manual=t.category_manual,
                    )
                    for t in (by_id[i] for i in ids)
                ],
                rules=[rule_info(session, r) for r in sorted(rules.values(), key=rule_order)],
                recategorized=recategorized,
            )

    @server.tool(annotations=WRITES)
    def add_rule(
        match_pattern: Annotated[
            Pattern,
            Field(
                description="Text to find in the description or memo, such as WOLT; for a "
                "plain pattern, case and extra spaces don't matter"
            ),
        ],
        category_id: Annotated[int, Field(description="From list_categories")],
        is_regex: Annotated[
            bool, Field(description="Treat the pattern as a regular expression")
        ] = False,
        priority: Annotated[
            int | None,
            Field(
                ge=-1000,
                le=1000,
                description="Higher is tried first; ties go to the longer pattern. Default: 0, "
                "or the existing rule's priority when one is changed",
            ),
        ] = None,
    ) -> RuleSaved:
        """Add a categorization rule and apply it now to every transaction not categorized by
        hand; future syncs use it too. A rule with the same pattern is changed instead of
        duplicated."""
        try:
            check_pattern(match_pattern, is_regex)
        except ValueError as err:
            raise ToolError(str(err)) from err
        with writer() as session:
            known_category(session, category_id)
            rule = same_rule(session, match_pattern, is_regex)
            replaced = rule is not None
            if rule is None:
                rule = CategorizationRule(
                    match_pattern=match_pattern, is_regex=is_regex, priority=0
                )
                session.add(rule)
            rule.category_id = category_id
            if priority is not None:
                rule.priority = priority
            session.flush()
            recategorized = apply_rules(session)
            session.commit()
            return RuleSaved(
                rule=rule_info(session, rule),
                replaced_existing=replaced,
                recategorized=recategorized,
            )

    server.custom_route("/login", methods=["GET", "POST"])(provider.login_page)

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok"})

    return server


def build_app(engine: Engine, settings: Settings) -> Starlette:
    # Behind a tunnel or proxy the Host header is the public name, so allow any host; the
    # bearer token is what protects /mcp.
    return build_server(engine, settings).streamable_http_app(host="0.0.0.0")
