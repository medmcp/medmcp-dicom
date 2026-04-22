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
            All output files are written here (no subdirectories).

    Returns:
        Dict with keys:
            converted: list of dicts, one per output NIfTI, each with:
                nifti: absolute path to the .nii.gz file
                json: absolute path to the .json sidecar (or null if absent)
                extra_files: list of paths for .bval/.bvec and other sidecars
                series_description: SeriesDescription from DICOM header
                modality: imaging modality string (e.g. "MR", "CT")
                series_number: SeriesNumber from DICOM header
            total_series: total number of NIfTI files created
            _render: display instructions
    """
    exe = find_dcm2niix()
    if exe is None:
        raise RuntimeError(_INSTALL_HINT)

    if not input_dir.is_dir():
        raise ValueError(f"input_dir does not exist or is not a directory: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
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
            str(input_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    converted: list[dict[str, Any]] = []
    for nifti_path in sorted(output_dir.glob("*.nii.gz")):
        stem = nifti_path.name[: -len(".nii.gz")]
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

        converted.append(
            {
                "nifti": str(nifti_path),
                "json": str(json_path) if json_path.exists() else None,
                "extra_files": extra,
                "series_description": str(metadata.get("SeriesDescription", "")),
                "modality": str(metadata.get("Modality", "")),
                "series_number": str(metadata.get("SeriesNumber", "")),
            }
        )

    n = len(converted)
    render = (
        f"Converted {n} series to NIfTI in: {output_dir}\n"
        "Render a table with columns: Series # | Modality | Description | Output file.\n"
        "Use '—' for missing values. Omit 'Extra files' column unless DWI is present.\n"
        "NEXT ACTION: Display the conversion table, then stop."
    )

    return {
        "converted": converted,
        "total_series": n,
        "_render": render,
    }
