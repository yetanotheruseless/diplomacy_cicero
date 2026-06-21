# Running Cicero on macOS (Apple Silicon) with Docker

This guide gets FAIR/Meta's **Cicero** Diplomacy AI building and running on an
Apple-Silicon Mac. The project targets a 2021-era Linux stack (Python 3.8,
PyTorch 1.10, protobuf 3.19.1, gcc-9), so everything runs inside a Linux
`aarch64` Docker container. It has been verified end-to-end on an M-series Mac
(128 GB RAM, Docker Desktop): the neural policy agent, the search agent, and the
**full Cicero dialogue agent** all run and produce real orders + negotiation
messages from the real model weights.

> **GPU note:** this runs on **CPU only**. Docker Desktop on macOS runs a Linux
> VM with no GPU passthrough (no Metal, no CUDA), and the code is CUDA-only
> (torch 1.10 predates Apple MPS). The full dialogue agent is therefore slow —
> minutes per power. For speed, run the same container on a CUDA GPU (cloud).
> See "Performance & GPUs" below.

---

## TL;DR

```bash
# 0. Start Docker Desktop. Give it plenty of RAM (Settings > Resources):
#    >= 48 GB for the full Cicero dialogue agent (it uses ~50 GB on CPU).

# 1. Make sure model weights are decrypted into ./models/ (see "Model weights").

# 2. Build the runnable image (one-time; reuses the legacy base if present).
./scripts/setup_cicero_macos.sh

# 3. Run an agent. Three modes, increasing in cost:
./scripts/run_cicero_macos.sh policy   AUSTRIA 1   # fast: pure neural policy
./scripts/run_cicero_macos.sh search   AUSTRIA 1   # medium: CFR/rollout search
./scripts/run_cicero_macos.sh cicero   TURKEY  1   # full: search + dialogue (slow)
```

Output games are written to
`./diplomacy_experiments/adhoc/<timestamp>/.../output.json`.

---

## Requirements

- **Docker Desktop** for Mac (Apple Silicon).
  - Increase memory: Docker Desktop → Settings → Resources → Memory.
    - `policy` / `search` modes: 8–16 GB is fine.
    - `cicero` (full dialogue): **≥ 48 GB** (the dialogue model alone is ~11 GB
      and the full agent peaks around 50 GB RSS on CPU).
- **~210 GB free disk** if you keep both `models/` (decrypted, ~99 GB) and
  `models_encrypted/` (~99 GB). The decrypted `models/` is what's used at
  runtime; you can delete `models_encrypted/` once decrypted.
- `gpg` on the host (for decrypting weights): `brew install gnupg`.

## Model weights

The neural weights are GPG-encrypted and downloaded separately. Three cases:

1. **You already have decrypted `models/`** (e.g. `models/blueprint.pt`,
   `models/dialogue`, …): you're done — skip to "Build".
2. **You have `models_encrypted/` but not `models/`:** decrypt in place:
   ```bash
   # PASSWORD is the 30-char Cicero model passphrase.
   cd models_encrypted
   mkdir -p ../models/nonsense_ensemble
   for f in *.gpg; do
     gpg --batch --yes --passphrase "$PASSWORD" --output "../models/${f%.gpg}" -d "$f"
   done
   for f in nonsense_ensemble/*.gpg; do
     gpg --batch --yes --passphrase "$PASSWORD" --output "../models/${f%.gpg}" -d "$f"
   done
   ```
3. **You have neither:** download + decrypt in one shot (needs ~200 GB and the
   passphrase):
   ```bash
   bash bin/download_model_files.sh <PASSWORD>
   ```

The passphrase is the Cicero model-weights password published by Meta (it is a
30-character string; it also appears in `CICERO_TURKEY_README.md` in this repo).

## Build

```bash
./scripts/setup_cicero_macos.sh
```

This produces the image **`diplomacy-cicero:working`**. It:

1. Ensures a legacy **base image** exists with the slow, correct pieces already
   built — Python 3.8.10, **torch 1.10.0**, numpy 1.20.3, **protoc 3.19.1**,
   gcc-9, pybind11. By default it reuses the compose-built
   `diplomacy_cicero-diplomacy:latest`; if that's missing it builds it from
   `Dockerfile.unified` via `docker compose build diplomacy` (this compiles
   protobuf from source and is the slow, one-time cost).
2. Makes the prebuilt Linux-`aarch64` `pydipcc.so` (the C++ game engine binding)
   visible to `fairdiplomacy`.
3. Layers in the remaining Python deps with the exact pins that work on
   `arm64` + numpy 1.20 + torch 1.10, and commits the result.

> Why layer instead of a clean `pip install -r requirements.txt`? Several pins
> in `requirements.txt` don't have arm64 wheels (notably `tokenizers==0.10.3`,
> which needs a Rust toolchain). The layered set avoids them — see
> "How it works" — and is the path that's actually verified to run.

## Run

```bash
./scripts/run_cicero_macos.sh <mode> [power] [max_turns]
```

| mode     | agents                                                | speed (CPU)      |
|----------|-------------------------------------------------------|------------------|
| `policy` | `base_strategy_model` vs `base_strategy_model`        | ~seconds/turn    |
| `search` | `searchbot` (no-press CFR) vs `base_strategy_model`   | ~1 min/turn      |
| `cicero` | **full Cicero** (search + pseudo-orders + dialogue) vs 6 imitation agents | minutes/power |

`max_turns` caps how many movement phases to play (default `1`). Use `1` for a
quick smoke test; omit/raise it to play out more of a game.

Examples:

```bash
./scripts/run_cicero_macos.sh policy AUSTRIA 1
./scripts/run_cicero_macos.sh cicero TURKEY  1   # the headline Cicero demo
```

The full `cicero` run loads the entire model stack (RL search + value models,
the order model, the 11 GB dialogue model, sleep/draw/nonsense classifiers),
then plays one phase: each power's outgoing negotiation **messages are generated
by the dialogue model**, e.g.:

```
ITALY -> AUSTRIA: Hey Austria! I really like the IA, because if we can get it
off the ground, it's very powerful against the corner powers...
```

before search produces the final orders.

## Performance & GPUs

CPU-only here, for two reasons: (1) Docker on macOS can't pass the Apple GPU
into the Linux VM at all; (2) the code is written for CUDA and pinned to torch
1.10, which predates Apple's MPS backend. To get real speed, run the **same
image on an NVIDIA GPU** (e.g. a cloud box) with `--gpus all`; the code's
`torch.cuda.is_available()` path then activates automatically and you can drop
the `half_precision=false` override. (Modal/Colab GPU recipes: TODO.)

## Troubleshooting / the fixes that matter

- **`module 'distutils' has no attribute 'version'`** when importing
  tensorboard — caused by setuptools ≥ 60 vs torch 1.10. Fixed by pinning
  `setuptools==59.5.0` (the setup script does this).
- **`"softmax_lastdim_kernel_impl" not implemented for 'Half'`** during the
  Cicero turn — `half_precision: true` is GPU-only. The `cicero` run mode passes
  `agent_one.bqre1p.base_searchbot_cfg.half_precision=false` to force fp32 on
  CPU.
- **`No module named 'fairscale'`** while loading the dialogue model — install
  `fairscale==0.4.6` (in the setup script).
- **`tokenizers` / Rust build errors** — don't install `transformers`/
  `tokenizers`. ParlAI uses its own fairseq GPT-2 BPE (it downloads
  `vocab.bpe`/`encoder.json` at first run), so they aren't needed.
- **`Loading ... models/...` fails / file not found** — heyhi `chdir`s into a
  fresh experiment dir but symlinks `./models` there (see `heyhi/util.py`), so
  always launch with the repo mounted at `/app` and `cwd=/app` (the run script
  does this).
- **Container killed / OOM during `cicero`** — raise Docker Desktop's memory to
  ≥ 48 GB.

## How it works (under the hood)

The runnable environment is the legacy base image plus this dependency layer
(installed by `scripts/setup_cicero_macos.sh`):

- pure-python: `tabulate termcolor joblib pygtrie typer tqdm psutil
  ephemeral-port-reserve dacite attrs colored requests tensorboard pyyaml scipy
  sentencepiece ftfy emoji tornado wandb iopath subword-nmt scikit-learn`
- `fairscale==0.4.6`
- the vendored **`nest`** pybind11 extension
  (`thirdparty/github/fairinternal/postman/nest/`, compiled with gcc-9)
- **ParlAI** at pinned commit `5214f42a…`, installed `--no-deps` so it can't
  upgrade torch off 1.10
- compatibility pins: `Pillow==9.5.0 importlib-metadata==4.2.0 markdown==3.3.2
  urllib3==1.26.18`
- the critical `setuptools==59.5.0`

The C++ engine (`dipcc` → `fairdiplomacy.pydipcc`) is the prebuilt
Linux-`aarch64` `pydipcc.so` shipped in the repo; `fairdiplomacy/__init__.py`
loads it by globbing `fairdiplomacy/pydipcc*.so`.

Related files: `scripts/setup_cicero_macos.sh`, `scripts/run_cicero_macos.sh`,
`Dockerfile.unified`, `docker-compose.yml`.
