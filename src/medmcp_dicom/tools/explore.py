"""DICOM data discovery tool."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pydicom


def _get(ds: pydicom.Dataset, tag: str, default: Any = None) -> Any:
    return getattr(ds, tag, default)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_iso_date(raw: str) -> str:
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw


def _format_person_name(raw: Any) -> str:
    # pydicom PersonName objects expose named components directly
    if hasattr(raw, "family_name") or hasattr(raw, "given_name"):
        family = str(getattr(raw, "family_name", "") or "").strip()
        given = str(getattr(raw, "given_name", "") or "").strip()
    else:
        parts = str(raw).split("^")
        family = parts[0].strip() if parts else ""
        given = parts[1].strip() if len(parts) > 1 else ""
    if given and family:
        return f"{given} {family}"
    return family or given


def _study_sort_key(item: tuple[str, dict[str, list[dict[str, Any]]]]) -> tuple[str, str]:
    first_inst = next(iter(item[1].values()))[0]
    return (str(first_inst["study_date"]), item[0])


def _series_sort_key(item: tuple[str, list[dict[str, Any]]]) -> tuple[int, str]:
    try:
        return (int(item[1][0]["series_number"]), item[0])
    except (ValueError, IndexError):
        return (9999, item[0])


def explore_data(
    root_dir: Path,
    include_phi: bool = False,
    summary_only: bool = True,
) -> dict[str, Any]:
    """Scan a directory tree and return a structured inventory of DICOM data.

    Reads only DICOM headers (no pixel data) for speed. Non-DICOM files are
    counted in ``summary.skipped_files`` and otherwise ignored. Results are
    grouped Patient → Study → Series; each series aggregates metadata from
    all its instances (slices).

    Args:
        root_dir: Root directory to scan recursively (tool walks all subdirs).
        include_phi: Include PatientName and real PatientID. Only set True
            when the user explicitly requests patient identifiers.
        summary_only: Return only the ``summary`` block; ``patients`` will be
            an empty list. Use True for an initial overview, False to get
            per-series detail needed to select a specific series.

    Returns:
        Dict with ``summary`` (aggregate counts, date range, modalities,
        body parts) and ``patients`` (per-patient/study/series breakdown,
        empty when ``summary_only=True``). Also contains ``_render`` with
        display instructions for this specific result.
    """
    root = Path(root_dir)
    if not root.is_dir():
        raise ValueError(f"root_dir does not exist or is not a directory: {root_dir}")

    # patient_id -> study_uid -> series_uid -> [per-instance metadata dicts]
    registry: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
    patient_names: dict[str, Any] = {}
    skipped = 0

    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            fpath = Path(dirpath) / fname
            try:
                ds: pydicom.Dataset = pydicom.dcmread(  # type: ignore[assignment]
                    str(fpath), stop_before_pixels=True
                )
            except Exception:
                skipped += 1
                continue

            patient_id = str(_get(ds, "PatientID", "UNKNOWN"))
            patient_names[patient_id] = _get(ds, "PatientName", "")
            study_uid = str(_get(ds, "StudyInstanceUID", "UNKNOWN"))
            series_uid = str(_get(ds, "SeriesInstanceUID", "UNKNOWN"))

            raw_spacing = _get(ds, "PixelSpacing")
            pixel_spacing: list[float] | None = (
                [float(raw_spacing[0]), float(raw_spacing[1])] if raw_spacing else None
            )

            instance: dict[str, Any] = {
                "study_date": str(_get(ds, "StudyDate", "")),
                "study_description": str(_get(ds, "StudyDescription", "")),
                "series_number": str(_get(ds, "SeriesNumber", "")),
                "series_description": str(_get(ds, "SeriesDescription", "")),
                "modality": str(_get(ds, "Modality", "")),
                "body_part": str(_get(ds, "BodyPartExamined", "")),
                "rows": int(_get(ds, "Rows", 0)),
                "columns": int(_get(ds, "Columns", 0)),
                "pixel_spacing_mm": pixel_spacing,
                "slice_thickness_mm": _safe_float(_get(ds, "SliceThickness")),
            }

            patient_studies = registry.setdefault(patient_id, {})
            study_series = patient_studies.setdefault(study_uid, {})
            study_series.setdefault(series_uid, []).append(instance)

    # --- aggregation pass (always runs) ---
    total_studies = 0
    total_series = 0
    total_instances = 0
    modality_counts: dict[str, int] = {}
    body_part_counts: dict[str, int] = {}
    study_dates: list[str] = []

    for studies in registry.values():
        total_studies += len(studies)
        for series_dict in studies.values():
            total_series += len(series_dict)
            first_inst = next(iter(series_dict.values()))[0]
            if first_inst["study_date"]:
                study_dates.append(first_inst["study_date"])
            for instances in series_dict.values():
                rep = instances[0]
                modality_counts[rep["modality"]] = modality_counts.get(rep["modality"], 0) + 1
                body_part_counts[rep["body_part"]] = body_part_counts.get(rep["body_part"], 0) + 1
                total_instances += len(instances)

    date_range: dict[str, str] | None = (
        {"min": _to_iso_date(min(study_dates)), "max": _to_iso_date(max(study_dates))}
        if study_dates
        else None
    )
    modalities = dict(sorted(modality_counts.items(), key=lambda x: (-x[1], x[0])))
    body_parts = dict(sorted(body_part_counts.items(), key=lambda x: (-x[1], x[0])))

    # --- patient/study/series build pass (skipped when summary_only=True) ---
    patients: list[dict[str, Any]] = []

    if not summary_only:
        for idx, (patient_id, studies) in enumerate(sorted(registry.items()), start=1):
            patient_entry: dict[str, Any] = {
                "patient_id": patient_id if include_phi else f"PATIENT_{idx:03d}",
            }
            if include_phi:
                patient_entry["patient_name"] = _format_person_name(
                    patient_names.get(patient_id, "")
                )

            study_list: list[dict[str, Any]] = []
            for study_uid, series_dict in sorted(studies.items(), key=_study_sort_key):
                first_inst = next(iter(series_dict.values()))[0]

                series_list: list[dict[str, Any]] = []
                for ser_uid, instances in sorted(series_dict.items(), key=_series_sort_key):
                    rep = instances[0]
                    rows, cols = rep["rows"], rep["columns"]
                    series_list.append(
                        {
                            "series_uid": ser_uid,
                            "modality": rep["modality"],
                            "body_part": rep["body_part"] or None,
                            "series_number": rep["series_number"],
                            "series_description": rep["series_description"],
                            "instances": len(instances),
                            "shape": [rows, cols] if rows and cols else None,
                            "pixel_spacing_mm": rep["pixel_spacing_mm"],
                            "slice_thickness_mm": rep["slice_thickness_mm"],
                        }
                    )

                study_list.append(
                    {
                        "study_uid": study_uid,
                        "study_date": _to_iso_date(first_inst["study_date"]),
                        "study_description": first_inst["study_description"],
                        "series_count": len(series_list),
                        "series": series_list,
                    }
                )

            patient_entry["studies"] = study_list
            patients.append(patient_entry)

    n_patients = len(registry)

    if summary_only and n_patients > 3:
        next_action = (
            "Large dataset (> 3 patients): render the statistics table only — "
            "do NOT enumerate patients, studies, or series. Stop after the last table."
        )
    elif summary_only and n_patients <= 3:
        next_action = (
            f"Small dataset ({n_patients} patient(s)): call explore_data again with "
            "summary_only=False to retrieve per-series detail, then render the "
            "per-patient breakdown below the statistics table."
        )
    else:
        next_action = (
            "Render the per-patient breakdown below the statistics table.\n"
            "Per study, check series_count:\n"
            "• series_count > 10 → COLLAPSED FORMAT — group by (modality, body_part, shape).\n"
            "  Columns: Modality | Body part | Series | Slices each | Resolution.\n"
            "  'Series' = group count; 'Slices each' = instance count if uniform, else min-max.\n"
            "  'Resolution' = Rows×Cols px, x×y mm; omit column if pixel_spacing absent for all.\n"  # noqa: RUF001
            "  Omit 'Body part' column if absent for all groups.\n"
            "• series_count ≤ 10 → INDIVIDUAL FORMAT — one row per series.\n"
            "  Columns: Series | Modality | Body part | Slices | Resolution.\n"
            "  'Resolution' = Rows×Cols px; append ', x×y mm' when pixel_spacing_mm non-null.\n"  # noqa: RUF001
            "  Omit 'Body part' column if absent for all series.\n"
            "  Omit 'Resolution' column if absent for all series."
        )

    render = (
        "DISPLAY RULES — follow exactly:\n"
        "• Use '—' (em dash U+2014) for every null or missing value.\n"
        "• Omit UIDs unless the user asks for them.\n"
        "• After the final table, stop. Do not add commentary, restatements, or suggestions.\n"
        f"• Statistics table header: **DICOM Overview** — `{root_dir}`\n"
        "• Statistics table rows (in order): Patients, Studies, Series, Instances;\n"
        "  Date range YYYY-MM-DD – YYYY-MM-DD (omit row when study_date_range is null);\n"  # noqa: RUF001
        "  Skipped files N (omit row when skipped_files is 0).\n"
        "• **Modalities** table — columns: Modality | Series — preserve pre-sorted order.\n"
        "• **Anatomical regions** table — columns: Body part | Series — omit if body_parts\n"
        '  is empty or its only key is ""; render "" key as \'—\'.\n'
        f"NEXT ACTION: {next_action}"
    )

    return {
        "summary": {
            "patients": n_patients,
            "studies": total_studies,
            "series": total_series,
            "instances": total_instances,
            "skipped_files": skipped,
            "study_date_range": date_range,
            "modalities": modalities,
            "body_parts": body_parts,
        },
        "patients": patients,
        "_render": render,
    }
