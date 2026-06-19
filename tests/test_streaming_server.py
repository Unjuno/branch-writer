"""Tests for the SSE streaming server."""
from __future__ import annotations

import threading
from unittest.mock import Mock, patch

import httpx
import pytest

from branch_writer.streaming_server import _is_port_in_use, _server_started, start_server


@pytest.fixture(autouse=True)
def reset_server_started() -> None:
    """Reset the module-level _server_started flag before each test."""
    import branch_writer.streaming_server as sv
    sv._server_started = False


def test_is_port_in_use_returns_true_when_port_occupied() -> None:
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen()
    try:
        assert _is_port_in_use(port) is True
    finally:
        sock.close()


def test_is_port_in_use_returns_false_when_port_free() -> None:
    assert _is_port_in_use(9876) is False


def test_start_server_is_idempotent() -> None:
    start_server(port=9877)
    thread_count_before = threading.active_count()
    start_server(port=9877)
    thread_count_after = threading.active_count()
    assert thread_count_after == thread_count_before, (
        "start_server called twice should not start a second thread"
    )


@patch("branch_writer.streaming_server._is_port_in_use", return_value=True)
@patch("httpx.get")
def test_start_server_reuses_existing_healthy_server(mock_get: Mock, mock_port: Mock) -> None:
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp

    start_server(port=9878)

    mock_get.assert_called_once_with("http://127.0.0.1:9878/health", timeout=2)


@patch("branch_writer.streaming_server._is_port_in_use", return_value=True)
@patch("httpx.get", side_effect=Exception("refused"))
def test_start_server_raises_on_port_conflict(mock_get: Mock, mock_port: Mock) -> None:
    with pytest.raises(RuntimeError, match="already in use"):
        start_server(port=9879)
