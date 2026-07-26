cmake_minimum_required(VERSION 3.28)
project(dipcc VERSION 0.0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/out")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/out")
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/out")

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 3 CONFIG REQUIRED)
find_package(Threads REQUIRED)

# Prefer Homebrew's current libraries over unrelated packages exposed by an
# activated Conda installation.
foreach(_brew_pkg glog gflags)
  foreach(_brew_prefix /opt/homebrew/opt /usr/local/opt)
    if(EXISTS "${_brew_prefix}/${_brew_pkg}/include")
      list(PREPEND CMAKE_PREFIX_PATH "${_brew_prefix}/${_brew_pkg}")
    endif()
  endforeach()
endforeach()

find_package(gflags CONFIG REQUIRED)
find_package(glog CONFIG REQUIRED)

# glog >=0.6 requires this when consumers include <glog/logging.h>.
add_compile_definitions(GLOG_USE_GLOG_EXPORT)

if(TARGET glog::glog)
  set(DIPCC_GLOG_TARGET glog::glog)
else()
  message(FATAL_ERROR "The glog package did not define the glog::glog target")
endif()

execute_process(
  COMMAND
    "${Python_EXECUTABLE}" -c
    "import torch; print(torch.utils.cmake_prefix_path, end='')"
  RESULT_VARIABLE TORCH_PREFIX_RESULT
  OUTPUT_VARIABLE TORCH_CMAKE_PREFIX
  ERROR_VARIABLE TORCH_PREFIX_ERROR
)
if(NOT TORCH_PREFIX_RESULT EQUAL 0)
  message(FATAL_ERROR "Unable to locate Torch with ${Python_EXECUTABLE}: ${TORCH_PREFIX_ERROR}")
endif()

list(APPEND CMAKE_PREFIX_PATH "${TORCH_CMAKE_PREFIX}")
find_package(Torch CONFIG REQUIRED)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${TORCH_CXX_FLAGS}")

execute_process(
  COMMAND
    "${Python_EXECUTABLE}" -c
    "import torch; print(torch.__path__[0], end='')"
  RESULT_VARIABLE TORCH_PATH_RESULT
  OUTPUT_VARIABLE TORCH_PATH
  ERROR_VARIABLE TORCH_PATH_ERROR
)
if(NOT TORCH_PATH_RESULT EQUAL 0)
  message(FATAL_ERROR "Unable to locate the Torch package: ${TORCH_PATH_ERROR}")
endif()

find_library(
  TORCH_PYTHON_LIBRARY
  NAMES torch_python libtorch_python
  PATHS "${TORCH_PATH}/lib"
  NO_DEFAULT_PATH
  REQUIRED
)

set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3")
set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -g -pg")

file(GLOB SOURCES CONFIGURE_DEPENDS "dipcc/cc/*.cc")
file(GLOB PY_SOURCES CONFIGURE_DEPENDS "dipcc/pybind/*.cc")

set(DIPCC_LINK_LIBRARIES
    ${DIPCC_GLOG_TARGET}
    Threads::Threads
    ${TORCH_LIBRARIES}
    ${TORCH_PYTHON_LIBRARY}
)

add_library(dipcc ${SOURCES})
target_compile_options(dipcc PRIVATE -Wall -Wextra -pedantic -Wno-sign-compare)
target_link_libraries(dipcc PRIVATE ${DIPCC_LINK_LIBRARIES})

pybind11_add_module(pydipcc ${PY_SOURCES} ${SOURCES})
target_link_libraries(pydipcc PRIVATE ${DIPCC_LINK_LIBRARIES})
if(DEFINED ENV{PYDIPCC_OUT_DIR})
  set_target_properties(
    pydipcc PROPERTIES LIBRARY_OUTPUT_DIRECTORY "$ENV{PYDIPCC_OUT_DIR}"
  )
else()
  set_target_properties(
    pydipcc PROPERTIES LIBRARY_OUTPUT_DIRECTORY "dipcc/python/"
  )
endif()

if(CMAKE_BUILD_TYPE MATCHES Release)
  add_executable(profile_dipcc dipcc/profiling/profile.cc ${SOURCES})
  target_link_libraries(
    profile_dipcc PRIVATE dipcc ${DIPCC_GLOG_TARGET} Threads::Threads
  )

  add_executable(profile_dipcc_late dipcc/profiling/profile_late.cc ${SOURCES})
  target_link_libraries(
    profile_dipcc_late PRIVATE dipcc ${DIPCC_GLOG_TARGET} Threads::Threads
  )
endif()
