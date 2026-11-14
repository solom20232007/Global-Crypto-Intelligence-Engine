import io
from urllib.error import HTTPError, URLError

import pytest

from gcie.collectors.public_market import PublicApiError, public_json


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, headers=None):
    return HTTPError("https://x", code, "error", headers or {}, io.BytesIO(b'{"msg":"x"}'))


def scripted_opener(outcomes):
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    return opener, calls


def test_retries_429_then_succeeds_and_honours_retry_after():
    opener, calls = scripted_opener([
        http_error(429, {"Retry-After": "7"}),
        http_error(503),
        b'{"ok": true}',
    ])
    waits = []
    result = public_json("https://x", opener=opener, sleep=waits.append, backoff_seconds=1)
    assert result == {"ok": True}
    assert len(calls) == 3
    assert waits == [7.0, 2.0]


def test_network_errors_are_retried():
    opener, calls = scripted_opener([URLError("reset"), TimeoutError(), b"[]"])
    assert public_json("https://x", opener=opener, sleep=lambda _s: None) == []
    assert len(calls) == 3


def test_418_ip_ban_fails_immediately():
    opener, calls = scripted_opener([http_error(418), b"[]"])
    with pytest.raises(PublicApiError, match="banned"):
        public_json("https://x", opener=opener, sleep=lambda _s: None)
    assert len(calls) == 1


def test_client_errors_are_not_retried():
    opener, calls = scripted_opener([http_error(400), b"[]"])
    with pytest.raises(PublicApiError, match="HTTP 400"):
        public_json("https://x", opener=opener, sleep=lambda _s: None)
    assert len(calls) == 1


def test_gives_up_after_max_attempts():
    opener, calls = scripted_opener([http_error(500)] * 3)
    with pytest.raises(PublicApiError, match="HTTP 500"):
        public_json("https://x", opener=opener, sleep=lambda _s: None, max_attempts=3)
    assert len(calls) == 3


def test_excessive_retry_after_fails_instead_of_hammering():
    opener, _ = scripted_opener([http_error(429, {"Retry-After": "3600"})])
    with pytest.raises(PublicApiError, match="too long"):
        public_json("https://x", opener=opener, sleep=lambda _s: None)
