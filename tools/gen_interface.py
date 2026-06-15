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

    Non-argument symbols (locals, a function's result symbol, imported
    symbols) are not ``ArgumentInterface`` and have no intent, so they
    fall back to ``"unknown"``. ``VALUE`` arguments arrive as an
    ``UnsupportedFortranType`` with ``Access.UNKNOWN``, so when the
    structured access is unknown we recover the intent from the raw
    declaration text.
    """
    if not isinstance(sym.interface, ArgumentInterface):
        return "unknown"

    mapped = {
        Access.READ: "in",
        Access.WRITE: "out",
        Access.READWRITE: "inout",
        Access.UNKNOWN: "unknown",
    }[sym.interface.access]

    if mapped != "unknown":
        return mapped

    _, raw_decl = unwrap_unsupported(sym.datatype)
    if raw_decl:
        return _intent_from_prefix(_decl_prefix(raw_decl))
    return "unknown"


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
        return _base_type_from_prefix(_decl_prefix(raw_decl))

    return "unknown"


def _split_top_level_commas(text):
    """Split ``text`` on commas that are not nested inside parentheses.

    Used to break a declaration prefix into its type/attribute tokens
    without splitting inside ``dimension(...)``, ``intent(...)``, kind
    selectors, etc.
    """
    parts = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def _decl_prefix(declaration):
    """Return a declaration's attribute/type prefix (the text before ``::``).

    For ``"integer, value, intent(in) :: n"`` this returns
    ``"integer, value, intent(in)"``. A declaration with no ``::`` is
    returned whole (stripped). Case is preserved -- callers lowercase
    when matching.
    """
    return declaration.split("::", 1)[0].strip()


# The five intrinsic *type classes* (BaseType) are real, complex, integer,
# logical, character. "double precision" is the real
# type with a double-precision kind, so it maps to "real" below.
INTRINSIC_TYPES = (
    "double precision",
    "real",
    "complex",
    "integer",
    "logical",
    "character",
)


def _base_type_from_prefix(prefix):
    """Classify the leading type token of a declaration prefix as a ``BaseType``.

    Matching is case-insensitive. ``double precision`` maps to ``"real"``;
    legacy ``complex*16`` and kind-qualified ``real(kind=8)`` match by their
    leading word. Derived types (``type(...)``) and polymorphic ``class(...)``
    are recognised. Anything else -- including ``procedure(...)`` dummies,
    which are handled separately -- falls back to ``"unknown"``.
    """
    first = _split_top_level_commas(prefix)[0].strip().lower()
    if first.startswith("type"):
        return "derived"
    if first.startswith("class"):
        return "class"
    for name in INTRINSIC_TYPES:
        if first.startswith(name):
            return "real" if name == "double precision" else name
    return "unknown"


def _intent_from_prefix(prefix):
    """Recover an ``Intent`` from an ``intent(...)`` token in the prefix.

    Matching is case-insensitive and tolerant of spaces (``intent ( in )``).
    Returns ``"unknown"`` when no ``intent(...)`` token is present.
    """
    for token in _split_top_level_commas(prefix):
        token = token.strip().lower()
        if token.startswith("intent"):
            inner = token[token.find("(") + 1 : token.rfind(")")].strip()
            if inner in ("in", "out", "inout"):
                return inner
    return "unknown"


# ---------------------------------------------------------------------------
# Extraction: PSyIR symbols -> model
# ---------------------------------------------------------------------------


def _dummy_from_symbol(sym):
    """Build a :class:`DummyArg` from a PSyIR data symbol.

    Populates the fields resolved so far -- ``name``, ``base_type``,
    ``intent``, ``is_active`` and the raw declaration text. The remaining
    fields (kind, rank/shape, attributes, derived-type and coarray details)
    stay at their defaults until their extractors are added.
    """
    _, raw_decl = unwrap_unsupported(sym.datatype)
    base_type = get_base_type(sym)
    return DummyArg(
        name=sym.name,
        arg_kind="data",  # TODO: detect procedure dummies
        base_type=base_type,
        type_spec_raw=None,  # TODO: gen_vardecl prefix (needed for emit)
        kind=None,  # TODO
        char_len=None,  # TODO
        derived_type_name=None,  # TODO
        derived_type_params=None,
        is_polymorphic=False,
        is_unlimited_polymorphic=False,
        is_assumed_type=False,
        rank=None,  # TODO: _rank_and_shape
        shape_kind=None,  # TODO: _rank_and_shape
        shape_raw=None,
        is_coarray=False,
        corank=None,
        coshape_raw=None,
        intent=get_intent(sym),
        attributes=frozenset(),  # TODO: _attributes_from_prefix
        raw_text=raw_decl,
        unsupported_reason=None,
        is_active=base_type in ("real", "complex"),
    )


def extract_signature(routine):
    """Build a :class:`ProcedureSignature` from a PSyIR ``Routine``.

    Maps :func:`_dummy_from_symbol` over the argument list and records the
    procedure kind (``function`` when the routine has a result symbol,
    otherwise ``subroutine``).
    """
    return_symbol = getattr(routine, "return_symbol", None)
    kind = "function" if return_symbol is not None else "subroutine"
    args = tuple(
        _dummy_from_symbol(sym) for sym in routine.symbol_table.argument_list
    )
    return_arg = (
        _dummy_from_symbol(return_symbol) if return_symbol is not None else None
    )
    return ProcedureSignature(
        name=routine.name,
        kind=kind,
        args=args,
        return_arg=return_arg,
        bind_c=False, # false as bind prime use is for activity descriptors
        elemental=False,
        pure=False,
        module=None,  # TODO: _module_name
        uses=(),  # TODO: collect use statements
    )


SOURCE = """
subroutine normalise_value(n, x, y)
  integer, value, intent(in) :: n
  real, dimension(n), intent(in) :: x
  real, dimension(n), intent(out) :: y
  y(:) = x / sum(x)
end subroutine normalise_value
"""


if __name__ == "__main__":
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
