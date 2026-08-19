# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `NOTICE` crediting the bundled conversion tools (dcm2niix BSD-3-Clause, pydicom and
  nibabel MIT) with licenses and citations; README gains a bundled-tools table and a
  "Citation" section. The container image redistributes the `dcm2niix` binary, so this
  is an attribution obligation rather than a courtesy.
- [all-contributors](https://allcontributors.org) setup (`.all-contributorsrc` + README
  section) to credit all contribution types.
- Container image: `Dockerfile` (`FROM medmcp-base`, stdio MCP server, multi-arch) + `.dockerignore`; `org.medmcp.stack` label for one-click install; `.devcontainer`; CI publishes to the private `ghcr.io/medmcp/dicom`.

- `convert_dcm_to_nifti` tool: converts all DICOM series under a directory to
  compressed NIfTI (`.nii.gz`) with BIDS-compatible JSON sidecars. DWI series
  additionally produce `.bval`/`.bvec` files. Intended for single-study use.
- `build_bids_dataset` tool: converts a full DICOM directory tree into a
  BIDS-organised dataset. Handles multi-patient/multi-study inputs, assigns
  anonymous `sub-XXX`/`ses-XX` labels, classifies series via `SeriesDescription`
  keyword heuristics, and calls `dcm2niix` per series. Writes
  `dataset_description.json`, `participants.tsv`, and `.bidsignore`.
  Non-standard modalities and unclassified series are flagged for review.
- `dcm-to-bids` skill (`skills/dcm-to-bids/SKILL.md`): LLM workflow guide for
  the BIDS conversion task — input gathering, confirmation step, and gotchas.
- Internal `tools/_dicom.py` module: `SeriesRecord` dataclass, `scan_series()`,
  and `find_dcm2niix()` shared across the conversion tools.

### Changed

- Tracks the files shared with [medmcp-template](https://github.com/medmcp/medmcp-template):
  `scripts/shared-files.txt` lists them, `scripts/sync-from-template.sh` pulls them in,
  and a **Template drift** workflow reports when one diverges. This first sync picked up
  a CI action bump that had already landed in the template.
- `CONTRIBUTING.md` no longer opens with instructions for creating a package from the
  template — a real stack repo was telling readers to run `scripts/rename.sh`, a script
  it does not have. It now documents the versioning policy and how to credit
  contributors, matching the sibling stacks.
- `CODEOWNERS` removed. It was entirely commented out behind a "replace before the repo
  goes public" note, so it assigned no ownership and requested no reviews.
- References to the core repo use its current name, `medmcp`, not the pre-rename
  `medmcp-dev` — including a link to its contributing guide.
- The README opens the way the sibling stacks do: links to medmcp.ai and the core
  repository, and a note that this repo is for people building or extending the stack
  — using MedMCP needs only the app and a one-click stack install. It also explains the
  shared-file contract, so a contributor whose pull request trips the drift check can
  see what it is and how to resolve it.
- One image build runs per branch at a time; a superseded pull-request push is cancelled
  rather than left racing the push that replaced it.

## [0.1.0] — 2026-04-20

### Added

- `explore_data` tool: recursively scans a DICOM directory tree and returns a
  structured inventory grouped by Patient → Study → Series. Reads headers only
  (`stop_before_pixels=True`) for speed. Returns `BodyPartExamined`, modality,
  series/study descriptions, instance count, image dimensions, pixel spacing,
  and slice thickness. PHI excluded by default (`include_phi=False`).
- FastMCP server over stdio with autodiscovery via `[medmcp.stacks]` entry point.
- Full CI: ruff lint/format, pyright strict, pytest on Python 3.12 / 3.13.
