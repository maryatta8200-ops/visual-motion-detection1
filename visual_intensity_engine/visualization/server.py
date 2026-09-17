"""Live viewer — EXPLORATORY visualization only (plan §20/§21).

Serves a browser dashboard with side-by-side ORIGINAL | GRAYSCALE | QUANTIZED
panels from a live-processing loop, plus palette legend and processing
metrics. Interactive parameter changes (levels, scene, fps) are logged with
UTC timestamps to `logs/viewer_interactions.jsonl`.

Boundary rule: this viewer is for human inspection; its outputs are NOT
benchmark data. Every page displays that warning (plan §21).
"""

from __future__ import annotations

import io
import json
import logging
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image

from ..config import InputDomainSettings, PipelineConfig, QuantizationSettings
from ..intensity.vocabulary import IntensityVocabulary
from ..preprocessing.grayscale import to_grayscale
from ..preprocessing.quantization import quantize
from .render import colorize, deterministic_palette, to_uint8_gray as _g8, _as_uint8_rgb

logger = logging.getLogger("vie.visualization.server")

_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>VIE live viewer (exploratory)</title>
<style>
 body {{ background:#111; color:#ddd; font-family: ui-monospace, monospace; margin: 12px; }}
 h1 {{ font-size: 16px; }} .warn {{ color:#ffb347; border:1px solid #ffb347; padding:6px; }}
 img.panel {{ max-width: 32%; border:1px solid #333; }}
 table {{ border-collapse: collapse; }} td, th {{ border:1px solid #444; padding: 2px 8px; font-size: 12px; }}
 a {{ color:#7ab8ff; }}
</style></head>
<body>
<h1>VIE live intensity viewer — Phase 1</h1>
<div class="warn">EXPLORATORY VISUALIZATION — NOT BENCHMARK OUTPUT. Parameter changes via links are logged with UTC timestamps.</div>
<p>
 Levels: {level_links} | Scenes: {scene_links} | FPS:
 {fps_links} | <a href="/" onclick="return false;">config:</a> <code>{config_summary}</code>
</p>
<p><img class="panel" src="/stream.mjpg"><img class="panel" src="/stream.mjpg?mode=gray"><img class="panel" src="/stream.mjpg?mode=quantized"></p>
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
                    if key == "levels":
                        val = int(val)
                    if key == "fps":
                        val = float(val)
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


def build_viewer(source, config: PipelineConfig, *, log_path: Path) -> tuple[ViewerState, dict]:
    state = ViewerState(
        scene="moving_square",
        levels=config.quantization.levels,
        fps=30.0,
        seed=config.seed,
        log_path=log_path,
    )
    return state, config.to_dict()


def _make_source(scene: str, levels: int, fps: float, seed: int):
    from ..input.synthetic import SyntheticSource

    return SyntheticSource(scene, (320, 240), 10**9, fps=fps, seed=seed, levels=levels)


class MJPEGServer:
    """Minimal threaded HTTP server: dashboard + MJPEG streams + state.json."""

    def __init__(self, *, host: str = "0.0.0.0", port: int = 8000, seed: int = 0, log_path: Path):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.state = ViewerState(
            scene="moving_square", levels=16, fps=30.0, seed=seed, log_path=log_path
        )
        self.config = PipelineConfig.default(levels=16)
        viewer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # quiet default access log
                logger.debug("%s %s", self.address_string(), fmt % args)

            def do_GET(self):
                path, _, query = self.path.partition("?")
                params = dict(kv.split("=", 1) for kv in query.split("&") if "=" in kv)
                if path == "/":
                    viewer.state.update(
                        levels=params.get("levels"), scene=params.get("scene"), fps=params.get("fps")
                    )
                    html = _HTML.format(
                        level_links=" ".join(
                            f'<a href="/?levels={lv}">{lv}</a>' for lv in (8, 16, 32, 64, 128, 256)
                        ),
                        scene_links=" ".join(
                            f'<a href="/?scene={s}">{s}</a>' for s in ("moving_square", "gradient", "ramp_bands", "static")
                        ),
                        fps_links=" ".join(f'<a href="/?fps={f}">{f}</a>' for f in (5, 15, 30, 60)),
                        config_summary=json.dumps(viewer.state.snapshot(), sort_keys=True),
                    )
                    body = html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif path == "/state.json":
                    body = json.dumps(viewer.state.snapshot(), indent=2).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif path == "/legend.png":
                    vocab = IntensityVocabulary.build_uniform(viewer.state.levels)
                    from .render import render_palette_legend

                    buf = io.BytesIO()
                    render_palette_legend(vocab, out_path=buf)
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(buf.getbuffer().nbytes))
                    self.end_headers()
                    self.wfile.write(buf.getvalue())
                elif path == "/stream.mjpg":
                    mode = params.get("mode", "color")
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
                        draw.text((4, 2), f"frame={rec.frame_index} ts_us={rec.timestamp_us} L={viewer.state.levels}", fill=(255, 255, 80))
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
                    self.send_response(404)
                    self.end_headers()

        self._server = ThreadingHTTPServer((host, port), Handler)
        self.host, self.port = host, port

    def serve_forever(self):  # pragma: no cover
        logger.info("live viewer on http://%s:%d (exploratory only)", self.host, self.port)
        self._server.serve_forever()

    def shutdown(self):  # pragma: no cover
        self._server.shutdown()
        self._server.server_close()


def serve(host: str = "0.0.0.0", port: int = 8000, *, seed: int = 0, log_path: Path | None = None) -> MJPEGServer:
    log_path = log_path or Path("logs/viewer_interactions.jsonl")
    server = MJPEGServer(host=host, port=port, seed=seed, log_path=log_path)
    return server


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.visualization.server",
        "version": "0.1.0",
        "input_schema": "synthetic source + PipelineConfig (interactive overrides logged)",
        "output_schema": "HTTP dashboard: MJPEG panels, palette legend, state.json",
        "config_schema": "levels/scene/fps via query params (logged, exploratory)",
        "error_behavior": "per-connection try/except; server keeps serving",
        "logging_behavior": "interaction log logs/viewer_interactions.jsonl (UTC timestamps)",
        "performance_expectations": "60+ fps at 320x240 per stream",
        "test_coverage": "smoke-tested manually; NOT used for benchmark output (plan §21)",
    }
