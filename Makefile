POSTMAN_DIR=$(realpath thirdparty/github/fairinternal/postman/)

.PHONY: all compile clean dipcc protos selfplay check_deps protos_basic validate_protos

all: compile

# Check for required dependencies
check_deps:
	@echo "Checking for required dependencies..."
	@which cmake > /dev/null || (echo "Error: cmake not found. Run scripts/install_dependencies.sh to install" && exit 1)
	@which protoc > /dev/null || (echo "Error: protoc not found. Run scripts/install_dependencies.sh to install" && exit 1)
	@echo "Dependencies OK"

# Target to build all internal code and resources.
compile: | check_deps dipcc protos selfplay

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

# Compiles protos and sets up pyi files for pyright to be happy.
protos:
	@echo "Compiling protocol buffers with mypy support..."
	@if command -v protoc-gen-mypy > /dev/null; then \
		protoc conf/*.proto --python_out ./ --mypy_out ./; \
	else \
		echo "Warning: protoc-gen-mypy not found, falling back to basic protoc"; \
		$(MAKE) protos_basic; \
	fi
	python heyhi/bin/patch_protos.py conf/*pb2.py

# Fallback target for protos without mypy support
protos_basic:
	@echo "Compiling protocol buffers without mypy support..."
	protoc conf/*.proto --python_out ./
	@echo "To validate protobuf compilation, run: python scripts/validate_protobuf.py"

validate_protos: | protos_basic
	@echo "Validating protocol buffer compilation..."
	python scripts/validate_protobuf.py

test: | test_fast test_cc

test_fast: | compile
	@echo "Running fast (unit) tests"
	python -m pytest heyhi/ fairdiplomacy/ parlai_diplomacy/ unit_tests/

test_cc: | compile
	@echo "Running c++ tests"
	./build/selfplay/prioritized_replay_test

pyright:
	./bin/pyright_local.py

clean:
	-make -C dipcc/build clean
	rm -rf build