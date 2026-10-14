#!/bin/bash
# For each test file, run PSyclone to insert Enzyme syntax. Then run tests.

# TODO: Make this a CMakeLists.txt

FFLAGS="-I/home/joe/projects/fortran_enzyme/enzyme/build/flang/modules --config=/home/joe/projects/fortran_enzyme/enzyme/build/flang/Enzyme/FlangEnzyme-21.cfg"

TEST_FILES="test_square_function.f90"

mkdir -p processed
for FILE in "${TEST_FILES}"; do
  psyclone --keep-comments -s trans_square.py ${FILE} >"processed/${FILE}"
done

# TODO: Use lit for testing
cd processed
for FILE in "${TEST_FILES}"; do
  flang -O0 ${FFLAGS} ${FILE} && ./a.out && rm a.out *.mod
  flang -O2 ${FFLAGS} ${FILE} && ./a.out && rm a.out *.mod
done
cd ..
# rm -rf processed
