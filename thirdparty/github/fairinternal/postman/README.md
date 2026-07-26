# Postman tensor RPC

Postman is Cicero's native tensor transport for distributed self-play. This
fork supports one runtime line:

- Python 3.12
- PyTorch 2.13.0 (CPU or CUDA 13)
- pybind11 3.0.4
- gRPC 1.83.0
- protobuf/protoc 35.1 with Python protobuf 7.35.1
- CMake 3.28+, Ninja, and C++20
- macOS 14+ on arm64, or Linux on x86-64

The old gRPC 1.20 and pybind11 gitlinks are gone. The canonical repository
helper fetches gRPC at its exact release commit, initializes its pinned
dependencies, verifies protobuf's exact source commit, builds a
platform-tagged wheel with scikit-build-core, installs that wheel, and runs the
native and Python RPC suites. macOS wheels pin and verify a 14.0 deployment
target instead of inheriting the build host's OS release:

```bash
./scripts/build_postman.sh
```

Run that command from the Cicero repository root after activating the
environment created by `scripts/modernize_setup.sh`. To select another prepared
canonical environment or out-of-tree cache:

```bash
CICERO_POSTMAN_PYTHON=/path/to/python3.12 \
CICERO_POSTMAN_BUILD_DIR=/tmp/cicero-postman-build \
CICERO_POSTMAN_DEPS_DIR=/tmp/cicero-postman-deps \
N_POSTMAN_JOBS=8 \
./scripts/build_postman.sh
```

`--build-only` produces and installs the native wheel. `--test-only` reuses that
build and runs the clean-wheel import, CTest, and pytest gates. The build
inspects the wheel artifact for a relative Torch RPATH and fails closed if the
dependency cache is dirty or does not match the pinned commits. Use this helper
for source builds: it verifies the active Torch flavor and intentionally builds
without an isolated environment that could resolve a different CPU/CUDA wheel.

The wire format carries nested tuples/lists, string-keyed maps, and CPU tensor
payloads. CUDA model servers receive CPU RPC inputs and explicitly transfer
them to their selected device; queue inputs that bypass the transport must also
be CPU tensors. Each message is capped at 512 MiB.

`ComputationQueue` retains at most 64 pending batches by default; pass
`max_pending_batches` to select another finite limit. `AsyncClient` also has
finite concurrent and outstanding-call limits. Closing either client rejects
new work, resolves queued work with an error, and cancels active RPC contexts.
When a server function waits for a full batch, configure
`max_concurrent_calls` to be at least that batch size.

The Python API remains the Cicero-facing interface:

```python
import postman
import torch

server = postman.Server("127.0.0.1:0")
server.bind("increment", lambda tensor: tensor + 1, batch_size=1)
server.run()

client = postman.Client(f"127.0.0.1:{server.port()}")
client.connect()
torch.testing.assert_close(client.increment(torch.tensor(2)), torch.tensor(3))

client.close()
server.stop()
server.wait()
```

RELA is Cicero's supported replay implementation. The unused Postman-local
replay buffer and its Python 3.7 build line were removed during modernization.
