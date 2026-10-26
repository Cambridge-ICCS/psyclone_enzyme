# CMake build system for the psyclone_enzyme Python package's lit test suite.
#
# This project does not build any compiled artefacts itself; the CMake project
# exists purely to run PSyclone over the Fortran tests under ``tests/`` and to
# drive LLVM's ``lit`` test runner against them, mimicking the build/test
# infrastructure used by Enzyme itself.

cmake_minimum_required(VERSION 3.20)
# NOTE: C needed for LLVMConfig.cmake's internal checks
project(psyclone_enzyme LANGUAGES C Fortran)

# Locate the same LLVM installation that Enzyme was built against. Required
# so that we can find LLVM's CMake helpers (e.g. ``configure_lit_site_cfg``,
# ``add_lit_testsuite``) and the LLVM tools (``opt``, ``FileCheck``, ...).
find_package(LLVM REQUIRED CONFIG)
message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}: ${LLVM_DIR}")

list(APPEND CMAKE_MODULE_PATH "${LLVM_CMAKE_DIR}")
include(AddLLVM)

# Locate the Enzyme build tree so that the tests can reference the Enzyme
# LLVM/flang plugins and the Fortran enzyme module directory. Either point
# this at the build directory directly (the directory containing
# ``Enzyme/LLVMEnzyme-<ver>.so`` etc.) or at a standard Enzyme install prefix.
set(Enzyme_BINARY_DIR "" CACHE PATH "Path to the Enzyme build directory")
if(NOT Enzyme_BINARY_DIR)
  message(FATAL_ERROR "Enzyme_BINARY_DIR must be set to the Enzyme build directory")
endif()

# Locate the ``psyclone`` driver used to pre-process each Fortran test.
find_program(PSYCLONE_EXECUTABLE NAMES psyclone REQUIRED)
message(STATUS "Found psyclone: ${PSYCLONE_EXECUTABLE}")

# Locate the ``lit`` test runner. AddLLVM's helpers expect this in the form
# of the LLVM_EXTERNAL_LIT cache FILEPATH; we always override it from the
# environment, picking up whatever 'lit' is on PATH (typically the one in
# the active Python virtualenv).
find_program(PSYCLONE_ENZYME_LIT_EXECUTABLE NAMES llvm-lit lit REQUIRED)
set(LLVM_EXTERNAL_LIT "${PSYCLONE_ENZYME_LIT_EXECUTABLE}"
    CACHE FILEPATH "Path to the lit test runner" FORCE)
message(STATUS "Found lit: ${LLVM_EXTERNAL_LIT}")

enable_testing()
add_subdirectory(tests)
