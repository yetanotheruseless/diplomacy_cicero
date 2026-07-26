# Modern Cicero Oracle — scale-to-zero Modal serving

The supported Cicero runtime (Ubuntu 24.04, Python 3.12, Torch 2.13.0+cu130,
CUDA 13.0, protobuf 7.35.1/protoc 35.1, patched ParlAI, and `pydipcc`) serves
the live no-press **`imitation`** and **`searchbot`** oracle tiers that
`agentic-diplomacy` consumes over HTTP. Harness: **`modal_serve.py`**.

## Deploy your own endpoint

There is no shared/hosted instance — you deploy the oracle into **your own Modal
workspace**:

```bash
export ORACLE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uvx modal secret create cicero-oracle-token ORACLE_TOKEN="$ORACLE_TOKEN"
uvx modal deploy modal_serve.py
```

`uvx modal deploy` prints the stable web URL it assigned. Modal derives it from your
workspace name and the app/class name, so it has the shape:

```
https://<your-workspace>--cicero-modern-oracle.modal.run
```

Substitute that URL (and `uvx modal app list` / the Modal dashboard for the app id)
everywhere this document writes `<your-workspace>`. The URL is stable across
redeploys of the same app in the same workspace.

| | |
|---|---|
| **URL** | `https://<your-workspace>--cicero-modern-oracle.modal.run` (printed by `uvx modal deploy`) |
| **Token** | bearer token supplied at runtime through `ORACLE_TOKEN` from the `cicero-oracle-token` Modal Secret; never commit or print its value |
| **Tiers** | `imitation` — `base_strategy_model` + human-imitation policy; `searchbot` — CFR search + RL policy/value models |
| **GPU** | A10G, `scaledown_window=120s` (raise for production), `min_containers=0` |
| **App** | `cicero-modern-oracle` (app id visible via `uvx modal app list`) |

The uploader reads an already-populated `.cicero_model_stage/`; it does not copy
from `models/` automatically. Stage the three serving checkpoints, then upload
them to the `cicero-models` Volume:

```bash
mkdir -p .cicero_model_stage
cp models/{no_press_human_imitation_policy,rl_search_orders,rl_value_function}.ckpt \
  .cicero_model_stage/
./scripts/upload_models_modal.sh
```

## Wire contract (matches `agentic-diplomacy/oracle/transport.py::HttpTransport`)

```
GET  /health  -> 200 {"status":"ok","ready":true}
POST /rpc     -> {"id","method","params"}  (+ Authorization: Bearer <ORACLE_TOKEN>)
              -> {"id","ok":true,"result":{...}}   |   {"id","ok":false,"error":...}
```
`get_orders` params: `{game_json, power, tier:"imitation|searchbot", seed?}` ->
`{orders:[str]}`.

## Current modern deployment evidence

The maintainer workspace was redeployed and validated on 2026-07-26 from
[`ee5b7d1f156ea5229354317f5c9e84f793f9615d`](https://github.com/yetanotheruseless/diplomacy_cicero/commit/ee5b7d1f156ea5229354317f5c9e84f793f9615d):

- deployed app: `ap-3hb6yPtUQLFbErF3reQRMM`;
- stable endpoint: `https://jakemannix--cicero-modern-oracle.modal.run`;
- cold-start `/health`: `200 {"status":"ok","ready":true}`;
- authenticated `info`: both `imitation` and `searchbot` were ready;
- authenticated `get_orders(FRANCE, imitation)`:
  `["F BRE - MAO","A PAR - BUR","A MAR S A PAR - BUR"]`;
- authenticated `get_orders(FRANCE, searchbot)`:
  `["F BRE - ENG","A PAR - PIC","A MAR - SPA"]`; and
- scale-to-zero: the deployed app returned from one active task to zero after
  the 120-second scale-down window.

For this recorded evidence, the authenticated RPC calls ran inside the serving
container using the injected `cicero-oracle-token` secret; the token was neither
copied to the local environment nor printed. The reusable
`modal_serve.py::verify` entry point instead accepts the matching token through
its local `ORACLE_TOKEN` environment variable or `--token` argument and never
prints its value.

## Historical initial deployment evidence (imitation tier)

Captured from a real deployment during the earlier Python 3.11/cu124
modernization spike; the deploying workspace name is redacted as `<workspace>`.
This demonstrates the wire/scale-to-zero design, but it is not current
Python-3.12/cu130 runtime evidence. Rerun `modal_serve.py::verify` after
deploying the current image.

```
/health -> 200 {'status': 'ok', 'ready': True}            # cold start
info    -> {ready:true, agent_config:base_strategy_model.prototxt, device:cuda,
            tiers:["imitation"], default_tier:"imitation"}
bad bearer token -> 401                                    # auth enforced
get_orders(FRANCE)  -> ["F BRE - MAO","A PAR - BUR","A MAR S A PAR - BUR"]   (9.4s, builds agent)
get_orders(GERMANY) -> ["F KIE - DEN","A MUN - RUH","A BER - KIE"]          (0.5s, agent cached)
```

Scale-to-zero (real `uvx modal app list`, after the request burst):
```
12:47:12  cicero-modern-oracle  deployed  Tasks 1     # warm
12:48:03  cicero-modern-oracle  deployed  Tasks 0     # idle past scaledown_window
12:49:44  cicero-modern-oracle  deployed  Tasks 0     # stays at 0 (=> $0 GPU); URL stable
```

## Architecture

The current stack uses one Python 3.12 interpreter for the Modal function and
the oracle process:

- Image = `modal_modern.gpu_image` (the validated modern build) + the 4 oracle
  sidecar files staged flat into `/opt/oracle`.
- `@app.cls` + `@modal.web_server(8000)`: `@modal.enter` `subprocess.Popen`s
  `oracle_server.py --transport http` in the same Python 3.12 interpreter Modal
  uses for the function runtime.
- `modal_modern.py` is baked into the image so the class module's runtime import
  (`from modal_modern import gpu_image, VOL`) resolves in-container.

## Serving dependency boundary

B1/B2/B3 exercise model loading and inference directly, while the oracle's
`get_orders` integration also reaches Matplotlib-backed visualization code.
The canonical `dialogue` extra already supplies Pillow; `modal_serve.py` adds
only pinned `matplotlib==3.11.1` as a serving-specific dependency. This layer is
installed before deployment and does not replace PyTorch or rebuild `pydipcc`.

## Wiring the runner

Point the runner's oracle client at:
- `--modal-url https://<your-workspace>--cicero-modern-oracle.modal.run` (the URL
  `uvx modal deploy` printed for your workspace)
- token via `ORACLE_TOKEN='<value from your secret manager>'` (matching
  `cicero-oracle-token` Secret).

Redeploy with a longer `scaledown_window` for an extended game:
`ORACLE_SCALEDOWN_WINDOW=600 uvx modal deploy modal_serve.py`.

## Operational notes

- The default deployment co-resides `imitation` and `searchbot`; set
  `ORACLE_TIERS` to a comma-separated subset when only one tier is needed.
- `ORACLE_SEARCHBOT_ROLLOUTS` controls the searchbot latency/quality tradeoff and
  defaults to 8 for serving latency.
- Both tiers are explicitly no-press and use `rl_value_function.ckpt` for
  positional values. Searchbot policy calls return search-refined candidates;
  imitation policy calls use the policy-net sampling path.
- `ORACLE_TOKEN='<value matching the Modal Secret>' uvx modal run
  modal_serve.py::verify` checks rejection of an invalid bearer token, then
  exercises `get_orders` for every configured tier and asserts scale-to-zero.
  Run it after deployment because the full check needs the Modal GPU image and
  model Volume.
