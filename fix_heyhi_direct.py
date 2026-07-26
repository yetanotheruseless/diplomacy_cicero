#!/usr/bin/env python3
"""
Script to directly fix the heyhi/util.py file with a clean implementation.
"""
import os

def fix_heyhi_util():
    """Write a clean version of the heyhi/util.py file with submitit fix."""
    # First make a backup
    os.system("cp heyhi/util.py heyhi/util.py.bak")
    
    # Find the start of imports in the existing file
    with open("heyhi/util.py", "r") as f:
        lines = f.readlines()
    
    # Find where the actual code starts after imports
    import_section_end = 0
    for i, line in enumerate(lines):
        if "import torch" in line:
            import_section_end = i + 1
            break
    
    if import_section_end == 0:
        print("Could not find imports section in heyhi/util.py")
        return False
    
    # Keep the top copyright and imports section
    header = "".join(lines[:import_section_end])
    
    # Add our fixed submitit implementation
    submitit_code = """
# Optional submitit import with fallback to dummy implementation
try:
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
    
    # Find the rest of the file after imports
    rest_of_file = "".join(lines[import_section_end:])
    
    # Fix return type annotations that reference submitit
    rest_of_file = rest_of_file.replace("-> submitit.JobEnvironment", "")
    
    # Write the complete fixed file
    with open("heyhi/util.py", "w") as f:
        f.write(header)
        f.write(submitit_code)
        f.write(rest_of_file)
    
    print("Successfully fixed heyhi/util.py with clean implementation")
    return True

if __name__ == "__main__":
    fix_heyhi_util()