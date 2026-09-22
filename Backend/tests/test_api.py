"""API-level tests covering FR-01, FR-09, FR-11 and the /api/stats addition."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_create_notification_all_channels(client):
    payload = {
        "title": "Deploy finished",
        "message": "Build #42 deployed to prod",
        "channels": {
            "teams": [{"destination": "ops-channel"}],
            "slack": [{"destination": "U123456"}],
            "email": [{"recipient": "a@example.com", "subject": "Deploy done"}],
        },
    }
    r = client.post("/api/notifications", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == payload["title"]
    assert len(body["deliveries"]) == 3
    channels = {d["channel"] for d in body["deliveries"]}
    assert channels == {"TEAMS", "SLACK", "EMAIL"}
    for delivery in body["deliveries"]:
        # MockProvider always succeeds (FORCE_MOCK_PROVIDERS=true in tests)
        assert delivery["status"] == "SENT"
        assert delivery["provider"] == "mock"
        assert delivery["provider_message_id"].startswith("mock-")


def test_create_notification_requires_at_least_one_channel(client):
    r = client.post("/api/notifications", json={"title": "x", "message": "y", "channels": {}})
    assert r.status_code == 422


def test_create_notification_rejects_invalid_email(client):
    r = client.post(
        "/api/notifications",
        json={"title": "x", "message": "y", "channels": {"email": [{"recipient": "not-an-email"}]}},
    )
    assert r.status_code == 422


def test_get_notification_round_trips(client):
    created = client.post(
        "/api/notifications",
        json={"title": "A", "message": "m", "channels": {"teams": [{"destination": "c1"}]}},
    ).json()

    r = client.get(f"/api/notifications/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_notification_not_found(client):
    r = client.get("/api/notifications/does-not-exist")
    assert r.status_code == 404


def test_list_and_filter_notifications(client):
    client.post(
        "/api/notifications",
        json={"title": "Alpha release", "message": "m", "channels": {"teams": [{"destination": "c1"}]}},
    )
    client.post(
        "/api/notifications",
        json={"title": "Beta release", "message": "m", "channels": {"email": [{"recipient": "b@example.com"}]}},
    )

    r = client.get("/api/notifications")
    assert r.status_code == 200
    assert r.json()["total"] == 2

    r = client.get("/api/notifications", params={"channel": "email"})
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["deliveries"][0]["channel"] == "EMAIL"

    r = client.get("/api/notifications", params={"q": "Alpha"})
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["title"] == "Alpha release"

    r = client.get("/api/notifications", params={"status": "SENT"})
    assert r.json()["total"] == 2


def test_stats_counts_across_channels(client):
    client.post(
        "/api/notifications",
        json={
            "title": "A",
            "message": "m",
            "channels": {"teams": [{"destination": "c1"}], "slack": [{"destination": "c2"}]},
        },
    )
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["delivered"] == 2  # both mock deliveries succeed -> SENT
    assert body["pending"] == 0
    assert body["failed"] == 0


def test_retry_on_notification_with_no_failed_deliveries_is_a_noop(client):
    created = client.post(
        "/api/notifications",
        json={"title": "A", "message": "m", "channels": {"teams": [{"destination": "c1"}]}},
    ).json()

    r = client.post(f"/api/notifications/{created['id']}/retry")
    assert r.status_code == 200
    assert r.json()["deliveries"][0]["status"] == "SENT"


def test_retry_not_found(client):
    r = client.post("/api/notifications/does-not-exist/retry")
    assert r.status_code == 404
