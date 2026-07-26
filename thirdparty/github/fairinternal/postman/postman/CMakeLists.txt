cmake_minimum_required(VERSION 3.28)
if(CMAKE_HOST_APPLE)
  set(
    CMAKE_OSX_DEPLOYMENT_TARGET
    "14.0"
    CACHE STRING
    "Minimum supported macOS release for Cicero Postman"
    FORCE
  )
endif()
project(cicero_postman VERSION 0.3.0 LANGUAGES C CXX)

include(CTest)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
option(
  CICERO_POSTMAN_WARNINGS_AS_ERRORS
  "Treat warnings in Cicero-owned Postman targets as errors"
  ON
)

set(
  CICERO_GRPC_SOURCE_DIR
  ""
  CACHE PATH
  "Path to the SHA-verified gRPC v1.83.0 checkout prepared by build_postman.sh"
)
set(CICERO_GRPC_VERSION "1.83.0" CACHE STRING "Required gRPC release")
set(CICERO_TORCH_VERSION "2.13.0" CACHE STRING "Required PyTorch release")
set(
  CICERO_GRPC_COMMIT
  "c876f4da50f7da2f331888b88b2a7243514139fe"
  CACHE STRING
  "Required gRPC source revision"
)
set(
  CICERO_PROTOBUF_COMMIT
  "35cd01f9fe9afbeea38cc7b979a3b6bfcde82c03"
  CACHE STRING
  "Required protobuf 35.1 source revision"
)

if(NOT CICERO_GRPC_SOURCE_DIR)
  message(
    FATAL_ERROR
    "CICERO_GRPC_SOURCE_DIR is required. Run scripts/build_postman.sh so that "
    "the pinned gRPC/protobuf sources are fetched and verified."
  )
endif()
if(NOT EXISTS "${CICERO_GRPC_SOURCE_DIR}/CMakeLists.txt")
  message(
    FATAL_ERROR
    "CICERO_GRPC_SOURCE_DIR does not contain gRPC sources: "
    "${CICERO_GRPC_SOURCE_DIR}"
  )
endif()

find_package(Python 3.12 EXACT REQUIRED COMPONENTS Interpreter Development.Module)
find_package(Threads REQUIRED)
find_package(Git REQUIRED)

set(PYBIND11_FINDPYTHON ON)
if(NOT pybind11_DIR)
  execute_process(
    COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
    RESULT_VARIABLE PYBIND11_CMAKEDIR_RESULT
    OUTPUT_VARIABLE PYBIND11_CMAKEDIR
    ERROR_VARIABLE PYBIND11_CMAKEDIR_ERROR
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )
  if(NOT PYBIND11_CMAKEDIR_RESULT EQUAL 0)
    message(
      FATAL_ERROR
      "Unable to locate pybind11 with ${Python_EXECUTABLE}: "
      "${PYBIND11_CMAKEDIR_ERROR}"
    )
  endif()
  list(PREPEND CMAKE_PREFIX_PATH "${PYBIND11_CMAKEDIR}")
endif()
find_package(pybind11 3.0.4 EXACT CONFIG REQUIRED)

# gRPC owns a tested dependency set. Its v1.83.0 checkout pins protobuf's 35.1
# source commit; build_postman.sh verifies both immutable revisions before
# configuration. Only the C++ plugin is needed for Postman's generated service.
execute_process(
  COMMAND "${GIT_EXECUTABLE}" -C "${CICERO_GRPC_SOURCE_DIR}" rev-parse HEAD
  RESULT_VARIABLE GRPC_REVISION_RESULT
  OUTPUT_VARIABLE GRPC_REVISION
  ERROR_VARIABLE GRPC_REVISION_ERROR
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
if(NOT GRPC_REVISION_RESULT EQUAL 0 OR NOT GRPC_REVISION STREQUAL CICERO_GRPC_COMMIT)
  message(
    FATAL_ERROR
    "Cicero Postman requires gRPC commit ${CICERO_GRPC_COMMIT}; "
    "${CICERO_GRPC_SOURCE_DIR} provides ${GRPC_REVISION}. "
    "${GRPC_REVISION_ERROR}"
  )
endif()
execute_process(
  COMMAND
    "${GIT_EXECUTABLE}" -C
    "${CICERO_GRPC_SOURCE_DIR}/third_party/protobuf" rev-parse HEAD
  RESULT_VARIABLE PROTOBUF_REVISION_RESULT
  OUTPUT_VARIABLE PROTOBUF_REVISION
  ERROR_VARIABLE PROTOBUF_REVISION_ERROR
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
if(
  NOT PROTOBUF_REVISION_RESULT EQUAL 0
  OR NOT PROTOBUF_REVISION STREQUAL CICERO_PROTOBUF_COMMIT
)
  message(
    FATAL_ERROR
    "Cicero Postman requires protobuf commit ${CICERO_PROTOBUF_COMMIT}; "
    "${CICERO_GRPC_SOURCE_DIR}/third_party/protobuf provides "
    "${PROTOBUF_REVISION}. ${PROTOBUF_REVISION_ERROR}"
  )
endif()

set(ABSL_PROPAGATE_CXX_STD ON CACHE BOOL "" FORCE)
set(gRPC_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(gRPC_INSTALL OFF CACHE BOOL "" FORCE)
set(gRPC_BUILD_CODEGEN ON CACHE BOOL "" FORCE)
set(gRPC_BUILD_GRPC_CPP_PLUGIN ON CACHE BOOL "" FORCE)
set(gRPC_BUILD_GRPC_CSHARP_PLUGIN OFF CACHE BOOL "" FORCE)
set(gRPC_BUILD_GRPC_NODE_PLUGIN OFF CACHE BOOL "" FORCE)
set(gRPC_BUILD_GRPC_OBJECTIVE_C_PLUGIN OFF CACHE BOOL "" FORCE)
set(gRPC_BUILD_GRPC_PHP_PLUGIN OFF CACHE BOOL "" FORCE)
set(gRPC_BUILD_GRPC_PYTHON_PLUGIN OFF CACHE BOOL "" FORCE)
set(gRPC_BUILD_GRPC_RUBY_PLUGIN OFF CACHE BOOL "" FORCE)
set(protobuf_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(protobuf_INSTALL OFF CACHE BOOL "" FORCE)
set(protobuf_WITH_ZLIB OFF CACHE BOOL "" FORCE)
set(RE2_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(ZLIB_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(RENAME_ZCONF OFF CACHE BOOL "" FORCE)
set(CARES_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(CARES_BUILD_CONTAINER_TESTS OFF CACHE BOOL "" FORCE)
set(CARES_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(CARES_INSTALL OFF CACHE BOOL "" FORCE)
add_subdirectory("${CICERO_GRPC_SOURCE_DIR}" grpc EXCLUDE_FROM_ALL)

# zlib's quoted source-header include bypasses its generated zconf.h. Recent
# macOS SDKs therefore need the successful unistd.h probe propagated directly
# when targeting macOS 14; otherwise POSIX calls are left undeclared.
if(APPLE)
  target_compile_definitions(zlib PRIVATE Z_HAVE_UNISTD_H)
  target_compile_definitions(zlibstatic PRIVATE Z_HAVE_UNISTD_H)
endif()

execute_process(
  COMMAND
    "${Python_EXECUTABLE}" -c
    "import torch; print(torch.__version__.split('+', 1)[0]); print(torch.utils.cmake_prefix_path); print(torch.__path__[0])"
  RESULT_VARIABLE TORCH_DISCOVERY_RESULT
  OUTPUT_VARIABLE TORCH_DISCOVERY_OUTPUT
  ERROR_VARIABLE TORCH_DISCOVERY_ERROR
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
if(NOT TORCH_DISCOVERY_RESULT EQUAL 0)
  message(
    FATAL_ERROR
    "Unable to inspect PyTorch with ${Python_EXECUTABLE}: "
    "${TORCH_DISCOVERY_ERROR}"
  )
endif()

string(REPLACE "\n" ";" TORCH_DISCOVERY "${TORCH_DISCOVERY_OUTPUT}")
list(LENGTH TORCH_DISCOVERY TORCH_DISCOVERY_LENGTH)
if(NOT TORCH_DISCOVERY_LENGTH EQUAL 3)
  message(FATAL_ERROR "Unexpected PyTorch discovery output: ${TORCH_DISCOVERY_OUTPUT}")
endif()
list(GET TORCH_DISCOVERY 0 TORCH_PYTHON_VERSION)
list(GET TORCH_DISCOVERY 1 TORCH_CMAKE_PREFIX)
list(GET TORCH_DISCOVERY 2 TORCH_PACKAGE_DIR)
if(NOT TORCH_PYTHON_VERSION VERSION_EQUAL CICERO_TORCH_VERSION)
  message(
    FATAL_ERROR
    "Cicero Postman requires torch ${CICERO_TORCH_VERSION}; "
    "${Python_EXECUTABLE} provides ${TORCH_PYTHON_VERSION}"
  )
endif()

list(APPEND CMAKE_PREFIX_PATH "${TORCH_CMAKE_PREFIX}")
find_package(Torch CONFIG REQUIRED)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${TORCH_CXX_FLAGS}")
find_library(
  TORCH_PYTHON_LIBRARY
  NAMES torch_python libtorch_python
  PATHS "${TORCH_PACKAGE_DIR}/lib"
  NO_DEFAULT_PATH
  REQUIRED
)

set(POSTMAN_PROTO "${CMAKE_CURRENT_SOURCE_DIR}/proto/rpc.proto")
set(POSTMAN_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(POSTMAN_PROTO_SOURCE "${POSTMAN_GENERATED_DIR}/rpc.pb.cc")
set(POSTMAN_PROTO_HEADER "${POSTMAN_GENERATED_DIR}/rpc.pb.h")
set(POSTMAN_GRPC_SOURCE "${POSTMAN_GENERATED_DIR}/rpc.grpc.pb.cc")
set(POSTMAN_GRPC_HEADER "${POSTMAN_GENERATED_DIR}/rpc.grpc.pb.h")
file(MAKE_DIRECTORY "${POSTMAN_GENERATED_DIR}")

add_custom_command(
  OUTPUT
    "${POSTMAN_PROTO_SOURCE}"
    "${POSTMAN_PROTO_HEADER}"
    "${POSTMAN_GRPC_SOURCE}"
    "${POSTMAN_GRPC_HEADER}"
  COMMAND
    "$<TARGET_FILE:protobuf::protoc>"
    --proto_path "${CMAKE_CURRENT_SOURCE_DIR}/proto"
    --cpp_out "${POSTMAN_GENERATED_DIR}"
    --grpc_out "${POSTMAN_GENERATED_DIR}"
    --plugin=protoc-gen-grpc=$<TARGET_FILE:grpc_cpp_plugin>
    "${POSTMAN_PROTO}"
  DEPENDS
    "${POSTMAN_PROTO}"
    grpc_cpp_plugin
    protobuf::protoc
  VERBATIM
)

add_library(
  postman_core STATIC
  cc/asyncclient.cc
  cc/client.cc
  cc/serialization.cc
  cc/server.cc
  "${POSTMAN_PROTO_SOURCE}"
  "${POSTMAN_GRPC_SOURCE}"
)
target_include_directories(
  postman_core
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/../nest/nest"
    "${POSTMAN_GENERATED_DIR}"
)
target_link_libraries(
  postman_core
  PUBLIC
    Threads::Threads
    grpc++_unsecure
    libprotobuf
    ${TORCH_LIBRARIES}
)

pybind11_add_module(rpc MODULE cc/rpc_python.cc)
target_compile_definitions(
  rpc
  PRIVATE
    CICERO_POSTMAN_GRPC_VERSION="${CICERO_GRPC_VERSION}"
    CICERO_POSTMAN_PROTOBUF_VERSION="35.1"
    CICERO_POSTMAN_TORCH_VERSION="${CICERO_TORCH_VERSION}"
)
target_link_libraries(
  rpc
  PRIVATE
    Python::Module
    postman_core
    ${TORCH_PYTHON_LIBRARY}
)
if(APPLE)
  set_target_properties(
    rpc
    PROPERTIES
      INSTALL_RPATH "@loader_path/../torch/lib"
      INSTALL_RPATH_USE_LINK_PATH FALSE
  )
elseif(UNIX)
  set_target_properties(
    rpc
    PROPERTIES
      INSTALL_RPATH "$ORIGIN/../torch/lib"
      INSTALL_RPATH_USE_LINK_PATH FALSE
  )
endif()

function(cicero_postman_target target)
  target_compile_features("${target}" PRIVATE cxx_std_20)
  target_compile_options(
    "${target}"
    PRIVATE
      $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wall>
      $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wextra>
      $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wpedantic>
      $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wno-sign-compare>
      $<$<CXX_COMPILER_ID:AppleClang,Clang>:-Wno-nullability-extension>
      $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wno-deprecated-declarations>
  )
  if(CICERO_POSTMAN_WARNINGS_AS_ERRORS)
    target_compile_options(
      "${target}"
      PRIVATE
        $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Werror>
    )
  endif()
endfunction()

cicero_postman_target(postman_core)
cicero_postman_target(rpc)

if(BUILD_TESTING)
  add_executable(
    postman_native_test
    tests/cc/postman_test.cc
  )
  target_link_libraries(postman_native_test PRIVATE postman_core)
  cicero_postman_target(postman_native_test)
  add_test(NAME postman_native_test COMMAND postman_native_test)
  set_tests_properties(postman_native_test PROPERTIES TIMEOUT 45)

  set(POSTMAN_HEADER_TEST_SOURCES)
  foreach(
    POSTMAN_HEADER
    asyncclient
    blocking_counter
    client
    computationqueue
    exceptions
    queue
    serialization
    server
  )
    set(
      POSTMAN_HEADER_TEST_SOURCE
      "${CMAKE_CURRENT_BINARY_DIR}/header-tests/${POSTMAN_HEADER}.cc"
    )
    file(
      CONFIGURE
      OUTPUT "${POSTMAN_HEADER_TEST_SOURCE}"
      CONTENT "#include <postman/${POSTMAN_HEADER}.h>\n"
      @ONLY
    )
    list(APPEND POSTMAN_HEADER_TEST_SOURCES "${POSTMAN_HEADER_TEST_SOURCE}")
  endforeach()
  add_library(
    postman_headers_test
    OBJECT
    ${POSTMAN_HEADER_TEST_SOURCES}
  )
  target_link_libraries(postman_headers_test PRIVATE postman_core)
  cicero_postman_target(postman_headers_test)
endif()

install(TARGETS rpc LIBRARY DESTINATION postman)
