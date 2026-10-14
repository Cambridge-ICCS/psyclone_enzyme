"""Module for querying intents of Fortran subroutines."""

__all__ = []


def _get_call_arg_intents(call):
    """Query the intents of the argument list associted with a call.

    Return a list of ``ArgumentInterface.Access`` values, one per argument at the call
    site, indicating the intent of the corresponding dummy argument in the callee.

    Uses ``Call.get_callee()`` to resolve the target routine and its argument mapping,
    so keyword arguments in any order are handled correctly.  If resolution fails (e.g.
    the callee is behind a wildcard import or defined in a ``CodeBlock``), a
    conservative fallback of ``READWRITE`` is returned for every argument.

    :param call: the call node to inspect.
    :type call: :py:class:`psyclone.psyir.nodes.Call`
    :returns: list of access values, one per call-site argument.
    :rtype: list[:py:class:`psyclone.psyir.symbols.ArgumentInterface.Access`]
    """
    try:
        callee, arg_map = call.get_callee()
        dummy_args = callee.symbol_table.argument_list
        return [
            dummy_args[arg_map[i]].interface.access for i in range(len(call.arguments))
        ]
    except Exception:
        # Conservative fallback: treat every argument as intent(inout).
        return [ArgumentInterface.Access.READWRITE] * len(call.arguments)
