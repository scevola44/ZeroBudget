"""Unit tests for the uvicorn access-log filter that silences /api/health noise."""

import logging

from app.main import _HealthCheckAccessFilter


def _access_record(path: str, status_code: int) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", path, "1.1", status_code),
        exc_info=None,
    )


def test_filters_out_successful_health_check():
    assert _HealthCheckAccessFilter().filter(_access_record("/api/health", 200)) is False


def test_keeps_failing_health_check():
    assert _HealthCheckAccessFilter().filter(_access_record("/api/health", 503)) is True


def test_keeps_unrelated_paths():
    assert _HealthCheckAccessFilter().filter(_access_record("/api/accounts", 200)) is True


def test_fails_open_on_unexpected_args_shape():
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="some other message",
        args=None,
        exc_info=None,
    )
    assert _HealthCheckAccessFilter().filter(record) is True
