"""Extract: PSyIR routine -> primal IR (:class:`~tools.model.ProcedureSignature`).

Stage 1 of the pipeline. Walks a PSyIR ``Routine``'s argument list and builds a
:class:`~tools.model.ProcedureSignature`, recovering type, intent, shape and
attribute information from structured PSyIR where available, and otherwise from
the raw declaration text for the ``UnsupportedFortranType`` cases (``value``,
``complex``, ...). The raw-declaration parsers (``_split_top_level_commas`` and
friends) support that text fallback.
"""

from __future__ import annotations

from psyclone.psyir.backend.fortran import FortranWriter
from psyclone.psyir.nodes import Routine
from psyclone.psyir.symbols import (
    ArgumentInterface,
    ArrayType,
    ScalarType,
    Symbol,
)
from psyclone.psyir.symbols.datatypes import (
    DataType,
    UnsupportedFortranType,
)

from tools.model import (
    BaseType,
    DummyArg,
    Intent,
    ProcedureSignature,
    ShapeKind,
)

Access = ArgumentInterface.Access

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

# Attribute keywords a data dummy argument may carry.
# intent(...), dimension(...) and codimension[...] have dedicated fields
# (intent, rank/shape_kind, coarray) so are excluded. bind(c) is excluded because a data dummy
# argument cannot carry it (a BIND(C) variable must be a module variable or common block).
ATTRIBUTE_KEYWORDS = frozenset(
    {
        "value",
        "optional",
        "pointer",
        "allocatable",
        "target",
        "contiguous",
        "asynchronous",
        "volatile",
    }
)


def get_intent(sym: Symbol) -> Intent:
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


def unwrap_unsupported(dtype: DataType) -> tuple[DataType, str | None]:
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


def get_base_type(sym: Symbol) -> BaseType:
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


def _split_top_level_commas(text: str) -> list[str]:
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


def _decl_prefix(declaration: str) -> str:
    """Return a declaration's attribute/type prefix (the text before ``::``).

    For ``"integer, value, intent(in) :: n"`` this returns
    ``"integer, value, intent(in)"``. A declaration with no ``::`` is
    returned whole (stripped). Case is preserved -- callers lowercase
    when matching.
    """
    return declaration.split("::", 1)[0].strip()


def _base_type_from_prefix(prefix: str) -> BaseType:
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


def _type_spec_raw_from_prefix(prefix: str) -> str:
    """Return the leading type token of a declaration prefix, lowercased.

    This type token is kept whole so a kind or length selector stays attached
    e.g. (``real(kind=8)``, ``character(len=*)``) remains intact.

    """
    return _split_top_level_commas(prefix)[0].strip().lower()


def _intent_from_prefix(prefix: str) -> Intent:
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


def _attributes_from_prefix(prefix: str) -> frozenset[str]:
    """Collect recognised attribute keywords (e.g. ``value``) from a prefix.

    Tokens that carry arguments, such as ``intent(...)`` and ``dimension(...)``,
    never match the keywords, so they are naturally excluded. Matching is
    case-insensitive; the result is an unordered ``frozenset``.
    """
    tokens = {token.strip().lower() for token in _split_top_level_commas(prefix)}
    return frozenset(tokens & ATTRIBUTE_KEYWORDS)


def _shape_raw_from_prefix(prefix: str) -> str | None:
    """Return the ``dimension(...)`` token from a declaration prefix, or ``None``.

    The token is returned with its original case and spacing preserved (emit
    reuses it verbatim). The comma split is parenthesis-aware, so a multi-rank
    ``dimension(n,3)`` stays intact. A scalar prefix has no such token and
    yields ``None``.
    """
    for token in _split_top_level_commas(prefix):
        token = token.strip()
        if token.lower().startswith("dimension"):
            return token
    return None


# ---------------------------------------------------------------------------
# Extraction: PSyIR symbols -> model
# ---------------------------------------------------------------------------


def _writer_prefix(sym: Symbol, writer: FortranWriter) -> str:
    """Render ``sym``'s declaration and return its prefix (text before ``::``).

    ``writer.gen_vardecl`` reconstructs a declaration for any symbol, e.g
    (``real, dimension(n), intent(in) :: x``)
    """
    return _decl_prefix(writer.gen_vardecl(sym))


def _rank_and_shape(sym: Symbol) -> tuple[int | None, ShapeKind | None]:
    """Return ``(rank, shape_kind)`` for a symbol.

    Explicit-shape and multi-rank arrays carry an ``ArrayBounds`` per
    dimension. Assumed-shape dummies (``dimension(:)``) use
    ``Extent.ATTRIBUTE``; deferred allocatable/pointer arrays use
    ``Extent.DEFERRED``. Assumed-size (``dimension(*)``) is not modelled by
    PSyclone, arriving as an ``UnsupportedFortranType``; it is reported as
    ``(None, None)`` rather than mislabelled scalar. (Assumed-rank
    ``dimension(..)`` does not reach here: fparser fails to parse it.)
    """
    dtype, raw_decl = unwrap_unsupported(sym.datatype)

    if isinstance(dtype, ArrayType):
        rank = len(dtype.shape)
        if any(dim is ArrayType.Extent.DEFERRED for dim in dtype.shape):
            return rank, "deferred"
        if any(dim is ArrayType.Extent.ATTRIBUTE for dim in dtype.shape):
            return rank, "assumed_shape"
        return rank, "explicit"

    if raw_decl and "dimension(" in _decl_prefix(raw_decl).lower():
        return None, None  # an array PSyclone could not resolve

    return 0, "scalar"


def _dummy_from_symbol(sym: Symbol, writer: FortranWriter) -> DummyArg:
    """Build a :class:`DummyArg` from a PSyIR data symbol.

    Populates the fields resolved so far: ``name``, ``base_type``,
    ``intent``, ``attributes``, ``is_active`` and the raw declaration text.
    The remaining fields (kind, rank/shape, derived-type and coarray
    details) stay at their defaults until their extractors are added.
    """
    _, raw_decl = unwrap_unsupported(sym.datatype)
    prefix = _writer_prefix(sym, writer)
    base_type = get_base_type(sym)
    rank, shape_kind = _rank_and_shape(sym)
    # Attributes that matter (value, pointer, target, optional, contiguous)
    # force the declaration to UnsupportedFortranType, so they are present in
    # raw_decl; a fully supported symbol has none. (allocatable arrays stay
    # supported, so that attribute is not captured here)
    attributes = (
        _attributes_from_prefix(_decl_prefix(raw_decl)) if raw_decl else frozenset()
    )
    return DummyArg(
        name=sym.name,
        arg_kind="data",  # TODO: detect procedure dummies
        base_type=base_type,
        type_spec_raw=_type_spec_raw_from_prefix(prefix),
        kind=None,  # TODO
        char_len=None,  # TODO
        derived_type_name=None,  # TODO
        derived_type_params=None,
        is_polymorphic=False,
        is_unlimited_polymorphic=False,
        is_assumed_type=False,
        rank=rank,
        shape_kind=shape_kind,
        shape_raw=_shape_raw_from_prefix(prefix),
        is_coarray=False,
        corank=None,
        coshape_raw=None,
        intent=get_intent(sym),
        attributes=attributes,
        raw_text=raw_decl,
        unsupported_reason=None,
        is_active=base_type in ("real", "complex"),
    )


def extract_signature(routine: Routine) -> ProcedureSignature:
    """Build a :class:`ProcedureSignature` from a PSyIR ``Routine``.

    Maps :func:`_dummy_from_symbol` over the argument list and records the
    procedure kind (``function`` when the routine has a result symbol,
    otherwise ``subroutine``).
    """
    writer = FortranWriter()
    return_symbol = getattr(routine, "return_symbol", None)
    kind = "function" if return_symbol is not None else "subroutine"
    args = tuple(
        _dummy_from_symbol(sym, writer) for sym in routine.symbol_table.argument_list
    )
    return_arg = (
        _dummy_from_symbol(return_symbol, writer) if return_symbol is not None else None
    )
    return ProcedureSignature(
        name=routine.name,
        kind=kind,
        args=args,
        return_arg=return_arg,
        bind_c=False,  # false as bind prime use is for activity descriptors
        elemental=False,
        pure=False,
        module=None,  # TODO: _module_name
        uses=(),  # TODO: collect use statements
    )
