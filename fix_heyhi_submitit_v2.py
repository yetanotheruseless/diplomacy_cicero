#!/usr/bin/env python3
"""
Script to fix submitit references in heyhi/util.py.
This makes submitit truly optional by implementing a dummy version when not available.
"""
import os

def patch_heyhi_util():
    """Patch heyhi/util.py to make submitit truly optional."""
    util_path = "heyhi/util.py"
    
    if not os.path.exists(util_path):
        print(f"Error: {util_path} not found")
        return False
    
    with open(util_path, "r") as f:
        lines = f.readlines()
    
    # Find the submitit import line
    submitit_line_idx = -1
    for i, line in enumerate(lines):
        if "import submitit" in line and not line.strip().startswith("#"):
            submitit_line_idx = i
            break
    
    if submitit_line_idx == -1:
        print(f"Could not find 'import submitit' line in {util_path}")
        return False
    
    # Replace the single line with the new block
    dummy_submitit_code = """try:
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
            self.hostname = "localhost"
        
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
    submitit = DummySubmitit
"""
    
    # Remove original line and insert new code
    new_lines = lines[:submitit_line_idx] + dummy_submitit_code.splitlines(True) + lines[submitit_line_idx+1:]
    
    # Fix get_job_env and other functions that use submitit
    final_lines = []
    for line in new_lines:
        # Remove typehints that reference submitit
        if "-> submitit." in line:
            line = line.split("->")[0] + ":\n"
        final_lines.append(line)
    
    # Write back the modified content
    with open(util_path, "w") as f:
        f.writelines(final_lines)
    
    print(f"Successfully patched {util_path}")
    return True

if __name__ == "__main__":
    patch_heyhi_util()