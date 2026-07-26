
# Simple Postman example

Build Postman from the Cicero repository root, then run one server:

```bash
./scripts/build_postman.sh
python thirdparty/github/fairinternal/postman/example/server.py
```

In two other shells, start one client in each. The server intentionally batches
the two `batched_identity` calls together:

```bash
python thirdparty/github/fairinternal/postman/example/client.py
```

`server_queue.py` shows the lower-level `ComputationQueue` interface. The
native integration examples live in `postman/tests/cc/postman_test.cc`.
