from datetime import date

from app.models import CategorizationRule
from tests.factories import make_account, make_category, make_txn


def ids(response):
    return [t["id"] for t in response.json()]


def test_list_filters_and_order(client, session):
    food = make_category(session, "Food")
    groceries = make_category(session, "Groceries", parent=food)
    checking, card = make_account(session), make_account(session, "visaCal")
    t1 = make_txn(session, checking, "Rent", -5000, day=date(2026, 9, 1))
    t2 = make_txn(session, card, "Shufersal", -300, day=date(2026, 9, 3), category=groceries)
    t3 = make_txn(session, card, "Aroma", -20, day=date(2026, 9, 3), category=food)
    t4 = make_txn(session, card, "August thing", -10, day=date(2026, 8, 31))
    session.commit()

    assert ids(client.get("/api/transactions")) == [t3.id, t2.id, t1.id, t4.id]
    assert ids(client.get("/api/transactions?month=2026-09")) == [t3.id, t2.id, t1.id]
    assert ids(client.get(f"/api/transactions?category_id={food.id}")) == [t3.id, t2.id]
    assert ids(client.get(f"/api/transactions?category_id={groceries.id}")) == [t2.id]
    assert ids(client.get("/api/transactions?uncategorized=true")) == [t1.id, t4.id]
    assert ids(client.get(f"/api/transactions?account_id={checking.id}")) == [t1.id]
    assert ids(client.get("/api/transactions?limit=2&offset=1")) == [t2.id, t1.id]
    assert client.get("/api/transactions?month=2026-13").status_code == 422

    first = client.get("/api/transactions?limit=1").json()[0]
    assert first["amount"] == "-20.00"
    assert first["date"] == "2026-09-03"


def test_manual_category_survives_rule_changes(client, session):
    dining, groceries = make_category(session, "Dining"), make_category(session, "Groceries")
    txn = make_txn(session, make_account(session), "Shufersal Deal", -150)
    session.commit()

    response = client.patch(f"/api/transactions/{txn.id}", json={"category_id": dining.id})
    assert response.status_code == 200
    assert response.json()["transaction"]["category_id"] == dining.id
    assert response.json()["transaction"]["category_manual"] is True
    assert response.json()["rule"] is None

    client.post("/api/rules", json={"match_pattern": "shufersal", "category_id": groceries.id})
    session.expire_all()
    assert txn.category_id == dining.id


def test_null_category_hands_back_to_rules(client, session):
    dining, groceries = make_category(session, "Dining"), make_category(session, "Groceries")
    session.add(CategorizationRule(match_pattern="shufersal", category_id=groceries.id))
    txn = make_txn(session, make_account(session), "Shufersal", -90, category=dining, manual=True)
    session.commit()

    response = client.patch(f"/api/transactions/{txn.id}", json={"category_id": None})
    assert response.json()["transaction"]["category_id"] == groceries.id
    assert response.json()["transaction"]["category_manual"] is False


def test_create_rule_learns_from_the_manual_tag(client, session):
    subscriptions = make_category(session, "Subscriptions")
    entertainment = make_category(session, "Entertainment")
    account = make_account(session)
    tagged = make_txn(session, account, "NETFLIX.COM   AMSTERDAM", -55)
    same_merchant = make_txn(session, account, "NETFLIX.COM AMSTERDAM", -55, day=date(2026, 8, 5))
    other = make_txn(session, account, "Spotify", -20)
    session.commit()

    body = {"category_id": subscriptions.id, "create_rule": True}
    response = client.patch(f"/api/transactions/{tagged.id}", json=body).json()
    assert response["rule"]["match_pattern"] == "NETFLIX.COM AMSTERDAM"
    assert response["rule"]["category_id"] == subscriptions.id
    assert response["recategorized"] == 1

    session.expire_all()
    assert same_merchant.category_id == subscriptions.id
    assert same_merchant.category_manual is False
    assert other.category_id is None

    # Tagging the same description again re-points the rule instead of adding another
    body = {"category_id": entertainment.id, "create_rule": True}
    again = client.patch(f"/api/transactions/{same_merchant.id}", json=body).json()
    assert again["rule"]["id"] == response["rule"]["id"]
    assert len(client.get("/api/rules").json()) == 1


def test_update_validation(client, session):
    txn = make_txn(session, make_account(session), "X", -1)
    session.commit()

    url = f"/api/transactions/{txn.id}"
    assert client.patch(url, json={"category_id": None, "create_rule": True}).status_code == 422
    assert client.patch(url, json={"category_id": 999}).status_code == 422
    assert client.patch(url, json={}).status_code == 422
    assert client.patch("/api/transactions/999", json={"category_id": None}).status_code == 404
