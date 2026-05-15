from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from psyclone.psyir.backend.fortran import FortranWriter
from psyclone.psyir.frontend.fortran import FortranReader
from psyclone.psyir.nodes import Routine
from psyclone.psyir.symbols import ArgumentInterface, DataSymbol
from psyclone.psyir.symbols.datatypes import UnsupportedFortranType

Access = ArgumentInterface.Access

BaseType = Literal["real", "complex", "integer", "logical", "character", "derived"]
ShapeKind = Literal[
    "scalar", "explicit", "assumed_shape", "assumed_rank", "deferred", "assumed_size"
]
Intent = Literal["in", "out", "inout", "unknown"]
ProcedureKind = Literal["subroutine", "function"]


@dataclass(frozen=True)
class DummyArg:
    """Internal model for one dummy argument."""

    name: str
    base_type: BaseType
    kind: str | None
    rank: int
    shape_kind: ShapeKind
    intent: Intent
    attributes: frozenset[str]
    derived_type_name: str | None
    raw_text: str | None
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