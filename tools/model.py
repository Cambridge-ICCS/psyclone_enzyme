"""Primal IR: the data model for a parsed primal procedure.

Dataclasses and enums (:class:`DummyArg`,
:class:`ProcedureSignature`) that ``extract.py`` populates from PSyIR and
``rules.py`` consumes. No PSyclone or Fortran-rendering concerns live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
