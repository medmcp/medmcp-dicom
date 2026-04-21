# medmcp-dicom

DICOM data discovery and exploration tools for the [medmcp](https://github.com/medmcp) ecosystem. Exposes an **MCP (Model Context Protocol) server** over stdio that an LLM can invoke to help physicians and researchers make sense of unorganised clinical DICOM exports.

> [!WARNING]
> MedMCP and its ecosystem are research software under active development and are **not licensed for clinical use**.

---

## Tool inventory

| Tool name | Description | Inputs | Outputs |
|---|---|---|---|
| `explore_data` | Scan a directory tree and return a structured inventory of DICOM data grouped by Patient → Study → Series | `root_dir: Path`, `include_phi: bool = False`, `summary_only: bool = True` | `{"summary": {...}, "patients": [...], "_render": "..."}` |

### Model / weights provenance

N/A — no pretrained weights.

### Hardware requirements

CPU-only. Memory usage scales with the number of DICOM files (headers only, no pixel data loaded).

---

## Development

```bash
just setup     # install uv, sync dev environment, register pre-commit hooks
just check     # lint + format-check + typecheck + tests
just fix       # auto-fix lint and format
```

### Install for local agent use

```bash
uv tool install --editable .
```

The package registers itself via the `[medmcp.stacks]` entry point. The local agent autodiscovers it on the next session — no manual config needed.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: fork, `just setup`, `just check`, open a PR against `main`.

## License

[Apache 2.0](LICENSE)
