# Modern Cicero Oracle — scale-to-zero Modal serving

Capstone of the modernization spike: the modernized Cicero (Python 3.11 / torch
2.6 cu124 / modern protobuf / pydipcc / pure-Python `nest` shim) serves the live
no-press **`imitation`** and **`searchbot`** oracle tiers that
`agentic-diplomacy` consumes over HTTP. Harness: **`modal_serve.py`**.

## Deployed endpoint

| | |
|---|---|
| **URL** | `https://jakemannix--cicero-modern-oracle.modal.run` |
| **Token** | bearer token supplied at runtime through `ORACLE_TOKEN` from the `cicero-oracle-token` Modal Secret; never commit or print its value |
| **Tiers** | `imitation` — `base_strategy_model` + human-imitation policy; `searchbot` — CFR search + RL policy/value models |
| **GPU** | A10G, `scaledown_window=120s` (raise for production), `min_containers=0` |
| **App** | `cicero-modern-oracle` (Modal app id `ap-Rtxiv2zpjjjz2lWlke40hw`) |

## Wire contract (matches `agentic-diplomacy/oracle/transport.py::HttpTransport`)

```
GET  /health  -> 200 {"status":"ok","ready":true}
POST /rpc     -> {"id","method","params"}  (+ Authorization: Bearer <ORACLE_TOKEN>)
              -> {"id","ok":true,"result":{...}}   |   {"id","ok":false,"error":...}
```
`get_orders` params: `{game_json, power, tier:"imitation|searchbot", seed?}` ->
`{orders:[str]}`.

## Initial deployment evidence (imitation tier)

```
/health -> 200 {'status': 'ok', 'ready': True}            # cold start
info    -> {ready:true, agent_config:base_strategy_model.prototxt, device:cuda,
            tiers:["imitation"], default_tier:"imitation"}
bad bearer token -> 401                                    # auth enforced
get_orders(FRANCE)  -> ["F BRE - MAO","A PAR - BUR","A MAR S A PAR - BUR"]   (9.4s, builds agent)
get_orders(GERMANY) -> ["F KIE - DEN","A MUN - RUH","A BER - KIE"]          (0.5s, agent cached)
```

Scale-to-zero (real `modal app list`, after the request burst):
```
12:47:12  cicero-modern-oracle  deployed  Tasks 1     # warm
12:48:03  cicero-modern-oracle  deployed  Tasks 0     # idle past scaledown_window
12:49:44  cicero-modern-oracle  deployed  Tasks 0     # stays at 0 (=> $0 GPU); URL stable
```

## Architecture — simpler than the legacy dual-python serving

The legacy oracle (`diplomacy_cicero-dualpy/modal_function.py`) had to overlay a
Python-3.11 standalone next to the load-bearing **Python-3.9** Cicero and run the
oracle in a 3.9 subprocess (Modal Functions require `python >= 3.10`, but the
legacy stack is 3.9-only). The **modern** stack is already pure 3.11, so:

- Image = `modal_modern.gpu_image` (the validated modern build) + the 4 oracle
  sidecar files staged flat into `/opt/oracle`.
- `@app.cls` + `@modal.web_server(8000)`: `@modal.enter` `subprocess.Popen`s
  `oracle_server.py --transport http` **in the same 3.11 interpreter** Modal uses
  for the function runtime. No overlay, no cross-interpreter subprocess, no PATH
  juggling.
- `modal_modern.py` is baked into the image so the class module's runtime import
  (`from modal_modern import gpu_image, VOL`) resolves in-container.

## Modern-stack integration bug found + fixed

This step is the first to run the `OracleService`/`CiceroBackend` wrapper on the
modern stack (B1/B2/B3 only exercised the model *import/inference* paths). It
surfaced one real bug: **`get_orders` transitively imports `PIL` (Pillow)** — a
viz dependency not pulled in by the model import paths, so it wasn't in
`modal_modern`'s `PIP_DEPS`. Fixed by adding `Pillow`/`matplotlib` as a serving
runtime layer (`SERVING_RUNTIME_DEPS` in `modal_serve.py`). After that, orders
generate cleanly.

## Wiring the runner

Point the runner's oracle client at:
- `--modal-url https://jakemannix--cicero-modern-oracle.modal.run`
- token via `ORACLE_TOKEN='<value from your secret manager>'` (matching
  `cicero-oracle-token` Secret).

Redeploy with a longer `scaledown_window` for an extended game:
`ORACLE_SCALEDOWN_WINDOW=600 modal deploy modal_serve.py`.

## Operational notes

- The default deployment co-resides `imitation` and `searchbot`; set
  `ORACLE_TIERS` to a comma-separated subset when only one tier is needed.
- `ORACLE_SEARCHBOT_ROLLOUTS` controls the searchbot latency/quality tradeoff and
  defaults to 8 for serving latency.
- Both tiers are explicitly no-press and use `rl_value_function.ckpt` for
  positional values. Searchbot policy calls return search-refined candidates;
  imitation policy calls use the policy-net sampling path.
- `modal run modal_serve.py::verify` exercises `get_orders` for every configured
  tier. Run it after deployment because the full check needs the Modal GPU image
  and model Volume.
