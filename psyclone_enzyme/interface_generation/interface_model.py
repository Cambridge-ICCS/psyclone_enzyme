"""Interface IR: the data model for a generated Enzyme autodiff interface.

Dataclasses describing the emitted ``<primal>__enzyme_autodiff`` interface
block (:class:`InterfaceArg`, :class:`CallbackInterface`,
:class:`AutodiffInterface`) that ``rules.py`` builds and ``emit.py`` renders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from psyclone_enzyme.interface_generation.model import Intent, ProcedureKind

__all__ = []

InterfaceArgRole = Literal["primal", "shadow", "descriptor"]


@dataclass(frozen=True)
class InterfaceArg:
    """One dummy-argument declaration in a generated interface, such as
    ``real, dimension(n), intent(out) :: dx``.

    Holds the declaration pieces for emit to assemble. ``role`` marks it as a
    primal copy, a shadow, or an activity descriptor.
    """

    role: InterfaceArgRole
    name: str
    type_spec: str  # e.g. "real", "integer(c_int)"
    shape: str | None  # e.g. "dimension(n)", or None for a scalar
    intent: Intent
    attributes: frozenset[str]


@dataclass(frozen=True)
class CallbackInterface:
    """The nested interface describing the callback procedure's signature.

    Mirrors the primal routine. ``result_type`` is the function result type
    (e.g. ``"real"``) for a function primal, or ``None`` for a subroutine.
    """

    name: str
    kind: ProcedureKind
    args: tuple[InterfaceArg, ...]
    result_type: str | None


@dataclass(frozen=True)
class AutodiffInterface:
    """The generated ``<primal>__enzyme_autodiff`` interface.

    For the value.f90 primal it represents this output:

        subroutine normalise_value__enzyme_autodiff(sr, n, x, dx, y, dy) ! name
          interface
            subroutine sr_value_decal(n, xx, yy)   ! callback_interface
              ...
            end subroutine
          end interface
          procedure(sr_value_decal) :: sr          ! callback_name ("sr")
          integer, value, intent(in) :: n          ! args: one InterfaceArg
          real, dimension(n), intent(in) :: x      !   per declaration line
          real, dimension(n), intent(out) :: dx    !   (primal copies, shadows,
          real, dimension(n), intent(out) :: y     !   and descriptors)
          real, dimension(n), intent(inout) :: dy
        end subroutine

    ``kind`` is ``"subroutine"`` (reverse mode). ``needs_iso_c_binding`` adds
    ``use iso_c_binding, only: c_int`` when descriptors are present (none here).
    """

    name: str
    kind: ProcedureKind
    callback_name: str
    callback_interface: CallbackInterface
    args: tuple[InterfaceArg, ...]
    needs_iso_c_binding: bool
