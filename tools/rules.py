"""Rules: primal IR -> interface IR (reverse-mode synthesis).

Stage 2 of the pipeline: the Enzyme reverse-mode rule set. Turns a
:class:`~tools.model.ProcedureSignature` into an
:class:`~tools.interface_model.AutodiffInterface` by naming the hook and
callback, expanding each primal arg into a primal copy (plus a shadow for
active args), and mirroring the primal in the nested callback interface.
"""

from __future__ import annotations

from tools.interface_model import (
    AutodiffInterface,
    CallbackInterface,
    InterfaceArg,
)
from tools.model import (
    DummyArg,
    Intent,
    ProcedureKind,
    ProcedureSignature,
)


def hook_name(primal_name: str) -> str:
    """Return the Enzyme reverse-mode hook name for a primal routine.

    ``normalise_value`` becomes ``normalise_value__enzyme_autodiff``.
    """
    return f"{primal_name}__enzyme_autodiff"


def callback_name(primal_kind: ProcedureKind) -> str:
    """Return prefix based on primal's type.

    ``"sr"`` for a subroutine primal, ``"fn"`` for a function.
    """
    return "fn" if primal_kind == "function" else "sr"


def callback_interface_name(primal_name: str, primal_kind: ProcedureKind) -> str:
    """Return the nested callback-interface name as ``{sr|fn}_<primal_name>``.

    ``normalise_value`` (subroutine) gives ``sr_normalise_value`` and
    ``square`` (function) gives ``fn_square``.
    """
    return f"{callback_name(primal_kind)}_{primal_name}"


def shadow_name(arg_name: str) -> str:
    """Return the reverse-mode shadow (derivative) argument name: ``d<name>``.

    ``x`` becomes ``dx`` and ``y`` becomes ``dy``.
    """
    return f"d{arg_name}"


def reverse_mode_shadow_intent(procedure_kind: ProcedureKind, primal_intent: Intent) -> Intent:
    """Map a primal argument's intent to its reverse-mode shadow intent.

    The mapping depends on the procedure kind (verified against the reverse
    goldens). A subroutine input produces a derivative output (in to out); a
    subroutine output must be seeded and is then incremented (out to inout). A
    function is mapped to "inout" for now.
    """
    if procedure_kind == "function":
        return "inout"
    return {
        "in": "out",
        "out": "inout",
        "inout": "inout",
        "unknown": "inout",
    }[primal_intent]


def primal_interface_arg(dummy: DummyArg) -> InterfaceArg:
    """Build the `InterfaceArg`, mapped from the primals `DummyArg`.

    The hook re-declares each primal argument unchanged (same type, shape,
    intent and attributes such as ``value``), so the call matches the primal 
    ABI exactly. The raw text fields populated during extraction map straight 
    into the `InterfaceArg.
    """
    return InterfaceArg(
        role="primal",
        name=dummy.name,
        type_spec=dummy.type_spec_raw,
        shape=dummy.shape_raw,
        intent=dummy.intent,
        attributes=dummy.attributes,
    )


def shadow_interface_arg(dummy: DummyArg, procedure_kind: ProcedureKind) -> InterfaceArg:
    """Build the shadow (derivative) :class:`InterfaceArg` for an active primal arg.

    Mirrors the primal's type and shape but renames it (``x`` to ``dx`` via
    :func:`shadow_name`), remaps the intent for reverse mode (via
    :func:`reverse_mode_shadow_intent`). It does not create a shadow for pass-by-value
    arguments.
    """
    return InterfaceArg(
        role="shadow",
        name=shadow_name(dummy.name),
        type_spec=dummy.type_spec_raw,
        shape=dummy.shape_raw,
        intent=reverse_mode_shadow_intent(procedure_kind, dummy.intent),
        attributes=dummy.attributes - {"value"},
    )


def build_callback_interface(signature: ProcedureSignature) -> CallbackInterface:
    """Build the :class:`CallbackInterface` mirroring the primal signature.

    The nested callback interface re-declares the primal exactly.
    """
    args = tuple(primal_interface_arg(arg) for arg in signature.args)
    result_type = (
        # if there's a return arg, use its type string; otherwise None.
        signature.return_arg.type_spec_raw if signature.return_arg else None
    )
    return CallbackInterface(
        name=callback_interface_name(signature.name, signature.kind),
        kind=signature.kind,
        args=args,
        result_type=result_type,
    )


def expand_primal_arg(dummy: DummyArg, procedure_kind: ProcedureKind) -> tuple[InterfaceArg, ...]:
    """Expand one primal arg into primal arg and shadow arg.

    Every arg contributes its primal copy; an active arg additionally
    contributes a shadow immediately after it (``x`` to ``x, dx``). Inactive
    args (such as the ``value`` size ``n``) contribute only the primal copy.
    """
    args = [primal_interface_arg(dummy)]
    if dummy.is_active:
        args.append(shadow_interface_arg(dummy, procedure_kind))
    return tuple(args)


def build_autodiff_interface(signature: ProcedureSignature) -> AutodiffInterface:
    """Build the reverse-mode :class:`AutodiffInterface` for a primal.

    The interface body is every primal arg expanded inorder (primal copy, plus 
    a shadow for active args), and it carries the nested callback interface.
    """
    body = tuple(
        arg
        for dummy in signature.args
        for arg in expand_primal_arg(dummy, signature.kind)
    )
    return AutodiffInterface(
        name=hook_name(signature.name),
        kind="subroutine",
        callback_name=callback_name(signature.kind),
        callback_interface=build_callback_interface(signature),
        args=body,
        needs_iso_c_binding=False,
    )
