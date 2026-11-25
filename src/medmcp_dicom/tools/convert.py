"""DICOM to NIfTI conversion tool."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from medmcp_dicom.tools._dicom import find_dcm2niix

_INSTALL_HINT = (
    "dcm2niix is not installed. Install it via:\n"
    "  Ubuntu/Debian: sudo apt install dcm2niix\n"
    "  macOS:         brew install dcm2niix\n"
    "  Conda:         conda install -c conda-forge dcm2niix\n"
    "  Direct:        https://github.com/rordenlab/dcm2niix/releases"
)


def dcm2niix_messages(stdout: str, stderr: str, limit: int = 20) -> list[str]:
    """dcm2niix's ``Warning:`` and ``Error:`` lines, de-duplicated, at most *limit*."""
    out: list[str] = []
    for line in (stdout + "\n" + stderr).splitlines():
        text = line.strip()
        if text.lower().startswith(("warning:", "error:")) and text not in out:
            out.append(text)
    return out[:limit]


def _snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    """``name -> (mtime_ns, size)`` of every NIfTI in *folder* (not recursive)."""
    out: dict[str, tuple[int, int]] = {}
    if folder.is_dir():
        for f in folder.glob("*.nii.gz"):
            st = f.stat()
            out[f.name] = (st.st_mtime_ns, st.st_size)
    return out


def _older_namesake(stem: str, before: dict[str, tuple[int, int]]) -> str | None:
    """The pre-existing file dcm2niix avoided overwriting by appending a letter, if any.

    dcm2niix never overwrites: when ``<name>.nii.gz`` exists it writes ``<name>a``,
    ``<name>b``, ... instead.
    """
    if len(stem) > 1 and stem[-1].isalpha() and stem[-1].islower():
        base = stem[:-1]
        for candidate in (base, *(base + c for c in "abcdefghijklmnopqrstuvwxyz")):
            if candidate != stem and f"{candidate}.nii.gz" in before:
                return f"{candidate}.nii.gz"
    return None


def convert_dcm_to_nifti(
    input_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Convert all DICOM series found in *input_dir* to compressed NIfTI format.

    Intended for single-study conversion only. For full dataset conversion, use
    the ``dcm-to-bids`` skill and ``build_bids_dataset`` — the framework expects
    BIDS-organised data and ``build_bids_dataset`` handles multi-patient/multi-study
    datasets correctly.

    Each DICOM series produces one ``*.nii.gz`` volume and a ``*.json`` sidecar
    with acquisition metadata (BIDS-compatible). DWI series additionally produce
    ``*.bval`` and ``*.bvec`` files. Requires ``dcm2niix`` to be installed on the
    system PATH.

    Args:
        input_dir: Directory containing DICOM files (scanned recursively).
            Pass a series-level directory for a single series, or a study/patient
            root for bulk conversion.
        output_dir: Destination directory. Created if it does not exist.
            All output files are written here (no subdirectories). Prefer a new,
            empty folder: dcm2niix never overwrites, so converting a series again
            into the same folder writes ``<name>a.nii.gz``, ``<name>b.nii.gz``, ...
            next to the older file. Only files written by this call are reported
            as ``converted``.

    Returns:
        Dict with keys:
            converted: list of dicts, one per output NIfTI, each with:
                nifti: absolute path to the .nii.gz file
                json: absolute path to the .json sidecar (or null if absent)
                extra_files: list of paths for .bval/.bvec and other sidecars
                series_description: SeriesDescription from DICOM header
                modality: imaging modality string (e.g. "MR", "CT")
                series_number: SeriesNumber from DICOM header
            total_series: total number of NIfTI files created by this call
            already_in_output_dir: NIfTI files that were in *output_dir* before this
                call and were not written by it (older conversions, masks, ...).
                They are listed only so they are not mistaken for this result.
            warnings: dcm2niix's warning and error lines (e.g. missing slices,
                varying slice spacing); empty when it reported none
            _render: display instructions
    """
    exe = find_dcm2niix()
    if exe is None:
        raise RuntimeError(_INSTALL_HINT)

    if not input_dir.is_dir():
        raise ValueError(f"input_dir does not exist or is not a directory: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    before = _snapshot(output_dir)

    proc = subprocess.run(
        [
            exe,
            "-o",
            str(output_dir),
            "-f",
            "%3s_%d",  # series-number_description — readable, unique within a study
            "-z",
            "y",  # gzip compression
            "-v",
            "0",  # minimal verbosity
            "-w",
            "2",  # a name taken by an earlier conversion gets a suffix, never overwritten
            str(input_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    after = _snapshot(output_dir)
    written = sorted(name for name, sig in after.items() if before.get(name) != sig)
    untouched = sorted(name for name in before if name in after and name not in written)

    converted: list[dict[str, Any]] = []
    for name in written:
        nifti_path = output_dir / name
        stem = name[: -len(".nii.gz")]
        json_path = output_dir / f"{stem}.json"

        metadata: dict[str, Any] = {}
        if json_path.exists():
            try:
                with json_path.open() as fh:
                    metadata = json.load(fh)
            except Exception:
                pass

        extra: list[str] = []
        for ext in (".bval", ".bvec"):
            candidate = output_dir / f"{stem}{ext}"
            if candidate.exists():
                extra.append(str(candidate))

        entry: dict[str, Any] = {
            "nifti": str(nifti_path),
            "json": str(json_path) if json_path.exists() else None,
            "extra_files": extra,
            "series_description": str(metadata.get("SeriesDescription", "")),
            "modality": str(metadata.get("Modality", "")),
            "series_number": str(metadata.get("SeriesNumber", "")),
        }
        namesake = _older_namesake(stem, before)
        if namesake is not None:
            entry["note"] = (
                f"An older {namesake} was already in the output folder, so dcm2niix "
                f"wrote this conversion as {name} instead of overwriting it. Use {name}."
            )
        converted.append(entry)

    n = len(converted)
    warnings = dcm2niix_messages(proc.stdout or "", proc.stderr or "")
    if n == 0 and proc.returncode != 0:
        detail = "; ".join(warnings) or (proc.stderr or proc.stdout or "").strip()[-500:]
        raise RuntimeError(f"dcm2niix failed (exit {proc.returncode}): {detail}")
    existing_note = ""
    if untouched:
        shown = ", ".join(untouched[:10]) + (" ..." if len(untouched) > 10 else "")
        existing_note = (
            f"The output folder already held {len(untouched)} other NIfTI file(s) "
            f"(already_in_output_dir: {shown}); they were NOT written by this call. Say "
            "so in one line, never present or use them as this conversion's result, and "
            "suggest a new, empty output folder for the next conversion.\n"
        )
    if n == 0:
        existing_note += (
            "This call wrote no NIfTI file. Tell the user that nothing was converted and "
            "give the warnings; do not use older files from the folder instead.\n"
        )
    render = (
        f"Converted {n} series to NIfTI in: {output_dir}\n"
        "Only the files in 'converted' were written by this call; use only those paths "
        "for further steps. If a converted entry has a 'note', give it.\n"
        + existing_note
        + "If 'warnings' is not empty, give each warning first, word for word: they come "
        "from dcm2niix and can mean a wrong or incomplete volume (missing slices, "
        "varying slice spacing, multi-frame or derived data).\n"
        "Render a table with columns: Series # | Modality | Description | Output file.\n"
        "Use '—' for missing values. Omit 'Extra files' column unless DWI is present.\n"
        "NEXT ACTION: Display the conversion table, then stop."
    )

    return {
        "converted": converted,
        "total_series": n,
        "already_in_output_dir": [str(output_dir / name) for name in untouched],
        "warnings": warnings,
        "_render": render,
    }
