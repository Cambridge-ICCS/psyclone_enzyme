"""Module containing the Enzyme function hook PSyIR transformation logic.

Provides functions to insert a function hook call after the first call to a target
procedure in a given routine.  Both the function form

    <y> = <f>(<x1>, <x2>, ...)

and the subroutine form

    call <f>(<arg1>, <arg2>, ...)

are recognised, with arbitrarily many arguments.
"""

from psyclone.psyir.nodes import Assignment, Call, Literal, Reference, Routine
from psyclone.psyir.symbols import (
    ArgumentInterface,
    ContainerSymbol,
    DataSymbol,
    ImportInterface,
    RoutineSymbol
)

from psyclone_enzyme.imports import _get_or_import_routine
from psyclone_enzyme.intents import _get_call_arg_intents

__all__ = ["add_enzyme_function_hook"]


def add_enzyme_function_hook(psyir, target_name, reverse=True):
    """Insert a function hook call after the first call to the target procedure in each
    routine in the PSyIR tree.

    If the function hook symbol is not already in scope (e.g. via a ``use enzyme``
    statement), an import from the ``enzyme`` module is added to the routine's symbol
    table so that a ``use enzyme`` statement is generated in the output code.

    Both the function form

        <y> = <f>(<x1>, <x2>, ...)

    and the subroutine form

        call <f>(<arg1>, <arg2>, ...)

    are recognised, with arbitrarily many arguments. For subroutines, the intent of each
    argument is inspected to determine which shadows to seed (``intent(out)`` or
    ``intent(inout)``) and which to zero (``intent(in)``).

    :param psyir: root of the PSyIR tree to transform.
    :type psyir: :py:class:`psyclone.psyir.nodes.FileContainer`
    :param target_name: name of the procedure to differentiate.
    :type target_name: str
    :param reverse: use `enzyme_autodiff` hook if True else `enzyme_fwddiff`
    :type reverse: bool
    """
    for routine in psyir.walk(Routine):

        # Function form: <y> = <f>(<x1>, <x2>, ...).
        for assign in routine.walk(Assignment, stop_type=Assignment):
            rhs = assign.rhs
            if not (isinstance(rhs, Call) and rhs.routine.name == target_name):
                continue
            if not reverse:
                raise NotImplementedError(
                    "Forward mode not yet implemented for functions because an"
                    " additional return value would be required"
                )
            _transform_function_call(routine, assign, rhs)
            return

        # Subroutine form: call <f>(<arg1>, <arg2>, ...) with mixed intents.
        for call in routine.walk(Call, stop_type=Call):
            if call.parent is not None and isinstance(call.parent, Assignment):
                continue  # Already handled by the loop above.
            if call.routine.name != target_name:
                continue
            _transform_subroutine_call(routine, call, reverse)
            return


def _transform_function_call(routine, assign, call):
    """Insert an Enzyme call after a function assignment.

    Given the form ``<y> = <f>(<x1>, <x2>, ...)``, a shadow variable ``d<xi>`` is
    created for each argument and is zeroed. Then the specified function hook is called
    on the primal function with interleaved primal and shadow arguments.

    In the case of functions, it only makes sense to use `enzyme_autodiff`, so reverse
    mode is assumed.

    :param routine: the routine containing the call.
    :type routine: :py:class:`psyclone.psyir.nodes.Routine`
    :param assign: the assignment containing the call.
    :type assign: :py:class:`psyclone.psyir.nodes.Assignment`
    :param call: the call to the target function.
    :type call: :py:class:`psyclone.psyir.nodes.Call`
    """
    table = routine.symbol_table
    args = call.arguments

    # Declare a shadow variable for each argument.
    shadows = [
        table.new_symbol(
            f"d{arg.symbol.name}",
            symbol_type=DataSymbol,
            datatype=arg.symbol.datatype.copy()
        )
        for arg in args
    ]

    # Zero each shadow
    parent = assign.parent
    idx = assign.position
    for i, shadow in enumerate(shadows):
        parent.addchild(
            Assignment.create(Reference(shadow), Literal("0.0", shadow.datatype)),
            idx + 1 + i
        )

    # Call function hook with interleaved primal/shadow argument pairs
    # No seed is needed for the output since the procedure is a function, not a
    # subroutine.
    func = call.routine.symbol
    hook_name = "enzyme_autodiff"
    hook_args = [Reference(func)]
    for arg, shadow in zip(args, shadows):
        hook_args.append(arg.copy())
        hook_args.append(Reference(shadow))
    hook = _get_or_import_routine(table, hook_name)
    parent.addchild(Call.create(hook, hook_args), idx + 1 + len(shadows))


def _transform_subroutine_call(routine, call, reverse=True):
    """Insert an Enzyme call after a standalone subroutine call.

    Given the form ``call <f>(<arg1>, <arg2>, ...)``, a shadow variable is created for
    each argument. The intent of each argument is inspected to determine whether its
    shadow should be seeded (``intent(out)`` or ``intent(inout)``) or zeroed
    (``intent(in)``). All output shadows are seeded with ``1.0`` and all input shadows
    are zeroed. Then the specified function hook is called on the primal subroutine with
    interleaved primal and shadow arguments.

    Keyword arguments in any order are handled correctly via the argument mapping
    returned by ``Call.get_callee()``. If the callee cannot be resolved (e.g. due to a
    wildcard import), all arguments are conservatively treated as ``intent(inout)`` and
    seeded.

    :param routine: the routine containing the call.
    :type routine: :py:class:`psyclone.psyir.nodes.Routine`
    :param call: the call to the target subroutine.
    :type call: :py:class:`psyclone.psyir.nodes.Call`
    :param reverse: use `enzyme_autodiff` hook if True else `enzyme_fwddiff`
    :type reverse: bool
    """
    table = routine.symbol_table
    args = call.arguments

    # Resolve the callee to inspect dummy argument intents.
    intents = _get_call_arg_intents(call)

    # Declare a shadow variable for each argument, tracking which are outputs (to be
    # seeded) and which are inputs (to be zeroed).
    shadows = []
    is_output = []
    output_types = (ArgumentInterface.Access.WRITE, ArgumentInterface.Access.READWRITE)
    for i, arg in enumerate(args):
        shadow = table.new_symbol(
            f"d{arg.symbol.name}",
            symbol_type=DataSymbol,
            datatype=arg.symbol.datatype.copy()
        )
        shadows.append(shadow)
        is_output.append(intents[i] in output_types)

    # Seed each output shadow and zero each input shadow
    parent = call.parent
    idx = call.position
    for i, (shadow, output) in enumerate(zip(shadows, is_output)):
        seed = "1.0" if (output == reverse) else "0.0"
        parent.addchild(
            Assignment.create(Reference(shadow), Literal(seed, shadow.datatype)),
            idx + int(reverse) + i
        )

    # Call function hook with interleaved primal/shadow argument pairs.
    func = call.routine.symbol
    hook_name = "enzyme_autodiff" if reverse else "enzyme_fwddiff"
    hook_args = [Reference(func)]
    for arg, shadow in zip(args, shadows):
        hook_args.append(arg.copy())
        hook_args.append(Reference(shadow))
    hook = _get_or_import_routine(table, hook_name)
    parent.addchild(Call.create(hook, hook_args), idx + 1 + len(shadows))
