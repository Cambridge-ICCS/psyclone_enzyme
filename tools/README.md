# Enzyme interface generator (`tools/`)

Tooling that generates explicit Fortran `interface` blocks for routines
differentiated with Enzyme (the `<name>__enzyme_autodiff` hooks). The
generators parse Fortran with [PSyclone](https://psyclone.readthedocs.io)'s
PSyIR frontend, build an intermediate model of the primal signature, apply the
reverse-mode rules, and emit the interface text.

## Layout

A pipeline that parses Fortran to PSyIR, extracts a primal model,
applies the reverse-mode rules to build an interface model, and emits Fortran
text. It is split one module per concern:

- `model.py` — primal IR dataclasses (`DummyArg`, `ProcedureSignature`).
- `extract.py` — a PSyIR `Routine` to the primal model.
- `rules.py` — primal model to interface model (reverse-mode synthesis).
- `interface_model.py` — interface IR dataclasses (`InterfaceArg`,
  `CallbackInterface`, `AutodiffInterface`).
- `emit.py` — interface model to Fortran interface text.
- `gen_interface.py` — the CLI entry point; drives extract, rules, emit. Its
  helpers live at module scope so they can be imported without running the CLI.


## Requirements

Install the pinned dependencies from the repo root:

```sh
python -m venv venv
source venv/bin/activate
pip install -r tools/requirements.txt
```

`PSyclone` is pinned to `3.2.2`. See "Troubleshooting" below for why the latest
release does not work. PSyclone pulls in its own dependencies (`fparser`,
`sympy`, `Jinja2`, `numpy`), so pinning it (plus `fparser`) is enough.

## Running the generator

`gen_interface.py` takes a Fortran source file and prints the generated
interface for the primal routine in it. Run it from the repo root:

```sh
python tools/gen_interface.py examples/norm/fortran/value.f90
```

It prints the extracted model for each dummy argument, followed by the
generated `<primal>__enzyme_autodiff` interface block, for example:

```fortran
interface
  subroutine normalise_value__enzyme_autodiff(sr, n, x, dx, y, dy)
    interface
      subroutine sr_normalise_value(n, x, y)
        integer, value, intent(in) :: n
        real, dimension(n), intent(in) :: x
        real, dimension(n), intent(out) :: y
      end subroutine
    end interface
    procedure(sr_normalise_value) :: sr
    integer, value, intent(in) :: n
    real, dimension(n), intent(in) :: x
    real, dimension(n), intent(out) :: dx
    real, dimension(n), intent(out) :: y
    real, dimension(n), intent(inout) :: dy
  end subroutine
end interface
```

The CLI is bare minimum: it always picks the first routine in the file and also
prints the intermediate model dump above the interface block. Selecting a
routine by name and printing only the interface are still TODO (see
`gen_interface.py`).

## Troubleshooting

**`AttributeError: 'ArrayType' object has no attribute 'datatype'`**

`pip install psyclone`
pulls the latest release, and `3.3.0` renamed the PSyIR element-type property
from `ArrayType.datatype` to `ArrayType.elemental_type`. `extract.py`
reads `dtype.datatype` (in `get_base_type`), so it fails
under `3.3.0`.

Fix: install the pinned version.

```sh
pip install -r tools/requirements.txt   # PSyclone==3.2.2
```

