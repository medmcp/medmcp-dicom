# medmcp-template

Scaffolding template for packages in the [medmcp](https://github.com/medmcp) ecosystem — foundations (e.g. `medmcp-dicom`), stacks (e.g. `medmcp-neuro`), and supporting tools.

Each package built from this template is a **distributable Python package** that exposes an **MCP (Model Context Protocol) server** over stdio. An LLM (e.g. a local Gemma4 instance) invokes the registered tools by name to perform medical image processing tasks.

Click **Use this template** on GitHub to scaffold a new package.

> [!WARNING]
> MedMCP and its ecosystem are research software under active development and are **not licensed for clinical use**.

---

## Tool inventory

<!-- Replace this table after scaffolding. One row per registered MCP tool. -->

| Tool name | Description | Inputs | Outputs |
|---|---|---|---|
| `add_numbers` | Placeholder — adds two floats | `a: float`, `b: float` | `{"result": float}` |

### Model / weights provenance

<!-- Document any pretrained weights used by your tools:
- Model name and version
- Source URL and checksum
- License
- How weights are downloaded / cached at runtime
-->

N/A — placeholder package, no pretrained weights.

### Hardware requirements

<!-- Document GPU/CPU/RAM requirements per tool, e.g.:
- `brain_extract`: CUDA GPU recommended (≥8 GB VRAM), CPU fallback available (~3× slower)
- `register`: CPU-only, ≥16 GB RAM for typical T1w volumes
-->

N/A — placeholder package.

---

## What's in the box

| Area | Files | Notes |
|---|---|---|
| Build / deps | `pyproject.toml`, `.python-version` | uv-managed, Python ≥3.12, `mcp>=1.0` |
| MCP server | `src/medmcp_template/server.py` | FastMCP over stdio; `server_config()` enables autodiscovery; add tools here |
| Tool scaffold | `src/medmcp_template/tools/example.py` | One file per tool group |
| AgentSkill | `skills/medmcp-template/SKILL.md` | Workflow guidance the LLM reads at activation |
| Tool reference | `skills/medmcp-template/references/TOOLS.md` | Loaded on demand; keep in sync with server.py |
| Dev workflow | `justfile`, `.pre-commit-config.yaml` | `just setup`, `just check`, `just fix` |
| CI | `.github/workflows/ci.yml` | Lint, format-check, pyright (strict), pytest on py3.12 / 3.13 |
| Contributor docs | `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` | |
| Issue management | `.github/ISSUE_TEMPLATE/*`, `PULL_REQUEST_TEMPLATE.md` | Medical-context-aware with PHI warnings |

---

## Using this template

### 1. Scaffold a new repo

Click **Use this template → Create a new repository** on GitHub, then clone locally.

### 2. Rename the placeholder package

```bash
./scripts/rename.sh medmcp-dicom
rm scripts/rename.sh
```

### 3. Update metadata

Edit `pyproject.toml`: set `description`, `keywords`, `authors`, and the `Homepage`/`Issues` URLs.

Confirm that `server_config()` in `server.py` returns the correct `name` and `command` — these must match the renamed console script so the local agent resolves the right binary during autodiscovery.

### 4. Implement your tools

- Add tool functions to `src/<your_package>/tools/`.
- Register them in `src/<your_package>/server.py` with `mcp.add_tool(your_tool)`.
- FastMCP derives the MCP `name`, `description`, and `inputSchema` from the function signature and docstring — write precise docstrings, the LLM reads them.

### 5. Update the AgentSkill

- Edit `skills/<your_package>/SKILL.md` — replace the placeholder description and workflow with domain-specific guidance (what the LLM should do, in what order, and what gotchas to watch for).
- Keep `skills/<your_package>/references/TOOLS.md` in sync with your registered tools.

### 6. Install and activate

Install the package as a uv tool — the local agent autodiscovers it on the next session:

```bash
uv tool install ./medmcp-dicom          # local dev
# or
uv tool install medmcp-dicom            # from PyPI once published
```

The package declares itself via the `[medmcp.stacks]` entry point (written to `entry_points.txt` at install time). The agent scans all uv tool environments for this section, calls `server_config()` to retrieve the server name and command, and resolves the absolute binary path — no manual edits to `.vibe/config.toml` needed.

The AgentSkill in `skills/<your_package>/` is picked up by the agent alongside the MCP server — no separate install step needed.

### 7. Verify

```bash
just setup && just check
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: fork, `just setup`, `just check`, open a PR against `main`.

## License

[Apache 2.0](LICENSE)
