# Tool reference

Load this file when you need parameter details for a specific tool.
The MCP server exposes these tools; their names and schemas are also
discoverable at runtime via the MCP `tools/list` call.

---

## add_numbers

Add two numbers and return the result. Placeholder — replace with real domain tools.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `a` | `float` | First operand |
| `b` | `float` | Second operand |

**Returns** `{"result": float}`

---

## process_image *(not yet implemented)*

Skeleton for a real image-processing tool. Raises `NotImplementedError` until
implemented by a downstream package.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `input_path` | `Path` | Absolute path to the input NIfTI or DICOM file |
| `output_dir` | `Path` | Workspace directory — all outputs must be written here |

**Returns** `{"output_path": str}` — absolute path to the result file
