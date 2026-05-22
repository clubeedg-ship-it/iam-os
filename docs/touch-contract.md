# IAM-OS Touch Contract

| | |
|---|---|
| **Version** | 1.0.0 |
| **Status** | Frozen |
| **Schema** | [`touch-contract.schema.json`](./touch-contract.schema.json) |
| **Defined by** | `specs.md` §4.2 |

## Purpose

The touch contract is the **integration boundary** between the IAM-OS platform
and everything that consumes touch input — games and the Launcher UI. It is the
only data contract the platform guarantees to game authors.

It is **frozen**: once a version is tagged, its shape does not change. Any change
ships as a new version and must remain backward-compatible with this one. The
machine-readable `touch-contract.schema.json` is the enforceable form — bridge
tests, launcher tests, and the game validator all assert against it.

## Transport

`touch-bridge` runs a WebSocket server at:

```
ws://localhost:8765
```

It accepts multiple clients (the Launcher UI and the active game) and
**broadcasts** one JSON text message per frame to every connected client.
Clients only read; they never send.

## Message format

Each message is a JSON object — a *touch frame*:

```json
{
  "seq": 1234,
  "count": 1,
  "touches": [
    { "id": 0, "x": 0.42, "y": 0.71 }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `seq` | integer ≥ 0 | Monotonically increasing frame counter. Resets to 0 only when `touch-bridge` restarts. |
| `count` | integer ≥ 0 | Number of active touches in this frame. |
| `touches` | array | The active touches. Empty when `count` is 0. |
| `touches[].id` | integer ≥ 0 | Stable identifier for one touch. The same physical touch keeps the same `id` across frames. |
| `touches[].x` | number 0.0–1.0 | Horizontal position, normalized to the projection surface (0.0 = left, 1.0 = right). |
| `touches[].y` | number 0.0–1.0 | Vertical position, normalized to the projection surface (0.0 = top, 1.0 = bottom). |

## Invariants

A consumer may rely on all of the following:

1. `count` equals `touches.length`.
2. `x` and `y` are always within `[0.0, 1.0]` — already calibrated and clamped.
3. `id` values are stable: a touch that persists across frames keeps its `id`.
4. `seq` strictly increases between consecutive messages from one bridge run.
5. When there is no input, the bridge still sends frames with `count: 0` and an
   empty `touches` array — it never goes silent and never sends stale data.

## Consumer guidance

- A game should treat `x`/`y` as fractions of its own viewport.
- A game should tolerate `id`s appearing and disappearing between frames.
- Games should include a mouse fallback for development without a sensor
  (see the reference game in `legacy/stapzone_training_v8_pro.html`).
- On socket close, reconnect with a short backoff — the bridge may restart.

## Versioning

This document and its schema are tagged `contract-v1.0.0`. Future revisions:

- **Backward-compatible additions** (new optional fields) bump the minor version.
- **Breaking changes** bump the major version and require a migration note.
- Existing games built against v1.x.y must keep working without changes.
