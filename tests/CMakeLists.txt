# Tests driven by PSyclone and lit.
#
# Each ``.f90`` file under a test subdirectory is a PSyclone input. At build
# time PSyclone is invoked with the appropriate transformation script to
# produce a processed Fortran file in
# ``${CMAKE_CURRENT_BINARY_DIR}/<subdir>/processed/<file>.f90``.
# Lit is then pointed at those processed files, which carry the original
# ``! RUN:`` / ``! CHECK``-style comments through thanks to PSyclone's
# ``--keep-comments`` flag.
#
# The use of LLVM's ``configure_lit_site_cfg`` and ``add_lit_testsuite``
# helpers below mirrors the pattern used by enzyme/test/CMakeLists.txt in
# the Enzyme project (https://github.com/EnzymeAD/Enzyme), which is licensed
# under the Apache License v2.0 with LLVM Exceptions.

# These variables are referenced by lit.site.cfg.py.in.
set(PSYCLONE_ENZYME_Fortran_COMPILER "${CMAKE_Fortran_COMPILER}")
set(PSYCLONE_ENZYME_ENZYME_BINARY_DIR "${Enzyme_BINARY_DIR}")
set(PSYCLONE_ENZYME_LLVM_TOOLS_DIR "${LLVM_TOOLS_BINARY_DIR}")
set(PSYCLONE_ENZYME_LLVM_VERSION_MAJOR "${LLVM_VERSION_MAJOR}")
set(PSYCLONE_ENZYME_LLVM_SHLIBEXT "${LLVM_PLUGIN_EXT}")

configure_lit_site_cfg(
  ${CMAKE_CURRENT_SOURCE_DIR}/lit.site.cfg.py.in
  ${CMAKE_CURRENT_BINARY_DIR}/lit.site.cfg.py MAIN_CONFIG
  ${CMAKE_CURRENT_SOURCE_DIR}/lit.cfg.py)

# PSyclone-transformation script used for every test in reverse_mode/.
set(REVERSE_MODE_TRANS_SCRIPT
    ${CMAKE_CURRENT_SOURCE_DIR}/reverse_mode/trans_square.py)

# Find PSyclone inputs and declare rules to produce their processed forms.
set(PSYCLONE_TEST_DIR reverse_mode)
file(GLOB PSYCLONE_TEST_SOURCES CONFIGURE_DEPENDS
     "${CMAKE_CURRENT_SOURCE_DIR}/${PSYCLONE_TEST_DIR}/*.f90")

set(PSYCLONE_PROCESSED_SOURCES)
foreach(src IN LISTS PSYCLONE_TEST_SOURCES)
  get_filename_component(fname "${src}" NAME)
  set(out "${CMAKE_CURRENT_BINARY_DIR}/${PSYCLONE_TEST_DIR}/processed/${fname}")
  add_custom_command(
    OUTPUT "${out}"
    COMMAND
      ${CMAKE_COMMAND} -E make_directory
      "${CMAKE_CURRENT_BINARY_DIR}/${PSYCLONE_TEST_DIR}/processed"
    COMMAND
      # fmt: off
      ${PSYCLONE_EXECUTABLE}
        --keep-comments
        -s "${REVERSE_MODE_TRANS_SCRIPT}"
        -o "${out}"
        "${src}"
      # fmt: on
    DEPENDS "${src}" "${REVERSE_MODE_TRANS_SCRIPT}"
    COMMENT "PSyclone: ${PSYCLONE_TEST_DIR}/${fname}"
    VERBATIM)
  list(APPEND PSYCLONE_PROCESSED_SOURCES "${out}")
endforeach()

# Build target that produces all the processed Fortran files. The lit target
# below depends on this so that sources are always up-to-date before the
# tests run.
add_custom_target(
  psyclone-enrol-tests
  ALL
  DEPENDS ${PSYCLONE_PROCESSED_SOURCES})

# Run the lit testsuite. Mirrors how Enzyme's test subdirectories declare
# their check-* targets.
add_lit_testsuite(
  check-psyclone-enzyme
  "Running PSyclone-Enzyme integration tests"
  ${CMAKE_CURRENT_BINARY_DIR}
  DEPENDS
  psyclone-enrol-tests
  ARGS
  -v)
set_target_properties(check-psyclone-enzyme PROPERTIES FOLDER "Tests")

# Also register with CTest so ``ctest`` picks the suite up from the build
# directory. (add_lit_testsuite only creates a build target.)
add_test(
  NAME psyclone-enzyme-lit
  COMMAND ${LLVM_EXTERNAL_LIT} -sv ${CMAKE_CURRENT_BINARY_DIR})
set_tests_properties(
  psyclone-enzyme-lit
  PROPERTIES DEPENDS psyclone-enrol-tests)
