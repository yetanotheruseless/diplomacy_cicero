import importlib
import sys


def test_run_import_does_not_load_optional_training_stack() -> None:
    sys.modules.pop("run", None)
    sys.modules.pop("fairdiplomacy.models.base_strategy_model.train_sl", None)

    module = importlib.import_module("run")

    assert "train" in module.TASKS
    assert "fairdiplomacy.models.base_strategy_model.train_sl" not in sys.modules
