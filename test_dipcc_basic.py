print("Looking for dipcc module...")

# Try multiple paths
import sys
import glob
import os

# Add potential paths
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/dipcc/build/dipcc/python")
sys.path.insert(0, "/app/dipcc/build/out")

# Print Python path
print("Python path:", sys.path)

# Look for .so files
print("Looking for .so files...")
so_files = []
for path in ["/app/fairdiplomacy", "/app/dipcc/build", "/app/dipcc/build/dipcc/python"]:
    if os.path.exists(path):
        so_files.extend(glob.glob(f"{path}/*.so"))
        so_files.extend(glob.glob(f"{path}/**/*.so"))

print(f"Found .so files: {so_files}")

# Try to import
try:
    print("Trying to import fairdiplomacy.pydipcc...")
    from fairdiplomacy import pydipcc
    print("Successfully imported fairdiplomacy.pydipcc")
    print("Available in pydipcc:", dir(pydipcc))
except ImportError as e:
    print(f"ImportError with fairdiplomacy.pydipcc: {e}")
    
    try:
        print("Trying to import dipcc directly...")
        import dipcc
        print("Successfully imported dipcc")
        print("Available in dipcc:", dir(dipcc))
    except ImportError as e:
        print(f"ImportError with dipcc: {e}")
        
        # Try to load directly from .so file if any were found
        if so_files:
            print(f"Trying to load directly from .so file: {so_files[0]}")
            import importlib.util
            spec = importlib.util.spec_from_file_location("direct_pydipcc", so_files[0])
            if spec:
                direct_pydipcc = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(direct_pydipcc)
                print("Loaded module directly:", dir(direct_pydipcc))
            else:
                print("Failed to create module spec from .so file")
        else:
            print("No .so files found to load directly")
