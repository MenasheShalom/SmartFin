from datetime import date
from decimal import Decimal

from app.models import Budget, CategorizationRule
from tests.factories import make_account, make_category, make_txn


def create(client, **body):
    return client.post("/api/categories", json=body)


def test_list_is_in_tree_order(client):
    food = create(client, name="Food").json()
    create(client, name="Transport")
    create(client, name="Groceries", parent_id=food["id"])
    create(client, name="Dining", parent_id=food["id"])

    names = [c["name"] for c in client.get("/api/categories").json()]
    assert names == ["Food", "Dining", "Groceries", "Transport"]


def test_subcategory_takes_parent_kind(client):
    income = create(client, name="Income", kind="income").json()
    assert income["kind"] == "income"

    salary = create(client, name="Salary", parent_id=income["id"])
    assert salary.status_code == 201
    assert salary.json()["kind"] == "income"

    conflicting = create(client, name="Bonus", parent_id=income["id"], kind="expense")
    assert conflicting.status_code == 422


def test_only_two_levels(client):
    food = create(client, name="Food").json()
    groceries = create(client, name="Groceries", parent_id=food["id"]).json()
    assert create(client, name="Organic", parent_id=groceries["id"]).status_code == 422


def test_names_are_unique_per_parent(client):
    food = create(client, name="Food").json()
    transport = create(client, name="Transport").json()

    assert create(client, name="food").status_code == 409
    assert create(client, name="Other", parent_id=food["id"]).status_code == 201
    assert create(client, name="Other", parent_id=transport["id"]).status_code == 201
    assert create(client, name="OTHER", parent_id=food["id"]).status_code == 409


def test_blank_name_and_unknown_parent_are_rejected(client):
    assert create(client, name="   ").status_code == 422
    assert create(client, name="X", parent_id=999).status_code == 422


def test_rename(client):
    food = create(client, name="Food").json()
    create(client, name="Groceries")

    response = client.patch(f"/api/categories/{food['id']}", json={"name": " Eating "})
    assert response.json()["name"] == "Eating"
    conflict = client.patch(f"/api/categories/{food['id']}", json={"name": "groceries"})
    assert conflict.status_code == 409


def test_kind_change_cascades_to_subcategories(client):
    savings = create(client, name="Savings").json()
    child = create(client, name="Deposit", parent_id=savings["id"]).json()

    response = client.patch(f"/api/categories/{savings['id']}", json={"kind": "transfer"})
    assert response.json()["kind"] == "transfer"
    kinds = {c["id"]: c["kind"] for c in client.get("/api/categories").json()}
    assert kinds[child["id"]] == "transfer"

    assert client.patch(f"/api/categories/{child['id']}", json={"kind": "expense"}).status_code == 422


def test_kind_change_blocked_by_budgets(client, session):
    food = make_category(session, "Food")
    session.add(Budget(category_id=food.id, month=date(2026, 9, 1), limit_amount=Decimal(100)))
    session.commit()

    response = client.patch(f"/api/categories/{food.id}", json={"kind": "transfer"})
    assert response.status_code == 409


def test_delete_unused_category(client):
    food = create(client, name="Food").json()
    assert client.delete(f"/api/categories/{food['id']}").status_code == 204
    assert client.get("/api/categories").json() == []
    assert client.delete(f"/api/categories/{food['id']}").status_code == 404


def test_delete_refuses_a_category_in_use(client, session):
    food = make_category(session, "Food")
    make_category(session, "Groceries", parent=food)
    session.add(CategorizationRule(match_pattern="aroma", category_id=food.id))
    make_txn(session, make_account(session), "Aroma", -20, category=food)
    session.commit()

    response = client.delete(f"/api/categories/{food.id}")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Category is still used by 1 subcategories, 1 rules, 1 transactions"
    )


def test_fixed_flag_is_inherited_and_cascades(client):
    housing = create(client, name="דיור", is_fixed=True).json()
    rent = create(client, name="שכירות", parent_id=housing["id"]).json()
    assert rent["is_fixed"] is True
    fun = create(client, name="בילויים").json()
    assert fun["is_fixed"] is False

    client.patch(f"/api/categories/{housing['id']}", json={"is_fixed": False})
    flags = {c["id"]: c["is_fixed"] for c in client.get("/api/categories").json()}
    assert flags[rent["id"]] is False
