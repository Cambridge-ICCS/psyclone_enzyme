#!/bin/env python3
from __future__ import annotations

"""CLI entrypoint: generate an Enzyme autodiff interface for a Fortran routine.

Takes a Fortran source file, parses its first routine with PSyclone, runs the
three extraction-to-emission pipeline stages (``extract.py`` -> ``rules.py`` ->
``emit.py``), and prints both the extracted argument model and the generated
``interface`` block.

Usage:  python gen_interface.py <source.f90>
"""


import argparse
from pathlib import Path

from psyclone.psyir.frontend.fortran import FortranReader
from psyclone.psyir.nodes import Routine

from psyclone_enzyme.interface_generation.emit import emit
from psyclone_enzyme.interface_generation.extract import extract_signature
from psyclone_enzyme.interface_generation.model import DummyArg
from psyclone_enzyme.interface_generation.rules import build_autodiff_interface

__all__ = []


# NOTE: Useful for debugging
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

def parse_user_input() -> argparse.Namespace:
    """Retrieve command line options."""
    parser = argparse.ArgumentParser(
        description="Generate the Enzyme autodiff interface for a primal routine."
    )
    parser.add_argument(
        "source", type=Path, help="Fortran source file with the primal routine"
    )
    return parser.parse_args()


def main_cli():
    """Driver for command line interface to the `gen_interface` script.

    This function is required for the version that gets installed into the Python
    environment's `bin` subdirectory.
    """
    parsed_args = parse_user_input()
    try:
        source = parsed_args.source.read_text()
    except OSError as exc:
        print(f"Error reading file: {exc}", file=__import__('sys').stderr)
        exit(1)

    reader = FortranReader()
    psyir = reader.psyir_from_source(source)
    routine = psyir.walk(Routine)[0]
    sig = extract_signature(routine)

    # TODO: Take a routine-name argument (walk(Routine)[0] only picks the primal when it
    #       is first in the file), and print just the emitted interface.

    # Run the rest of the pipeline (rules, emit) and then print the interface block
    print("\n".join(emit(build_autodiff_interface(sig))))


if __name__ == "__main__":
    main_cli()
