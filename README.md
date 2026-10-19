# Python modules supporting working with PSyclone and Enzyme

The `psyclone_enzyme` Python package provides PSyIR transformations that
prepare Fortran source for automatic differentiation with Enzyme, in
particular inserting calls to `enzyme_autodiff` after calls to a target
procedure.

## Tests

The `tests/` directory contains a lit-driven Fortran test suite, mirroring
the layout used by Enzyme's `test/Fortran` suite. The tests are not
compiled directly; instead, each `*.f90` file under `tests/<subdir>/` is a
PSyclone input, and CMake runs PSyclone over them at build time to produce
processed Fortran files under `build/tests/<subdir>/processed/`, which are
then fed to `flang` and `opt` with the Enzyme plugins via lit.

The `CHECK:` lines are preserved by PSyclone's `--keep-comments` only at the
top of each source file (prior to the first module/program), so the CHECK
directives there assert the expected program output of the processed code.

### Building and running the tests

The test suite is driven by a small CMake project at the top of this
repository, which configures PSyclone pre-processing rules and registers a
lit testsuite. Prerequisites:

- a Python virtualenv with `psyclone` and `lit` installed and activated,
- `LLVM_DIR` pointing at an LLVM CMake package config (an activated spack
  environment that provides LLVM will typically set this via
  `CMAKE_PREFIX_PATH`), and
- an Enzyme build tree to test against, supplied via the `Enzyme_BINARY_DIR`
  CMake variable (there is no default; CMake will error out if it is unset).

Configure and build in the usual CMake way:

```sh
cmake -G Ninja -S . -B build \
  -DCMAKE_Fortran_COMPILER=flang \
  -DLLVM_DIR="${LLVM_DIR}" \
  -DEnzyme_BINARY_DIR=/path/to/enzyme/build/flang
cmake --build build --target check-psyclone-enzyme
```

The build step runs PSyclone over each `tests/<subdir>/*.f90` file to
produce processed Fortran under `build/tests/<subdir>/processed/`, and the
`check-psyclone-enzyme` target then runs `lit` against them. The suite is
also registered with CTest, so `ctest` from the build directory works too.

To run individual tests or get more verbose output, invoke `lit` directly
on the build directory:

```sh
lit -v build/tests
```
