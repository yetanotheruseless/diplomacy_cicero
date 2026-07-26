#!/usr/bin/env python3
"""Fail-fast validation for the modern protobuf compiler and runtime."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
from typing import Sequence

EXPECTED_PROTOBUF_RUNTIME = "7.35.1"
EXPECTED_PROTOC = "35.1"
REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PROJECT_MODULES = (
    "conf.agents_pb2",
    "conf.common_pb2",
    "conf.conf_pb2",
    "conf.misc_pb2",
)


class ValidationError(RuntimeError):
    """Raised when the protobuf toolchain violates the project contract."""


def require(condition: bool, message: str) -> None:
    """Raise a descriptive validation error when a contract is not satisfied."""
    if not condition:
        raise ValidationError(message)


def check_runtime_version() -> None:
    """Require the single supported Python protobuf runtime."""
    import google.protobuf

    distribution_version = importlib.metadata.version("protobuf")
    module_version = google.protobuf.__version__
    require(
        distribution_version == EXPECTED_PROTOBUF_RUNTIME,
        f"Expected protobuf distribution {EXPECTED_PROTOBUF_RUNTIME}; found {distribution_version}",
    )
    require(
        module_version == EXPECTED_PROTOBUF_RUNTIME,
        f"Expected google.protobuf {EXPECTED_PROTOBUF_RUNTIME}; found {module_version}",
    )
    print(f"protobuf runtime: {module_version}")


def check_protoc_version() -> None:
    """Require the matching modern protoc release."""
    result = subprocess.run(
        ["protoc", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    installed = result.stdout.strip()
    expected = f"libprotoc {EXPECTED_PROTOC}"
    require(installed == expected, f"Expected {expected}; found {installed}")
    print(f"protobuf compiler: {installed}")


def validate_project_modules() -> None:
    """Import every generated project module and require the core module set."""
    generated_paths = sorted((REPO_ROOT / "conf").glob("*_pb2.py"))
    generated_modules = tuple(f"conf.{path.stem}" for path in generated_paths)
    missing = sorted(set(EXPECTED_PROJECT_MODULES) - set(generated_modules))
    require(bool(generated_modules), "No generated conf/*_pb2.py modules were found")
    require(not missing, f"Missing generated protobuf modules: {', '.join(missing)}")

    for module_name in generated_modules:
        importlib.import_module(module_name)
        print(f"imported: {module_name}")


def load_module(module_name: str, path: Path) -> ModuleType:
    """Load a generated module from an isolated temporary path."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    require(spec is not None and spec.loader is not None, f"Could not load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compiler_runtime_round_trip() -> None:
    """Compile a minimal schema in a temporary directory and round-trip a message."""
    with tempfile.TemporaryDirectory(prefix="cicero-protobuf-") as temp_dir:
        output_dir = Path(temp_dir)
        subprocess.run(
            [
                "protoc",
                f"--proto_path={REPO_ROOT}",
                f"--python_out={output_dir}",
                "minimal.proto",
            ],
            cwd=REPO_ROOT,
            check=True,
        )
        minimal_pb2 = load_module("_cicero_minimal_pb2", output_dir / "minimal_pb2.py")
        message = minimal_pb2.TestMessage(text="modern protobuf", number=35)
        restored = minimal_pb2.TestMessage.FromString(message.SerializeToString())
        require(
            restored == message, "Minimal protobuf serialization round-trip changed the message"
        )
    print("compiler/runtime round-trip: passed")


def test_project_message_round_trip() -> None:
    """Exercise a real project oneof and its serialization contract."""
    from conf import agents_pb2

    agent = agents_pb2.Agent()
    agent.random.SetInParent()
    restored = agents_pb2.Agent.FromString(agent.SerializeToString())
    require(
        restored.WhichOneof("agent") == "random", "Agent oneof round-trip lost the random variant"
    )
    print("project message round-trip: passed")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-only",
        action="store_true",
        help="Skip protoc checks for a stripped runtime image that contains generated modules only.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run validation in dependency order and stop at the first failure."""
    args = parse_args(argv)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    try:
        check_runtime_version()
        if not args.runtime_only:
            check_protoc_version()
            test_compiler_runtime_round_trip()
        validate_project_modules()
        test_project_message_round_trip()
    except ValidationError as error:
        print(f"protobuf validation failed: {error}", file=sys.stderr)
        return 1

    mode = "runtime" if args.runtime_only else "compiler and runtime"
    print(f"Modern protobuf {mode} validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
