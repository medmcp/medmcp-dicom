"""Tests for the explore_bids tool."""

import gzip
import json
from pathlib import Path

import pytest

from medmcp_dicom.tools.explore_bids import explore_bids


def _write_nifti(path: Path, content: bytes = b"\x00" * 8) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as f:
        f.write(content)


def _write_desc(bids_root: Path, name: str = "TestDataset", version: str = "1.9.0") -> None:
    (bids_root / "dataset_description.json").write_text(
        json.dumps({"Name": name, "BIDSVersion": version})
    )


@pytest.fixture()
def bids_dir(tmp_path: Path) -> Path:
    """Two subjects, two sessions each, anat T1w + func bold per session."""
    _write_desc(tmp_path)
    for sub in ("001", "002"):
        for ses in ("01", "02"):
            _write_nifti(
                tmp_path / f"sub-{sub}" / f"ses-{ses}" / "anat" / f"sub-{sub}_ses-{ses}_T1w.nii.gz"
            )
            _write_nifti(
                tmp_path
                / f"sub-{sub}"
                / f"ses-{ses}"
                / "func"
                / f"sub-{sub}_ses-{ses}_task-rest_bold.nii.gz"
            )
    return tmp_path


@pytest.fixture()
def sessionless_bids_dir(tmp_path: Path) -> Path:
    """One subject, no sessions, one anat series."""
    _write_nifti(tmp_path / "sub-001" / "anat" / "sub-001_T1w.nii.gz")
    return tmp_path


def test_summary_counts(bids_dir: Path) -> None:
    """Summary counts match the written fixture."""
    result = explore_bids(bids_dir)
    s = result["summary"]
    assert s["subjects"] == 2
    assert s["sessions"] == 4
    assert s["series"] == 8


def test_summary_only_omits_subjects(bids_dir: Path) -> None:
    """summary_only=True returns correct counts but an empty subjects list."""
    result = explore_bids(bids_dir, summary_only=True)
    assert result["subjects"] == []
    assert result["summary"]["subjects"] == 2


def test_datatype_breakdown(bids_dir: Path) -> None:
    """Datatype breakdown aggregates series counts by (datatype, suffix)."""
    s = explore_bids(bids_dir)["summary"]
    breakdown = {(r["datatype"], r["suffix"]): r["series"] for r in s["datatype_breakdown"]}
    assert breakdown[("anat", "T1w")] == 4
    assert breakdown[("func", "bold")] == 4


def test_dataset_description_read(bids_dir: Path) -> None:
    """Name and BIDSVersion are read from dataset_description.json."""
    s = explore_bids(bids_dir)["summary"]
    assert s["dataset_name"] == "TestDataset"
    assert s["bids_version"] == "1.9.0"


def test_no_dataset_description(sessionless_bids_dir: Path) -> None:
    """dataset_name and bids_version are None when dataset_description.json is absent."""
    s = explore_bids(sessionless_bids_dir)["summary"]
    assert s["dataset_name"] is None
    assert s["bids_version"] is None


def test_sessionless_subject(sessionless_bids_dir: Path) -> None:
    """Subjects without ses-* dirs are counted with sessions=0."""
    s = explore_bids(sessionless_bids_dir)["summary"]
    assert s["subjects"] == 1
    assert s["sessions"] == 0
    assert s["series"] == 1


def test_per_subject_detail(bids_dir: Path) -> None:
    """summary_only=False returns per-subject session and series detail."""
    result = explore_bids(bids_dir, summary_only=False)
    assert len(result["subjects"]) == 2
    sub = result["subjects"][0]
    assert sub["subject"].startswith("sub-")
    assert len(sub["sessions"]) == 2
    session = sub["sessions"][0]
    assert "session" in session
    assert session["series_count"] == 2
    filenames = {s["filename"] for s in session["series"]}
    assert any(f.endswith("_T1w.nii.gz") for f in filenames)
    assert any(f.endswith("_bold.nii.gz") for f in filenames)


def test_sessionless_per_subject_detail(sessionless_bids_dir: Path) -> None:
    """Session-less subjects have no 'session' key in their session entry."""
    result = explore_bids(sessionless_bids_dir, summary_only=False)
    sub = result["subjects"][0]
    session = sub["sessions"][0]
    assert "session" not in session
    assert session["series_count"] == 1
    assert session["series"][0]["suffix"] == "T1w"
    assert session["series"][0]["datatype"] == "anat"


def test_empty_bids_dir(tmp_path: Path) -> None:
    """Empty directory returns zero counts without error."""
    result = explore_bids(tmp_path)
    assert result["summary"] == {
        "subjects": 0,
        "sessions": 0,
        "series": 0,
        "dataset_name": None,
        "bids_version": None,
        "datatype_breakdown": [],
    }
    assert result["subjects"] == []


def test_nonexistent_dir_raises(tmp_path: Path) -> None:
    """Non-existent bids_dir raises ValueError."""
    with pytest.raises(ValueError, match="does not exist"):
        explore_bids(tmp_path / "does_not_exist")


def test_render_key_present(bids_dir: Path) -> None:
    """Result always contains a _render key with a NEXT ACTION directive."""
    result = explore_bids(bids_dir)
    assert "_render" in result
    assert "NEXT ACTION" in result["_render"]


def test_subjects_sorted(tmp_path: Path) -> None:
    """Subject order is deterministic (sorted by label), not by scan order."""
    for sub in ("003", "001", "002"):
        _write_nifti(tmp_path / f"sub-{sub}" / "anat" / f"sub-{sub}_T1w.nii.gz")
    result = explore_bids(tmp_path, summary_only=False)
    labels = [s["subject"] for s in result["subjects"]]
    assert labels == ["sub-001", "sub-002", "sub-003"]
