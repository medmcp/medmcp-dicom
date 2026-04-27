"""DICOM to BIDS dataset conversion tool."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

from medmcp_dicom import __version__
from medmcp_dicom.tools._dicom import SeriesRecord, find_dcm2niix, scan_series

# ---------------------------------------------------------------------------
# Series → BIDS classification
# ---------------------------------------------------------------------------

# (keywords_in_series_description, datatype, suffix)
_MR_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("t1", "mprage", "mp-rage", "spgr", "bravo", "vibe", "flash", "irfse"), "anat", "T1w"),
    (("t2",), "anat", "T2w"),
    (("flair",), "anat", "FLAIR"),
    (("pd",), "anat", "PDw"),
    (("dwi", "dti", "diffusion", "hardi", "dki"), "dwi", "dwi"),
    (("bold", "rest", "task", "epi", "fmri"), "func", "bold"),
    (("asl", "perfusion"), "perf", "asl"),
    (("fmap", "fieldmap", "b0 map", "b0map", "field map"), "fmap", "magnitude"),
    (("angio", "mra", "tof", "swi", "sus"), "anat", "angio"),
]

_MODALITY_DEFAULTS: dict[str, tuple[str, str]] = {
    "CT": ("anat", "CT"),
    "PT": ("pet", "pet"),
    "NM": ("anat", "NM"),  # SPECT/scintigraphy — not PET; no BIDS standard exists
    "MG": ("anat", "MG"),
    "US": ("anat", "US"),
    "XA": ("anat", "XA"),
    "CR": ("anat", "CR"),
    "DX": ("anat", "DX"),
}

# Modalities placed in a BIDS-like structure but not officially supported by the standard.
# PT (PET) is the only modality in _MODALITY_DEFAULTS with full BIDS support.
_NON_BIDS_MODALITIES: frozenset[str] = frozenset({"CT", "NM", "MG", "US", "XA", "CR", "DX"})


def classify_series(modality: str, series_description: str) -> tuple[str, str, bool]:
    """Map a DICOM series to a BIDS ``(datatype, suffix)``.

    Args:
        modality: DICOM Modality tag value (e.g. ``"MR"``, ``"CT"``).
        series_description: DICOM SeriesDescription tag value.

    Returns:
        Tuple of ``(datatype, suffix, classified)`` where ``classified`` is
        ``False`` when no rule matched and a generic fallback was used.
    """
    desc = series_description.lower()

    if modality == "MR":
        for keywords, datatype, suffix in _MR_RULES:
            if any(kw in desc for kw in keywords):
                return datatype, suffix, True
        return "anat", "T1w", False  # most common MR fallback

    if modality in _MODALITY_DEFAULTS:
        dt, sx = _MODALITY_DEFAULTS[modality]
        return dt, sx, True

    fallback_suffix = modality if modality else "unknown"
    return "anat", fallback_suffix, False


# ---------------------------------------------------------------------------
# BIDS label and filename helpers
# ---------------------------------------------------------------------------


def make_bids_filename(
    sub: str,
    ses: str,
    suffix: str,
    extension: str,
    *,
    task: str | None = None,
    run: int | None = None,
) -> str:
    """Build a BIDS-compliant filename.

    Args:
        sub: Subject label (without ``sub-`` prefix).
        ses: Session label (without ``ses-`` prefix).
        suffix: BIDS suffix (e.g. ``"T1w"``, ``"bold"``).
        extension: File extension including leading dot (e.g. ``".nii.gz"``).
        task: Task label for functional data (without ``task-`` prefix).
        run: Run index (1-based). Omitted from filename when ``None``.

    Returns:
        BIDS filename string.
    """
    parts = [f"sub-{sub}", f"ses-{ses}"]
    if task is not None:
        parts.append(f"task-{task}")
    if run is not None:
        parts.append(f"run-{run:02d}")
    parts.append(suffix)
    return "_".join(parts) + extension


# ---------------------------------------------------------------------------
# Subject / session label assignment
# ---------------------------------------------------------------------------


def assign_labels(
    series_records: list[SeriesRecord],
) -> tuple[dict[str, str], dict[str, str]]:
    """Build subject and session label maps from scanned series records.

    Args:
        series_records: Output of :func:`scan_series`.

    Returns:
        Tuple of ``(sub_map, ses_map)`` where ``sub_map`` maps
        ``patient_id → sub_label`` and ``ses_map`` maps
        ``study_uid → ses_label``.
    """
    # Collect unique patients and their study UIDs (sorted by date)
    patient_studies: dict[str, set[str]] = {}
    study_date: dict[str, str] = {}
    study_patient: dict[str, str] = {}

    for rec in series_records:
        patient_studies.setdefault(rec.patient_id, set()).add(rec.study_uid)
        study_date[rec.study_uid] = rec.study_date
        study_patient[rec.study_uid] = rec.patient_id

    sorted_patients = sorted(patient_studies.keys())
    sub_map: dict[str, str] = {pid: f"{idx + 1:03d}" for idx, pid in enumerate(sorted_patients)}

    ses_map: dict[str, str] = {}
    for pid in sorted_patients:
        studies = sorted(
            patient_studies[pid],
            key=lambda u: study_date.get(u, "99999999"),
        )
        for ses_idx, uid in enumerate(studies):
            ses_map[uid] = f"{ses_idx + 1:02d}"

    return sub_map, ses_map


_INSTALL_HINT = (
    "dcm2niix is not installed or could not be found.\n"
    "It is listed as a dependency and should have been installed automatically.\n"
    "If the problem persists, reinstall the package:\n"
    "  uv tool install --reinstall medmcp-dicom\n"
    "Or install dcm2niix separately:\n"
    "  pip install dcm2niix"
)


def _infer_classification(created: list[Path]) -> tuple[str, str] | None:
    """Infer BIDS (datatype, suffix) from dcm2niix output files and JSON sidecar.

    Args:
        created: Files produced by ``_convert_series``.

    Returns:
        ``(datatype, suffix)`` override, or ``None`` if no inference is possible.
    """
    suffixes = {f.suffix for f in created}

    # DWI: bval/bvec are produced exclusively for diffusion sequences
    if ".bval" in suffixes and ".bvec" in suffixes:
        return "dwi", "dwi"

    json_file = next((f for f in created if f.suffix == ".json"), None)
    if json_file is None:
        return None

    try:
        meta: dict[str, Any] = json.loads(json_file.read_text())
    except Exception:
        return None

    # DWI from ImageType (catches edge cases where bval/bvec may be absent)
    image_type = meta.get("ImageType", [])
    if isinstance(image_type, str):
        image_type = [image_type]
    if "DIFFUSION" in [str(t).upper() for t in image_type]:
        return "dwi", "dwi"

    # fMRI BOLD: EPI sequence with SliceTiming (dcm2niix only writes SliceTiming for BOLD EPI)
    scanning_seq_raw = meta.get("ScanningSequence", "")
    if isinstance(scanning_seq_raw, list):
        scanning_seq = " ".join(str(x) for x in cast(list[Any], scanning_seq_raw))
    else:
        scanning_seq = str(scanning_seq_raw)
    if "EP" in scanning_seq.upper() and "SliceTiming" in meta:
        return "func", "bold"

    return None


def _convert_series(
    files: list[Path], out_dir: Path, stem: str, exe: str, *, multi_label: str = "echo"
) -> list[Path]:
    """Convert one DICOM series to NIfTI using dcm2niix.

    Creates a temp directory with symlinks (or copies) to *files*, runs
    dcm2niix, then moves all produced files to *out_dir* with the given *stem*.

    Args:
        files: DICOM files belonging to a single series.
        out_dir: Destination directory (must exist).
        stem: Output filename stem without extension (e.g. ``"sub-001_ses-01_T1w"``).
        exe: Absolute path to the dcm2niix executable.
        multi_label: Entity label used when dcm2niix produces multiple NIfTI files
            from one series (e.g. ``"echo"`` for MRI, ``"part"`` for non-MRI modalities).

    Returns:
        List of paths to every file written under *out_dir* for this series.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Stage DICOM files — prefer symlinks, fall back to hard links then copy
        for i, src in enumerate(files):
            dst = tmp_path / f"{i:06d}.dcm"
            try:
                os.symlink(src.resolve(), dst)
            except OSError:
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)

        subprocess.run(
            [
                exe,
                "-o",
                str(tmp_path),
                "-f",
                "series",
                "-z",
                "y",
                "-v",
                "0",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        created: list[Path] = []
        nifti_files = sorted(tmp_path.glob("*.nii.gz"))

        for nii_idx, nii_src in enumerate(nifti_files):
            out_stem = f"{stem}_{multi_label}-{nii_idx + 1}" if len(nifti_files) > 1 else stem

            nii_dst = out_dir / f"{out_stem}.nii.gz"
            shutil.move(str(nii_src), str(nii_dst))
            created.append(nii_dst)

            # Move matching sidecar files (json, bval, bvec, tsv)
            raw_stem = nii_src.name[: -len(".nii.gz")]
            for ext in (".json", ".bval", ".bvec", ".tsv"):
                src_sidecar = tmp_path / f"{raw_stem}{ext}"
                if src_sidecar.exists():
                    dst_sidecar = out_dir / f"{out_stem}{ext}"
                    shutil.move(str(src_sidecar), str(dst_sidecar))
                    created.append(dst_sidecar)

    return created


# ---------------------------------------------------------------------------
# Public tool
# ---------------------------------------------------------------------------


def build_bids_dataset(
    dicom_root: Path,
    output_dir: Path,
    dataset_name: str | None = None,
    anonymize: bool = True,
) -> dict[str, Any]:
    """Convert a DICOM directory tree into a BIDS-organised dataset.

    Load the ``dcm-to-bids`` skill before calling this tool. Do not prompt the
    user for parameters or make any decisions before the skill is loaded — it
    defines what to ask, in what order, and what to confirm.

    Scans all DICOM files under *dicom_root*, maps them to BIDS entities
    (sub/ses/datatype/suffix) via keyword heuristics on SeriesDescription, then
    calls ``dcm2niix`` to convert each series to compressed NIfTI. The
    ``dcm2niix`` binary is resolved from the local Python environment first
    (installed as the ``dcm2niix`` package dependency), then from the system PATH.

    Subject labels are always anonymized sequential numbers (``sub-001``,
    ``sub-002`` …). When *anonymize* is ``False`` the source patient IDs are
    also recorded in ``participants.tsv``.

    Args:
        dicom_root: Root directory containing DICOM files (scanned recursively).
        output_dir: Destination for the BIDS dataset. Created if absent. Must
            not overlap with *dicom_root*.
        dataset_name: Value for the ``Name`` field in ``dataset_description.json``.
            Defaults to ``<dicom_root directory name>_bids`` when not provided.
        anonymize: When ``True`` (default), only anonymous ``sub-XXX`` labels
            appear in output. When ``False``, source patient IDs are written to
            ``participants.tsv`` under a ``source_patient_id`` column.

    Returns:
        Dict with keys:
            output_dir: Absolute path to the BIDS root.
            subjects: number of subjects written.
            sessions: total number of sessions written.
            files_created: total number of NIfTI (and sidecar) files created.
            unclassified: list of series for which no BIDS suffix rule matched;
                each entry has keys sub, ses, modality, series_description.
            _render: display instructions.
    """
    exe = find_dcm2niix()
    if exe is None:
        raise RuntimeError(_INSTALL_HINT)

    if not dicom_root.is_dir():
        raise ValueError(f"dicom_root does not exist or is not a directory: {dicom_root}")

    dicom_resolved = dicom_root.resolve()
    output_resolved = output_dir.resolve()
    if output_resolved == dicom_resolved or dicom_resolved in output_resolved.parents:
        raise ValueError(
            f"output_dir ({output_dir}) must not be inside dicom_root ({dicom_root}). "
            "Choose a separate destination directory."
        )

    resolved_name = dataset_name if dataset_name is not None else f"{dicom_root.name}_bids"

    # 1. Scan DICOM tree
    series_records, _ = scan_series(dicom_root)

    if not series_records:
        return {
            "output_dir": str(output_dir),
            "subjects": 0,
            "sessions": 0,
            "files_created": 0,
            "unclassified": [],
            "_render": (
                f"No DICOM series found under {dicom_root}.\n"
                "NEXT ACTION: Report that no DICOM files were found and stop."
            ),
        }

    # Capture DICOM input counts for the overview table
    dicom_n_patients = len({r.patient_id for r in series_records})
    dicom_n_studies = len({r.study_uid for r in series_records})
    dicom_n_series = len(series_records)

    # 2. Assign BIDS subject/session labels
    sub_map, ses_map = assign_labels(series_records)

    # 3. First pass: convert all series to a staging area and apply all inference.
    #    Run numbers can only be assigned after final classifications are known.
    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = output_dir / ".medmcp_staging"
    staging_dir.mkdir(exist_ok=True)

    staged: list[tuple[str, str, str, str, bool, list[Path], str, SeriesRecord]] = []
    unclassified: list[dict[str, str]] = []
    participant_ids: dict[str, str] = {}

    for idx, rec in enumerate(series_records):
        sub = sub_map[rec.patient_id]
        ses = ses_map[rec.study_uid]
        participant_ids[sub] = rec.patient_id

        datatype, suffix, classified = classify_series(rec.modality, rec.series_description)
        staging_stem = f"s{idx:05d}"
        series_staging = staging_dir / staging_stem
        series_staging.mkdir()

        multi_label = "echo" if rec.modality == "MR" else "part"
        try:
            created = _convert_series(
                rec.files, series_staging, staging_stem, exe, multi_label=multi_label
            )
        except Exception:
            unclassified.append(
                {
                    "sub": sub,
                    "ses": ses,
                    "modality": rec.modality,
                    "series_description": rec.series_description,
                    "reason": "dcm2niix conversion failed",
                }
            )
            continue

        if not classified:
            inferred = _infer_classification(created)
            if inferred is not None:
                datatype, suffix = inferred
                classified = True

        staged.append((sub, ses, datatype, suffix, classified, created, staging_stem, rec))

    # 4. Compute run counts from final post-inference classifications
    key_counts: Counter[tuple[str, str, str, str]] = Counter(
        (sub, ses, dt, sx) for sub, ses, dt, sx, _, _, _, _ in staged
    )
    key_run_counter: defaultdict[tuple[str, str, str, str], int] = defaultdict(int)

    # 5. Second pass: move files from staging to final BIDS locations with correct run numbers
    all_files: list[Path] = []
    asl_needs_review: list[dict[str, str]] = []
    non_bids_standard: list[dict[str, str]] = []
    datatype_counts: Counter[str] = Counter()
    suffix_counts: Counter[str] = Counter()
    subject_summary: dict[str, dict[str, Any]] = {}

    for sub, ses, datatype, suffix, classified, created, staging_stem, rec in staged:
        key = (sub, ses, datatype, suffix)
        run_idx = key_run_counter[key]
        key_run_counter[key] += 1
        run: int | None = run_idx + 1 if key_counts[key] > 1 else None

        task = "rest" if suffix == "bold" else None
        bids_stem = make_bids_filename(sub, ses, suffix, "", task=task, run=run)
        series_dir = output_dir / f"sub-{sub}" / f"ses-{ses}" / datatype
        series_dir.mkdir(parents=True, exist_ok=True)

        for f in created:
            ext = f.name[len(staging_stem) :]
            new_path = series_dir / (bids_stem + ext)
            shutil.move(str(f), str(new_path))
            all_files.append(new_path)

        datatype_counts[datatype] += 1
        suffix_counts[suffix] += 1
        sub_key = f"sub-{sub}"
        entry = subject_summary.setdefault(
            sub_key, {"sessions": set(), "series": 0, "datatypes": set()}
        )
        entry["sessions"].add(f"ses-{ses}")
        entry["series"] = int(entry["series"]) + 1
        entry["datatypes"].add(datatype)

        if rec.modality in _NON_BIDS_MODALITIES:
            non_bids_standard.append(
                {
                    "sub": f"sub-{sub}",
                    "ses": f"ses-{ses}",
                    "modality": rec.modality,
                    "series_description": rec.series_description,
                    "placed_at": str(series_dir / f"{bids_stem}.nii.gz"),
                }
            )

        if suffix == "asl":
            aslcontext_path = series_dir / f"{bids_stem}_aslcontext.tsv"
            if not aslcontext_path.exists():
                aslcontext_path.write_text("volume_type\nlabel\n")
                all_files.append(aslcontext_path)
            asl_needs_review.append(
                {
                    "sub": f"sub-{sub}",
                    "ses": f"ses-{ses}",
                    "series_description": rec.series_description,
                    "aslcontext": str(aslcontext_path),
                }
            )

        if not classified:
            unclassified.append(
                {
                    "sub": sub,
                    "ses": ses,
                    "modality": rec.modality,
                    "series_description": rec.series_description,
                    "reason": "no BIDS suffix rule matched; placed in anat/ with fallback suffix",
                }
            )

    shutil.rmtree(str(staging_dir), ignore_errors=True)

    # 7. Write dataset_description.json
    dataset_desc = {
        "Name": resolved_name,
        "BIDSVersion": "1.9.0",
        "GeneratedBy": [{"Name": "medmcp-dicom", "Version": __version__}],
    }
    desc_path = output_dir / "dataset_description.json"
    desc_path.write_text(json.dumps(dataset_desc, indent=2))

    # 8. Write participants.tsv
    sorted_subs = sorted(participant_ids.keys())
    if anonymize:
        tsv_lines = ["participant_id"] + [f"sub-{s}" for s in sorted_subs]
    else:
        tsv_lines = ["participant_id\tsource_patient_id"] + [
            f"sub-{s}\t{participant_ids[s]}" for s in sorted_subs
        ]
    (output_dir / "participants.tsv").write_text("\n".join(tsv_lines) + "\n")

    # 9. Write .bidsignore
    (output_dir / ".bidsignore").write_text("# generated by medmcp-dicom\n")

    n_subjects = len(set(sub_map.values()))
    n_sessions = len(set(ses_map.values()))

    all_series_counts = [entry["series"] for entry in subject_summary.values()]
    series_per_subject = (
        {
            "min": min(all_series_counts),
            "max": max(all_series_counts),
            "median": sorted(all_series_counts)[len(all_series_counts) // 2],
        }
        if all_series_counts
        else None
    )
    subject_summary_out = {
        sub: {
            "sessions": len(entry["sessions"]),
            "series": entry["series"],
            "datatypes": sorted(entry["datatypes"]),
        }
        for sub, entry in sorted(subject_summary.items())
    }

    # Collapsed exception summaries (grouped by description, not one row per series)
    def _group_by_desc(items: list[dict[str, str]]) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter(item["series_description"] for item in items)
        return [{"series_description": d, "count": c} for d, c in counts.most_common()]

    unclassified_grouped = _group_by_desc(unclassified)
    non_bids_grouped: list[dict[str, Any]] = [
        {"modality": mod, "count": cnt}
        for mod, cnt in Counter(e["modality"] for e in non_bids_standard).most_common()
    ]

    large_dataset = n_subjects > 10

    render = (
        "Display the result in the following sections. "
        "Use '—' for null/missing values. No trailing commentary.\n\n"
        "## BIDS conversion complete\n"
        f"Source: `{dicom_root}` → Output: `{output_dir}`\n\n"
        "### Overview\n"
        "Render a two-column table: Metric | Value\n"
        "Rows (in order, use the exact labels):\n"
        f"  DICOM input | {dicom_n_patients} patients · {dicom_n_studies} studies · {dicom_n_series} series\n"  # noqa: E501
        f"  BIDS output | {n_subjects} subjects · {n_sessions} sessions · {sum(datatype_counts.values())} series\n"  # noqa: E501
        f"  Files written | {len(all_files)}\n"
        f"  Dataset name | {resolved_name}\n"
        f"  Output path | {output_dir}\n\n"
        "### Dataset structure\n"
        "Render two side-by-side tables (or sequential):\n"
        "  Table 1 — Datatype | Series — from result['datatype_counts'], sorted by series desc.\n"
        "  Table 2 — Suffix | Series — from result['suffix_counts'], sorted by series desc.\n\n"
        + (
            "### Per-subject breakdown\n"
            "Render a table: Subject | Sessions | Series | Datatypes — from result['subject_summary'].\n"  # noqa: E501
            "Datatypes column: comma-separated. Include all subjects.\n\n"
            if not large_dataset
            else (
                "### Subject summary\n"
                f"There are {n_subjects} subjects — too many to list individually.\n"
                "Render a small table from result['series_per_subject'] with two columns "
                "Metric | Value and three rows:\n"
                "  Fewest series (any subject) | <min>\n"
                "  Median series per subject   | <median>\n"
                "  Most series (any subject)   | <max>\n\n"
            )
        )
        + (
            "### Exceptions\n"
            + (
                f"**Unclassified series ({len(unclassified)} total):** "
                "Could not match a BIDS suffix. Placed in anat/ with fallback suffix. "
                "Grouped by series description from result['unclassified_grouped'] — render as: "
                "Description | Count. Ask the user how to handle them.\n\n"
                if unclassified
                else ""
            )
            + (
                f"**Non-standard modalities ({len(non_bids_standard)} series):** "
                "Placed in BIDS-like layout but will not pass BIDS validation. "
                "From result['non_bids_grouped'] render as: Modality | Series.\n\n"
                if non_bids_standard
                else ""
            )
            + (
                f"**ASL series requiring manual review ({len(asl_needs_review)}):** "
                "A placeholder aslcontext.tsv was written for each. "
                "Remind the user to edit these files to match actual volume types "
                "(control/label/m0scan). Files are listed in result['asl_needs_review'].\n\n"
                if asl_needs_review
                else ""
            )
            if (unclassified or non_bids_standard or asl_needs_review)
            else ""
        )
        + "NEXT ACTION: Display all sections above, then stop."
    )

    return {
        "output_dir": str(output_dir),
        "dataset_name": resolved_name,
        "subjects": n_subjects,
        "sessions": n_sessions,
        "total_series": sum(datatype_counts.values()),
        "files_created": len(all_files),
        "dicom_input": {
            "patients": dicom_n_patients,
            "studies": dicom_n_studies,
            "series": dicom_n_series,
        },
        "datatype_counts": dict(datatype_counts.most_common()),
        "suffix_counts": dict(suffix_counts.most_common()),
        "subject_summary": subject_summary_out,
        "series_per_subject": series_per_subject,
        "unclassified": unclassified,
        "unclassified_grouped": unclassified_grouped,
        "asl_needs_review": asl_needs_review,
        "non_bids_standard": non_bids_standard,
        "non_bids_grouped": non_bids_grouped,
        "_render": render,
    }
