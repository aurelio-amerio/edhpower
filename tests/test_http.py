import json

import pytest

from edhpower.http import HttpClient, HttpError


def test_sends_user_agent_and_accept(fake_send):
    fake_send.route("GET", "https://x/", {"ok": True})
    client = HttpClient(user_agent="edhpower/test", send=fake_send)
    status, body = client.get("https://x/a", params={"q": "1"})
    assert status == 200 and body == {"ok": True}
    h = fake_send.calls[0]["headers"]
    assert h["User-Agent"] == "edhpower/test"
    assert h["Accept"] == "application/json"


def test_min_interval_sleeps_between_calls(fake_send):
    fake_send.route("GET", "https://x/", {})
    slept: list[float] = []
    now = [100.0]
    client = HttpClient("ua", min_interval=1.0, send=fake_send, sleep=slept.append, clock=lambda: now[0])
    client.get("https://x/1")
    now[0] += 0.25
    client.get("https://x/2")
    assert slept and abs(slept[0] - 0.75) < 1e-6


def test_429_sleeps_retry_after_and_retries_once(fake_send):
    attempts = {"n": 0}

    def responder(params, body):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return 429, {"Retry-After": "7"}, json.dumps({"code": "rate_limited"})
        return 200, {}, json.dumps({"fine": 1})

    fake_send.route("GET", "https://x/", responder)
    slept: list[float] = []
    client = HttpClient("ua", send=fake_send, sleep=slept.append)
    status, body = client.get("https://x/r")
    assert status == 200 and body == {"fine": 1}
    assert slept == [7.0]


def test_429_without_header_defaults_to_60s(fake_send):
    fake_send.route("GET", "https://x/", lambda p, b: (429, {}, "{}"))
    slept: list[float] = []
    client = HttpClient("ua", send=fake_send, sleep=slept.append)
    status, _ = client.get("https://x/r")
    assert status == 429 and slept == [60.0]


def test_post_sends_json_and_returns_4xx_to_caller(fake_send):
    fake_send.route("POST", "https://x/", lambda p, b: (400, {}, json.dumps({"detail": "bad"})))
    client = HttpClient("ua", send=fake_send)
    status, body = client.post("https://x/p", {"a": 1})
    assert status == 400 and body == {"detail": "bad"}
    assert fake_send.calls[0]["json"] == {"a": 1}


def test_non_json_body_returns_none(fake_send):
    fake_send.route("GET", "https://x/", lambda p, b: (200, {}, "<html>"))
    client = HttpClient("ua", send=fake_send)
    assert client.get("https://x/h") == (200, None)


def test_with_min_interval_clones_transport_with_own_pacing(fake_send):
    fake_send.route("GET", "https://x/", {})
    slept: list[float] = []
    now = [0.0]
    fast = HttpClient("ua", min_interval=0.0, send=fake_send, sleep=slept.append, clock=lambda: now[0])
    slow = fast.with_min_interval(1.0)
    fast.get("https://x/1")
    slow.get("https://x/2")   # first call on the clone: no wait
    slow.get("https://x/3")   # second call: waits the full second
    assert slept == [1.0]
    assert fake_send.calls[1]["headers"]["User-Agent"] == "ua"


def test_5xx_retries_once_then_raises_http_error(fake_send):
    fake_send.route("GET", "https://x/", lambda p, b: (503, {}, "down"))
    slept: list[float] = []
    client = HttpClient("ua", send=fake_send, sleep=slept.append)
    with pytest.raises(HttpError) as exc_info:
        client.get("https://x/s")
    assert exc_info.value.status == 503
    assert slept == [2.0]
    assert len(fake_send.calls) == 2
