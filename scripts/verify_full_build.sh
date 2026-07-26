#!/bin/bash
# Script to verify that the full build is working correctly

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "\n${GREEN}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

# Check if --full-test flag is provided
FULL_TEST=0
if [[ "$1" == "--full-test" ]]; then
    FULL_TEST=1
fi

# Start verification
print_header "Starting Full Build Verification"
echo "Current directory: $(pwd)"

# Step 1: Verify Python environment
print_header "Verifying Python Environment"
echo "Python version: $(python --version 2>&1)"
echo "Python path: $(which python)"

# Check for critical packages
print_header "Checking Critical Packages"
packages=("numpy" "torch" "protobuf" "pybind11")
for pkg in "${packages[@]}"; do
    if python -c "import $pkg; print($pkg.__version__)" 2>/dev/null; then
        print_success "$pkg is installed"
    else
        print_error "$pkg is not installed"
        exit 1
    fi
done

# Check protobuf version specifically (must be 3.19.1)
PROTOBUF_VERSION=$(python -c "import google.protobuf; print(google.protobuf.__version__)" 2>/dev/null)
if [[ "$PROTOBUF_VERSION" == "3.19.1" ]]; then
    print_success "Protobuf version is correct: $PROTOBUF_VERSION"
else
    print_error "Protobuf version is incorrect: $PROTOBUF_VERSION (should be 3.19.1)"
    exit 1
fi

# Step 2: Verify protoc is installed and has the correct version
print_header "Verifying Protoc Installation"
if command -v protoc >/dev/null 2>&1; then
    PROTOC_VERSION=$(protoc --version | awk '{print $2}')
    echo "Protoc version: $PROTOC_VERSION"
    if [[ "$PROTOC_VERSION" == "3.19.1" ]]; then
        print_success "Protoc version is correct: $PROTOC_VERSION"
    else
        print_warning "Protoc version is $PROTOC_VERSION (should be 3.19.1)"
    fi
else
    print_error "Protoc is not installed"
    exit 1
fi

# Step 3: Verify protobuf files are compiled
print_header "Verifying Protobuf Files"
if [[ -f "conf/conf_pb2.py" && -f "conf/agents_pb2.py" ]]; then
    print_success "Protobuf Python files exist"
else
    print_error "Protobuf Python files are missing"
    print_warning "Running make protos_basic..."
    make protos_basic
    if [[ -f "conf/conf_pb2.py" && -f "conf/agents_pb2.py" ]]; then
        print_success "Protobuf Python files have been generated"
    else
        print_error "Failed to generate protobuf Python files"
        exit 1
    fi
fi

# Step 4: Verify dipcc module is built
print_header "Verifying dipcc Module"
PYDIPCC_FILES=$(find . -name "pydipcc*.so" | sort)
if [[ -n "$PYDIPCC_FILES" ]]; then
    print_success "Found pydipcc files:"
    for file in $PYDIPCC_FILES; do
        echo "  - $file"
    done
else
    print_error "No pydipcc.so files found"
    print_warning "You may need to build the C++ module with: make dipcc"
    exit 1
fi

# Step 5: Test importing pydipcc
print_header "Testing pydipcc Import"
if python -c "from fairdiplomacy import pydipcc; print('pydipcc version:', getattr(pydipcc, '__version__', 'unknown')); game = pydipcc.Game(); print('Successfully created game object')" 2>/dev/null; then
    print_success "Successfully imported pydipcc and created a Game object"
else
    print_error "Failed to import pydipcc or create a Game object"
    exit 1
fi

# Step 6: Verify heyhi module
print_header "Verifying heyhi Module"
if python -c "import heyhi; print('Successfully imported heyhi module')" 2>/dev/null; then
    print_success "Successfully imported heyhi module"
else
    print_error "Failed to import heyhi module"
    exit 1
fi

# Step 7: Run the test_pydipcc.py script
print_header "Running test_pydipcc.py"
if python test_pydipcc.py; then
    print_success "test_pydipcc.py passed"
else
    print_error "test_pydipcc.py failed"
    exit 1
fi

# Step 8: If --full-test was specified, run more comprehensive tests
if [[ $FULL_TEST -eq 1 ]]; then
    print_header "Running Full Test Suite"
    
    # Test importing key modules
    print_header "Testing Key Module Imports"
    modules=("fairdiplomacy" "fairdiplomacy.pydipcc" "fairdiplomacy.game" "fairdiplomacy.models" "fairdiplomacy.agents" "heyhi")
    for module in "${modules[@]}"; do
        if python -c "import $module; print(f'Successfully imported {module}')" 2>/dev/null; then
            print_success "Successfully imported $module"
        else
            print_error "Failed to import $module"
            exit 1
        fi
    done
    
    # Run our comprehensive test script
    if [[ -f "test_scripts/test_full_pipeline.py" ]]; then
        print_header "Running Comprehensive Pipeline Test"
        if python test_scripts/test_full_pipeline.py; then
            print_success "Full pipeline test passed"
        else
            print_error "Full pipeline test failed"
            exit 1
        fi
    else
        print_warning "test_scripts/test_full_pipeline.py not found, skipping comprehensive testing"
    fi
fi

# Final success message
print_header "Verification Complete"
print_success "All verification steps passed!"
echo ""
echo "You should now be able to use the Diplomacy Cicero codebase."
echo ""
echo "Try running one of these commands to verify:"
echo "  python run.py --help"
echo "  python -c \"from fairdiplomacy import pydipcc; game = pydipcc.Game(); print(game.get_current_phase())\""
echo ""
echo "To play one Cicero agent as Turkey against six full-press imitation agents, run:"
echo "  python run.py --adhoc --cfg conf/c01_ag_cmp/cmp.prototxt Iagent_one=agents/cicero.prototxt Iagent_six=agents/ablations/cicero_imitation_only.prototxt power_one=TURKEY"
echo ""

exit 0