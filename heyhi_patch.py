import os
import re

# Path to the file we want to patch
path = "heyhi/util.py"

# Read the file content
with open(path, "r") as f:
    content = f.read()

# Add a try/except block around the submitit import
content = re.sub(
    r"import submitit",
    "try:\n    import submitit\nexcept ImportError:\n    submitit = None\n    print('Warning: submitit not available, some functionality will be limited')",
    content
)

# Make functions that use submitit check if it's available
content = re.sub(
    r"def get_slurm_job_id\(\):",
    "def get_slurm_job_id():\n    if submitit is None:\n        return None",
    content
)

content = re.sub(
    r"def get_slurm_master\(\):",
    "def get_slurm_master():\n    if submitit is None:\n        return None",
    content
)

content = re.sub(
    r"def maybe_init_requeue_handler\(\):",
    "def maybe_init_requeue_handler():\n    if submitit is None:\n        return",
    content
)

# Write the patched content back to the file
with open(path, "w") as f:
    f.write(content)

print("Patched heyhi/util.py to make submitit optional")
