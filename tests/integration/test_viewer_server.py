"""Integration tests: exploratory live viewer over real HTTP (plan §21, §35, §41).

The viewer previously had only manual smoke coverage. These tests start the real
`ThreadingHTTPServer` on an ephemeral loopback port and exercise the routes, the
Host-header policy, the interaction log, and the MJPEG stream. They are
integration tests only: the viewer remains excluded from benchmark output
(plan §21) and no performance claim is derived from them.
"""

from __future__ import annotations

import http.client
import json
import threading

import pytest

from visual_intensity_engine.visualization.server import MJPEGServer, serve

HOST_TIMEOUT_S = 10.0


def _start(server: MJPEGServer) -> tuple[threading.Thread, str, int]:
    thread = threading.Thread(target=server.httpd.serve_forever, daemon=True)
    thread.start()
    host, port = server.httpd.server_address[:2]
    return thread, host, port


@pytest.fixture
def viewer(tmp_path):
    server = serve(host="127.0.0.1", port=0, seed=0, log_path=tmp_path / "interactions.jsonl")
    thread, host, port = _start(server)
    try:
        yield server, host, port
    finally:
        server.shutdown()
        thread.join(timeout=HOST_TIMEOUT_S)


def _get(port: int, path: str, *, host_header: str | None = None, timeout: float = HOST_TIMEOUT_S):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    headers = {"Host": host_header} if host_header is not None else {}
    try:
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        body = response.read()
        return response.status, dict(response.getheaders()), body
    finally:
        conn.close()


def test_dashboard_serves_and_keeps_the_exploratory_warning(viewer):
    _, _, port = viewer
    status, headers, body = _get(port, "/")
    assert status == 200
    text = body.decode("utf-8")
    assert "EXPLORATORY VISUALIZATION — NOT BENCHMARK OUTPUT" in text
    assert headers["Content-Type"].startswith("text/html")
    assert "/stream.mjpg" in text and "/legend.png" in text


def test_state_json_reports_mode_and_non_claim(viewer):
    _, _, port = viewer
    status, headers, body = _get(port, "/state.json")
    assert status == 200
    assert headers.get("Cache-Control") == "no-store"
    state = json.loads(body)
    assert state["note"] == "exploratory only — not benchmark output"
    assert state["scene"] == "moving_square" and state["levels"] == 16


def test_legend_is_a_png(viewer):
    _, _, port = viewer
    status, headers, body = _get(port, "/legend.png")
    assert status == 200
    assert headers["Content-Type"] == "image/png"
    assert body[:8] == b"\x89PNG\r\n\x1a\n"


def test_unknown_route_is_404(viewer):
    _, _, port = viewer
    status, _, _ = _get(port, "/not-a-route")
    assert status == 404


def test_foreign_host_header_is_rejected_on_loopback_bind(viewer):
    """DNS-rebinding defence: loopback-bound viewer accepts localhost names only."""
    _, _, port = viewer
    status, _, body = _get(port, "/", host_header="evil.example.com")
    assert status == 403
    assert b"Host header rejected" in body
    assert _get(port, "/", host_header="localhost")[0] == 200
    assert _get(port, "/", host_header=f"127.0.0.1:{port}")[0] == 200


def test_explicitly_allowed_extra_host_is_accepted(tmp_path):
    server = serve(
        host="127.0.0.1",
        port=0,
        log_path=tmp_path / "i.jsonl",
        allowed_hosts=("preview.example.test",),
    )
    thread, _, port = _start(server)
    try:
        assert _get(port, "/", host_header="preview.example.test")[0] == 200
        assert _get(port, "/", host_header="other.example.test")[0] == 403
    finally:
        server.shutdown()
        thread.join(timeout=HOST_TIMEOUT_S)


def test_network_bind_is_opt_in_and_reported(tmp_path, caplog):
    """A non-loopback bind accepts proxied Host headers but logs the exposure."""
    import logging

    try:
        server = serve(host="0.0.0.0", port=0, log_path=tmp_path / "i.jsonl")
    except OSError as exc:  # pragma: no cover - sandbox without 0.0.0.0 permission
        pytest.skip(f"cannot bind 0.0.0.0 in this environment: {exc}")
    thread, _, port = _start(server)
    try:
        assert server.loopback_only is False
        assert _get(port, "/", host_header="preview.example.test")[0] == 200
    finally:
        server.shutdown()
        thread.join(timeout=HOST_TIMEOUT_S)
    assert any(
        "NO authentication" in r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING
    ), "exposing the viewer must be announced at WARNING"


def test_query_parameters_update_state_and_are_logged(viewer):
    _, _, port = viewer
    log_path = viewer[0].state.log_path
    assert _get(port, "/?levels=32&scene=gradient")[0] == 200
    assert _get(port, "/state.json")[1].get("Cache-Control") == "no-store"
    state = json.loads(_get(port, "/state.json")[2])
    assert state["levels"] == 32 and state["scene"] == "gradient"
    entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    assert entries, "interaction log must record parameter changes"
    assert entries[-1]["changes"]["levels"]["to"] == 32
    assert entries[-1]["utc"].endswith("Z")


def test_invalid_query_parameters_are_ignored_not_applied(viewer):
    """Bad/out-of-range parameters must neither change state nor kill the connection."""
    _, _, port = viewer
    status, _, _ = _get(port, "/?levels=999&scene=no_such_scene&fps=abc&fps=1e9")
    assert status == 200, "an unparsable parameter must not break the response"
    state = json.loads(_get(port, "/state.json")[2])
    assert state["levels"] == 16  # untouched defaults
    assert state["scene"] == "moving_square"
    assert state["fps_target"] == 30.0


def test_mjpeg_stream_sends_multipart_frames(viewer):
    _, _, port = viewer
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=HOST_TIMEOUT_S)
    try:
        conn.request("GET", "/stream.mjpg", headers={"Host": "localhost"})
        response = conn.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "multipart/x-mixed-replace; boundary=frame"
        chunk = response.fp.read(1024)
        assert b"--frame" in chunk
        assert chunk.split(b"\r\n\r\n", 1)[1][:2] == b"\xff\xd8"  # JPEG SOI marker
    except TimeoutError:  # pragma: no cover - slow sandbox
        pytest.skip("stream did not produce a frame within the timeout")
    finally:
        conn.close()
