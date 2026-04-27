"""Internal DICOM scanning utilities shared across tools."""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pydicom


def find_dcm2niix() -> str | None:
    """Locate the dcm2niix executable.

    Resolution order:
    1. Binary alongside the current Python interpreter — covers pip/uv installs
       where the environment bin/ directory may not be on PATH.
    2. System PATH — covers system package manager installs (apt, brew, conda).

    Returns:
        Absolute path string if found, ``None`` otherwise.
    """
    try:
        importlib.metadata.version("dcm2niix")
        sibling = Path(sys.executable).parent / "dcm2niix"
        if sibling.is_file():
            return str(sibling)
    except importlib.metadata.PackageNotFoundError:
        pass
    return shutil.which("dcm2niix")


def _empty_path_list() -> list[Path]:
    return []


@dataclass
class SeriesRecord:
    """Metadata and file list for one DICOM series."""

    patient_id: str
    study_uid: str
    study_date: str  # raw YYYYMMDD or ""
    series_uid: str
    series_number: str
    modality: str
    series_description: str
    files: list[Path] = field(default_factory=_empty_path_list)


def scan_series(root_dir: Path) -> tuple[list[SeriesRecord], int]:
    """Walk *root_dir* recursively and group DICOM files by SeriesInstanceUID.

    Each readable DICOM file is assigned to a SeriesRecord; files that cannot
    be parsed as DICOM are counted as skipped.

    Args:
        root_dir: Root directory to scan.

    Returns:
        Tuple of (series_records, skipped_count). Series are returned in
        scan order (not sorted).
    """
    records: dict[str, SeriesRecord] = {}
    skipped = 0

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in sorted(filenames):
            filepath = Path(dirpath) / filename
            try:
                ds: pydicom.Dataset = pydicom.dcmread(  # type: ignore[assignment]
                    str(filepath), stop_before_pixels=True
                )
            except Exception:
                skipped += 1
                continue

            series_uid = str(getattr(ds, "SeriesInstanceUID", ""))
            if not series_uid:
                skipped += 1
                continue

            if series_uid not in records:
                records[series_uid] = SeriesRecord(
                    patient_id=str(getattr(ds, "PatientID", "")),
                    study_uid=str(getattr(ds, "StudyInstanceUID", "")),
                    study_date=str(getattr(ds, "StudyDate", "")),
                    series_uid=series_uid,
                    series_number=str(getattr(ds, "SeriesNumber", "")),
                    modality=str(getattr(ds, "Modality", "")),
                    series_description=str(getattr(ds, "SeriesDescription", "")),
                )
            records[series_uid].files.append(filepath)

    return list(records.values()), skipped
