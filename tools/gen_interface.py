from __future__ import annotations

"""Generate an explicit ``interface`` block for forward or reverse mode differentiation.

This module parses Fortran subroutines and functions using PSyclone's PSyIR, extracts
argument signatures, and provides utilities for synthesising the derivative interface
that Enzyme requires.
"""

import sys
from pathlib import Path

from psyclone.psyir.frontend.fortran import FortranReader
from psyclone.psyir.nodes import Routine

# Put the repo root on the path so ``from tools.emit`` resolves
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.emit import emit
from tools.extract import extract_signature
from tools.rules import build_autodiff_interface


def _format_dummy(arg: DummyArg) -> str:
    """Render one extracted :class:`DummyArg` as an indented block.

    Shows the fields the extraction layer currently populates; the raw
    declaration is included only when PSyclone left the type unsupported
    (so it carries information the structured fields do not). The
    remaining model fields stay at their TODO defaults.
    """
    lines = [
        f"  {arg.name} ({arg.arg_kind}):",
        f"    base_type  = {arg.base_type}",
        f"    rank       = {arg.rank}",
        f"    shape_kind = {arg.shape_kind}",
        f"    intent     = {arg.intent}",
        f"    attributes = {sorted(arg.attributes)}",
        f"    is_active  = {arg.is_active}",
    ]
    if arg.raw_text:
        lines.append(f"    raw_text   = {arg.raw_text!r}")
    return "\n".join(lines)


if __name__ == "__main__":
    test_code = """
    subroutine normalise_value(n, x, y)
    integer, value, intent(in) :: n
    real, dimension(n), intent(in) :: x
    real, dimension(n), intent(out) :: y
    y(:) = x / sum(x)
    end subroutine normalise_value
    """
    reader = FortranReader()
    psyir = reader.psyir_from_source(test_code)
    routine = psyir.walk(Routine)[0]
    sig = extract_signature(routine)

    print(f"{sig.kind} {sig.name}")
    for arg in sig.args:
        print(_format_dummy(arg))
    # checks if function or subroutine
    if sig.return_arg is not None:
        print("  returns:")
        print(_format_dummy(sig.return_arg))

    # run the rest of the pipeline (rules, then emit) and print the block.
    print()
    print("\n".join(emit(build_autodiff_interface(sig))))
