"""Live viewer — EXPLORATORY visualization only (plan §20/§21).

Serves a browser dashboard with side-by-side ORIGINAL | GRAYSCALE | QUANTIZED
panels from a live-processing loop, plus palette legend and processing
metrics. Interactive parameter changes (levels, scene, fps) are logged with
UTC timestamps to `logs/viewer_interactions.jsonl`.

Boundary rule: this viewer is for human inspection; its outputs are NOT
benchmark data. Every page displays that warning (plan §21).

Security rules (plan §41; audit AUD-04):

1. The viewer binds **127.0.0.1 by default** and rejects requests whose `Host`
   header is not a localhost name while it is bound to a loopback address
   (DNS-rebinding defence). Network exposure is an explicit opt-in
   (`--host 0.0.0.0`, plus `--allowed-host` when a proxy rewrites `Host`); the
   server logs a warning when it starts exposed.
2. **No state changes on GET.** Parameters change only through `POST /` carrying
   a per-process random token that is embedded in the dashboard's own forms, so
   a cross-site page (or a plain link/prefetch) cannot drive the viewer. The
   token is a CSRF control, not authentication: the viewer still has no users,
   no TLS and no rate limiting.
"""

from __future__ import annotations

import io
import json
import logging
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs

import numpy as np
from PIL import Image

from ..config import PipelineConfig
from ..intensity.vocabulary import IntensityVocabulary
from ..preprocessing.grayscale import to_grayscale
from ..preprocessing.quantization import quantize
from .render import _as_uint8_rgb, colorize, deterministic_palette
from .render import to_uint8_gray as _g8

logger = logging.getLogger("vie.visualization.server")

LOOPBACK_BIND_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "localhost.localdomain"})


def hostname_from_host_header(value: str | None) -> str:
    """Host header → lowercase hostname, dropping any port and IPv6 brackets."""
    text = (value or "").strip().lower()
    if text.startswith("["):  # [::1]:8000
        return text[1:].split("]", 1)[0]
    if text.count(":") == 1:
        name, _, port = text.partition(":")
        if port.isdigit():
            return name
    return text


def is_loopback_hostname(name: str) -> bool:
    """True for localhost names and the whole 127.0.0.0/8 block (plus ::1)."""
    if name in {"localhost", "::1"} or name.endswith(".localhost"):
        return True
    parts = name.split(".")
    if len(parts) == 4 and parts[0] == "127":
        return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
    return False


def is_loopback_bind(host: str) -> bool:
    return host.strip().lower() in LOOPBACK_BIND_HOSTS or is_loopback_hostname(host.strip().lower())


MAX_FORM_BYTES = 8192  # a state change is a handful of short fields, nothing more

_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>VIE live viewer (exploratory)</title>
<style>
 body {{ background:#111; color:#ddd; font-family: ui-monospace, monospace; margin: 12px; }}
 h1 {{ font-size: 16px; }} .warn {{ color:#ffb347; border:1px solid #ffb347; padding:6px; }}
 img.panel {{ max-width: 32%; border:1px solid #333; }}
 table {{ border-collapse: collapse; }} td, th {{ border:1px solid #444; padding: 2px 8px; font-size: 12px; }}
 a {{ color:#7ab8ff; }}
 form.inline {{ display:inline; }}
 form.inline button {{ background:none; border:none; color:#7ab8ff; cursor:pointer;
                       font:inherit; padding:0 3px; }}
 form.inline button.current {{ color:#fff; font-weight:700; text-decoration:underline; }}
</style></head>
<body>
<h1>VIE live intensity viewer — Phase 1</h1>
<div class="warn">EXPLORATORY VISUALIZATION — NOT BENCHMARK OUTPUT.<br>
 Parameter changes are POSTed with this process's form token and logged with UTC
 timestamps; read-only GET requests cannot change the viewer (plan §41).</div>
<p>
 Levels: {level_links} | Scenes: {scene_links} | FPS:
 {fps_links} | config: <code>{config_summary}</code>
</p>
<p><img class="panel" src="/stream.mjpg">
<img class="panel" src="/stream.mjpg?mode=gray">
<img class="panel" src="/stream.mjpg?mode=quantized"></p>
<h2>Palette legend</h2>
<img src="/legend.png" style="max-width:360px">
<h2>Live metrics (updated every second)</h2>
<pre id="metrics">loading…</pre>
<script>
 setInterval(async () => {{
   const r = await fetch('/state.json'); const s = await r.json();
   document.getElementById('metrics').textContent = JSON.stringify(s, null, 2);
 }}, 1000);
</script>
</body></html>"""


class ViewerState:
    def __init__(self, *, scene: str, levels: int, fps: float, seed: int, log_path: Path):
        self.scene = scene
        self.levels = levels
        self.fps = fps
        self.seed = seed
        self.frame_index = 0
        self.last_latency_ms = 0.0
        self.fps_measured = 0.0
        self.log_path = log_path
        self.lock = threading.Lock()

    def update(self, **kwargs):
        with self.lock:
            changed = {}
            for key, allowed in (
                ("scene", ("gradient", "ramp_bands", "moving_square", "static")),
                ("levels", tuple(range(2, 257))),
                ("fps", None),
            ):
                if key in kwargs and kwargs[key] is not None:
                    val = kwargs[key]
                    try:
                        if key == "levels":
                            val = int(val)
                        if key == "fps":
                            val = float(val)
                    except (TypeError, ValueError):
                        # unparsable query parameter: ignore it, never drop the connection
                        logger.warning("ignoring invalid %s=%r in viewer query", key, kwargs[key])
                        continue
                    if key == "fps" and not 0.1 <= val <= 240.0:
                        logger.warning("ignoring out-of-range fps=%r in viewer query", val)
                        continue
                    if allowed is not None and val not in allowed:
                        continue
                    if getattr(self, key) != val:
                        changed[key] = (getattr(self, key), val)
                        setattr(self, key, val)
            if changed:
                self._log_change(changed)

    def _log_change(self, changed: dict):
        from ..provenance import utc_now_rfc3339

        entry = {"utc": utc_now_rfc3339(), "changes": {k: {"from": v[0], "to": v[1]} for k, v in changed.items()}}
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")
        except OSError:  # pragma: no cover
            logger.warning("cannot write viewer interaction log", exc_info=True)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "scene": self.scene,
                "levels": self.levels,
                "fps_target": self.fps,
                "fps_measured": round(self.fps_measured, 2),
                "frame_index": self.frame_index,
                "last_latency_ms": round(self.last_latency_ms, 3),
                "mode": "LIVE (synthetic source)",
                "note": "exploratory only — not benchmark output",
            }


def control_form(*, token: str, field: str, value: object, label: str, active: bool) -> str:
    """One dashboard control: a POST form carrying the session token.

    Deliberately not a link: a GET must never change viewer state (audit AUD-04).
    `field`/`value` come from fixed enumerations, so no HTML escaping is needed.
    """
    current = ' class="current"' if active else ""
    return (
        '<form class="inline" method="post" action="/">'
        f'<input type="hidden" name="csrf" value="{token}">'
        f'<input type="hidden" name="{field}" value="{value}">'
        f'<button type="submit"{current}>{label}</button></form>'
    )


def _make_source(scene: str, levels: int, fps: float, seed: int):
    from ..input.synthetic import SyntheticSource

    return SyntheticSource(scene, (320, 240), 10**9, fps=fps, seed=seed, levels=levels)


class MJPEGServer:
    """Minimal threaded HTTP server: dashboard + MJPEG streams + state.json.

    `allowed_hosts` lists extra Host-header hostnames accepted while bound to a
    loopback address (e.g. a tunnel or preview proxy that forwards its own host).
    When bound to a non-loopback address, every Host is accepted **unless**
    `allowed_hosts` is given, in which case only those names are.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        seed: int = 0,
        log_path: Path,
        allowed_hosts: tuple[str, ...] = (),
    ):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.state = ViewerState(
            scene="moving_square", levels=16, fps=30.0, seed=seed, log_path=log_path
        )
        self.config = PipelineConfig.default(levels=16)
        self.loopback_only = is_loopback_bind(host)
        self.allowed_hosts = tuple(h.strip().lower() for h in allowed_hosts if h.strip())
        # CSRF token for this process only: state changes must carry it (AUD-04).
        self.csrf_token = secrets.token_urlsafe(32)
        viewer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # quiet default access log
                logger.debug("%s %s", self.address_string(), fmt % args)

            def _host_allowed(self) -> bool:
                name = hostname_from_host_header(self.headers.get("Host"))
                if is_loopback_hostname(name):
                    return True
                if name in viewer.allowed_hosts:
                    return True
                if viewer.loopback_only:
                    return False
                # explicit non-loopback bind: open unless the operator narrowed it
                return not viewer.allowed_hosts

            def _send(self, status: int, content_type: str, body: bytes, *, extra=()) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                for name, value in extra:
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def _forbidden(self) -> None:
                logger.warning(
                    "rejected request with Host=%r on %s bind",
                    self.headers.get("Host"),
                    "loopback" if viewer.loopback_only else "non-loopback",
                )
                body = (
                    "403 — Host header rejected. The viewer accepts localhost names only "
                    "while bound to 127.0.0.1; start it with --host 0.0.0.0 (and "
                    "--allowed-host <name> if a proxy rewrites Host) for network access.\n"
                ).encode()
                self._send(403, "text/plain; charset=utf-8", body)

            def _read_form(self) -> dict | None:
                """POST body → {field: last value}; bounded, never raises a traceback."""
                raw_length = self.headers.get("Content-Length")
                try:
                    length = int(raw_length) if raw_length is not None else 0
                except ValueError:
                    self._send(400, "text/plain; charset=utf-8",
                               "400 — malformed Content-Length\n".encode())
                    return None
                if length < 0:
                    self._send(400, "text/plain; charset=utf-8",
                               "400 — malformed Content-Length\n".encode())
                    return None
                if length > MAX_FORM_BYTES:
                    self._send(
                        413,
                        "text/plain; charset=utf-8",
                        f"413 — form body larger than {MAX_FORM_BYTES} bytes\n".encode(),
                    )
                    return None
                text = self.rfile.read(length).decode("utf-8", "replace")
                return {key: values[-1] for key, values in parse_qs(text, keep_blank_values=True).items()}

            def _token_ok(self, params: dict) -> bool:
                supplied = params.get("csrf") or ""
                return bool(supplied) and secrets.compare_digest(supplied, viewer.csrf_token)

            def do_GET(self):
                if not self._host_allowed():
                    self._forbidden()
                    return
                path, _, query = self.path.partition("?")
                if path == "/":
                    if query:
                        # state changes are POST-only (audit AUD-04); say so, don't obey
                        logger.warning(
                            "ignoring query parameters on GET %s: the viewer changes state only "
                            "through its own POST forms (plan §41)", self.path,
                        )
                    snapshot = viewer.state.snapshot()
                    html = _HTML.format(
                        level_links=" ".join(
                            control_form(
                                token=viewer.csrf_token, field="levels", value=lv, label=str(lv),
                                active=lv == snapshot["levels"],
                            )
                            for lv in (8, 16, 32, 64, 128, 256)
                        ),
                        scene_links=" ".join(
                            control_form(
                                token=viewer.csrf_token, field="scene", value=s, label=s,
                                active=s == snapshot["scene"],
                            )
                            for s in ("moving_square", "gradient", "ramp_bands", "static")
                        ),
                        fps_links=" ".join(
                            control_form(
                                token=viewer.csrf_token, field="fps", value=f, label=str(f),
                                active=float(f) == snapshot["fps_target"],
                            )
                            for f in (5, 15, 30, 60)
                        ),
                        config_summary=json.dumps(snapshot, sort_keys=True),
                    )
                    self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
                elif path == "/state.json":
                    body = json.dumps(viewer.state.snapshot(), indent=2).encode()
                    self._send(200, "application/json", body, extra=(("Cache-Control", "no-store"),))
                elif path == "/legend.png":
                    vocab = IntensityVocabulary.build_uniform(viewer.state.levels)
                    from .render import render_palette_legend

                    buf = io.BytesIO()
                    render_palette_legend(vocab, out_path=buf)
                    self._send(200, "image/png", buf.getvalue())
                elif path == "/stream.mjpg":
                    mode = parse_qs(query).get("mode", ["color"])[-1]
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.end_headers()
                    fps_target = viewer.state.fps
                    source = _make_source(viewer.state.scene, viewer.state.levels, fps_target, viewer.state.seed)
                    cfg = PipelineConfig.default(levels=viewer.state.levels)
                    palette = deterministic_palette(viewer.state.levels)
                    for rec in source.frames():
                        t0 = time.perf_counter_ns()
                        y, _, _ = to_grayscale(rec.data, cfg.input_domain)
                        q = quantize(y, cfg.quantization)
                        if mode == "gray":
                            arr = np.stack([_g8(y)] * 3, axis=-1)
                        elif mode == "quantized":
                            arr = colorize(q, palette)
                        else:
                            arr = _as_uint8_rgb(rec.data)
                        img = Image.fromarray(arr)
                        # annotation strip
                        from PIL import ImageDraw

                        draw = ImageDraw.Draw(img)
                        draw.text(
                            (4, 2),
                            f"frame={rec.frame_index} ts_us={rec.timestamp_us} L={viewer.state.levels}",
                            fill=(255, 255, 80),
                        )
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=80)
                        try:
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n")
                            self.wfile.write(buf.getvalue())
                            self.wfile.write(b"\r\n")
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        latency_ms = (time.perf_counter_ns() - t0) / 1e6
                        with viewer.state.lock:
                            viewer.state.frame_index = rec.frame_index
                            viewer.state.last_latency_ms = latency_ms
                            viewer.state.fps_measured = 1000.0 / max(latency_ms, 1e-9)
                        time.sleep(max(0.0, 1.0 / fps_target - latency_ms / 1000.0))
                    source.close()
                else:
                    self._send(404, "text/plain; charset=utf-8", b"404 - not found\n")

            def do_POST(self):
                """The only way to change viewer state (audit AUD-04).

                A cross-site page cannot read the dashboard, so it cannot learn the
                per-process `csrf` token; a token-less POST is rejected with 403 and
                the state is left untouched.
                """
                if not self._host_allowed():
                    self._forbidden()
                    return
                path = self.path.partition("?")[0]
                if path != "/":
                    self._send(404, "text/plain; charset=utf-8", b"404 - not found\n")
                    return
                params = self._read_form()
                if params is None:
                    return
                if not self._token_ok(params):
                    logger.warning(
                        "rejected POST with missing/invalid viewer token (Host=%r) — "
                        "state unchanged",
                        self.headers.get("Host"),
                    )
                    self._send(
                        403,
                        "text/plain; charset=utf-8",
                        ("403 — a viewer state change requires this process's session token. "
                         "Reload the dashboard and use its parameter buttons.\n").encode(),
                    )
                    return
                viewer.state.update(
                    levels=params.get("levels"), scene=params.get("scene"), fps=params.get("fps")
                )
                # PRG: redirect to a fresh GET so a reload cannot resubmit the form
                self._send(
                    303, "text/plain; charset=utf-8", b"see /\n",  # ASCII: PRG redirect body
                    extra=(("Location", "/"), ("Cache-Control", "no-store")),
                )

        self._server = ThreadingHTTPServer((host, port), Handler)
        # port 0 (ephemeral) means the effective port must be read back from the socket
        self.host = host
        self.port = int(self._server.server_address[1])
        if not self.loopback_only:
            logger.warning(
                "viewer bound to %s:%d — reachable from the network and it has NO authentication; "
                "expose only on a trusted network or through a trusted tunnel (plan §41)",
                host,
                self.port,
            )

    @property
    def httpd(self):
        """The underlying ThreadingHTTPServer (for tests / embedding)."""
        return self._server

    def serve_forever(self):  # pragma: no cover
        logger.info("live viewer on http://%s:%d (exploratory only)", self.host, self.port)
        self._server.serve_forever()

    def shutdown(self):  # pragma: no cover
        self._server.shutdown()
        self._server.server_close()


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    seed: int = 0,
    log_path: Path | None = None,
    allowed_hosts: tuple[str, ...] = (),
) -> MJPEGServer:
    log_path = log_path or Path("logs/viewer_interactions.jsonl")
    server = MJPEGServer(
        host=host, port=port, seed=seed, log_path=log_path, allowed_hosts=allowed_hosts
    )
    return server


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.visualization.server",
        "version": "0.1.0",
        "input_schema": "synthetic source + PipelineConfig (interactive overrides logged)",
        "output_schema": "HTTP dashboard: MJPEG panels, palette legend, state.json",
        "config_schema": "levels/scene/fps via POST forms carrying the per-process token "
                         "(logged, exploratory); GET never mutates state",
        "error_behavior": "per-connection try/except; server keeps serving; 403 on "
                          "non-localhost Host while loopback-bound; 403 on a POST without "
                          "the session token",
        "logging_behavior": "interaction log logs/viewer_interactions.jsonl (UTC timestamps); "
                            "warning when bound beyond loopback",
        "performance_expectations": "no target claimed (plan §21): exploratory viewer, "
                                    "excluded from benchmark measurement",
        "test_coverage": "tests/integration/test_viewer_server.py (HTTP routes, Host validation, interaction log)",
    }
