# -*- Python -*-
# Configuration file for the 'lit' test runner.
#
# Portions adapted from enzyme/test/lit.cfg.py in the Enzyme project
# (https://github.com/EnzymeAD/Enzyme), which is licensed under the Apache
# License v2.0 with LLVM Exceptions.

import os
import platform

import lit
import lit.formats

# name: The name of this test suite.
config.name = 'PSyclone-Enzyme'

# testFormat: The test format to use to interpret tests.
LLVM_VERSION_MAJOR = lit.__versioninfo__[0]
execute_external = platform.system() != 'Windows'
if LLVM_VERSION_MAJOR >= 23:
    config.test_format = lit.formats.ShTest(execute_external, force_execute_external=True)
else:
    config.test_format = lit.formats.ShTest(execute_external)

# suffixes: file extensions to treat as test files.
config.suffixes = ['.f90']

# test_source_root: the location of the processed test sources. Those live in
# the per-suite 'processed/' subdirs of the CMake build tree: PSyclone copies
# the source comments (including the ! RUN lines) into them, and they are the
# files that are actually fed to the Fortran compiler under test.
config.test_source_root = config.psyclone_enzyme_test_root

# test_exec_root: where tests should be run.
config.test_exec_root = os.path.join(config.psyclone_enzyme_test_root, '.lit')

# Tweak PATH to include the LLVM tools dir.
base_paths = [config.llvm_tools_dir, config.environment['PATH']]
config.environment['PATH'] = os.path.pathsep.join(base_paths)
config.environment['LD_LIBRARY_PATH'] = os.path.pathsep.join(
    (config.llvm_libs_dir, config.environment.get('LD_LIBRARY_PATH', '')))

# --- Substitutions used by the ! RUN lines -----------------------------

config.substitutions.append(('%shlibext', config.llvm_shlib_ext))
config.substitutions.append(('%llvmver', config.llvm_ver))
config.substitutions.append(
    ('%FileCheck', os.path.join(config.llvm_tools_dir, 'FileCheck')))
config.substitutions.append(
    ('%opt', os.path.join(config.llvm_tools_dir, 'opt')))
config.substitutions.append(('%fc', config.fc))

# Load the LLVM-side Enzyme plugin into opt, using the new pass-manager
# interface where appropriate. Mirrors the %loadEnzyme substitution in the
# Enzyme tests' lit.site.cfg.py.in.
llvmenzyme = os.path.join(
    config.enzyme_obj_root, 'Enzyme',
    f'LLVMEnzyme-{config.llvm_ver}{config.llvm_shlib_ext}')
new_pm = (' -load-pass-plugin=' + llvmenzyme
          + ' -load=' + llvmenzyme
          + (' --enzyme-attributor=0' if int(config.llvm_ver) >= 13 else ''))
old_pm = (' -load=' + llvmenzyme
          + (' --enzyme-attributor=0' if int(config.llvm_ver) >= 13 else ''))
config.substitutions.append(
    ('%loadEnzyme', old_pm if int(config.llvm_ver) < 16 else new_pm))
config.substitutions.append(
    ('%enzyme', ('-enzyme' if int(config.llvm_ver) < 16 else '-passes="enzyme"')))

# The Fortan module include dir produced by an Enzyme build with
# ENZYME_FORTRAN=ON: contains enzyme.mod etc.
config.substitutions.append(
    ('%loadFortran', '-I' + os.path.join(config.enzyme_obj_root, 'modules')))

# FlangEnzyme plugin: lets flang run Enzyme itself rather than piping IR to
# opt. Mirrors the %loadFlangEnzyme substitution in the Enzyme tests'
# lit.site.cfg.py.in.
flangenzyme = os.path.join(
    config.enzyme_obj_root, 'Enzyme',
    f'FlangEnzyme-{config.llvm_ver}{config.llvm_shlib_ext}')
config.substitutions.append(
    ('%loadFlangEnzyme',
     ' -fpass-plugin=' + flangenzyme
     + ' -Xflang -load -Xflang ' + flangenzyme))

# --- Available features -------------------------------------------------

# The Fortran tests require a fairly recent LLVM/Flang stack.
if int(config.llvm_ver) >= 13:
    config.available_features.add('fortran')

# Only advertise the flangenzyme feature if the relevant plugin actually
# exists and the compiler in use is flang.
import shutil
if (os.path.basename(config.fc).startswith('flang')
        and os.path.exists(flangenzyme)):
    config.available_features.add('flangenzyme')
