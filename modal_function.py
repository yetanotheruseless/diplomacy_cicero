"""Serve the Cicero tactics oracle as a Modal **Function** (scale-to-zero, stable URL).

This is the "Option B1" of ``TACTICS_SERVING_DESIGN.md`` and the successor to the
``modal_app.py::serve`` **Sandbox** entrypoint. The Sandbox approach exists *only*
because the Cicero image is **Python 3.9** (torch 1.10 + a C++ ``pydipcc`` compiled
against 3.9) and Modal **Functions require Python >= 3.10**. Functions, unlike
Sandboxes, scale to zero on their own (``scaledown_window``) and cold-start on the
next request behind a **stable** URL — exactly what we want for the oracle.

Architecture (dual-python in one container, one GPU):

  * The Python-3.9 Cicero stack is kept **as-is** (it is load-bearing: old C++
    libs, ``torch==1.10.0+cu113``, compiled ``pydipcc``). It still owns the CUDA
    context.
  * A **Python-3.11** standalone build is overlaid into its **own prefix**
    (``/opt/py311``) so it does NOT clobber the base image's ``python`` (3.9). 3.11
    is put **first on PATH** so Modal's *function runtime* uses it (Modal requires
    ``python`` on PATH to be >= 3.10), while the 3.9 interpreter is invoked by
    **absolute path** for the oracle subprocess.
  * ``@app.cls`` + ``@modal.web_server(port)``: in ``@modal.enter`` we
    ``subprocess.Popen`` the **existing** oracle HTTP server
    (``oracle/server/oracle_server.py --transport http``) using the **3.9**
    interpreter, bound to ``localhost:<port>``. Modal proxies inbound HTTP straight
    to that port — so ``oracle/transport.py``'s ``HttpTransport`` talks to it with
    byte-identical wire behaviour to the Sandbox tunnel.

See ``DUAL_PYTHON_SERVING.md`` for deploy + smoke commands, the runner wiring, and
the (clearly-marked) blockers that must be verified on a real Modal account/GPU.

NOTE: This module was authored without a Modal account or GPU. It is
``py_compile``-clean and the cross-interpreter subprocess+proxy pattern was proven
locally with two different interpreters, but the *image build* and *GPU serve* are
UNVERIFIED. Every uncertainty is annotated here and in ``DUAL_PYTHON_SERVING.md``.
"""
import os
import pathlib
import secrets
import subprocess

import modal

# Reuse the proven Python-3.9 Cicero image, the models Volume, oracle staging, the
# per-tier presets, and the oracle argv builder from the existing Sandbox module so
# there is a single source of truth for the heavy build.
from modal_app import (  # noqa: E402
    ORACLE_FILES,
    ORACLE_SRC,
    TIER_PRESETS,
    TORCH_LIB,
    VOL,
    _oracle_cmd,
    _rollout_key,
    image as cicero_py39_image,
    models_volume,
)

REPO = pathlib.Path(__file__).parent

# --- 3.11 overlay -----------------------------------------------------------
#
# We do NOT use ``Image.from_registry(..., add_python="3.11")``: that does
# ``COPY /python/. /usr/local`` and ``ln -s /usr/local/bin/python3
# /usr/local/bin/python`` (see modal-client ``image.py::_registry_setup_commands``),
# i.e. it OVERWRITES the base ``python``/``python3`` in ``/usr/local`` — which on
# ``python:3.9-slim`` is the 3.9 we must preserve. So we install 3.11 into a
# SEPARATE prefix and prepend it to PATH, leaving 3.9 untouched at its own paths.
#
# We pull the SAME python-build-standalone glibc build Modal itself uses for
# ``add_python="3.11"`` (release 20230826, 3.11.5, gnu libc — from
# modal/mount.py::PYTHON_STANDALONE_VERSIONS), so it's a known-good x86_64 dist.
PY311_PREFIX = "/opt/py311"
PY311 = f"{PY311_PREFIX}/bin/python3.11"
PY311_VENV = "/opt/py311-venv"
PY311_VENV_PY = f"{PY311_VENV}/bin/python"

# python-build-standalone, the exact release Modal's add_python pins for 3.11.
_PBS_RELEASE = "20230826"
_PBS_VERSION = "3.11.5"
_PBS_URL = (
    "https://github.com/indygreg/python-build-standalone/releases/download/"
    f"{_PBS_RELEASE}/cpython-{_PBS_VERSION}+{_PBS_RELEASE}-x86_64-unknown-linux-gnu-install_only.tar.gz"
)

# Absolute path to the 3.9 interpreter in the base image. ``python:3.9-slim`` ships
# it at /usr/local/bin/python3.9 (and /usr/local/bin/python -> it). We call this by
# absolute path so the PATH reorder (3.11 first) can't shadow it for the subprocess.
PY39 = "/usr/local/bin/python3.9"

# Minimal deps the 3.11 overlay needs: just the modal client (its container agent +
# web_server runtime). stdlib http is all the proxy needs; the heavy web stack lives
# in the 3.9 oracle process, not here.
PY311_PIP = ["modal"]


def _dual_python_image() -> modal.Image:
    """The 3.9 Cicero image + a 3.11 standalone overlay (3.11 first on PATH).

    Built on top of the *fully-built* py3.9 ``image`` from ``modal_app`` (torch,
    pydipcc, ParlAI, all baked), so we add only the 3.11 layer + the oracle sidecar
    files — the slow nest/dipcc/torch layers are reused from cache unchanged.
    """
    img = cicero_py39_image

    # Stage the oracle sidecar files FLAT at /opt/oracle (same as _serving_image()).
    for src_rel, dst_name in ORACLE_FILES:
        src = ORACLE_SRC / src_rel
        if not src.exists():
            raise FileNotFoundError(
                f"oracle source {src} not found; set AGENTIC_ORACLE_DIR to the "
                "agentic-diplomacy/oracle directory"
            )
        img = img.add_local_file(str(src), f"/opt/oracle/{dst_name}", copy=True)

    img = (
        img
        # 1) Install the 3.11 standalone build into its OWN prefix. This does NOT
        #    touch /usr/local/bin/python* (the 3.9 the image was built against).
        .run_commands(
            f"mkdir -p {PY311_PREFIX} && "
            f"wget -q '{_PBS_URL}' -O /tmp/py311.tgz && "
            # the tarball unpacks a top-level `python/` dir; strip it into PY311_PREFIX.
            f"tar -xzf /tmp/py311.tgz -C {PY311_PREFIX} --strip-components=1 && "
            f"rm /tmp/py311.tgz && "
            f"{PY311} --version"
        )
        # 2) A venv on top of 3.11 for the overlay's own deps (modal). Keeping it in
        #    a venv means `pip install` here can never reach the 3.9 site-packages.
        .run_commands(
            f"{PY311} -m venv {PY311_VENV} && "
            f"{PY311_VENV_PY} -m pip install --upgrade pip && "
            f"{PY311_VENV_PY} -m pip install " + " ".join(PY311_PIP) + " && "
            f"{PY311_VENV_PY} -c 'import modal, sys; print(\"overlay py\", sys.version.split()[0])'"
        )
        # 3) Put the 3.11 venv FIRST on PATH so Modal's function runtime (which
        #    resolves `python` on PATH) uses 3.11. The 3.9 interpreter is still
        #    reachable at its absolute path (PY39) for the subprocess. We also assert
        #    `python` now resolves to 3.11 and PY39 still resolves to 3.9.
        .env({"PATH": f"{PY311_VENV}/bin:{PY311_PREFIX}/bin:/usr/local/bin:/usr/bin:/bin"})
        .run_commands(
            "python --version && "  # should be 3.11 (overlay)
            f"{PY39} --version && "  # should be 3.9 (legacy, still intact)
            # hard-fail the build if either assumption broke.
            'python -c "import sys; assert sys.version_info[:2]==(3,11), sys.version"',
            f'{PY39} -c "import sys; assert sys.version_info[:2]==(3,9), sys.version"',
        )
    )
    return img


# Build lazily: importing this module on a machine without the oracle checkout (or
# just to run ``--help``) shouldn't trigger the FileNotFoundError / image graph.
_image_cache: dict[str, modal.Image] = {}


def _serving_image() -> modal.Image:
    if "img" not in _image_cache:
        _image_cache["img"] = _dual_python_image()
    return _image_cache["img"]


app = modal.App("cicero-oracle-fn")

# Which tiers a deployed Function serves, and its search budget. These are
# deploy-time (env) config because a ``@modal.web_server`` Function can't take
# per-deploy CLI args the way the Sandbox ``serve`` entrypoint did. Override at
# ``modal deploy`` time via ``--env``-style ``modal.Secret``/env, or edit here.
DEFAULT_TIERS = os.environ.get("ORACLE_TIERS", "searchbot")
DEFAULT_GPU = os.environ.get("ORACLE_GPU", "A10G")
DEFAULT_PORT = int(os.environ.get("ORACLE_PORT", "8000"))
# scaledown_window: idle seconds before the container is torn down (=> $0 GPU).
# NOTE: Modal's docs (guide/cold-start) state a 2..1200s range in places; the owner
# wanted 1800. Set 1800 here but VERIFY it isn't clamped/rejected (see
# DUAL_PYTHON_SERVING.md "Blockers"). Lower to <=1200 if Modal complains.
SCALEDOWN_WINDOW = int(os.environ.get("ORACLE_SCALEDOWN_WINDOW", "1800"))
# Model load is minutes; web_server.startup_timeout defaults to 5s (way too short).
WEB_STARTUP_TIMEOUT = int(os.environ.get("ORACLE_STARTUP_TIMEOUT", "1800"))
# Keep N containers always-warm (no cold start) at the cost of idle GPU. 0 = pure
# scale-to-zero (cold first request after idle).
MIN_CONTAINERS = int(os.environ.get("ORACLE_MIN_CONTAINERS", "0"))


def _tier_list() -> list[str]:
    tiers = [t.strip() for t in DEFAULT_TIERS.split(",") if t.strip()]
    unknown = [t for t in tiers if t not in TIER_PRESETS]
    if unknown:
        raise ValueError(f"unknown tiers {unknown}; choose from {sorted(TIER_PRESETS)}")
    return tiers


@app.cls(
    image=_serving_image(),
    gpu=DEFAULT_GPU,
    volumes=VOL,
    scaledown_window=SCALEDOWN_WINDOW,
    min_containers=MIN_CONTAINERS,
    # Container-startup budget (the @app.cls-level startup_timeout, distinct from
    # web_server's): governs how long Modal allows boot + @modal.enter. Model load
    # is minutes, so make it generous. (modal >= 1.1.4.)
    startup_timeout=WEB_STARTUP_TIMEOUT,
    # One GPU = one in-flight search at a time; the oracle's own gpu_lock also
    # serialises, but we set concurrency so Modal scales OUT (more containers) under
    # load rather than piling requests onto one GPU.
    timeout=24 * 3600,
)
@modal.concurrent(max_inputs=1)
class CiceroOracle:
    """A scale-to-zero Cicero oracle Function fronting the py3.9 HTTP server."""

    @modal.enter()
    def _start_backend(self) -> None:
        """Launch the py3.9 oracle HTTP server on localhost:<port> (warm the GPU).

        Runs under the 3.11 runtime; the subprocess is the 3.9 interpreter by
        absolute path. We do NOT block here for readiness — Modal's readiness check
        is a TCP connect to the port, governed by ``@modal.web_server``'s
        ``startup_timeout``. IMPORTANT: ``oracle_server.py`` binds its socket only
        AFTER building the backend and eager-loading value nets (it calls
        ``serve_http`` last), so the port does not open until model loading is well
        underway — ``startup_timeout`` must therefore cover the full model-load time
        (minutes), which is why it defaults to 1800s here, not the web_server 5s
        default. See DUAL_PYTHON_SERVING.md §5.
        """
        tiers = _tier_list()
        # A bearer token so the public URL isn't open. Read by clients from
        # ORACLE_TOKEN (the runner/registry already use token_env="ORACLE_TOKEN").
        # Provide it as a Modal Secret named "cicero-oracle-token" for a STABLE
        # token across cold starts; otherwise we mint an ephemeral one (logged).
        token = os.environ.get("ORACLE_TOKEN") or secrets.token_urlsafe(24)
        if not os.environ.get("ORACLE_TOKEN"):
            print(f"[enter] no ORACLE_TOKEN secret set; minted ephemeral token: {token}", flush=True)

        # ``_oracle_cmd`` returns a bash one-liner that `cd /app`, pip-installs the
        # ParlAI runtime closure, and execs oracle_server.py. Its bare ``python``/
        # ``pip`` tokens MUST resolve to the 3.9 interpreter, NOT the 3.11 runtime.
        # We force that below by prepending the legacy python's bin dir to the
        # subprocess PATH (overriding the 3.11-first PATH Modal's runtime uses).
        cmd = _oracle_cmd(tiers, DEFAULT_PORT, token, rollouts=int(os.environ.get("ORACLE_ROLLOUTS", "0")))

        # Run the whole thing under the 3.9 interpreter. The simplest robust way:
        # invoke bash with the legacy python's dir FIRST on PATH so the bare
        # ``python``/``pip`` tokens inside ``cmd`` resolve to 3.9 — overriding the
        # 3.11-first PATH we set for Modal's runtime.
        legacy_bin = os.path.dirname(PY39)  # /usr/local/bin
        env = dict(os.environ)
        env["PATH"] = legacy_bin + ":" + env.get("PATH", "")
        env.setdefault("PYTHONPATH", "/app")
        env.setdefault("LD_LIBRARY_PATH", TORCH_LIB)
        env.setdefault("OMP_NUM_THREADS", "8")

        print(f"[enter] launching py3.9 oracle: tiers={tiers} port={DEFAULT_PORT} "
              f"(python={PY39})", flush=True)
        # NOTE: not captured — let the oracle's stdout/stderr stream into the Modal
        # container logs so a crash traceback is visible. Popen is non-blocking;
        # Modal then proxies HTTP to DEFAULT_PORT once the socket is up.
        self._proc = subprocess.Popen(["bash", "-lc", cmd], env=env)
        self._token = token

    @modal.web_server(DEFAULT_PORT, startup_timeout=WEB_STARTUP_TIMEOUT, label="cicero-oracle")
    def web(self) -> None:
        """Expose the py3.9 oracle's port. The subprocess (started in
        ``@modal.enter``) is already listening; Modal proxies to it. No body needed
        — ``@modal.web_server`` only requires the port be open by ``startup_timeout``.
        """
        # Intentionally empty: the server is the subprocess from _start_backend.
        # (Modal calls this once per container to learn the function exists; the
        # actual liveness check is the TCP connect to DEFAULT_PORT.)
        return None

    @modal.exit()
    def _stop_backend(self) -> None:
        proc = getattr(self, "_proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


# --- local entrypoint: print the deployed URL + a copy-paste smoke ----------


@app.local_entrypoint()
def info() -> None:
    """Print how to reach the deployed Function (no GPU spent).

    After ``modal deploy modal_function.py`` the web endpoint has a STABLE URL of
    the form ``https://<workspace>--cicero-oracle-fn-cicerooracle-web.modal.run``.
    The exact URL is printed by ``modal deploy`` and visible in the dashboard; this
    just echoes the tier/knob config so the owner can wire the runner.
    """
    tiers = _tier_list()
    print("Cicero oracle Function config:")
    print(f"  tiers            = {tiers}")
    print(f"  gpu              = {DEFAULT_GPU}")
    print(f"  port             = {DEFAULT_PORT}")
    print(f"  scaledown_window = {SCALEDOWN_WINDOW}s")
    print(f"  min_containers   = {MIN_CONTAINERS}")
    print(f"  web startup_to   = {WEB_STARTUP_TIMEOUT}s")
    print()
    print("Deploy:   modal deploy modal_function.py")
    print("URL:      printed by `modal deploy` (stable). Wire it into the runner as")
    print("          --modal-url <URL>  (token via ORACLE_TOKEN secret/env).")


# Sanity guard so a stray reference to the unused import doesn't trip linters and so
# the symbol is reachable for documentation/tests of the budget mapping.
_ = _rollout_key
