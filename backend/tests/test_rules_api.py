from tests.factories import make_account, make_category, make_txn


def test_new_rule_categorizes_existing_transactions_except_manual_ones(client, session):
    groceries = make_category(session, "Groceries")
    other = make_category(session, "Other")
    account = make_account(session)
    auto = make_txn(session, account, "שופרסל דיל רמת גן", -120)
    manual = make_txn(session, account, "שופרסל אונליין", -80, category=other, manual=True)
    unrelated = make_txn(session, account, "Aroma", -20)
    session.commit()

    response = client.post(
        "/api/rules", json={"match_pattern": "שופרסל", "category_id": groceries.id}
    )
    assert response.status_code == 201
    assert response.json() | {"id": 0} == {
        "id": 0,
        "match_pattern": "שופרסל",
        "is_regex": False,
        "category_id": groceries.id,
        "priority": 0,
        "recategorized": 1,
    }

    session.expire_all()
    assert auto.category_id == groceries.id
    assert manual.category_id == other.id
    assert unrelated.category_id is None


def test_invalid_rules_are_rejected(client, session):
    groceries = make_category(session, "Groceries")
    session.commit()

    def post(**body):
        return client.post("/api/rules", json={"category_id": groceries.id} | body)

    assert post(match_pattern="(unclosed", is_regex=True).status_code == 422
    assert post(match_pattern="   ").status_code == 422
    assert post(match_pattern="ok", category_id=999).status_code == 422
    assert post(match_pattern="ok", priority=10**12).status_code == 422


def test_update_moves_matching_transactions(client, session):
    food = make_category(session, "Food")
    dining = make_category(session, "Dining")
    txn = make_txn(session, make_account(session), "Aroma Tel Aviv", -30)
    session.commit()

    rule = client.post("/api/rules", json={"match_pattern": "aroma", "category_id": food.id}).json()
    response = client.patch(f"/api/rules/{rule['id']}", json={"category_id": dining.id})
    assert response.json()["recategorized"] == 1
    session.expire_all()
    assert txn.category_id == dining.id

    bad = client.patch(f"/api/rules/{rule['id']}", json={"match_pattern": "[", "is_regex": True})
    assert bad.status_code == 422
    assert client.patch("/api/rules/999", json={"priority": 1}).status_code == 404


def test_delete_falls_back_to_the_next_rule(client, session):
    food = make_category(session, "Food")
    coffee = make_category(session, "Coffee")
    txn = make_txn(session, make_account(session), "Aroma Espresso Bar", -18)
    session.commit()

    client.post("/api/rules", json={"match_pattern": "aroma", "category_id": food.id})
    specific = client.post(
        "/api/rules", json={"match_pattern": "aroma espresso", "category_id": coffee.id}
    ).json()
    session.expire_all()
    assert txn.category_id == coffee.id

    response = client.delete(f"/api/rules/{specific['id']}")
    assert response.json() == {"recategorized": 1}
    session.expire_all()
    assert txn.category_id == food.id


def test_list_is_in_evaluation_order(client, session):
    food = make_category(session, "Food")
    session.commit()
    for pattern, priority in [("a", 0), ("longer pattern", 0), ("b", 10)]:
        client.post(
            "/api/rules", json={"match_pattern": pattern, "category_id": food.id, "priority": priority}
        )

    patterns = [r["match_pattern"] for r in client.get("/api/rules").json()]
    assert patterns == ["b", "longer pattern", "a"]
