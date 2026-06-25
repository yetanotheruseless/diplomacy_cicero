# Modern Cicero Oracle — scale-to-zero Modal serving

Capstone of the modernization spike: the modernized Cicero (Python 3.11 / torch
2.6 cu124 / modern protobuf / pydipcc / pure-Python `nest` shim) served as the
live **`imitation`** tier oracle that `agentic-diplomacy`'s runner consumes over
HTTP. Harness: **`modal_serve.py`**.

## Deployed endpoint

| | |
|---|---|
| **URL** | `https://jakemannix--cicero-modern-oracle.modal.run` |
| **Token** | bearer token in the `cicero-oracle-token` Modal Secret (`ORACLE_TOKEN`); current value `<ORACLE_TOKEN>` |
| **Tier** | `imitation` — no-press `base_strategy_model` agent + `no_press_human_imitation_policy.ckpt` |
| **GPU** | A10G, `scaledown_window=120s` (raise for production), `min_containers=0` |
| **App** | `cicero-modern-oracle` (Modal app id `ap-Rtxiv2zpjjjz2lWlke40hw`) |

## Wire contract (matches `agentic-diplomacy/oracle/transport.py::HttpTransport`)

```
GET  /health  -> 200 {"status":"ok","ready":true}
POST /rpc     -> {"id","method","params"}  (+ Authorization: Bearer <ORACLE_TOKEN>)
              -> {"id","ok":true,"result":{...}}   |   {"id","ok":false,"error":...}
```
`get_orders` params: `{game_json, power, tier:"imitation", seed?}` -> `{orders:[str]}`.

## Verification evidence (real requests against the deployed URL)

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
- token via `ORACLE_TOKEN=<ORACLE_TOKEN>` (from the
  `cicero-oracle-token` Secret).

Redeploy with a longer `scaledown_window` for an extended game:
`ORACLE_SCALEDOWN_WINDOW=600 modal deploy modal_serve.py`.

## Known caveats / honesty

- `info` reports `full_press: true` for the `imitation` tier because the oracle's
  `schema.FULL_PRESS_TIERS` (in agentic-diplomacy, read-only here) lists
  `imitation`. This is cosmetic for `get_orders` (no-press) — the agent is the
  no-press `base_strategy_model`. `generate_message`/press-aware `value` are not
  served by this tier as configured (no dialogue model / value net wired).
- `input_version: null` in `info` because no value-model is configured (the
  imitation tier doesn't need one for `get_orders`); the version is sniffed from a
  value wrapper, which isn't built here.
- Only `get_orders` was integration-tested. `policy` needs a search agent (not
  this tier); `value`/`generate_message` need a value-net / dialogue model wired.
