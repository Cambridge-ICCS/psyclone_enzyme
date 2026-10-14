"""Module containing logic for importing from the ``enzyme`` Fortran module."""

from psyclone.psyir.symbols import ContainerSymbol, ImportInterface, RoutineSymbol

__all__ = []


def _get_or_import_routine(table, routine):
    """Return a RoutineSymbol in the given symbol table.

    Looks up the symbol specified by the ``routine`` argument and specialises it to a
    :py:class:`psyclone.psyir.symbols.RoutineSymbol`. If the symbol is not already in
    scope, it is created with an import from the ``enzyme`` module, resulting in a
    ``use enzyme, only:`` statement being generated in the output code.

    :param table: the symbol table to look up/extend.
    :type table: :py:class:`psyclone.psyir.symbols.SymbolTable`
    :param routine: the name of the routine to return
    :type routine: str
    :return: the symbol for the imported routine
    :rtype: :py:class:`psyclone.psyir.symbols.RoutineTable`
    """
    try:
        autodiff = table.lookup(routine)
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
    return table.new_symbol(routine, symbol_type=RoutineSymbol,
                            interface=ImportInterface(enzyme_mod))
