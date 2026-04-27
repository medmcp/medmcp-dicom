# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

## [0.1.0] — 2026-04-20

### Added

- `explore_data` tool: recursively scans a DICOM directory tree and returns a
  structured inventory grouped by Patient → Study → Series. Reads headers only
  (`stop_before_pixels=True`) for speed. Returns `BodyPartExamined`, modality,
  series/study descriptions, instance count, image dimensions, pixel spacing,
  and slice thickness. PHI excluded by default (`include_phi=False`).
- FastMCP server over stdio with autodiscovery via `[medmcp.stacks]` entry point.
- Full CI: ruff lint/format, pyright strict, pytest on Python 3.12 / 3.13.
