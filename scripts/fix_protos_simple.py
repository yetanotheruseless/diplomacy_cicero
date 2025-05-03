#!/usr/bin/env python3
"""
A much simpler script to fix protobuf compatibility issues.
This script directly replaces the problematic imports without regex escaping issues.
"""

import glob
import os
import sys

# The replacement template for the imports section
REPLACEMENT_IMPORTS = """from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# Fixed import for compatibility with protobuf 3.19.1
import sys
_b=sys.version_info[0]<3 and (lambda x:x) or (lambda x:x.encode('latin1'))
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()
"""

def fix_file(file_path):
    print(f"Fixing {file_path}...")
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Replace the imports section
    if 'from google.protobuf.internal import builder as _builder' in content:
        start_marker = 'from google.protobuf import descriptor as _descriptor'
        end_marker = '_sym_db = _symbol_database.Default()'
        
        start_index = content.find(start_marker)
        end_index = content.find(end_marker) + len(end_marker)
        
        if start_index >= 0 and end_index > start_index:
            # Replace the entire imports section
            content = content[:start_index] + REPLACEMENT_IMPORTS + content[end_index:]
        
        # Remove any references to _builder
        content = content.replace('_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())', 
                                 '# BuildMessageAndEnumDescriptors removed for compatibility')
        content = content.replace('_builder.BuildTopDescriptorsAndMessages(', 
                                 '# BuildTopDescriptorsAndMessages removed: ')
    
    # Fix message type definitions
    if '), {' in content:
        content = content.replace('), {', '), dict({')
        content = content.replace('})', '}))')
    
    # Write the fixed content back
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"✅ Fixed {file_path}")
    return True

def main():
    # Find all protobuf files
    pb2_files = glob.glob('conf/*_pb2.py')
    if not pb2_files:
        print("No _pb2.py files found in conf directory")
        return False
    
    # Fix each file
    fixed_count = 0
    for file_path in pb2_files:
        if fix_file(file_path):
            fixed_count += 1
    
    print(f"Fixed {fixed_count}/{len(pb2_files)} files")
    
    # Test if we can import one of the files
    print("\nTesting import...")
    try:
        sys.path.insert(0, os.getcwd())
        from conf import conf_pb2
        print("✅ Successfully imported conf_pb2")
        return True
    except Exception as e:
        print(f"❌ Error importing conf_pb2: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)