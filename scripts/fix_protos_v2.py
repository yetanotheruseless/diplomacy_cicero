#!/usr/bin/env python3
"""
A completely rewritten script to fix protobuf files for compatibility with protobuf 3.19.1.
This script uses a working minimal_pb2.py as a template to properly fix protobuf files.
"""
import os
import sys
import glob
import re

def get_imports_from_file(file_path):
    """Extract import statements from a proto file."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Use regex to find imports
    imports = re.findall(r'import\s+"([^"]+)";', content)
    
    return imports

def extract_serialized_data(file_path):
    """Extract the serialized data from a _pb2.py file."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find serialized data - find the line with AddSerializedFile and extract the raw data
    match = re.search(r'DESCRIPTOR\s*=\s*_descriptor_pool\.Default\(\)\.AddSerializedFile\((?:_b|b)\((.*?)\)\)', content, re.DOTALL)
    if match:
        return match.group(1)
    
    return None

def extract_globals_section(file_path):
    """Extract the _globals section from a _pb2.py file."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find the globals section
    match = re.search(r'if _descriptor\._USE_C_DESCRIPTORS == False:.*?# @@protoc_insertion_point\(module_scope\)', content, re.DOTALL)
    if match:
        return match.group(0)
    
    return None

def fix_proto_file(file_path, template_path):
    """Fix a protobuf file using the template."""
    print(f"Fixing {file_path}...")
    
    # Get the filename
    filename = os.path.basename(file_path)
    module_name = filename[:-3]  # Remove .py
    proto_name = module_name[:-4] if module_name.endswith('_pb2') else module_name  # Remove _pb2
    
    with open(template_path, 'r') as f:
        template = f.read()
    
    # Extract raw serialized data
    serialized_data = extract_serialized_data(file_path)
    if not serialized_data:
        print(f"WARNING: Could not extract serialized data from {file_path}")
        return False
    
    # Extract globals section if possible
    globals_section = extract_globals_section(file_path)
    
    # Extract imports from the pb2 file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Extract imports
    imports = []
    import_lines = re.findall(r'from\s+([^\s]+)\s+import\s+([^\n]+)', content)
    for module, what in import_lines:
        if module != 'google.protobuf':
            imports.append((module, what))
    
    # Create a fixed version based on the template
    fixed_content = template.replace('minimal.proto', f"{proto_name}.proto")
    fixed_content = fixed_content.replace('minimal_pb2', f"{module_name}")
    
    # Add our custom _b function for protobuf 3.19.1 compatibility
    fixed_content = fixed_content.replace(
        'from google.protobuf.internal import builder as _builder',
        '# Fixed import for compatibility with protobuf 3.19.1\nimport sys\n_b=sys.version_info[0]<3 and (lambda x:x) or (lambda x:x.encode(\'latin1\'))'
    )
    
    # Replace the AddSerializedFile line
    # Create a pattern that doesn't require processing the serialized data
    pattern = r'DESCRIPTOR\s*=\s*_descriptor_pool\.Default\(\)\.AddSerializedFile\((?:_b|b)\([^)]+\)\)'
    replacement = f'DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(_b({serialized_data}))'
    fixed_content = re.sub(pattern, replacement, fixed_content)
    
    # Add the imports
    import_section = ''
    for module, what in imports:
        import_section += f'from {module} import {what}\n'
    
    # Insert import section after the original imports
    fixed_content = fixed_content.replace('# @@protoc_insertion_point(imports)', 
                                         f'# @@protoc_insertion_point(imports)\n\n{import_section}')
    
    # Replace the globals section
    if globals_section:
        fixed_content = re.sub(
            r'if _descriptor\._USE_C_DESCRIPTORS == False:.*?# @@protoc_insertion_point\(module_scope\)',
            globals_section,
            fixed_content,
            flags=re.DOTALL
        )
    
    # Fix _builder references
    fixed_content = fixed_content.replace('_builder.BuildMessageAndEnumDescriptors', 
                                         '# _builder.BuildMessageAndEnumDescriptors')
    fixed_content = re.sub(
        r'_builder\.BuildTopDescriptorsAndMessages\(.*?\)',
        '# BuildTopDescriptorsAndMessages removed for compatibility',
        fixed_content
    )
    
    # Write the fixed file
    with open(file_path, 'w') as f:
        f.write(fixed_content)
    
    print(f"✅ Fixed {file_path}")
    return True

def test_import(module_name):
    """Test if a module can be imported."""
    try:
        __import__(module_name)
        return True
    except ImportError as e:
        print(f"❌ Could not import {module_name}: {e}")
        return False
    except SyntaxError as e:
        print(f"❌ Syntax error in {module_name}: {e}")
        return False

def main():
    if not os.path.exists('protobuf_template.py'):
        print("❌ protobuf_template.py not found")
        print("Run scripts/generate_minimal_protobuf.py first")
        return False
    
    # Add the current directory to the path
    sys.path.insert(0, os.getcwd())
    
    # Find all _pb2.py files in the conf directory
    pb2_files = glob.glob('conf/*_pb2.py')
    if not pb2_files:
        print("No _pb2.py files found in conf directory")
        return False
    
    # Fix each file
    success_count = 0
    for file_path in pb2_files:
        if fix_proto_file(file_path, 'protobuf_template.py'):
            success_count += 1
    
    print(f"Fixed {success_count}/{len(pb2_files)} files")
    
    # Test imports
    print("\nTesting imports...")
    import_success = True
    for file_path in pb2_files:
        module_name = 'conf.' + os.path.basename(file_path)[:-3]  # Remove .py
        if test_import(module_name):
            print(f"✅ Successfully imported {module_name}")
        else:
            import_success = False
    
    if import_success:
        print("\n✅ All protobuf modules can be successfully imported!")
    else:
        print("\n❌ Some protobuf modules could not be imported")
    
    return import_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)