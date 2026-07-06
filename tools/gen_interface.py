from __future__ import annotations

"""Generate an explicit ``interface`` block for forward or reverse mode differentiation.

This module parses Fortran subroutines and functions using PSyclone's PSyIR, extracts
argument signatures, and provides utilities for synthesising the derivative interface
that Enzyme requires.
"""

import argparse
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
    parser = argparse.ArgumentParser(
        description="Generate the Enzyme autodiff interface for a primal routine."
    )
    parser.add_argument(
        "source", type=Path, help="Fortran source file with the primal routine"
    )
    args = parser.parse_args()

    try:
        source = args.source.read_text()
    except OSError as exc:
        parser.error(str(exc))

    reader = FortranReader()
    psyir = reader.psyir_from_source(source)
    # TODO: the CLI is bare minimum. Still to do next: take a routine-name argument
    # (walk(Routine)[0] only picks the primal when it is first in the file), and
    # print just the emitted interface instead of the _format_dummy model dump.
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
