"""Module containing the transformation function for tests``test_square_*.f90``."""
from psyclone_enzyme import add_enzyme_function_hook


def trans(psyir):
    """Entry point called by PSyclone with the root PSyIR node.

    Applies the Enzyme fwddiff transformation to the ``square`` procedure
    in every routine found in the PSyIR tree, passing explicit activity
    descriptors for each argument.

    :param psyir: root of the PSyIR tree to transform.
    :type psyir: :py:class:`psyclone.psyir.nodes.FileContainer`
    """
    add_enzyme_function_hook(
        psyir,
        "square",
        reverse=False,
        activity_descriptors={"x": "enzyme_dup", "y": "enzyme_dup"},
    )
