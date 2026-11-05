#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# Import conf first since it doesn't require torch
from .conf import (
    load_config,
    load_root_config,
    load_proto_message,
    flatten_cfg,
    save_config,
    CONF_ROOT,
    PROJ_ROOT,
    conf_to_dict,
    conf_is_set,
    conf_get,
    conf_set,
    conf_with_overrides,
)

# Try to import run-related functionality
try:
    from .run import parse_args_and_maybe_launch, maybe_launch, get_default_exp_dir
except ImportError as e:
    import sys
    if "torch" in str(e):
        if "torch" not in sys.modules:
            print("Warning: torch is required for the run module. Some functionality will be limited.")
    else:
        # Re-raise the exception if it's not related to torch
        raise

# Try to import util-related functionality
try:
    from .util import (
        MODES,
        get_job_env,
        get_slurm_job_id,
        get_slurm_master,
        is_adhoc,
        is_aws,
        is_devfair,
        is_master,
        is_on_slurm,
        log_git_status,
        maybe_init_requeue_handler,
        reset_slurm_cache,
        save_result_in_cwd,
        setup_logging,
    )
except ImportError as e:
    import sys
    if "torch" in str(e) or "submitit" in str(e):
        if "torch" not in sys.modules:
            print("Warning: torch and/or submitit are required for the util module. Some functionality will be limited.")
    else:
        # Re-raise the exception if it's not related to torch or submitit
        raise
