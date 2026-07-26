cmake_minimum_required(VERSION 3.28)
project(cicero_selfplay VERSION 0.1.0 LANGUAGES CXX)

include(CTest)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Python 3.12 EXACT REQUIRED COMPONENTS Interpreter Development.Module)
find_package(Threads REQUIRED)

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
      "Unable to locate pybind11 with ${Python_EXECUTABLE}: ${PYBIND11_CMAKEDIR_ERROR}"
    )
  endif()
  list(PREPEND CMAKE_PREFIX_PATH "${PYBIND11_CMAKEDIR}")
endif()
find_package(pybind11 3 CONFIG REQUIRED)

set(CICERO_TORCH_VERSION "2.13.0" CACHE STRING "Required PyTorch release")
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
    "Unable to inspect PyTorch with ${Python_EXECUTABLE}: ${TORCH_DISCOVERY_ERROR}"
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
    "Cicero self-play requires torch ${CICERO_TORCH_VERSION}; "
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

function(cicero_selfplay_target target)
  target_compile_features("${target}" PRIVATE cxx_std_20)
  target_compile_options(
    "${target}"
    PRIVATE
      $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wall>
      $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wextra>
      $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wpedantic>
      $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wno-sign-compare>
  )
endfunction()

pybind11_add_module(rela MODULE pybind.cc)
target_link_libraries(
  rela
  PRIVATE
    Python::Module
    Threads::Threads
    ${TORCH_LIBRARIES}
    ${TORCH_PYTHON_LIBRARY}
)
cicero_selfplay_target(rela)

if(BUILD_TESTING)
  add_executable(prioritized_replay_test prioritized_replay_test.cc)
  target_link_libraries(
    prioritized_replay_test
    PRIVATE
      Threads::Threads
      ${TORCH_LIBRARIES}
  )
  cicero_selfplay_target(prioritized_replay_test)
  add_test(NAME prioritized_replay_test COMMAND prioritized_replay_test)
endif()
