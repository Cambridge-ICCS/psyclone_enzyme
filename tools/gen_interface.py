from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from psyclone.psyir.backend.fortran import FortranWriter
from psyclone.psyir.frontend.fortran import FortranReader
from psyclone.psyir.nodes import Routine
from psyclone.psyir.symbols import ArgumentInterface, DataSymbol, ArrayType, ScalarType
from psyclone.psyir.symbols.datatypes import UnsupportedFortranType

Access = ArgumentInterface.Access

BaseType = Literal[
    "real",
    "complex",
    "integer",
    "logical",
    "character",
    "derived",
    "class",
    "assumed_type",
    "procedure",
    "unknown",
]

ShapeKind = Literal[
    "scalar",
    "explicit",
    "assumed_shape",
    "assumed_rank",
    "deferred",
    "assumed_size",
]
Intent = Literal["in", "out", "inout", "unknown"]
ProcedureKind = Literal["subroutine", "function"]
ArgKind = Literal["data", "procedure"]


@dataclass(frozen=True)
class DummyArg:
    """Internal model for one dummy argument."""

    name: str

    # data vs callback/procedure dummy
    arg_kind: ArgKind

    # type information
    base_type: BaseType
    type_spec_raw: str | None
    kind: str | None
    char_len: str | None

    # derived/class/type(*) information
    derived_type_name: str | None
    derived_type_params: str | None
    is_polymorphic: bool
    is_unlimited_polymorphic: bool
    is_assumed_type: bool

    # array/coarray information
    rank: int | None
    shape_kind: ShapeKind | None
    shape_raw: str | None
    is_coarray: bool
    corank: int | None
    coshape_raw: str | None

    # dummy argument attributes
    intent: Intent
    attributes: frozenset[str]

    # source preservation / fallback
    raw_text: str | None
    unsupported_reason: str | None

    # Enzyme-specific classification
    is_active: bool


@dataclass(frozen=True)
class ProcedureSignature:
    """Internal model for a primal procedure signature."""

    name: str
    kind: ProcedureKind
    args: tuple[DummyArg, ...]
    return_arg: DummyArg | None
    bind_c: bool
    elemental: bool
    pure: bool
    module: str | None
    uses: tuple[str, ...]

def get_intent(sym):
    """Map a symbol's argument access onto an ``Intent`` string.

    Non-argument symbols (e.g. locals) have no intent, so they fall
    back to ``"unknown"``.
    """
    if not isinstance(sym.interface, ArgumentInterface):
        return "unknown"

    return {
        Access.READ: "in",
        Access.WRITE: "out",
        Access.READWRITE: "inout",
        Access.UNKNOWN: "unknown",
    }[sym.interface.access]


def describe_type(sym):
    """Summarise a symbol's type as a flat dict.

    Reports the element base type, whether it is an array, its rank,
    and any raw declaration text recovered from an unsupported type.
    """
    dtype, raw_decl = unwrap_unsupported(sym.datatype)

    is_array = isinstance(dtype, ArrayType)
    rank = len(dtype.shape) if is_array else 0

    return {
        "name": sym.name,
        "is_array": is_array,
        "rank": rank,
        "base_type": get_base_type(sym),
        "raw_text": raw_decl,
    }

def unwrap_unsupported(dtype):
    """Split an ``UnsupportedFortranType`` into its partial datatype.

    Returns the underlying datatype (the partial datatype when one is
    available, otherwise the input unchanged) alongside the original
    raw declaration string, or ``None`` if the type was already
    supported.
    """
    raw_decl = None

    if isinstance(dtype, UnsupportedFortranType):
        raw_decl = dtype.declaration
        if dtype.partial_datatype is not None:
            dtype = dtype.partial_datatype

    return dtype, raw_decl


def get_base_type(sym):
    """Resolve a symbol's intrinsic element type to a ``BaseType``.

    Looks through array types to the element type, then maps the
    scalar intrinsic onto a ``BaseType`` string. Falls back to the
    raw declaration (unimplemented) or ``"unknown"``.
    """
    dtype, raw_decl = unwrap_unsupported(sym.datatype)

    if isinstance(dtype, ArrayType):
        elem_type = dtype.datatype
    else:
        elem_type = dtype

    if isinstance(elem_type, ScalarType):
        mapping = {
            ScalarType.Intrinsic.REAL: "real",
            ScalarType.Intrinsic.INTEGER: "integer",
            ScalarType.Intrinsic.BOOLEAN: "logical",
            ScalarType.Intrinsic.CHARACTER: "character",
        }

        return mapping.get(elem_type.intrinsic, "unknown")

    if raw_decl:
        return "Fallback for raw text is to be implemented"

    return "unknown"


SOURCE = """
subroutine normalise_value(n, x, y)
  integer, value, intent(in) :: n
  real, dimension(n), intent(in) :: x
  real, dimension(n), intent(out) :: y
  y(:) = x / sum(x)
end subroutine normalise_value
"""


reader = FortranReader()
psyir = reader.psyir_from_source(SOURCE)

routine = psyir.walk(Routine)[0]

print("Routine:", routine.name)
print("Arguments:")

for sym in routine.symbol_table.argument_list:
    print("  ", sym.name, sym.datatype, sym.interface)
    dtype = sym.datatype
    if isinstance(dtype, UnsupportedFortranType):
        print("There is a Unsupported datatype:", dtype)
        if dtype.partial_datatype:
                dtype = dtype.partial_datatype
                print("Partial datatype:", dtype)


for sym in routine.symbol_table.argument_list:
    print(sym.name, get_intent(sym))

for sym in routine.symbol_table.argument_list:
    print(describe_type(sym))
