"""Tests for cross-notification threading: repeated notifications to the
same (channel, destination) should reply into one running conversation
thread instead of each showing up as a brand new, unrelated message/email.

Covers app/repositories/notification_repository.py's get_thread_key /
save_thread_key (the persistence half) and the API-level wiring in
app/services/notification_service.py (the "use it" half), exercised through
MockProvider (FORCE_MOCK_PROVIDERS=true in tests - see conftest.py), which
deliberately mirrors the real Slack/Email providers' thread_key contract:
echo back what it was given, or mint a new anchor if this is the first
message to that recipient.
"""
from app.db import Database, _connect
from app.providers.teams.provider import TeamsProvider
from app.repositories import notification_repository as repo


def _db():
    return Database(_connect())


def test_thread_key_round_trips_and_first_write_wins(client):
    db = _db()
    try:
        assert repo.get_thread_key(db, "SLACK", "a@example.com") is None

        repo.save_thread_key(db, "SLACK", "a@example.com", "root-1")
        db.commit()
        assert repo.get_thread_key(db, "SLACK", "a@example.com") == "root-1"

        # A later notification to the same recipient must never move the
        # thread anchor once one is already recorded - otherwise replies
        # would keep jumping to a new "latest" thread instead of staying in
        # the original conversation.
        repo.save_thread_key(db, "SLACK", "a@example.com", "root-2-should-be-ignored")
        db.commit()
        assert repo.get_thread_key(db, "SLACK", "a@example.com") == "root-1"

        # Different channel and different destination are independent
        # anchors - threading is scoped per (channel, destination).
        assert repo.get_thread_key(db, "EMAIL", "a@example.com") is None
        assert repo.get_thread_key(db, "SLACK", "b@example.com") is None
    finally:
        db.close()


def test_repeated_notifications_to_same_recipient_share_one_thread(client):
    payload = {
        "title": "Deploy finished",
        "message": "Build #42 deployed to prod",
        "channels": {"slack": [{"destination": "a@example.com"}]},
    }

    client.post("/api/notifications", json=payload)
    client.post("/api/notifications", json=payload)
    client.post("/api/notifications", json=payload)

    db = _db()
    try:
        rows = db.execute(
            "SELECT thread_key FROM channel_threads WHERE channel = %s AND destination = %s",
            ("SLACK", "a@example.com"),
        ).fetchall()
        # Exactly one anchor recorded, even after three sends.
        assert len(rows) == 1
        assert rows[0]["thread_key"]
    finally:
        db.close()


def test_different_recipients_get_independent_threads(client):
    client.post(
        "/api/notifications",
        json={"title": "t", "message": "m", "channels": {"slack": [{"destination": "a@example.com"}]}},
    )
    client.post(
        "/api/notifications",
        json={"title": "t", "message": "m", "channels": {"slack": [{"destination": "b@example.com"}]}},
    )

    db = _db()
    try:
        rows = db.execute(
            "SELECT destination, thread_key FROM channel_threads WHERE channel = 'SLACK' ORDER BY destination"
        ).fetchall()
        assert [r["destination"] for r in rows] == ["a@example.com", "b@example.com"]
        assert rows[0]["thread_key"] != rows[1]["thread_key"]
    finally:
        db.close()


def test_teams_provider_never_returns_a_thread_key(monkeypatch):
    """Teams is a 1:1 chat - already one continuous conversation, so unlike
    Slack/Email the real provider must never hand back a thread anchor for
    the service layer to persist (see app/providers/teams/provider.py's
    module docstring). Exercises TeamsProvider directly, with httpx.post
    stubbed out - no real network call, no MockProvider involved, since the
    test suite's MockProvider deliberately always mints one for every
    channel and would hide a regression here."""

    class _FakeResponse:
        status_code = 202

    def _fake_post(url, json, timeout):
        return _FakeResponse()

    monkeypatch.setattr("app.providers.teams.provider.httpx.post", _fake_post)

    provider = TeamsProvider(webhook_url="https://example.com/webhook")
    result = provider.send(
        destination="a@example.com", title="t", message="m", thread_key="should-be-ignored"
    )

    assert result.success is True
    assert result.thread_key is None
