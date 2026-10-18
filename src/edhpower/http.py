"""Single HTTP entry point: headers, pacing, 429 handling, injectable transport."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

SendFn = Callable[[str, str, dict | None, Any, dict[str, str]], tuple[int, dict[str, str], str]]

DEFAULT_RETRY_AFTER = 60.0


class HttpError(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(f"HTTP {status}: {text[:200]}")
        self.status = status
        self.text = text


def _requests_send(method: str, url: str, params: dict | None, json_body: Any, headers: dict[str, str]) -> tuple[int, dict[str, str], str]:
    import requests  # imported lazily so tests never need the network stack

    r = requests.request(method, url, params=params, json=json_body, headers=headers, timeout=30)
    return r.status_code, dict(r.headers), r.text


class HttpClient:
    def __init__(
        self,
        user_agent: str,
        min_interval: float = 0.0,
        send: SendFn | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._min_interval = min_interval
        self._send = send or _requests_send
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None

    def get(self, url: str, params: dict | None = None) -> tuple[int, Any]:
        return self._request("GET", url, params, None)

    def post(self, url: str, json_body: Any) -> tuple[int, Any]:
        return self._request("POST", url, None, json_body)

    def with_min_interval(self, seconds: float) -> HttpClient:
        clone = HttpClient(self._headers["User-Agent"], seconds, self._send, self._sleep, self._clock)
        return clone

    def _pace(self) -> None:
        if self._last is not None and self._min_interval > 0:
            wait = self._min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def _request(self, method: str, url: str, params: dict | None, json_body: Any) -> tuple[int, Any]:
        headers = dict(self._headers)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        for attempt in (1, 2):
            self._pace()
            status, resp_headers, text = self._send(method, url, params, json_body, headers)
            if status == 429 and attempt == 1:
                self._sleep(_retry_after(resp_headers))
                continue
            if status >= 500 and attempt == 1:
                self._sleep(2.0)
                continue
            if status >= 500:
                raise HttpError(status, text)
            return status, _parse_json(text)
        raise AssertionError("unreachable")


def _retry_after(headers: dict[str, str]) -> float:
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return float(v)
            except ValueError:
                break
    return DEFAULT_RETRY_AFTER


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
