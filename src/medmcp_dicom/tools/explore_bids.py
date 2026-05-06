"""BIDS dataset discovery tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _is_nifti(name: str) -> bool:
    return name.endswith(".nii.gz") or name.endswith(".nii")


def _parse_bids_suffix(filename: str) -> str:
    """Extract the BIDS suffix (last underscore-delimited part before the extension)."""
    stem = filename
    for ext in (".nii.gz", ".nii"):
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break
    return stem.rsplit("_", 1)[-1]


def _collect_niftis(datatype_dir: Path) -> list[dict[str, Any]]:
    """Return one entry per NIfTI file found directly in *datatype_dir*."""
    entries: list[dict[str, Any]] = []
    for f in sorted(datatype_dir.iterdir()):
        if f.is_file() and _is_nifti(f.name):
            entries.append(
                {
                    "datatype": datatype_dir.name,
                    "suffix": _parse_bids_suffix(f.name),
                    "filename": f.name,
                    "file_size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                }
            )
    return entries


def explore_bids(
    bids_dir: Path,
    summary_only: bool = True,
) -> dict[str, Any]:
    """Scan a BIDS dataset directory and return a structured inventory.

    Only call this tool when the user explicitly asks to explore or inspect a BIDS dataset.

    Reads only the directory structure and file sizes — no image data is loaded.
    Only NIfTI files (.nii.gz, .nii) are counted as series; sidecar files
    (.json, .bval, .bvec, .tsv) are ignored. Results are grouped
    Subject → Session → Datatype.

    Args:
        bids_dir: Root directory of the BIDS dataset.
        summary_only: Return only the ``summary`` block; ``subjects`` will be
            an empty list. Use True for an initial overview, False to get
            per-subject detail needed to inspect individual series.

    Returns:
        Dict with ``summary`` (counts, dataset name, BIDS version, datatype
        breakdown) and ``subjects`` (per-subject/session/series breakdown, empty
        when ``summary_only=True``). Also contains ``_render`` with display
        instructions for this specific result.
    """
    root = Path(bids_dir)
    if not root.is_dir():
        raise ValueError(f"bids_dir does not exist or is not a directory: {bids_dir}")

    # Read dataset_description.json
    dataset_name: str | None = None
    bids_version: str | None = None
    desc_path = root / "dataset_description.json"
    if desc_path.exists():
        try:
            desc: dict[str, Any] = json.loads(desc_path.read_text())
            dataset_name = str(desc.get("Name") or "") or None
            bids_version = str(desc.get("BIDSVersion") or "") or None
        except Exception:
            pass

    # subject_data: sub_label -> [(ses_label | None, [series_entry, ...])]
    subject_data: dict[str, list[tuple[str | None, list[dict[str, Any]]]]] = {}

    for sub_dir in sorted(d for d in root.iterdir() if d.is_dir() and d.name.startswith("sub-")):
        sub_label = sub_dir.name
        subject_data[sub_label] = []

        ses_dirs = sorted(d for d in sub_dir.iterdir() if d.is_dir() and d.name.startswith("ses-"))

        if ses_dirs:
            for ses_dir in ses_dirs:
                series: list[dict[str, Any]] = []
                for d in sorted(ses_dir.iterdir()):
                    if d.is_dir():
                        series.extend(_collect_niftis(d))
                subject_data[sub_label].append((ses_dir.name, series))
        else:
            series = []
            for d in sorted(sub_dir.iterdir()):
                if d.is_dir() and not d.name.startswith("ses-"):
                    series.extend(_collect_niftis(d))
            subject_data[sub_label].append((None, series))

    # Aggregation
    total_subjects = len(subject_data)
    total_sessions = sum(
        1
        for sessions in subject_data.values()
        for ses_label, _ in sessions
        if ses_label is not None
    )
    combo_counts: dict[str, int] = {}
    total_series = 0
    for sessions in subject_data.values():
        for _, series_list in sessions:
            for s in series_list:
                key = f"{s['datatype']}|{s['suffix']}"
                combo_counts[key] = combo_counts.get(key, 0) + 1
                total_series += 1

    datatype_breakdown: list[dict[str, Any]] = sorted(
        (
            {"datatype": dt, "suffix": sx, "series": cnt}
            for key, cnt in combo_counts.items()
            for dt, sx in [key.split("|", 1)]
        ),
        key=lambda r: (r["datatype"] or "", -r["series"], r["suffix"] or ""),
    )

    # Per-subject detail (only when not summary_only)
    subjects: list[dict[str, Any]] = []
    if not summary_only:
        for sub_label, sessions in subject_data.items():
            session_list: list[dict[str, Any]] = []
            for ses_label, series_list in sessions:
                entry: dict[str, Any] = {"series": series_list, "series_count": len(series_list)}
                if ses_label is not None:
                    entry["session"] = ses_label
                session_list.append(entry)
            subjects.append({"subject": sub_label, "sessions": session_list})

    # _render
    if summary_only and total_subjects > 3:
        next_action = (
            "Large dataset (> 3 subjects): render the statistics table only — "
            "do NOT enumerate subjects or sessions. Stop after the last table."
        )
    elif summary_only:
        next_action = (
            f"Small dataset ({total_subjects} subject(s)): call explore_bids again with "
            "summary_only=False to retrieve per-subject detail, then render the "
            "per-subject breakdown below the statistics table."
        )
    else:
        next_action = (
            "Render the per-subject breakdown below the statistics table.\n"
            "Per subject, check total series across all sessions:\n"
            "• total series > 10 → COLLAPSED FORMAT — group by (datatype, suffix).\n"
            "  Columns: Datatype | Suffix | Series.\n"
            "• total series ≤ 10 → INDIVIDUAL FORMAT — one row per series.\n"
            "  Columns: Session | Datatype | Suffix | File | Size (MB).\n"
            "  Omit 'Session' column if no sessions are present for this subject.\n"
            "  Omit 'Size (MB)' column if all sizes are 0."
        )

    stats_rows = "• Statistics table rows (in order): Subjects"
    if total_sessions > 0:
        stats_rows += ", Sessions"
    stats_rows += ", Series"
    if dataset_name:
        stats_rows += f", Dataset name: {dataset_name}"
    if bids_version:
        stats_rows += f", BIDS version: {bids_version}"
    stats_rows += ".\n"

    render = (
        "DISPLAY RULES — follow exactly:\n"
        "• Use '—' (em dash U+2014) for every null or missing value.\n"
        "• After the final table, stop. Do not add commentary, restatements, or suggestions.\n"
        f"• Statistics table header: **BIDS Overview** — `{bids_dir}`\n"
        + stats_rows
        + "• **Datatype breakdown** table — columns: Datatype | Suffix | Series.\n"
        "  Preserve pre-sorted order (datatype A→Z, then series desc within each datatype).\n"
        f"NEXT ACTION: {next_action}"
    )

    return {
        "summary": {
            "subjects": total_subjects,
            "sessions": total_sessions,
            "series": total_series,
            "dataset_name": dataset_name,
            "bids_version": bids_version,
            "datatype_breakdown": datatype_breakdown,
        },
        "subjects": subjects,
        "_render": render,
    }
