# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0]

First public release. `medmcp-dicom` is the DICOM stack for MedMCP — an MCP server
exposing tools an agent can call to make sense of unorganised clinical DICOM
exports: inventory them, convert them to NIfTI, and organise them into BIDS
datasets.

**Not licensed for clinical use.**

### Added

- `explore_dicom` tool: recursively scans a DICOM directory tree and returns a
  structured inventory grouped by Patient → Study → Series. Reads headers only
  (`stop_before_pixels=True`) for speed. Returns `BodyPartExamined`, modality,
  series/study descriptions, instance count, image dimensions, pixel spacing, and
  slice thickness. PHI is excluded by default (`include_phi=False`).
- `explore_bids` tool: scans a BIDS dataset and returns a structured inventory
  grouped by Subject → Session → Datatype, reading directory structure and file
  sizes only.
- `convert_dcm_to_nifti` tool: converts all DICOM series under a directory to
  compressed NIfTI (`.nii.gz`) with BIDS-compatible JSON sidecars. DWI series
  additionally produce `.bval`/`.bvec` files. Intended for single-study use.
- `build_bids_dataset` tool: converts a full DICOM directory tree into a
  BIDS-organised dataset. Handles multi-patient/multi-study inputs, assigns
  anonymous `sub-XXX`/`ses-XX` labels, classifies series via `SeriesDescription`
  keyword heuristics, and calls `dcm2niix` per series. Writes
  `dataset_description.json`, `participants.tsv`, and `.bidsignore`.
  Non-standard modalities and unclassified series are flagged for review.
- `inspect_nifti` tool: reads a NIfTI header and returns structured metadata —
  shape, voxel size, TR, orientation, dtype, file size, NIfTI version. Read-only;
  no pixel data is loaded.
- `dcm-to-bids` skill (`skills/dcm-to-bids/SKILL.md`): LLM workflow guide for the
  BIDS conversion task — input gathering, confirmation step, and gotchas.
- FastMCP server over stdio with autodiscovery via the `[medmcp.stacks]` entry
  point.
- Container image: `Dockerfile` (`FROM medmcp-base`, stdio MCP server, multi-arch
  amd64 + arm64) + `.dockerignore`; `org.medmcp.stack` label for one-click install
  from the workspace UI; `.devcontainer` for development.
- `NOTICE` crediting the bundled conversion tools (dcm2niix BSD-3-Clause, pydicom
  and nibabel MIT) with licenses and citations, and a matching bundled-tools table
  and "Citation" section in the README. The container image redistributes the
  `dcm2niix` binary, so this is an attribution obligation rather than a courtesy.
- [all-contributors](https://allcontributors.org) setup (`.all-contributorsrc` +
  README section) to credit all contribution types.
- Full CI: ruff lint/format, pyright strict, and pytest on Python 3.12 / 3.13, plus
  multi-arch image builds.
- Shared-file contract with [medmcp-template](https://github.com/medmcp/medmcp-template):
  `scripts/shared-files.txt` lists the files every stack takes from the template,
  `scripts/sync-from-template.sh` pulls them in, and a **Template drift** workflow
  reports when one diverges.
- Internal `tools/_dicom.py` module: `SeriesRecord` dataclass, `scan_series()`, and
  `find_dcm2niix()`, shared across the conversion tools.
