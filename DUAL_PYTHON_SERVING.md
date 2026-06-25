# Dual-Python Modal Function for the Cicero oracle

Serve the Cicero / Diplodocus tactics oracle as a Modal **Function**
(`@app.cls` + `@modal.web_server`) instead of a `modal.Sandbox`. The payoff is
**native scale-to-zero**, a **stable URL**, and **automatic cold-start** — none of
which a Sandbox gives you. This is "Option B1" from
[`TACTICS_SERVING_DESIGN.md`](./TACTICS_SERVING_DESIGN.md) §5.

> **Status: DRAFT, UNVERIFIED ON MODAL.** Authored without a Modal account or GPU.
> The module is `py_compile`-clean and imports cleanly under the real `modal`
> 1.4.1 client (all decorators/kwargs validated). The **image build** and **GPU
> serve** have **not** been run. Every uncertainty is called out under
> [Blockers](#blockers-the-owner-must-resolve-on-modal). Treat the numbers
> (`scaledown_window`, `startup_timeout`, GPU sizes) as starting points to verify.

New file: [`modal_function.py`](./modal_function.py). The old
`modal_app.py::serve` Sandbox path is **left intact as a fallback** (it still works
and is the only thing proven on GPU today).

---

## 1. Why a Function, and why dual-python

`modal_app.py` serves Cicero from a `modal.Sandbox` *because* the image is **Python
3.9** (torch `1.10.0+cu113` + a C++ `pydipcc` compiled against 3.9), and Modal
**Functions require Python ≥ 3.10** — Modal dropped 3.9. A `Sandbox` has no such
requirement (it just `exec`s commands in the image), but a Sandbox **does not scale
to zero**: you pay for the GPU for the whole `timeout`, manage lifecycle by hand,
and the tunnel URL changes every launch.

A **Function** with `scaledown_window` tears the container (and GPU) down after an
idle period → **$0 when no game is using it** — and **cold-starts on the next
request** behind a **stable URL**. That is what we want for an oracle that's only
hit during active games.

The catch: the Function's *runtime* must be ≥ 3.10, but the Cicero stack must stay
3.9. So we run **two Python interpreters in one container** (one GPU):

```
┌─ Modal container (one GPU) ───────────────────────────────────────────────┐
│  PATH starts with /opt/py311-venv/bin  ⇒  Modal runtime uses Python 3.11   │
│                                                                            │
│  @modal.enter (py3.11) ──Popen──▶  /usr/local/bin/python3.9                │
│                                     oracle_server.py --transport http      │
│                                     binds 127.0.0.1:8000, owns CUDA        │
│                                                                            │
│  @modal.web_server(8000) ◀── Modal proxies inbound HTTPS ──▶ :8000         │
└────────────────────────────────────────────────────────────────────────────┘
        ▲ stable URL: https://<workspace>--cicero-oracle.modal.run
        │ POST /rpc, GET /health  ← byte-identical to the Sandbox tunnel
   agentic-diplomacy HttpTransport (oracle/transport.py)
```

The wire contract is **unchanged**: the py3.9 process is the *same*
`oracle/server/oracle_server.py --transport http` the Sandbox already runs, so
`oracle/transport.py`'s `HttpTransport` (the runner's client) cannot tell the
difference between a Sandbox tunnel and a Function endpoint.

---

## 2. How the dual-python image is built (the crux)

**Do NOT use `Image.from_registry("python:3.9-slim", add_python="3.11")`.** I read
the modal-client source (`modal/image.py::_registry_setup_commands`): `add_python`
emits

```dockerfile
COPY /python/. /usr/local
RUN ln -s /usr/local/bin/python3 /usr/local/bin/python
```

i.e. it **overlays the standalone 3.11 into `/usr/local` and repoints
`python`/`python3` there**. On `python:3.9-slim`, `/usr/local` is exactly where the
3.9 lives — so `add_python` would **clobber the 3.9 interpreter** and every
`pip_install(...)` in `modal_app.image` (torch 1.10, pydipcc build deps) would land
in 3.11. That breaks the whole load-bearing stack.

So `modal_function.py` keeps **3.9 as the image's real `python`** (which satisfies
Modal's "image must have `python` on PATH" requirement *during build*) and adds
3.11 as a **separate, side-by-side overlay**:

1. **Reuse the fully-built 3.9 image** (`from modal_app import image`). All the slow
   layers (nest, dipcc compile, torch swap, patchelf) are cached and reused
   unchanged.
2. **Install python-build-standalone 3.11 into `/opt/py311`** (its own prefix —
   does **not** touch `/usr/local/bin/python*`). We pull the *exact* glibc build
   Modal itself pins for `add_python="3.11"` (release `20230826`, `3.11.5`, from
   `modal/mount.py::PYTHON_STANDALONE_VERSIONS`), so it's a known-good x86_64 dist.
3. **Make a venv** `/opt/py311-venv` on top of it and `pip install modal` there (the
   only dep the 3.11 *runtime* needs — the heavy web stack stays in the 3.9 process).
4. **Prepend the 3.11 venv to `PATH`** via `.env({"PATH": "/opt/py311-venv/bin:…"})`
   so Modal's function runtime resolves `python` → 3.11. The 3.9 interpreter is
   still at its absolute path `/usr/local/bin/python3.9`.
5. **Assert both** in a build `RUN`: `python` is 3.11 *and* `/usr/local/bin/python3.9`
   is still 3.9 — the build hard-fails if either assumption broke.

The `@modal.enter` subprocess forces the legacy interpreter two ways (belt +
braces): it `Popen`s `bash -lc "<cmd>"` with **`/usr/local/bin` prepended to the
subprocess PATH** (so the bare `python`/`pip` tokens inside `_oracle_cmd` resolve to
3.9), overriding the 3.11-first PATH that Modal's runtime uses.

### Why this is the documented-correct mechanism

- Modal's only stated requirement for a registry image is: *"the image is expected
  to have Python on PATH as `python`, along with `pip`"* (modal `from_registry`
  docstring). Our final `python` on PATH is 3.11 (≥ 3.10) ✓.
- Modal resolves the function entrypoint's interpreter via **PATH** (it shells a
  `python` from PATH; there is no fixed absolute path). Putting 3.11 first is the
  supported way to choose it. **(This PATH-resolution detail is the single biggest
  thing to verify on a real deploy — see Blocker B1.)**

### Local proof of the cross-interpreter pattern

The "modern interpreter `Popen`s a *different* interpreter's HTTP server and proxies
a request" pattern was proven locally on macOS with two real interpreters
(py3.13 as the "modern runtime", py3.10 as the "legacy 3.9"): the modern process
launched the legacy one by absolute path, polled `/health`, POSTed `/rpc`, and
asserted the **legacy** interpreter answered with the exact
`{"id","ok","result"}` envelope `HttpTransport` expects. This validates the
mechanism; it does **not** validate the Modal image build or GPU.

---

## 3. Deploy + smoke-test commands

All run from the `diplomacy_cicero` checkout (this worktree), with the
`agentic-diplomacy` oracle sources reachable (default sibling path, or set
`AGENTIC_ORACLE_DIR`).

```bash
# 0) one-time: models Volume must be populated (same as the Sandbox path)
modal volume put cicero-models .cicero_model_stage /     # or: modal run modal_app.py::download
# (searchbot/imitation/cicero tiers need rl_search_orders.ckpt + rl_value_function.ckpt;
#  diplodocus_* need their 3 ckpts via modal_app.py::download — see modal_app.TIER_PRESETS.)

# 1) (recommended) a STABLE bearer token + tiers/gpu as deploy-time config.
#    The token is read by clients from ORACLE_TOKEN (the runner already uses
#    token_env="ORACLE_TOKEN").
modal secret create cicero-oracle-token ORACLE_TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')
#    NOTE: to actually inject that secret into the Function you must add
#    `secrets=[modal.Secret.from_name("cicero-oracle-token")]` to the @app.cls(...)
#    decorator (left out by default so a bare deploy works with an ephemeral token).
#    See Blocker B5.

# 2) deploy. Tiers/GPU/knobs come from env at deploy time (see modal_function.py top):
ORACLE_TIERS=searchbot ORACLE_GPU=A10G modal deploy modal_function.py
#    -> prints the stable web URL, e.g.
#       https://<workspace>--cicero-oracle.modal.run
#    (the label="cicero-oracle" on @modal.web_server makes the URL deterministic.)

# 3) print the wiring config (no GPU spent):
modal run modal_function.py::info

# 4) cold-start smoke from agentic-diplomacy (drives the REAL client transport):
cd ../agentic-diplomacy
uv run --no-project python -m oracle.server.modal_smoke \
    --url https://<workspace>--cicero-oracle.modal.run \
    --token "$ORACLE_TOKEN" --tier searchbot --health-timeout 1800
#    (modal_smoke retries /health for up to --health-timeout s while the cold
#     container boots + loads models, then exercises info/get_orders/policy/value.)
```

A raw one-liner smoke without the client (just curl the envelope):

```bash
curl -s https://<workspace>--cicero-oracle.modal.run/health
curl -s -X POST https://<workspace>--cicero-oracle.modal.run/rpc \
  -H "Authorization: Bearer $ORACLE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"id":1,"method":"info","params":{}}'
```

To run **multiple tiers** (e.g. a heavy `cicero` on its own A100 and a light
`searchbot` on an A10G), deploy **two apps** with different `ORACLE_TIERS`/`ORACLE_GPU`
and (to avoid URL collision) different `label=`/app name — see Blocker B6.

---

## 4. Wiring the agentic-diplomacy runner to the stable URL

The whole point of a Function vs. a Sandbox: **the URL is stable**, so the runner
**never has to re-spawn** the oracle. The runner resolves the oracle URL from (in
order) `--modal-url`, `agents/.oracle-endpoint`, then `$ORACLE_MODAL_URL`
(`run_agents.sh` + `agents/runner/oracle.py::build_oracle_registry`). All three feed
the same `RegistryOracle`/`HttpTransport`.

Pick **one** of:

```bash
# A) put the stable URL where start_oracle.sh would have written it, ONCE:
echo 'https://<workspace>--cicero-oracle.modal.run' > agents/.oracle-endpoint
# then just:
./run_agents.sh <game-id>          # reads .oracle-endpoint, wires --modal-url

# B) or in agents/.env (auto-loaded), set the stable URL + token:
#     ORACLE_MODAL_URL=https://<workspace>--cicero-oracle.modal.run
#     ORACLE_TOKEN=<the token you put in the cicero-oracle-token secret>

# C) or pass it explicitly:
./run_agents.sh <game-id> --modal-url https://<workspace>--cicero-oracle.modal.run
```

`HttpTransport` POSTs to `<url>/rpc` with `Authorization: Bearer $ORACLE_TOKEN` and
ready-checks `<url>/health` — exactly the routes the Function exposes.

### What changes vs. the Sandbox flow

- `start_oracle.sh`'s **re-spawn machinery becomes unnecessary** for the Function.
  Today `run_agents.sh` detects an idled-down Sandbox (dead tunnel URL) and re-runs
  `start_oracle.sh --modal --persist`. With a Function the URL **stays valid across
  scale-to-zero**: a request to the idle URL just **cold-starts** a new container.
  So the runner can keep `agents/.oracle-endpoint` = the stable URL permanently and
  the "re-spawn on unreachable" branch in `run_agents.sh` never needs to fire.
- The runner's **eager readiness check** (`validate_tiers` → `HttpTransport.start`)
  will **trigger a cold start** at game launch. With `ORACLE_HTTP_RETRIES`/timeouts
  at defaults this may time out on a cold boot (model load is minutes). **Bump the
  ready timeout for cold starts** — see Blocker B3 (cold-start budget). Setting
  `min_containers=1` (a warm GPU) avoids the cold start entirely, at idle-GPU cost.

> A tiny follow-up (out of scope here, owner's repo): teach `start_oracle.sh` a
> `--function` mode that `modal deploy`s this module once and writes the stable URL
> to `agents/.oracle-endpoint`, instead of streaming a Sandbox tunnel. Not required
> — option A/B above already wire it.

---

## 5. Cold-start expectation & the knobs

| Knob | Where | Default here | Meaning |
|---|---|---|---|
| `scaledown_window` | `@app.cls` | **1800 s** | idle seconds before the container (and GPU) is torn down → $0. **See Blocker B2: docs mention a 1200 s cap in one place.** |
| `startup_timeout` (cls) | `@app.cls` | 1800 s | how long Modal allows container boot + `@modal.enter` (modal ≥ 1.1.4). |
| `startup_timeout` (web) | `@modal.web_server` | 1800 s | how long Modal waits for **port 8000 to accept a TCP connection**. Default is **5 s** — far too short; model load gates the socket bind (see below). |
| `min_containers` | `@app.cls` | 0 | keep N GPUs always-warm (no cold start) at idle cost. `0` = pure scale-to-zero. |
| `@modal.concurrent(max_inputs=1)` | method | 1 | one search saturates the GPU; scale **out** (more containers), not in. |

**Cold start = container boot + model load.** When idle, the container is gone;
the next request boots a fresh one, runs `@modal.enter` (Popen the 3.9 oracle), and
the oracle loads its tier's policy/value nets to the GPU. The no-press nets are
**small** (8M params, ≤150 MB ckpts — see `docs/cicero-oracle.md` §10), so expect
**~30–60 s** for `searchbot`; full-press `cicero` (dialogue ensembles) is much
heavier (minutes). `WEB_STARTUP_TIMEOUT`/`startup_timeout` of **1800 s** is generous
on purpose.

**Critical ordering fact:** `oracle_server.py::main()` builds `CiceroBackend`,
eager-loads the value nets, and **only then** calls `serve_http()` (which binds the
socket). So **the port does not open until model loading is well underway** — the
`web_server` `startup_timeout` *must* cover the model-load time, which is why 5 s
would fail every cold start. 1800 s covers it.

To eliminate cold starts for an interactive session, deploy with
`ORACLE_MIN_CONTAINERS=1` (keeps one warm GPU; you pay for it continuously, like the
old Sandbox but with the autoscale/stable-URL upside).

---

## 6. Files

- [`modal_function.py`](./modal_function.py) — the dual-python image
  (`_dual_python_image()`), the `@app.cls` `CiceroOracle` with `@modal.enter`
  (Popen the 3.9 oracle), `@modal.web_server` (proxy), `@modal.exit` (teardown),
  and a `modal run …::info` local entrypoint. Reuses the proven 3.9 `image`, the
  `cicero-models` Volume, `ORACLE_FILES` staging, `TIER_PRESETS`, and `_oracle_cmd`
  from `modal_app.py` (single source of truth for the heavy build).
- [`modal_app.py`](./modal_app.py) — **unchanged path kept as fallback**: the
  Sandbox `serve` (proven on GPU) and the `smoke`/`game`/`main`/`download`
  entrypoints.

---

## Blockers the owner must resolve on Modal

Ordered by how likely they are to bite. None are testable without a Modal account +
GPU; each says exactly what to check.

**B1 — Does Modal's function runtime really pick `python` from PATH? (the crux)**
The whole design assumes Modal shells the function entrypoint via a `python`
resolved on `$PATH`, so prepending the 3.11 venv selects 3.11. This is consistent
with the documented `from_registry` requirement ("python on PATH") but Modal's
*exact* runtime-launch mechanism for a registry image with a non-default `python` is
**not documented**. *Verify:* deploy and confirm the container starts (the
`@modal.enter` runs under 3.11). If Modal instead hardcodes an absolute interpreter
path or re-derives one, the fix is `setup_dockerfile_commands` to set the
interpreter, or — simplest fallback — invert to **3.11-base + a 3.9 overlay**
(`add_python` is not usable for 3.9 since Modal dropped it; you'd install
python-build-standalone 3.9 into `/opt/py39` and **rebuild pydipcc/nest against that
3.9**, which is more work but removes the PATH ambiguity). The build's own
`python`/`python3.9` version asserts will catch a broken overlay at **build** time;
B1 is specifically about *runtime* selection.

**B2 — `scaledown_window=1800` may exceed Modal's cap.** The cold-start guide says
the idle window is configurable "between 2 and 1,200 seconds" in one place; the
`@app.cls` reference doesn't state a cap, and the client accepts 1800 (even 99999)
**without complaint** — so any limit is enforced **server-side** at deploy/run.
*Verify:* `modal deploy` and watch for a clamp/reject. If rejected, set
`ORACLE_SCALEDOWN_WINDOW=1200` (the documented max). This does not affect
correctness, only how long the GPU lingers idle.

**B3 — Cold-start budget vs. the runner's readiness check.** The runner's
`validate_tiers` opens each tier (`HttpTransport.start` → `/health` + an `info`
call) at game launch, which **triggers a cold start**. `HttpTransport`'s defaults
(`ORACLE_HTTP_RETRIES=4`, modest backoff) likely won't span a minutes-long cold
boot. *Verify/resolve:* either run with `min_containers=1` (warm), or raise the
client's ready timeout for the first call (the runner passes `ready_timeout` into
`OracleClient.modal`; `modal_smoke.py` already uses `--health-timeout 1800`). Decide
the interactive vs. cost tradeoff.

**B4 — `@modal.web_server` + `@modal.enter` interaction / empty `web()` body.** The
Modal docs show `@modal.web_server` with the server `Popen`'d **inside** the
decorated function. We instead start the server in `@modal.enter` and leave `web()`
empty (the server is already listening; Modal only needs the port open). This
*should* be equivalent (Modal's liveness check is a TCP connect to the port), and is
arguably cleaner (one Popen per container, in `enter`), but it is **not the exact
documented shape**. *Verify:* if the endpoint 502s or Modal complains the function
"never opened the port," move the `subprocess.Popen` into `web()` and drop
`@modal.enter` (the docs' canonical pattern). The argv/env are identical either way;
only which decorator owns the Popen changes.

**B5 — The auth token is not wired into the Function by default.** `@modal.enter`
reads `ORACLE_TOKEN` from env and mints an ephemeral one (logged) if absent. To get
a **stable** token across cold starts you must attach the secret:
`@app.cls(..., secrets=[modal.Secret.from_name("cicero-oracle-token")])`. It's left
off so a bare `modal deploy` works out of the box. *Resolve:* create the secret (see
§3 step 1) and add the `secrets=[…]` kwarg before deploying for real, then put the
same token in `agents/.env` as `ORACLE_TOKEN`. Without this, each cold start has a
new token and clients can't authenticate. (Alternatively use `requires_proxy_auth=True`
on `@modal.web_server` for Modal's built-in proxy auth and drop the bearer token.)

**B6 — Tiers/GPU are deploy-time, not per-request.** A `@modal.web_server` Function
can't take the Sandbox `serve`'s CLI args, so `ORACLE_TIERS`/`ORACLE_GPU` are read
from env at `modal deploy`. A single deploy serves a fixed tier set on a fixed GPU.
For a heavy `cicero` (A100) **and** a light `searchbot` (A10G), deploy **two**
apps with distinct app names + `label=` (else both web servers collide on
`…--cicero-oracle.modal.run`). *Resolve:* parameterize app name/label by tier set,
or just maintain two copies. The runner can point different tiers at different URLs
via an oracle-config JSON instead of a single `--modal-url`.

**B7 — Volume contents & per-tier ckpts.** Same as the Sandbox path: `searchbot`
(RL nets) is ready on the Volume; `diplodocus_*` need a one-time `modal run
modal_app.py::download`. *Verify:* the Volume has the ckpts referenced by the chosen
`TIER_PRESETS` before deploying.

**B8 — python-build-standalone download at build time.** The image build wgets the
3.11 tarball from GitHub releases (`indygreg/python-build-standalone`,
`20230826`/`3.11.5`). *Verify:* the build has network egress to GitHub (Modal
builders do); if that release URL ever 404s, bump `_PBS_RELEASE`/`_PBS_VERSION` to a
current standalone build (any `3.11.x x86_64-unknown-linux-gnu-install_only` works).

**B9 — `add_local_file(copy=True)` for the oracle sidecar files invalidates layers
on edit.** The oracle `.py` files are baked into the image; editing them in
`agentic-diplomacy` forces a rebuild of the layers after the COPY. This is fine
(those layers are cheap, after the cached torch/dipcc layers) but worth knowing when
iterating on the oracle code. *No action needed*; just expect a partial rebuild.

---

## What was validated vs. not

**Validated locally (no Modal):**
- `modal_function.py` is `py_compile`-clean and **imports under real `modal` 1.4.1**;
  the `@app.cls` image graph, `@modal.web_server(port, startup_timeout=…, label=…)`,
  `@modal.enter`/`@modal.exit`, `@modal.concurrent(max_inputs=1)`, and the
  `scaledown_window`/`min_containers`/`startup_timeout`/`gpu`/`volumes` kwargs are
  all accepted (signatures introspected; a throwaway cls with `scaledown_window=1800`
  + both `startup_timeout`s decorates without error).
- The `add_python` clobber hazard was confirmed by **reading the modal-client source**
  (`COPY /python/. /usr/local` + symlink), which is *why* we use a side-by-side
  overlay instead.
- The python-build-standalone 3.11 pin matches what Modal's own `add_python="3.11"`
  uses (`modal/mount.py`), so the dist is known-good for x86_64/glibc.
- The **cross-interpreter Popen + HTTP-proxy** pattern was run end-to-end with two
  real interpreters and asserted the legacy one answered with the exact
  `HttpTransport` envelope.

**NOT validated (needs Modal account + GPU):**
- The image **build** (3.9 base + 3.11 overlay; the build-time version asserts).
- That Modal's runtime actually launches the function under the **3.11 on PATH**
  (Blocker B1 — the load-bearing assumption).
- The **GPU serve**: cold start, model load, `/health`, `/rpc` answering real
  searches; and that `web_server`+`enter` proxy correctly (Blocker B4).
- `scaledown_window=1800` not being clamped (Blocker B2).
- End-to-end through the **runner** against the stable URL.
