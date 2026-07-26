.PHONY: all compile compile_selfplay clean clean_protos dipcc protos selfplay check_deps protos_basic validate_protos test test_fast test_thread_pool test_selfplay test_selfplay_rela

all: compile

# Check for required dependencies
check_deps:
	@echo "Checking for required dependencies..."
	@command -v cmake > /dev/null || (echo "Error: cmake 3.28+ is required; use the canonical Dockerfile or install it before scripts/modernize_setup.sh" && exit 1)
	@command -v ninja > /dev/null || (echo "Error: ninja is required; use the canonical Dockerfile or install ninja-build" && exit 1)
	@command -v protoc > /dev/null || (echo "Error: protoc 35.1 is required; run scripts/modernize_setup.sh or scripts/install_protoc.sh" && exit 1)
	@command -v protoc-gen-mypy > /dev/null || (echo "Error: protoc-gen-mypy is required; install the project build extra" && exit 1)
	@echo "Dependencies OK"

# Build the supported inference and dialogue runtime.
compile: | check_deps protos dipcc

# The optional RELA prioritized-replay extension is kept out of the inference
# build. Postman RPC remains a separate dependency; see docs/selfplay_runtime.md.
compile_selfplay: | compile selfplay

dipcc:
	@echo "Building dipcc..."
	PYDIPCC_OUT_DIR=$(realpath ./fairdiplomacy) SKIP_TESTS=1 bash ./dipcc/compile.sh

dipcc_debug:
	MODE=Debug bash ./dipcc/compile.sh

selfplay:
	@echo "Building the optional RELA prioritized-replay extension..."
	./scripts/build_selfplay.sh --build-only

# Compile modern protobuf modules, type stubs, and heyhi frozen-config wrappers.
protos:
	@echo "Compiling protocol buffers..."
	rm -f conf/*_pb2.py conf/*_pb2.pyi conf/*_cfgs.py conf/*_cfgs.pyi
	protoc --proto_path=. --python_out=. --mypy_out=. conf/*.proto
	python heyhi/bin/patch_protos.py conf/*_pb2.py

# Compatibility alias: callers still receive the complete modern generation.
protos_basic: protos

validate_protos: | protos
	@echo "Validating protocol buffer compilation..."
	python scripts/validate_protobuf.py

test: | test_fast test_thread_pool

test_fast: | compile
	@echo "Running runtime unit and integration tests"
	python -m pytest \
		--ignore=fairdiplomacy/selfplay/exploit_test.py \
		--ignore=fairdiplomacy/selfplay/search/rollout_test.py \
		heyhi/ fairdiplomacy/ parlai_diplomacy/ unit_tests/

test_thread_pool: | compile
	python -m pytest dipcc/python/test_thread_pool.py

test_selfplay_rela: | selfplay
	@echo "Running RELA prioritized-replay native and Python tests"
	./scripts/build_selfplay.sh --test-only

test_selfplay: | compile_selfplay
	@echo "Running RELA prioritized-replay native and Python tests"
	./scripts/build_selfplay.sh --test-only
	@echo "Running self-play integration tests (requires a separately installed Postman RPC extension)"
	@python -c "from postman import Client, ComputationQueue, Server" >/dev/null 2>&1 \
		|| (echo "Postman RPC is not installed; see docs/selfplay_runtime.md" >&2; exit 1)
	python -m pytest \
		fairdiplomacy/selfplay/exploit_test.py \
		fairdiplomacy/selfplay/search/rollout_test.py

pyright:
	./bin/pyright_local.py

clean:
	-make -C dipcc/build clean
	rm -rf build
	rm -f fairdiplomacy/selfplay/rela*.so fairdiplomacy/selfplay/rela*.dylib fairdiplomacy/selfplay/rela*.pyd

clean_protos:
	rm -f conf/*_pb2.py conf/*_pb2.pyi conf/*_cfgs.py conf/*_cfgs.pyi
