"""Example tool — replace with real domain tools after scaffolding.

Each function in this module that is registered in server.py becomes an
LLM-invokable MCP tool. FastMCP derives the tool name, description, and
JSON-schema inputSchema from the function signature and docstring, so:

  - Use precise, unambiguous docstrings — the LLM reads these to plan calls.
  - Type-annotate every parameter and the return type.
  - Return a plain dict; values must be JSON-serialisable.
  - Confine all filesystem writes to the ``output_dir`` argument.
"""

from pathlib import Path


def add_numbers(a: float, b: float) -> dict[str, float]:
    """Add two numbers and return the result.

    Placeholder tool demonstrating the minimal tool signature. Replace with
    a real domain operation (e.g. skull stripping, registration, segmentation).

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        A dict with key ``result`` containing the sum.
    """
    return {"result": a + b}


def process_image(input_path: Path, output_dir: Path) -> dict[str, str]:
    """Skeleton for a real image-processing tool.

    Args:
        input_path: Absolute path to the input file (NIfTI or DICOM).
        output_dir: Workspace directory where all outputs must be written.
            Writing outside this directory is not permitted.

    Returns:
        A dict with ``output_path`` pointing to the result file.

    Raises:
        NotImplementedError: Until implemented by a real downstream package.
    """
    raise NotImplementedError
