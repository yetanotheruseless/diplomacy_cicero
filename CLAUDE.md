# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Environment
- **Recommended setup**: Use Docker (works on all platforms)
  - Build image: `./scripts/docker_build.sh`
  - Run container: `./scripts/docker_run.sh`
- Alternative conda setup: `./scripts/setup_conda_env.sh` (not recommended on macOS)
- Alternative venv setup: `./scripts/setup_env.sh` (uses uv) or `./scripts/setup_env_pip.sh` (uses pip)
- **Note**: This project was primarily developed for Linux/Ubuntu. Docker provides the most reliable environment.

## System Requirements
- Docker (recommended)
- Alternatively:
  - Protocol Buffer Compiler (protoc): `brew install protobuf` (macOS) or `apt-get install protobuf-compiler` (Ubuntu)
  - CMake: `brew install cmake` (macOS) or `apt-get install cmake` (Ubuntu)
  - C++ compiler with C++11 support

## Build & Testing Commands
- Compile and build: `make compile`
- Compile protobuf only: `make protos_basic`
- Run all tests: `make test`
- Run fast tests: `make test_fast`
- Run single test: `python -m pytest path/to/test.py::test_function -v`
- Run tests with filter: `pytest -k pattern`
- Run tests with output: `pytest -s`
- Show test durations: `pytest --durations=0`
- Check types: `./bin/pyright_local.py`

## Code Style Guidelines
- **Python**: 3.7+ with static typing
- **Formatting**: Use black with line length of 99 (`black . --line-length=99`)
- **Imports**: Standard first, third-party next, project imports last, separated by blank lines
- **Naming**: snake_case for variables/functions, PascalCase for classes
- **Error handling**: Use explicit exception handling with descriptive messages
- **Pre-commit**: Run `pre-commit install` to auto-format code before commits
- **Protobuf**: Format with `clang-format-8 conf/*.proto -i`
- **Documentation**: Use docstrings for functions and methods, especially for public APIs
- **Testing**: Write pytest tests with descriptive names in unit_tests/ directory