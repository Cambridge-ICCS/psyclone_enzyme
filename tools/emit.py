"""Emit: render the interface IR to Fortran interface-block text.

Stage 4 of the pipeline: formatting. The renderers are duck-typed over the
interface IR (``InterfaceArg``, ``CallbackInterface``, ``AutodiffInterface``):
they only read attributes.

Nested blocks are returned at column 0 with their own internal two-space
indentation; the parent renderer prefixes the leading indent when it nests a
child block.
"""

from __future__ import annotations

from tools.interface_model import AutodiffInterface, CallbackInterface, InterfaceArg

INDENT = "  "


def render_declaration(arg: InterfaceArg) -> str:
    """Render one :class:`InterfaceArg` as a Fortran declaration line.

    Assembles the pieces in canonical order: type spec, shape, then any
    attributes (sorted for determinism), with ``intent`` last, matching the
    goldens (``integer, value, intent(in) :: n``, ``real, dimension(n),
    intent(out) :: dx``). An ``"unknown"`` intent is omitted, since
    ``intent(unknown)`` is not valid Fortran.
    """
    parts = [arg.type_spec]
    if arg.shape:
        parts.append(arg.shape)
    parts.extend(sorted(arg.attributes))
    if arg.intent in ("in", "out", "inout"):
        parts.append(f"intent({arg.intent})")
    return f"{', '.join(parts)} :: {arg.name}"


def render_callback_interface(callback: CallbackInterface) -> list[str]:
    """Render a :class:`CallbackInterface` as a list of Fortran lines.

    Returns the nested ``interface ... end interface`` block at column 0 with
    its own internal two-space indentation (subroutine under interface,
    declarations under subroutine). The parent renderer prefixes the leading
    indent to nest the block. A function primal renders a
    ``<result_type> function`` header, a subroutine a ``subroutine`` header.
    """
    names = ", ".join(arg.name for arg in callback.args)
    if callback.kind == "function":
        header = f"{callback.result_type} function {callback.name}({names})"
        footer = "end function"
    else:
        header = f"subroutine {callback.name}({names})"
        footer = "end subroutine"

    lines = ["interface", INDENT + header]
    for arg in callback.args:
        lines.append(2 * INDENT + render_declaration(arg))
    lines.append(INDENT + footer)
    lines.append("end interface")
    return lines


def emit(autodiff: AutodiffInterface) -> list[str]:
    """Render an :class:`AutodiffInterface` as the full Fortran interface block.

    Returns a list of lines at column 0 (the caller joins with newlines). The
    body, at two indents, holds: an optional ``use iso_c_binding`` line (when
    descriptors are present), the nested callback interface (reindented to body
    level), the ``procedure(...) :: <callback>`` line, then one declaration per
    body arg. The hook header lists the callback name followed by the body args
    (``sr, n, x, dx, y, dy``).
    """
    # the nested callback block, used both to render the interface and to name
    # the procedure declaration below.
    callback_interface = autodiff.callback_interface
    body_indent = 2 * INDENT
    # hook argument list: the callback dummy first, then every body arg
    # (e.g. "sr, n, x, dx, y, dy").
    names = ", ".join(
        [autodiff.callback_name] + [arg.name for arg in autodiff.args]
    )

    # "interface" at column 0, then the hook header one indent in
    # ("  subroutine <hook>(...)"). autodiff.kind is always "subroutine" here.
    lines = ["interface", INDENT + f"{autodiff.kind} {autodiff.name}({names})"]
    # descriptors need the c_int kind; emitted only when they are present
    if autodiff.needs_iso_c_binding:
        lines.append(body_indent + "use iso_c_binding, only: c_int")

    lines.extend(
        body_indent + line
        for line in render_callback_interface(callback_interface)
    )
    # bind the callback dummy to its interface: "procedure(<iface>) :: <dummy>".
    lines.append(
        body_indent
        + f"procedure({callback_interface.name}) :: {autodiff.callback_name}"
    )
    # one declaration line per body arg (primal copies interleaved with shadows).
    for arg in autodiff.args:
        lines.append(body_indent + render_declaration(arg))

    lines.append(INDENT + f"end {autodiff.kind}")
    lines.append("end interface")
    return lines
