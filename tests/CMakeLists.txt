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

# Process test files with PSyclone
set(PSYCLONE_PROCESSED_SOURCES)

# Test directories, one per differentiation mode handled by
# psyclone_enzyme. Each holds its own trans_<name>_<interface_type>.py scripts and
# test_<name>_*.f90 inputs.
set(PSYCLONE_TEST_DIRS reverse_mode forward_mode)

# Test names: for each name, every mode directory listed in
# PSYCLONE_TEST_DIRS provides one or more inputs test_<name>_*.f90
# and, for each interface type and activity set, a transformation script
# trans_<name>_<interface_type>_<activity_set>.py.
set(TEST_NAMES square)

# Interface types: implicit (use the enzyme module) or explicit
# (generate a Fortran interface block).
set(TEST_INTERFACE_TYPES implicit explicit)

# Activity descriptor sets: default (no descriptors passed to the hook) or
# descriptors (explicit per-argument activity descriptors such as enzyme_dup).
set(TEST_ACTIVITY_SETS default descriptors)

# For every test_<name>_*.f90 file in <mode_dir>, declare a rule that
# runs PSyclone with <mode_dir>/trans_<name>_<interface_type>_<activity_set>.py
# to produce the processed file under
# ${CMAKE_CURRENT_BINARY_DIR}/<mode_dir>/processed/<interface_type>/<activity_set>/,
# and append it to PSYCLONE_PROCESSED_SOURCES. A macro rather than a function so
# that the APPEND updates the parent-scope list in place.
macro(psyclone_enrol_tests mode_dir name interface_type activity_set)
  set(TRANS_SCRIPT
      "${CMAKE_CURRENT_SOURCE_DIR}/${mode_dir}/trans_${name}_${interface_type}_${activity_set}.py")
  # Skip (mode, name, interface_type, activity_set) combinations that have no
  # trans script.
  if(EXISTS "${TRANS_SCRIPT}")
    file(GLOB PSYCLONE_TEST_SOURCES CONFIGURE_DEPENDS
         "${CMAKE_CURRENT_SOURCE_DIR}/${mode_dir}/test_${name}_*.f90")

    foreach(src IN LISTS PSYCLONE_TEST_SOURCES)
      get_filename_component(fname "${src}" NAME)
      set(out
          "${CMAKE_CURRENT_BINARY_DIR}/${mode_dir}/processed/${interface_type}/${activity_set}/${fname}")
      add_custom_command(
        OUTPUT "${out}"
        COMMAND
          ${CMAKE_COMMAND} -E make_directory
          "${CMAKE_CURRENT_BINARY_DIR}/${mode_dir}/processed/${interface_type}/${activity_set}"
        COMMAND
          # fmt: off
          ${PSYCLONE_EXECUTABLE}
            --keep-comments
            -s "${TRANS_SCRIPT}"
            -o "${out}"
            "${src}"
          # fmt: on
        DEPENDS "${src}" "${TRANS_SCRIPT}"
        COMMENT "PSyclone: ${mode_dir}/${interface_type}/${activity_set}/${fname}"
        VERBATIM)
      list(APPEND PSYCLONE_PROCESSED_SOURCES "${out}")
    endforeach()
  endif()
endmacro()

foreach(mode_dir IN LISTS PSYCLONE_TEST_DIRS)
  foreach(name IN LISTS TEST_NAMES)
    foreach(interface_type IN LISTS TEST_INTERFACE_TYPES)
      foreach(activity_set IN LISTS TEST_ACTIVITY_SETS)
        psyclone_enrol_tests(${mode_dir} ${name} ${interface_type} ${activity_set})
      endforeach()
    endforeach()
  endforeach()
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
