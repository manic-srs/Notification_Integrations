"""Webhook endpoint tests (spec FR-10/FR-12): shared-secret protection,
idempotent duplicate callbacks, protecting a terminal DELIVERED status
from a stale FAILED callback, and unknown ids/providers."""


def _create_with_teams(client):
    r = client.post(
        "/api/notifications",
        json={"title": "A", "message": "m", "channels": {"teams": [{"destination": "c1"}]}},
    )
    body = r.json()
    return body["id"], body["deliveries"][0]["provider_message_id"]


def test_webhook_rejects_wrong_secret(client):
    _nid, mid = _create_with_teams(client)

    r = client.post(
        "/api/webhooks/teams",
        json={"provider_message_id": mid, "status": "DELIVERED"},
        headers={"X-Webhook-Secret": "wrong"},
    )
    assert r.status_code == 401


def test_webhook_rejects_missing_secret(client):
    _nid, mid = _create_with_teams(client)

    r = client.post("/api/webhooks/teams", json={"provider_message_id": mid, "status": "DELIVERED"})
    assert r.status_code == 401


def test_webhook_updates_status(client):
    nid, mid = _create_with_teams(client)

    r = client.post(
        "/api/webhooks/teams",
        json={"provider_message_id": mid, "status": "DELIVERED"},
        headers={"X-Webhook-Secret": "test-secret"},
    )
    assert r.status_code == 200
    assert r.json()["new_status"] == "DELIVERED"

    r = client.get(f"/api/notifications/{nid}")
    assert r.json()["deliveries"][0]["status"] == "DELIVERED"


def test_webhook_duplicate_callback_is_idempotent(client):
    _nid, mid = _create_with_teams(client)
    headers = {"X-Webhook-Secret": "test-secret"}

    first = client.post("/api/webhooks/teams", json={"provider_message_id": mid, "status": "DELIVERED"}, headers=headers)
    second = client.post("/api/webhooks/teams", json={"provider_message_id": mid, "status": "DELIVERED"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200


def test_stale_failed_callback_cannot_undeliver(client):
    nid, mid = _create_with_teams(client)
    headers = {"X-Webhook-Secret": "test-secret"}

    client.post("/api/webhooks/teams", json={"provider_message_id": mid, "status": "DELIVERED"}, headers=headers)
    r = client.post(
        "/api/webhooks/teams",
        json={"provider_message_id": mid, "status": "FAILED", "error_message": "stale"},
        headers=headers,
    )
    assert r.status_code == 200

    final = client.get(f"/api/notifications/{nid}")
    assert final.json()["deliveries"][0]["status"] == "DELIVERED"


def test_webhook_unknown_message_id_is_ignored_not_an_error(client):
    r = client.post(
        "/api/webhooks/teams",
        json={"provider_message_id": "no-such-id", "status": "DELIVERED"},
        headers={"X-Webhook-Secret": "test-secret"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


def test_webhook_unknown_provider_is_404(client):
    r = client.post(
        "/api/webhooks/pager",
        json={"provider_message_id": "x", "status": "DELIVERED"},
        headers={"X-Webhook-Secret": "test-secret"},
    )
    assert r.status_code == 404
