"""Unit tests: viewer host policy (plan §41 network-exposure rule).

These are pure functions — no sockets — so the rule is testable in isolation:
only localhost names are accepted while the viewer is bound to loopback, which
blocks DNS-rebinding style requests (Host pointing at an attacker domain while
the socket is loopback).
"""

from __future__ import annotations

import pytest

from visual_intensity_engine.visualization.server import (
    hostname_from_host_header,
    is_loopback_bind,
    is_loopback_hostname,
)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("localhost", "localhost"),
        ("localhost:8000", "localhost"),
        ("LOCALHOST:8000", "localhost"),
        ("127.0.0.1:8000", "127.0.0.1"),
        ("[::1]:8000", "::1"),
        ("[::1]", "::1"),
        ("viewer.example.test", "viewer.example.test"),
        ("viewer.example.test:443", "viewer.example.test"),
        ("", ""),
        (None, ""),
        # a non-numeric "port" suffix is part of the name, not a port
        ("host:notaport", "host:notaport"),
    ],
)
def test_hostname_extraction(header, expected):
    assert hostname_from_host_header(header) == expected


@pytest.mark.parametrize(
    "name", ["localhost", "app.localhost", "127.0.0.1", "127.0.0.2", "127.255.255.254", "::1"]
)
def test_loopback_names_accepted(name):
    assert is_loopback_hostname(name)


@pytest.mark.parametrize(
    "name",
    [
        "evil.example.com",
        "127.0.0.1.evil.example.com",  # prefix trick must not pass
        "localhost.evil.example.com",  # suffix trick must not pass
        "128.0.0.1",
        "10.0.0.5",
        "0.0.0.0",
        "",
    ],
)
def test_non_loopback_names_rejected(name):
    assert not is_loopback_hostname(name)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("::1", True),
        ("0.0.0.0", False),
        ("192.168.1.10", False),
        ("viewer.example.test", False),
    ],
)
def test_bind_address_classification(host, expected):
    assert is_loopback_bind(host) is expected
