#!/usr/bin/env python3
"""
Script to fix protobuf imports in the generated pb2 files.
This is necessary because the version of protoc used may not match the Python protobuf library.

Specifically, this script:
1. Removes dependency on the missing 'builder' module from protobuf 3.19.1
2. Replaces it with compatible code that works with protobuf 3.19.1
3. Fixes message declaration syntax and serialized options formatting
"""
import os
import sys
import glob
import re

def fix_protobuf_imports(file_path):
    print(f"Fixing imports in {file_path}")
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Step 1: Complete replacement of builder import with _b function
    fixed_content = re.sub(
        r'from google\.protobuf\.internal import builder as _builder',
        '# Fixed import for compatibility with protobuf 3.19.1\nimport sys\n_b=sys.version_info[0]<3 and (lambda x:x) or (lambda x:x.encode(\'latin1\'))',
        content
    )
    
    # Step 2: Replace all references to _builder
    fixed_content = re.sub(
        r'_builder\.BuildMessageAndEnumDescriptors\(DESCRIPTOR, globals\(\)\)',
        '# _builder.BuildMessageAndEnumDescriptors removed for compatibility',
        fixed_content
    )
    
    fixed_content = re.sub(
        r'_builder\.BuildTopDescriptorsAndMessages\(DESCRIPTOR, [^\)]+\)',
        '# _builder.BuildTopDescriptorsAndMessages removed for compatibility',
        fixed_content
    )
    
    # Step 3: Fix serialized options
    fixed_content = re.sub(
        r'serialized_options=None',
        'serialized_options=_b("")',
        fixed_content
    )
    
    # Step 4: Fix message definition format
    # Change to dict() constructor style
    pattern = r'([a-zA-Z_][a-zA-Z0-9_]*) = _reflection\.GeneratedProtocolMessageType\(\'([a-zA-Z_][a-zA-Z0-9_]*)\', \(_message\.Message,\), \{'
    repl = r'\1 = _reflection.GeneratedProtocolMessageType(\'\2\', (_message.Message,), dict('
    fixed_content = re.sub(pattern, repl, fixed_content)
    
    # Ensure closing braces also have the right parenthesis
    fixed_content = re.sub(
        r'}\)',
        '}))',
        fixed_content
    )
    
    # Step 5: Fix remaining string encodings 
    # Look for any b'...' strings that should be _b('...')
    fixed_content = re.sub(
        r'([\s=\(])b([\'"])',
        r'\1_b(\2',
        fixed_content
    )
    fixed_content = re.sub(
        r'([\'"])(\)[\s,\)])',
        r'\1)\2',
        fixed_content
    )
    
    # Step 6: Special handling for descriptor creation
    # Make sure all descriptor field definitions use _b for string fields
    descriptor_pattern = r'(_descriptor\.[A-Za-z]+Descriptor\([^)]+serialized_options=)b([\'"][^\'"]*[\'"])'
    fixed_content = re.sub(descriptor_pattern, r'\1_b(\2)', fixed_content)
    
    # Write back the fixed content
    with open(file_path, 'w') as f:
        f.write(fixed_content)
    
    print(f"Fixed imports in {file_path}")
    return True

def main():
    pb2_files = glob.glob("conf/*_pb2.py")
    if not pb2_files:
        print("No protobuf files found. Run 'make protos_basic' first.")
        sys.exit(1)
    
    # Fix all the files
    for pb2_file in pb2_files:
        fix_protobuf_imports(pb2_file)
    
    print(f"Applied fixes to {len(pb2_files)} protobuf files.")
    
    # Create a simple test file to verify our fixes
    test_file_path = "test_proto_import.py"
    with open(test_file_path, "w") as f:
        f.write("""
import sys
import os

# Add the current directory to the path so we can import the conf modules
sys.path.insert(0, os.getcwd())

try:
    from conf import conf_pb2
    print("Successfully imported conf_pb2")
    
    # Try to create a config object
    config = conf_pb2.Config()
    print("Successfully created a Config object")
    
    # Try other imports
    from conf import agents_pb2, common_pb2, misc_pb2
    print("Successfully imported all protobuf modules")
    
    print("PROTOBUF FIXES SUCCESSFUL!")
except Exception as e:
    print(f"Error importing protobuf modules: {e}")
    sys.exit(1)
""")
    
    print(f"Created test file at {test_file_path}")
    print("Run 'python test_proto_import.py' to test if the fixes were successful.")

if __name__ == "__main__":
    main()

def test_final_imports():
    """Try to import all the main protobuf modules to verify everything works."""
    try:
        from conf import conf_pb2, agents_pb2, common_pb2, misc_pb2
        print("✅ All main protobuf modules can be imported successfully")
        return True
    except Exception as e:
        print(f"❌ Error importing main protobuf modules: {e}")
        return False

if __name__ == "__main__":
    pb2_files = glob.glob("conf/*pb2.py")
    if not pb2_files:
        print("No protobuf files found. Run 'make protos_basic' first.")
        sys.exit(1)
    
    fixed_files = 0
    for pb2_file in pb2_files:
        if fix_protobuf_imports(pb2_file):
            fixed_files += 1
    
    print(f"Fixed {fixed_files}/{len(pb2_files)} protobuf files.")
    
    # Add conf directory to sys.path to allow imports
    sys.path.insert(0, os.getcwd())
    
    if test_final_imports():
        print("✅ All protobuf files have been fixed successfully.")
        sys.exit(0)
    else:
        print("⚠️ Some protobuf files still have issues. Manual inspection may be required.")
        sys.exit(1)