"""Module containing the Enzyme autodiff PSyIR transformation logic.

Provides functions to insert an ``enzyme_autodiff`` call after the first
call to a target procedure in a given routine.  Both the function form

    <y> = <f>(<x1>, <x2>, ...)

and the subroutine form

    call <f>(<arg1>, <arg2>, ...)

are recognised, with arbitrarily many arguments in any order and mixed
intents.
"""

from psyclone.psyir.nodes import Assignment, Call, Literal, Reference, Routine
from psyclone.psyir.symbols import (ArgumentInterface, ContainerSymbol,
                                    DataSymbol, ImportInterface, RoutineSymbol)

__all__ = ["add_enzyme_autodiff"]


def add_enzyme_autodiff(psyir, target_name):
    """Insert an ``enzyme_autodiff`` call after the first call to the
    target procedure in each routine in the PSyIR tree. If the
    `enzyme_autodiff` symbol is not already in scope (e.g. via a
    ``use enzyme`` statement), an import from the ``enzyme`` module is
    added to the routine's symbol table so that a ``use enzyme``
    statement is generated in the output code.

    Both the function form

        <y> = <f>(<x1>, <x2>, ...)

    and the subroutine form

        call <f>(<arg1>, <arg2>, ...)

    are recognised, with arbitrarily many arguments in any order and
    mixed intents.  For subroutines, the intent of each dummy argument
    is inspected to determine which shadows to seed
    (``intent(out)``/``intent(inout)``) and which to zero
    (``intent(in)``).

    :param psyir: root of the PSyIR tree to transform.
    :type psyir: :py:class:`psyclone.psyir.nodes.FileContainer`
    :param target_name: name of the procedure to differentiate.
    :type target_name: str
    """
    for routine in psyir.walk(Routine):

        # Function form: <y> = <f>(<x1>, <x2>, ...).
        for assign in routine.walk(Assignment, stop_type=Assignment):
            rhs = assign.rhs
            if not (isinstance(rhs, Call)
                    and rhs.routine.name == target_name):
                continue
            _transform_function_call(routine, assign, rhs)
            return

        # Subroutine form: call <f>(<arg1>, <arg2>, ...) with mixed intents.
        for call in routine.walk(Call, stop_type=Call):
            if call.parent is not None and isinstance(call.parent, Assignment):
                continue  # Already handled by the loop above.
            if call.routine.name != target_name:
                continue
            _transform_subroutine_call(routine, call)
            return


def _transform_function_call(routine, assign, call):
    """Insert an Enzyme call after an assignment of the form
    ``<y> = <f>(<x1>, <x2>, ...)``.

    A shadow variable ``d<x_i>`` is created for each argument, zeroed,
    then ``enzyme_autodiff`` is called on the primal function with
    interleaved primal and shadow arguments.

    :param routine: the routine containing the call.
    :type routine: :py:class:`psyclone.psyir.nodes.Routine`
    :param assign: the assignment containing the call.
    :type assign: :py:class:`psyclone.psyir.nodes.Assignment`
    :param call: the call to the target function.
    :type call: :py:class:`psyclone.psyir.nodes.Call`
    """
    table = routine.symbol_table
    autodiff = _get_or_import_autodiff(table)
    if autodiff is None:
        return  # Cannot bring enzyme_autodiff into scope - skip.

    func = call.routine.symbol
    args = call.arguments

    # Declare a shadow variable for each argument.
    shadows = []
    for arg in args:
        real_type = arg.symbol.datatype.copy()
        shadow = table.new_symbol(f"d{arg.symbol.name}",
                                  symbol_type=DataSymbol, datatype=real_type)
        shadows.append(shadow)

    # Zero each shadow, then call enzyme_autodiff with interleaved
    # primal/shadow argument pairs (no seed is needed for the output
    # since the procedure is a function, not a subroutine).
    parent = assign.parent
    idx = assign.position
    for i, shadow in enumerate(shadows):
        parent.addchild(Assignment.create(Reference(shadow),
                                          Literal("0.0",
                                                  shadow.datatype)), idx + 1 + i)
    autodiff_args = [Reference(func)]
    for arg, shadow in zip(args, shadows):
        autodiff_args.append(arg.copy())
        autodiff_args.append(Reference(shadow))
    parent.addchild(Call.create(autodiff, autodiff_args), idx + 1 + len(shadows))


def _transform_subroutine_call(routine, call):
    """Insert an Enzyme call after a standalone subroutine call of the form
    ``call <f>(<arg1>, <arg2>, ...)``.

    A shadow variable is created for each argument.  The intent of each
    dummy argument is inspected to determine whether its shadow should
    be seeded (``intent(out)`` or ``intent(inout)``) or zeroed
    (``intent(in)``).  All output shadows are seeded with ``1.0`` and
    all input shadows are zeroed, then ``enzyme_autodiff`` is called on
    the primal subroutine with interleaved primal and shadow arguments.

    Keyword arguments in any order are handled correctly via the
    argument mapping returned by ``Call.get_callee()``.  If the callee
    cannot be resolved (e.g. due to a wildcard import), all arguments
    are conservatively treated as ``intent(inout)`` and seeded.

    :param routine: the routine containing the call.
    :type routine: :py:class:`psyclone.psyir.nodes.Routine`
    :param call: the call to the target subroutine.
    :type call: :py:class:`psyclone.psyir.nodes.Call`
    """
    table = routine.symbol_table
    autodiff = _get_or_import_autodiff(table)
    if autodiff is None:
        return  # Cannot bring enzyme_autodiff into scope - skip.

    func = call.routine.symbol
    args = call.arguments

    # Resolve the callee to inspect dummy argument intents.
    intents = _get_call_arg_intents(call)

    # Declare a shadow variable for each argument, tracking which are
    # outputs (to be seeded) and which are inputs (to be zeroed).
    shadows = []
    is_output = []
    for i, arg in enumerate(args):
        real_type = arg.symbol.datatype.copy()
        shadow = table.new_symbol(f"d{arg.symbol.name}",
                                  symbol_type=DataSymbol, datatype=real_type)
        shadows.append(shadow)
        is_output.append(intents[i] in (ArgumentInterface.Access.WRITE,
                                        ArgumentInterface.Access.READWRITE))

    # Seed each output shadow and zero each input shadow, then call
    # enzyme_autodiff with interleaved primal/shadow argument pairs.
    parent = call.parent
    idx = call.position
    for i, (shadow, output) in enumerate(zip(shadows, is_output)):
        seed = "1.0" if output else "0.0"
        parent.addchild(Assignment.create(Reference(shadow),
                                          Literal(seed,
                                                  shadow.datatype)), idx + 1 + i)
    autodiff_args = [Reference(func)]
    for arg, shadow in zip(args, shadows):
        autodiff_args.append(arg.copy())
        autodiff_args.append(Reference(shadow))
    parent.addchild(Call.create(autodiff, autodiff_args), idx + 1 + len(shadows))


def _get_call_arg_intents(call):
    """Return a list of ``ArgumentInterface.Access`` values, one per
    argument at the call site, indicating the intent of the
    corresponding dummy argument in the callee.

    Uses ``Call.get_callee()`` to resolve the target routine and its
    argument mapping, so keyword arguments in any order are handled
    correctly.  If resolution fails (e.g. the callee is behind a
    wildcard import or defined in a ``CodeBlock``), a conservative
    fallback of ``READWRITE`` is returned for every argument.

    :param call: the call node to inspect.
    :type call: :py:class:`psyclone.psyir.nodes.Call`
    :returns: list of access values, one per call-site argument.
    :rtype: list[:py:class:`psyclone.psyir.symbols.ArgumentInterface.Access`]
    """
    try:
        callee, arg_map = call.get_callee()
        dummy_args = callee.symbol_table.argument_list
        return [dummy_args[arg_map[i]].interface.access
                for i in range(len(call.arguments))]
    except Exception:
        # Conservative fallback: treat every argument as intent(inout).
        return [ArgumentInterface.Access.READWRITE] * len(call.arguments)


def _get_or_import_autodiff(table):
    """Return a RoutineSymbol for `enzyme_autodiff` in the given symbol table.

    Looks up the `enzyme_autodiff` symbol and specialises it to a
    :py:class:`psyclone.psyir.symbols.RoutineSymbol`. If the symbol is not
    already in scope, it is created with an import from the ``enzyme``
    module, resulting in a ``use enzyme, only: enzyme_autodiff`` statement
    being generated in the output code.

    :param table: the symbol table to look up/extend.
    :type table: :py:class:`psyclone.psyir.symbols.SymbolTable`
    """
    try:
        autodiff = table.lookup("enzyme_autodiff")
        autodiff.specialise(RoutineSymbol)
        return autodiff
    except (KeyError, TypeError):
        pass  # Fall through and import the symbol from the enzyme module.
    try:
        enzyme_mod = table.lookup("enzyme")
        if not isinstance(enzyme_mod, ContainerSymbol):
            return None  # Something else named 'enzyme' is in scope.
    except KeyError:
        enzyme_mod = table.new_symbol("enzyme", symbol_type=ContainerSymbol)
    return table.new_symbol("enzyme_autodiff", symbol_type=RoutineSymbol,
                            interface=ImportInterface(enzyme_mod))
