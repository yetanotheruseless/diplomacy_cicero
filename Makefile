POSTMAN_DIR=$(realpath thirdparty/github/fairinternal/postman/)

.PHONY: all compile compile_selfplay clean clean_protos dipcc protos selfplay check_deps protos_basic validate_protos test test_fast test_thread_pool test_selfplay

all: compile

# Check for required dependencies
check_deps:
	@echo "Checking for required dependencies..."
	@which cmake > /dev/null || (echo "Error: cmake not found. Run scripts/install_dependencies.sh to install" && exit 1)
	@which ninja > /dev/null || (echo "Error: ninja not found. Install ninja-build" && exit 1)
	@which protoc > /dev/null || (echo "Error: protoc not found. Run scripts/install_dependencies.sh to install" && exit 1)
	@which protoc-gen-mypy > /dev/null || (echo "Error: protoc-gen-mypy not found. Install the build extra" && exit 1)
	@echo "Dependencies OK"

# Build the supported inference and dialogue runtime.
compile: | check_deps protos dipcc

# Distributed self-play has additional native dependencies and is intentionally
# opt-in until that subsystem's modernization is complete.
compile_selfplay: | compile selfplay

dipcc:
	@echo "Building dipcc..."
	PYDIPCC_OUT_DIR=$(realpath ./fairdiplomacy) SKIP_TESTS=1 bash ./dipcc/compile.sh

dipcc_debug:
	MODE=Debug bash ./dipcc/compile.sh

selfplay:
	@echo "Building selfplay components..."
	mkdir -p build/selfplay
	cd build/selfplay \
		&& cmake ../../fairdiplomacy/selfplay/cc -DPOSTMAN_DIR=$(POSTMAN_DIR) -DCMAKE_LIBRARY_OUTPUT_DIRECTORY=../../fairdiplomacy/selfplay \
		&& make -j

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

test_selfplay: | compile_selfplay
	@echo "Running distributed self-play C++ tests"
	./build/selfplay/prioritized_replay_test
	python -m pytest \
		fairdiplomacy/selfplay/exploit_test.py \
		fairdiplomacy/selfplay/search/rollout_test.py

pyright:
	./bin/pyright_local.py

clean:
	-make -C dipcc/build clean
	rm -rf build

clean_protos:
	rm -f conf/*_pb2.py conf/*_pb2.pyi conf/*_cfgs.py conf/*_cfgs.pyi
