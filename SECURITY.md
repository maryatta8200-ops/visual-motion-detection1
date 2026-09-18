# Security policy

## Scope

This repository is a **research prototype** (MASTER_PLAN §32, §42). It must not be used for
medical, security, surveillance, or safety-critical purposes, and no early-stage result here
implies operational safety. Current stage: Phase 2 (discrete intensity tokens + deterministic
frame store + per-frame intensity objects); there is still no cross-frame tracking, no
detection, and no learned component. License: [`LICENSE`](LICENSE) (proprietary research).

## What the code does with data

- Raw frames are read from a file, camera, or the seeded synthetic generator; raw frames are
  never required to be discarded, and stores are additive representations bound to their
  source (plan §2).
- The live viewer (`vie serve`) binds **127.0.0.1** by default and, while loopback-bound,
  rejects requests whose `Host` header is not a localhost name (DNS-rebinding defence).
  Network exposure is an explicit opt-in (`--host 0.0.0.0`) and the server warns at startup
  that it has **no authentication, no TLS, and no rate limiting**. `--allowed-host NAME`
  narrows or extends the accepted `Host` names for proxies and tunnels.
- The viewer changes state **only on `POST /`**, and only when the request carries the
  per-process random token that the dashboard embeds in its own parameter forms. A `GET`
  (a link, an image load, a prefetch, a cross-site navigation) can never change
  levels/scene/fps; a token-less or wrongly-tokened `POST` is refused with `403` and leaves
  state untouched. Request bodies are bounded (8 KiB). This is a CSRF control, not
  authentication: anyone who can load the dashboard can still drive the viewer.
- The viewer writes an interaction log (which parameters a human changed, with UTC
  timestamps) to `logs/viewer_interactions.jsonl` by default; select another location with
  `--log-path`. No video is retained beyond explicitly exported frame stores.
- Store bundles are validated against JSON Schemas and SHA-256 checksummed; NPZ loading uses
  `allow_pickle=False`.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository (Security → Report a
vulnerability) rather than a public issue. Include the commit, a minimal reproduction, and
the observed vs expected behavior. Please do not include real camera footage or personal
data in reports; synthetic reproductions (`--input synthetic:<scene>`) are sufficient.

Expected response: acknowledgement within a few days; a decision record entry
(`docs/decisions/decision_log.md`) when a fix changes documented behavior.

## Known limitations relevant to security

- The viewer is a development tool with no authentication; anyone who can reach the port and
  load the dashboard (and therefore read its token) can drive it. Expose it only on a trusted
  network or through a tunnel, and prefer the default loopback bind. State changes are also
  logged to `logs/viewer_interactions.jsonl`, which is the audit trail for who-changed-what.
- Video decoding uses OpenCV; malformed media is handled as a typed `SourceError`, but no
  fuzzing campaign has been run against the decoders.
- No credentials, tokens, or personal data are stored by the tooling.
