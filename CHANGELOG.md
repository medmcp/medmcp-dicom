# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-04-20

### Added

- `explore_data` tool: recursively scans a DICOM directory tree and returns a
  structured inventory grouped by Patient → Study → Series. Reads headers only
  (`stop_before_pixels=True`) for speed. Returns `BodyPartExamined`, modality,
  series/study descriptions, instance count, image dimensions, pixel spacing,
  and slice thickness. PHI excluded by default (`include_phi=False`).
- FastMCP server over stdio with autodiscovery via `[medmcp.stacks]` entry point.
- SKILL.md and TOOLS.md for LLM workflow guidance and tool reference.
- Full CI: ruff lint/format, pyright strict, pytest on Python 3.12 / 3.13.
