#!/usr/bin/env python3
"""
Script to fix submitit references in heyhi/util.py.
This makes submitit truly optional by patching return types and type annotations.
"""
import os
import re
import typing

def patch_heyhi_util():
    """Patch heyhi/util.py to make submitit truly optional."""
    util_path = "heyhi/util.py"
    
    if not os.path.exists(util_path):
        print(f"Error: {util_path} not found")
        return False
    
    with open(util_path, "r") as f:
        content = f.read()
    
    # Create a better patch for submitit import
    patched_content = re.sub(
        r"import submitit",
        """try:
    import submitit
except ImportError:
    submitit = None
    print('Warning: submitit not available, some functionality will be limited')

# Create dummy classes if submitit is not available
if submitit is None:
    class DummyJobEnvironment:
        def __init__(self):
            self.job_id = "dummy_job"
            self.num_tasks = 1
            self.num_nodes = 1
            self.node = 0
            self.global_rank = 0
            self.local_rank = 0
        
        def activated(self):
            return False
    
    class DummySubmitit:
        class JobEnvironment(DummyJobEnvironment):
            pass
        
        class AutoExecutor:
            def __init__(self, *args, **kwargs):
                pass
            
            def update_parameters(self, *args, **kwargs):
                pass
            
            def submit(self, *args, **kwargs):
                raise NotImplementedError("submitit is not available")
    
    # Replace None with the dummy implementation
    submitit = DummySubmitit""",
        content
    )
    
    # Fix get_job_env function
    patched_content = re.sub(
        r"def get_job_env\(\) -> submitit\.JobEnvironment:",
        "def get_job_env():",
        patched_content
    )
    
    # Fix get_slurm_job_id function
    patched_content = re.sub(
        r"def get_slurm_job_id\(\):",
        "def get_slurm_job_id():",
        patched_content
    )
    
    # Fix get_slurm_master function
    patched_content = re.sub(
        r"def get_slurm_master\(\):",
        "def get_slurm_master():",
        patched_content
    )
    
    # Fix maybe_init_requeue_handler function
    patched_content = re.sub(
        r"def maybe_init_requeue_handler\(\):",
        "def maybe_init_requeue_handler():",
        patched_content
    )
    
    # Write the patched content back to the file
    with open(util_path, "w") as f:
        f.write(patched_content)
    
    print(f"Successfully patched {util_path}")
    return True

if __name__ == "__main__":
    patch_heyhi_util()