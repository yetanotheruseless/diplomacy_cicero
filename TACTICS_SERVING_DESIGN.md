# Design: Exposing searchbot / diplodocus tactics from the Modal GPU image

Status: **draft for review**
Author: Jake + Claude
Related: `modal_app.py`, `cicero-modal-gpu-recipe` (memory), `README_MACOS.md`

## 1. Goal & scope

Turn the no-press **search agents** (`searchbot`, `diplodocus`) into a callable
**tactics service**: given a board state, return that agent's orders (and,
optionally, its policy distribution and position value). Out of scope: dialogue
/ full-press Cicero (already demonstrated as a batch game); training.

The unit of work is one search call:

```
POST {game_json, power|powers, opts} -> {power: orders, [policy], [value]}
```

## 2. Background & the one hard constraint

What we already have, working and on-GPU:
- The built **x86_64+CUDA Modal image** (Python **3.9**, torch `1.10.0+cu113`,
  `pydipcc`, the full `fairdiplomacy` search stack). Cached on Modal.
- Modal **Volume `cicero-models`** with `rl_search_orders.ckpt` +
  `rl_value_function.ckpt` — i.e. a **proven searchbot already runs on this
  image** (full Cicero's order selection *is* this search; see §3).
- Agent API: `agent = build_agent_from_cfg(cfg)`; then
  `agent.get_orders(game, power, state)` or
  `agent.get_orders_many_powers(game, powers)`. Wire format is the game JSON via
  `pydipcc.Game.from_json(str)` / `game.to_json()`.

**The constraint that shapes every option below:** torch 1.10 caps us at
**Python 3.9**, but Modal's *function runtime* (`@app.function`, `@app.cls`,
`@modal.web_server`, `@modal.fastapi_endpoint`) requires Python **≥3.10** in the
image. **`modal.Sandbox` has no such requirement** — it just `exec`s commands in
the image. So every design is really answering: *how do we put an HTTP/RPC front
on a Python-3.9 GPU process?*

## 3. The agents

| Agent | Type | Models | On Volume? |
|---|---|---|---|
| **searchbot** (`agents/searchbot.prototxt`) | `bqre1p` CFR search | default refs `models/blueprint.pt` (supervised policy) | blueprint.pt **no**, but… |
| **searchbot (RL-fed)** = Cicero's tactical core | `bqre1p` CFR search | `rl_search_orders.ckpt` + `rl_value_function.ckpt` | **yes — ready now** |
| **diplodocus_high/low** (`agents/diplodocus_*.prototxt`) | `bqre1p` + DO order-aug | `diplodocus_high_rl_policy.ckpt`, `diplodocus_high_rl_value_function.ckpt`, `no_press_human_imitation_policy.ckpt` | **no — 3-file download** |

Notes:
- **searchbot needs no new models.** Cicero already ran this exact `bqre1p`
  search on the RL nets (the run log shows `rl_search_orders.ckpt` +
  `rl_value_function.ckpt` loading to CUDA before any messaging). Strip the
  dialogue `includes` off `cicero.prototxt` (or write a thin `bqre1p` config
  pointing at the RL nets) and you have a pure no-press searchbot. `blueprint.pt`
  is only the *default* policy choice and is optional.
- **diplodocus needs a one-time Volume add** of its 3 ckpts via the existing
  `fetch_models` downloader (`modal run modal_app.py::download` after appending
  the relpaths). It's a genuinely different agent (ICLR-2023 human-regularized
  RL + planning).
- Both are **light** (no 11GB dialogue model, no nonsense ensemble) → fit
  **A10G / L4**, and a call is bounded by the search budget (`n_rollouts`,
  `bqre1p` iterations).

## 4. The interface ("tactics" contract)

Request:
```jsonc
{
  "game_json": "...",            // pydipcc Game.to_json() string
  "powers": ["TURKEY"],          // or all 7 for a full-board equilibrium
  "agent": "searchbot|diplodocus_high|diplodocus_low",  // pick config
  "n_rollouts": 256,             // optional latency/quality dial
  "seed": 0,                     // optional determinism
  "return": ["orders","policy","value"]   // what to compute
}
```
Response:
```jsonc
{ "TURKEY": { "orders": ["F BLA - CON", ...],
              "policy": {"(F BLA - CON, ...)": 0.42, ...},   // optional
              "value":  {"TURKEY": 0.18, ...} } }            // optional
```

Decisions baked into the contract:
- **Stateless vs. session.** A single-position oracle is **stateless** — build
  the agent once at startup, create a fresh `AgentState` per request. A
  *game-playing* client that steps turn-by-turn benefits from a **session**
  (keep agent + game + per-power state warm across turns, reuse CFR warm-starts)
  → needs session affinity. Recommend: ship stateless first; add sessions later.
- **One power vs. all.** `get_orders_many_powers` computes the all-power
  equilibrium in a single search (no-press makes this natural) — good for a
  "analyze the whole board" call; single-power is cheaper.
- **Beyond orders.** The `bqre1p` agent can surface the **policy distribution**
  over plausible orders and the **value/win-prob** — i.e. "what does it think and
  how sure," not just the move. Worth exposing; needs a small amount of glue to
  reach the internal search result rather than just the sampled action.

## 5. Exposure options

### A. Persistent Sandbox + warm in-image server + Modal tunnel  *(simplest)*
Run a tiny FastAPI/uvicorn server **inside the py3.9 image** that builds the
agent once (models → GPU) and serves `/orders`. Expose the port via a Sandbox
tunnel:
```python
sb = modal.Sandbox.create(app=app, image=image, gpu="A10G", volumes=VOL,
                          encrypted_ports=[8000], timeout=...)
sb.exec("bash","-lc","cd /app && /usr/local/bin/uvicorn tactics_server:app --host 0.0.0.0 --port 8000")
url = sb.tunnels()[8000].url     # public HTTPS
```
- ✅ No version bridge; faithful to current stack; warm GPU; low latency.
- ❌ **No native scale-to-zero.** You manage lifecycle (keep alive; `terminate()`
  or rely on `timeout`). One long-lived box = one GPU billed while up.
- Good for: an internal tactics URL, demos, a single always-on oracle.

### B. Native serverless endpoint (autoscale + scale-to-zero)
This is the only family that gives request-driven replicas that spin down when
idle (`scaledown_window`) — the "scale to zero" behavior. Requires a py≥3.10
runtime, so we bridge to the py3.9 agent. Two sub-variants:

- **B1. Dual-python image + `@modal.web_server`.** Build an image whose *default*
  python is 3.11 (Modal-happy) **and** that carries a separate Python-3.9
  install with the Cicero stack (pydipcc/torch built against it). The web_server
  function (py3.11) launches the **py3.9 uvicorn** server bound to the port;
  Modal proxies. The py3.9 process *is* the server — no hand-rolled IPC.
  ```python
  @app.function(image=dual_py_image, gpu="A10G", volumes=VOL,
                scaledown_window=300, min_containers=0)
  @modal.web_server(8000, startup_timeout=120)
  def serve():
      subprocess.Popen(["/opt/py39/bin/uvicorn","tactics_server:app",
                        "--host","0.0.0.0","--port","8000"])
  ```
  - ✅ Native autoscale + scale-to-zero + a stable URL; clean request model.
  - ❌ Must build a **two-python image** (extra build complexity: py3.9 via
    `python-build-standalone`/`uv`, rebuild pydipcc+nest against it).
- **B2. py3.11 `@app.cls` front + py3.9 worker subprocess over local IPC.**
  `@modal.enter` boots a long-lived py3.9 worker (warm agent); `@modal.method` /
  `@modal.fastapi_endpoint` forwards requests over a unix socket/pipe.
  - ✅ Same autoscale/scale-to-zero; can keep current single-python build and
    just add a 3.11 front layer.
  - ❌ Hand-rolled request/response bridge (serialization, backpressure, worker
    liveness) — more moving parts than B1.

### C. Sandbox `exec` per request (no warm server)
Each request = `sb.exec("python score.py game.json POWER")`.
- ✅ Trivial; stateless; great for **batch** (score N positions, eval sweeps).
- ❌ **Cold model load per call** unless you keep a warm Sandbox and pool — high
  per-request latency. Use for offline batch, not interactive tactics.

### D. Sandbox pool behind a dispatcher
N warm Sandboxes (option A) registered with a small dispatcher (round-robin /
least-loaded), to scale the simple approach for throughput.
- ✅ Reuses A; horizontal scale; you control everything.
- ❌ You're re-implementing what Modal autoscale gives you in B; manual health
  checks, registration, draining.

### E. Escape the Python-3.9 jail (long-term)
Port the no-press agent + `pydipcc` to **torch 2.x / py3.11** so the whole thing
is a first-class Modal function (no Sandbox, no bridge). Checkpoints are
state-dicts (likely load under torch 2.x), but `pydipcc` is built against the
torch 1.10 ABI and the model code may touch removed APIs.
- ✅ Eliminates every workaround; cleanest production story.
- ❌ Uncertain effort (ABI rebuild, API fixups, re-validation); risk of subtle
  behavior drift. Track as a separate spike, not a prerequisite.

### Option comparison

| | Setup | Cold start | Warm latency | Scale-to-zero | Py bridge | Best for |
|---|---|---|---|---|---|---|
| **A** Sandbox+tunnel | low | once (~30–60s) | low | ❌ (manual) | none | demo / internal oracle |
| **B1** dual-py web_server | med-high | per-replica | low | ✅ | image-level | production endpoint |
| **B2** 3.11 front + worker | med | per-replica | low | ✅ | IPC | production w/o image rework |
| **C** exec/request | low | **every call** | n/a | n/a | none | batch eval |
| **D** Sandbox pool | med | once/box | low | ❌ | none | self-managed throughput |
| **E** port to torch2/py3.11 | high | per-replica | low | ✅ | none | long-term clean state |

## 6. Cross-cutting concerns

- **Cold start.** Agent build = load policy+value nets to GPU (~30–60s for
  no-press). Mitigate with `min_containers=1` (always-warm, no scale-to-zero) or
  accept a cold first request after idle. Snapshotting/`@modal.enter` caching
  helps but the GPU load dominates.
- **GPU concurrency.** A search saturates the GPU; serialize per container
  (`@modal.concurrent(max_inputs=1)` or a lock) and scale **out** (more replicas
  = more GPUs) for throughput rather than in-container concurrency.
- **State.** Stateless oracle = fresh `AgentState` per call (simplest, safe).
  Stateful game sessions (turn-by-turn, warm CFR) need session affinity → maps
  cleanly onto a per-session Sandbox (A) or a sticky `@app.cls` instance.
- **Auth.** Tunnels and web endpoints are **public URLs** — add a bearer token /
  Modal proxy auth; don't expose raw.
- **Determinism.** Thread a `seed` through; document that search is stochastic
  otherwise.
- **Agent/version selection.** Either one deployment per agent (searchbot vs
  diplodocus_high vs _low), or one deployment that builds/caches multiple agents
  and picks per request (more GPU memory; fine — they're small).
- **Cost.** A10G ≈ $1.10/hr. A (always-on) bills continuously; B (scale-to-zero)
  bills per request-burst + `scaledown_window` tail. Pick by traffic shape.
- **Observability.** Log search time, n_rollouts, chosen action, value; emit per
  request for latency/quality tuning.

## 7. Recommendation & phasing

1. **Phase 1 (today, ~½ day): Option A.** `tactics_server.py` (warm
   searchbot via the RL nets already on the Volume) + a `modal_app.py::serve`
   entrypoint that boots the Sandbox, opens an `encrypted_ports` tunnel, prints
   the URL. Validate it returns orders + policy + value for a sample S1901M
   board. Zero new model downloads.
2. **Phase 1b:** add diplodocus — append its 3 ckpts to `fetch_models`, run the
   downloader, expose `agent=diplodocus_high|low` as a config switch.
3. **Phase 2 (when it needs to be a real service): Option B1.** Dual-python image
   so it's an autoscaling, scale-to-zero endpoint with a stable URL + auth.
4. **Phase 3 (optional spike): Option E.** Evaluate a torch-2/py-3.11 port to
   retire the bridge entirely.

## 8. Open questions for review

1. **Primary consumer?** Interactive UI (latency-sensitive → warm A or B1) vs.
   batch analysis (C) vs. an agent-vs-agent harness (sessions)?
2. **Stateless oracle or game sessions?** Decides A-stateless vs. sticky
   sessions and shapes the API.
3. **One agent or a menu?** Just searchbot, or searchbot + diplodocus_high/low
   selectable per request?
4. **Always-warm vs. scale-to-zero?** i.e. cost (idle GPU) vs. cold-start
   latency — drives A vs. B and `min_containers`.
5. **What to expose beyond orders?** Orders only, or also policy distribution +
   value (needs a bit more glue into the search result)?
6. **Is the dual-python image (B1) acceptable build complexity**, or prefer the
   IPC bridge (B2)?
```
