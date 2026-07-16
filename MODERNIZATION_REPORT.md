# Cicero Modernization Spike — Report

**Goal:** upgrade Meta/FAIR's **Cicero** Diplomacy AI from its pinned legacy stack
(Python 3.7–3.9, torch 1.10, protobuf **3.19.1 EXACT**, old C++ toolchain) to
**modern Python (3.11) + modern torch 2.x + modern protobuf**.

**Environment:** macOS 26.2, **arm64, no CUDA**. All work below is CPU/arm64.
Anything needing x86_64+CUDA is explicitly marked "needs container/Modal to validate".

**Branch:** `wip/modernize-python`. The uv-managed environment lives at
`.venv-modern` (Python 3.11.10).

---

## TL;DR verdict

**Partial modernization achieved, and it is substantially further than the
"blocked by C++/ProtoBuf/ParlAI wall" hypothesis predicted.** On a modern stack
(Python 3.11.10 / torch 2.12.1 / protobuf 7.35.1 / pybind11 3.0.4) I got, with
reproducible evidence, **all of**:

- protobuf regenerated with modern `protoc` and the heyhi frozen-config codegen
  rewritten for the new format — **35/37 config unit tests pass** (2 cosmetic);
- the **dipcc C++ engine (`pydipcc`) compiled and loaded on macOS/arm64** against
  torch 2.12 — full multi-turn adjudication is correct;
- the **no-press strategy model + agents import and run**;
- the **full Cicero full-press (dialogue) agent imports**, and ParlAI at its
  pinned commit installs + imports on Python 3.11;
- an **end-to-end `config → agent → live game → orders` pipeline** runs.

The three "famous walls" all turned out to be **surmountable**: protobuf 3.19.1
EXACT (broken — works on 7.x after a codegen rewrite), the dipcc C++ build (built
on arm64 after 4 small portability fixes), and ParlAI (installs + imports on
3.11).

> **UPDATE — Modal validation (see `MODAL_VALIDATION.md`).** The blockers below
> marked "needs the container/Modal env to validate" have since been **run on
> real Modal Linux x86_64 + CUDA (A10G)** and all PASS: **B5** (pydipcc Linux
> build + adjudication), **B1** (`torch.load(weights_only=False)` → 4/4 real
> checkpoints into the modern `BaseStrategyModelV2` `nn.Module`), **B2**
> (base_strategy_model fp16 GPU inference), **B3** (ParlAI/BART dialogue forward
> pass on CUDA). With `modal run` logs as evidence, full modernization is **not**
> blocked by a C++, protobuf, or ParlAI wall — see `modal_modern.py`.

---

## 1. Version inventory (what was pinned vs. what now works)

| Component | Legacy pin (`requirements.txt` / `pyproject.toml`) | Modern (validated in `.venv-modern`) |
|---|---|---|
| Python | 3.7–3.9 | **3.11.10** |
| torch | 1.10 (implicit) | **2.12.1** (CPU/arm64) |
| numpy | `>=1.20.3,<1.21` (for numba) | **2.2.6** |
| protobuf | **3.19.1 EXACT** | **7.35.1** (runtime), `protoc` **25.3** |
| pybind11 | `>=2.10` (vendored submodule, empty) | **3.0.4** (pip) |
| ParlAI | git pin `5214f42…` (ParlAI 1.5.1) | **same commit, installs + imports on 3.11** |
| glog | conda 0.4/0.5 | **0.7.1** (Homebrew) + `GLOG_USE_GLOG_EXPORT` |
| numba | `0.54.1` (forces numpy<1.21) | **not needed** — never imported by agent paths |
| pandas / transformers / fairseq | pinned old | **not needed** by the import paths exercised |
| nest | `facebookresearch/nest` C++ ext | **replaced by a pure-Python shim** |

Reproduce the whole thing: `scripts/modernize_setup.sh`.

---

## 2. What was changed, and what now works (with evidence)

### 2.1 ProtoBuf — the "3.19.1 EXACT" constraint is broken ✅

**Root cause of the pin.** Cicero's config system (`heyhi/conf.py`,
`MetaCfg`, `FrozenConf`) is built by `heyhi/bin/patch_protos.py`, which
**text-scrapes the generated `*_pb2.py`** for `# @@protoc_insertion_point(class_scope:…)`
markers and monkeypatches `_reflection.GeneratedProtocolMessageType`. Modern
protoc (≥3.20) emits a completely different format: one serialized
`FileDescriptorProto` built via `_builder.BuildTopDescriptorsAndMessages`, with
**zero `class_scope:` markers and zero `GeneratedProtocolMessageType` calls**.
Under modern protobuf the legacy patcher silently produced an **empty
`*_cfgs.py`**, so the entire frozen-config layer was dead.

**Fix** (`heyhi/bin/patch_protos.py`, commit `protobuf: modernize patch_protos.py…`):
rewrote message **discovery** (walk `DESCRIPTOR` recursively instead of scraping
text) and **injection** (patch the `to_frozen`/`to_dict`/… methods directly onto
each upb message class at import time; `MessageMeta` still allows `setattr`).
Kept the runtime machinery (`_FrozenConf`, `_extra_fields`, `FROZEN_SYM_BD`)
intact. Cross-version fixes inside the embedded helpers:
- `field.label == field.LABEL_REPEATED` → prefer `field.is_repeated` (the
  per-instance `label` attribute was removed in protobuf-5/upb);
- `_message.Message.__getattribute__(self, name)` → `getattr(self, name)` (upb
  messages don't route field access through `Message.__getattribute__`);
- inject `import google.protobuf.message as _message` into the generated block;
- register + module-bind `Frozen<Name>` classes (pickle support) and wire nested
  Frozen classes as attributes of their parent (`cfgs.TrainTask.TransformerDecoder`).

**Evidence:**
```
protoc conf/*.proto --python_out=./ --mypy_out=./
python heyhi/bin/patch_protos.py conf/*_pb2.py
python -m pytest heyhi/tests/test_conf.py     # -> 35 passed, 2 failed
```
The **2 failures are cosmetic**: `testToStrWithDefault` hardcodes the legacy
protobuf text-format for a whole-number float default (`scalar: -1.0`); modern
protobuf's `Message.__str__` renders it `scalar: -1` (the *value* is unchanged).
10 real `conf/**/*.prototxt` root configs load end-to-end via
`heyhi.conf.load_root_config` (includes + overrides + freeze).

### 2.2 dipcc C++ engine (`pydipcc`) — builds + runs on macOS/arm64 ✅

This was flagged as "likely the HARDEST … may not validate locally." It
**validated locally**. Four portability fixes (commit `dipcc: build pydipcc on
macOS/arm64…`), none of which the legacy conda/x86_64 path exercised:

1. **glog include path** (`CMakeLists.txt`): legacy build relied on
   `link_directories($CONDA_PREFIX/lib)` + conda glog headers on the default
   include path. Added portable `find_package` + Homebrew-prefix fallback for
   include/link dirs → `<glog/logging.h>` resolves.
2. **modern glog guard** (`CMakeLists.txt`): glog ≥0.6 `#error`s "was not
   included correctly" unless `GLOG_USE_GLOG_EXPORT` is defined (so it pulls in
   `glog/export.h`). Added `-DGLOG_USE_GLOG_EXPORT` (no-op on old glog).
3. **libtorch_python extension** (`CMakeLists.txt`): `.dylib` on macOS, not `.so`.
4. **`data_ptr<long>` / `accessor<long,3>`** (`thread_pool.cc`, `orders_encoder.cc`):
   the **key arm64/macOS bug**. libtorch only exports the `data_ptr<>`
   instantiation for `long long` (`int64_t`), **not `long`**. On Linux
   `long == int64_t` so it linked; on macOS/arm64 `long` is a *distinct* 64-bit
   type, so `dlopen` failed with
   `symbol not found: at::TensorBase::mutable_data_ptr<long>()`. Switched to
   `int64_t` (the `kLong` storage type) + `reinterpret_cast<long*>` to keep the
   encoder API unchanged.

**Evidence:**
```
cd dipcc/build && cmake -DCMAKE_BUILD_TYPE=Release .. && make pydipcc
  -> dipcc/python/pydipcc.cpython-311-darwin.so
# load + adjudicate:
import torch; load pydipcc.so; g = pydipcc.Game()
# S1901M -> F1901M -> W1901A -> S1902M: VIE-GAL/WAR-GAL bounce correct,
# SC capture counts correct (Germany 6, Austria 4), equal-strength support
# bounce correct, JSON round-trip OK.
```
(Note: the bundled `dipcc/python/datc/` is an **interactive annotation tool**,
not an auto-runnable regression; correctness was validated via multi-turn play.
The auto-runnable DATC suite lives in the separate `agentic-diplomacy` Rust engine.)

### 2.3 `nest` native extension — replaced with a pure-Python shim ✅

`nest` (`facebookresearch/nest`, a C++/pybind11 nested-structure library from the
unreleased `fairinternal/postman` tree) is imported by ~10 files including the
no-press wrapper. It is not pip-installable and would be a *second* native build.
Cicero uses only `flatten`, `map` (~23×), `map_many` (~4×) — pure tree
traversals. Reimplemented in `nest/__init__.py` with semantics matching the
upstream C++ library and its `nest_test.py` (sorted-key dict order; `map_many`
hands `f` a tuple of corresponding leaves). Validated against the upstream test
assertions.

### 2.4 Python-level torch/numpy fixes ✅

A survey of `fairdiplomacy/`, `heyhi/`, `parlai_diplomacy/` found a **small**
legacy-API surface (most code was already modern). Applied:
- numpy ≥1.24/2.0 removed aliases: `np.bool`→`bool` (`state_space.py`),
  `np.int`→`np.int64` (`press_br_agent.py`);
- torch 2.x AMP: `torch.cuda.amp.grad_scaler.GradScaler` /
  `…autocast_mode.autocast` → `torch.amp.GradScaler("cuda")` /
  `torch.amp.autocast("cuda")` (`train_sl.py`).

### 2.5 ParlAI — installs and imports on Python 3.11 ✅ (surprise result)

ParlAI was the prime suspect for a hard wall. At its **pinned commit** it:
- `uv pip install --no-deps git+…@5214f42…` → **installs** (ParlAI 1.5.1);
- `import parlai.utils.logging` → OK;
- `import parlai.core.opt / core.agents / core.torch_agent /
  core.torch_generator_agent` → OK;
- `from parlai.agents.bart.bart import BartAgent` → **OK** (the dialogue base).

The only cost was installing ordinary pip deps it expects (`iopath`, `requests`,
`scikit-learn`, `subword-nmt`, `setuptools<81`). No source patches were needed to
*import* ParlAI on 3.11.

### 2.6 End-to-end pipeline ✅

```
import fairdiplomacy.agents.parlai_full_press_agent  # full Cicero -> OK
agent = build_agent_from_cfg(ag.Agent(random=ag.RandomAgent()).to_frozen())
agent.get_orders(pydipcc.Game(), "FRANCE", agent.initialize_state("FRANCE"))
  -> ['A MAR - BUR', 'A PAR S A MUN - BUR', 'F BRE - MAO']   # valid orders
```
Config (frozen protobuf) → agent factory → live pydipcc game → valid orders, all
on the modern stack.

---

## 3. BLOCKERS (specific error + root cause + effort)

> B1, B2, B3, B5 below were "needs container/Modal" at arm64-time and have since
> been **CLEARED on Modal Linux x86_64 + CUDA** — see `MODAL_VALIDATION.md` /
> `modal_modern.py`. Only B4 (cosmetic) and the out-of-scope distributed C++
> remain.

### B1. Real model-weight loading — `torch.load` `weights_only` — ✅ CLEARED (Modal CPU)
- **Symptom:** in torch ≥2.6, `torch.load` defaults to `weights_only=True`;
  Cicero checkpoints are **full pickled objects** (they embed the `args`
  `TrainTask` config alongside the `model` weights), so this raised
  `UnpicklingError`.
- **Fix (applied):** `load_model.py:156` → `torch.load(..., weights_only=False)`
  (trusted local checkpoints). Other `torch.load` sites (`env.py`,
  `selfplay/ckpt_syncer.py`, `heyhi/run.py`) take the same one-line fix when
  exercised.
- **Validated:** `modal run modal_modern.py::load_weights` → **4/4 real
  checkpoints** (`no_press_human_imitation_policy`, `rl_search_orders`,
  `rl_value_function`, `diplodocus_high_rl_policy`) load into the modern
  `BaseStrategyModelV2` `nn.Module` (8.1M / 3.5M params) from the `cicero-models`
  Volume.

### B2. CUDA-only inference — ✅ CLEARED (Modal A10G)
- GPU `base_strategy_model` inference (incl. the **fp16** `half_precision=True`
  path that can't run on CPU) executes on the modern CUDA wheel.
- **Validated:** `modal run modal_modern.py::gpu_checks` →
  `torch 2.6.0+cu124 cuda 12.4 dev NVIDIA A10`; `forward_policy(...)` returns
  valid orders for all powers.
- **Still container-only (by nature):** AMP *training* and
  `torch.distributed.init_process_group("nccl", …)` (`train_sl.py:848`,
  `selfplay/exploit.py`) are multi-GPU training paths — not exercised (inference
  is the agent use case), but they import fine and the AMP API is already
  modernized (§2.4).

### B3. ParlAI *runtime* (dialogue forward pass) — ✅ CLEARED (Modal A10G)
- ParlAI 1.5.1 (pinned commit) loads a real Cicero dialogue checkpoint
  (`cicero_imitation_bilateral_orders_prefix`) on CUDA and runs `agent.act()`
  generation. Only ordinary pip deps were missing (`regex`, `sentencepiece`,
  `ftfy`, `emoji`) — **no source patches** to ParlAI.
- **Validated:** `modal run modal_modern.py::gpu_checks` → B3 PASS, generated
  output `A BEL  A MUN`.

### B4. Cosmetic test deltas (NOT a blocker)
- 2 `heyhi/tests/test_conf.py` failures from protobuf's `Message.__str__` float
  formatting (`-1` vs `-1.0`). Value semantics unchanged. Either update the
  expected strings or route `to_str_with_defaults` through
  `text_format.MessageToString` (which still emits `-1.0`).

### B5. dipcc on Linux/x86_64 — ✅ CLEARED (Modal CPU); `selfplay` C++ out of scope
- **Validated:** `modal run modal_modern.py::build_and_adjudicate` builds
  `pydipcc.cpython-311-x86_64-linux-gnu.so` against torch 2.6 and runs correct
  multi-turn adjudication. The `int64_t` change is a no-op on Linux
  (`long == int64_t`) and compiled clean — no Linux-specific regressions.
- **Out of scope:** the separate `fairdiplomacy/selfplay/cc` (postman/grpc) C++
  was not attempted — it needs the `fairinternal/postman` + grpc submodules
  (`.gitmodules` point at `grpc v1.20.x` and an empty `pybind11` submodule). It's
  a larger native build only needed for **distributed RL self-play**, not for
  agent play/inference.

---

## 4. Recommended path

1. **Adopt the modern protobuf + `patch_protos.py` rewrite as-is** — it's the
   highest-leverage win and fully validated (§2.1). Drop the `protobuf==3.19.1`
   pin entirely.
2. **Adopt the dipcc CMake/`int64_t` fixes** (§2.2). They're portable (guarded by
   `if(APPLE)` / no-op defines) and also harden the Linux build.
3. **Keep the pure-Python `nest` shim** (§2.3) — it removes a native dependency
   for the whole agent path; only the distributed self-play data loaders use the
   parts that touch it, and those still work via the shim.
4. **B1 done** — `weights_only=False` applied in `load_model.py`; 4/4 real
   checkpoints load into the modern `BaseStrategyModelV2` `nn.Module` on Modal.
5. **B2/B3/B5 done on Modal** — `modal_modern.py` builds the modern stack on
   Linux x86_64, and the GPU run validates base_strategy_model fp16 inference +
   a ParlAI/BART dialogue forward pass (see `MODAL_VALIDATION.md`).

**Honest verdict:** **Full modernization is feasible, not blocked by a C++,
protobuf, or ParlAI wall.** The Python/protobuf/C++ build layer is done and proven
on a modern stack on **both** macOS/arm64 (Python 3.11 + torch 2.12 + protobuf
7.35) **and** Modal Linux x86_64 + CUDA (Python 3.11 + torch 2.6 + protobuf 7.35).
Real production weights load into the modern model code, GPU inference runs, and
ParlAI generates dialogue. The only items not closed are **cosmetic** (B4: 2
float-formatting test strings) and **out of scope** (distributed RL self-play C++,
which needs the unreleased postman/grpc submodules and isn't part of agent
play/inference).

---

## 5. Commits on this branch

```
modal: validate modern stack on Linux x86_64 + CUDA; fix torch.load weights_only
nest: pure-Python drop-in for FAIR's nest pybind11 extension
py3/torch/numpy: nested frozen configs + modern numpy & AMP fixes
dipcc: build pydipcc on macOS/arm64 against modern torch + glog
protobuf: modernize patch_protos.py for protobuf >= 4 (upb codegen)
```
plus this report, `MODAL_VALIDATION.md`, `modal_modern.py` (Linux/CUDA harness),
and `scripts/modernize_setup.sh` (reproducible local setup/evidence).
