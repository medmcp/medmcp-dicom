# medmcp-dicom

DICOM data discovery, conversion, and BIDS organisation tools for the [medmcp](https://github.com/medmcp) ecosystem. Exposes an **MCP (Model Context Protocol) server** over stdio that an LLM can invoke to help physicians and researchers make sense of unorganised clinical DICOM exports.

> [!WARNING]
> MedMCP and its ecosystem are research software under active development and are **not licensed for clinical use**.

---

## Tool inventory

| Tool name | Description | Inputs | Outputs |
|---|---|---|---|
| `explore_dicom` | Scan a directory tree and return a structured inventory of DICOM data grouped by Patient → Study → Series | `root_dir: Path`, `include_phi: bool = False`, `summary_only: bool = True` | `{"summary": {...}, "patients": [...], "_render": "..."}` |
| `explore_bids` | Scan a BIDS dataset directory and return a structured inventory grouped by Subject → Session → Datatype | `bids_dir: Path`, `summary_only: bool = True` | `{"summary": {...}, "subjects": [...], "_render": "..."}` |
| `convert_dcm_to_nifti` | Convert all DICOM series in a directory to compressed NIfTI (`.nii.gz`) with JSON sidecars. For single-study use; for full datasets use `build_bids_dataset` | `input_dir: Path`, `output_dir: Path` | `{"converted": [...], "total_series": N, "_render": "..."}` |
| `build_bids_dataset` | Convert a DICOM directory tree into a BIDS-organised dataset. Load the `dcm-to-bids` skill before calling | `dicom_root: Path`, `output_dir: Path`, `dataset_name: str \| None = None`, `anonymize: bool = True` | `{"output_dir": "...", "subjects": N, "sessions": N, "files_created": N, ..., "_render": "..."}` |
| `inspect_nifti` | Read a NIfTI file's header and return structured metadata (shape, voxel size, TR, orientation, dtype, file size, NIfTI version). Read-only; no pixel data loaded | `path: Path` | `{"path": "...", "shape": [...], "voxel_size_mm": [...], "tr_sec": float\|null, "n_volumes": int\|null, "dtype": "...", "orientation": "...", "file_size_mb": float, "nifti_version": int, "_render": "..."}` |

## Skill inventory

Skills are SKILL.md files the agent loads on demand to follow multi-step workflows. They are bundled under `src/medmcp_dicom/skills/` and discovered automatically via `server_config()`.

| Skill name | Description |
|---|---|
| `dcm-to-bids` | Step-by-step workflow for converting a DICOM directory tree into a BIDS dataset, including confirmation prompts, anonymisation guidance, and gotchas (unclassified series, DWI sidecars, duplicate runs). |

---

### Bundled tools

`medmcp-dicom` wraps established third-party software, and the container image
redistributes the `dcm2niix` binary. Each is used under its own license:

| Tool | Used by | Source | License |
|---|---|---|---|
| dcm2niix | `convert_dcm_to_nifti`, `build_bids_dataset` | [`dcm2niix`](https://github.com/rordenlab/dcm2niix) package dependency, invoked as a subprocess (baked into the image) | [BSD-3-Clause](https://github.com/rordenlab/dcm2niix/blob/master/license.txt) |
| pydicom | `explore_dicom`, DICOM header reading | [`pydicom`](https://github.com/pydicom/pydicom) package dependency | [MIT](https://github.com/pydicom/pydicom/blob/main/LICENSE) |
| nibabel | `inspect_nifti`, `explore_bids` | [`nibabel`](https://github.com/nipy/nibabel) package dependency | [MIT](https://github.com/nipy/nibabel/blob/master/COPYING) |

No pretrained model weights are bundled or redistributed — this stack runs no models.

### Citation

`dcm2niix` is a third-party scientific tool. **If you use `medmcp-dicom` conversion output in research, please cite it:**

- **dcm2niix** — Li X, Morgan PS, Ashburner J, Smith J, Rorden C. The first step for neuroimaging data analysis: DICOM to NIfTI conversion. *Journal of Neuroscience Methods* 264, 47–56 (2016). [doi:10.1016/j.jneumeth.2016.03.001](https://doi.org/10.1016/j.jneumeth.2016.03.001)

Full third-party attribution is in [`NOTICE`](NOTICE).

### Hardware requirements

CPU-only. `explore_dicom` reads DICOM headers only (no pixel data). `explore_bids` reads only directory structure and file sizes. `convert_dcm_to_nifti` and `build_bids_dataset` call [`dcm2niix`](https://github.com/rordenlab/dcm2niix), which is installed automatically as a package dependency. (The container image derives from the shared CUDA base `medmcp-base` for layer-sharing across the fleet, but this stack performs no GPU computation.)

---

## Development

### Develop in the dev container (recommended)

This repo ships a dev container (`.devcontainer/`) with the full toolchain
(Python 3.12 + uv, `just`, git, Docker CLI). It derives from the shared
`medmcp-base` image, so build that once from the core repo first (`just docker-base`
in a `medmcp` checkout). Then open the repo with the **Dev Container** action in PyCharm
(2024.2+) or **Reopen in Container** in VS Code — `uv sync` runs on first start.
See the core repo's [CONTRIBUTING](https://github.com/medmcp/medmcp/blob/main/CONTRIBUTING.md)
for IDE specifics.

### Local install (alternative)

```bash
just setup     # install uv, sync dev environment, register pre-commit hooks
just check     # lint + format-check + typecheck + tests
just fix       # auto-fix lint and format
```

For local agent use, install the stack into its own uv tool environment:

```bash
uv tool install --editable .
```

The package registers itself via the `[medmcp.stacks]` entry point. The local agent autodiscovers it on the next session — no manual config needed.

### Container image (deployment)

This stack also ships as a container with a fixed environment:

```bash
just docker-build           # build medmcp-dicom:dev (FROM medmcp-base)
```

It is a stdio MCP server (`ENTRYPOINT ["tini", "--", "medmcp-dicom"]`). The medmcp
**core** launches it on demand via a `stacks.d/medmcp-dicom.toml` manifest
(`docker run -i …`), so deployment nodes need no host Python install. The image is
cleanly multi-arch (amd64 + arm64 — all deps, incl. `dcm2niix`, have aarch64
wheels).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: fork, `just setup`, `just check`, open a PR against `main`.

### Contributors

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://jqmcginnis.github.io/"><img src="https://avatars.githubusercontent.com/u/33037028?v=4?s=100" width="100px;" alt="Julian McGinnis"/><br /><sub><b>Julian McGinnis</b></sub></a><br /><a href="https://github.com/medmcp/medmcp-dicom/commits?author=jqmcginnis" title="Code">💻</a> <a href="#infra-jqmcginnis" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://pfriedri.github.io"><img src="https://avatars.githubusercontent.com/u/101359393?v=4?s=100" width="100px;" alt="Paul Friedrich"/><br /><sub><b>Paul Friedrich</b></sub></a><br /><a href="https://github.com/medmcp/medmcp-dicom/commits?author=pfriedri" title="Code">💻</a> <a href="https://github.com/medmcp/medmcp-dicom/commits?author=pfriedri" title="Documentation">📖</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

This project follows the [all-contributors](https://allcontributors.org) specification — contributions of any kind are welcome!

## License

[Apache 2.0](LICENSE). Third-party tools bundled by this stack retain their own licenses and are attributed in [`NOTICE`](NOTICE).
