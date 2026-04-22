"""Tests for DICOM domain tools."""

from pathlib import Path

import pydicom
import pydicom.uid
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset

from medmcp_dicom.tools.explore import explore_data


def _write_dicom(
    path: Path,
    *,
    patient_id: str,
    study_uid: str,
    series_uid: str,
    modality: str = "CT",
    study_date: str = "20240101",
    study_description: str = "Test Study",
    series_description: str = "Test Series",
    series_number: str = "1",
    body_part: str = "",
    rows: int = 512,
    columns: int = 512,
) -> None:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\x00" * 128)

    ds.PatientID = patient_id
    ds.PatientName = f"Patient^{patient_id}"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    ds.SOPClassUID = pydicom.uid.CTImageStorage
    ds.Modality = modality
    ds.StudyDate = study_date
    ds.StudyDescription = study_description
    ds.SeriesDescription = series_description
    ds.SeriesNumber = series_number
    if body_part:
        ds.BodyPartExamined = body_part
    ds.Rows = rows
    ds.Columns = columns
    ds.PixelSpacing = [0.5, 0.5]
    ds.SliceThickness = 1.0

    pydicom.dcmwrite(str(path), ds)  # type: ignore[misc]


@pytest.fixture()
def dicom_dir(tmp_path: Path) -> Path:
    """Two patients, one study each, one series each (3 and 5 slices)."""
    study_a = pydicom.uid.generate_uid()
    series_a = pydicom.uid.generate_uid()
    study_b = pydicom.uid.generate_uid()
    series_b = pydicom.uid.generate_uid()

    for i in range(3):
        _write_dicom(
            tmp_path / f"p1_s{i}.dcm",
            patient_id="P001",
            study_uid=study_a,
            series_uid=series_a,
            modality="CT",
        )
    for i in range(5):
        _write_dicom(
            tmp_path / f"p2_s{i}.dcm",
            patient_id="P002",
            study_uid=study_b,
            series_uid=series_b,
            modality="MR",
        )

    (tmp_path / "not_a_dicom.txt").write_text("ignore me")
    return tmp_path


def test_summary_counts(dicom_dir: Path) -> None:
    """Summary counts match the written fixture."""
    result = explore_data(dicom_dir)
    s = result["summary"]
    assert s["patients"] == 2
    assert s["studies"] == 2
    assert s["series"] == 2
    assert s["instances"] == 8
    assert s["skipped_files"] == 1


def test_summary_aggregations(dicom_dir: Path) -> None:
    """Summary carries modality breakdown, non_imaging, and date range."""
    result = explore_data(dicom_dir)
    s = result["summary"]
    breakdown = s["modality_breakdown"]
    modalities_in_breakdown = {r["modality"] for r in breakdown}
    assert modalities_in_breakdown == {"CT", "MR"}
    assert all(r["series"] >= 1 for r in breakdown)
    assert s["non_imaging"] == {}
    assert s["study_date_range"] == {"min": "2024-01-01", "max": "2024-01-01"}


def test_summary_only_omits_patients(dicom_dir: Path) -> None:
    """summary_only=True returns correct counts but an empty patients list."""
    result = explore_data(dicom_dir, summary_only=True)
    assert result["summary"]["patients"] == 2
    assert result["summary"]["series"] == 2
    assert result["patients"] == []


def test_phi_excluded_by_default(dicom_dir: Path) -> None:
    """Real patient IDs are not exposed when include_phi=False."""
    result = explore_data(dicom_dir, summary_only=False)
    for patient in result["patients"]:
        assert patient["patient_id"].startswith("PATIENT_")
        assert "patient_name" not in patient


def test_phi_included_when_requested(dicom_dir: Path) -> None:
    """Real patient IDs and names are present when include_phi=True."""
    result = explore_data(dicom_dir, include_phi=True, summary_only=False)
    ids = {p["patient_id"] for p in result["patients"]}
    assert "P001" in ids
    assert "P002" in ids
    for patient in result["patients"]:
        assert "patient_name" in patient


def test_series_metadata(dicom_dir: Path) -> None:
    """Series entries carry the expected metadata fields."""
    result = explore_data(dicom_dir, include_phi=True, summary_only=False)
    ct_patient = next(p for p in result["patients"] if p["patient_id"] == "P001")
    series = ct_patient["studies"][0]["series"][0]

    assert series["modality"] == "CT"
    assert series["instances"] == 3
    assert series["shape"] == [512, 512]
    assert series["pixel_spacing_mm"] == [0.5, 0.5]
    assert series["slice_thickness_mm"] == pytest.approx(1.0)  # type: ignore[misc]
    assert series["body_part"] is None
    assert "series_uid" in series
    assert isinstance(series["series_uid"], str)


def test_body_part_examined(tmp_path: Path) -> None:
    """BodyPartExamined tag is returned when present, None when absent."""
    uid = pydicom.uid.generate_uid()
    _write_dicom(
        tmp_path / "chest.dcm",
        patient_id="P1",
        study_uid=uid,
        series_uid=pydicom.uid.generate_uid(),
        body_part="CHEST",
    )
    _write_dicom(
        tmp_path / "no_tag.dcm",
        patient_id="P2",
        study_uid=uid,
        series_uid=pydicom.uid.generate_uid(),
    )

    result = explore_data(tmp_path, include_phi=True, summary_only=False)
    series_by_patient = {p["patient_id"]: p["studies"][0]["series"][0] for p in result["patients"]}
    assert series_by_patient["P1"]["body_part"] == "CHEST"
    assert series_by_patient["P2"]["body_part"] is None


def test_empty_directory(tmp_path: Path) -> None:
    """Empty directory returns zero counts without error."""
    result = explore_data(tmp_path)
    assert result["summary"] == {
        "patients": 0,
        "studies": 0,
        "series": 0,
        "instances": 0,
        "skipped_files": 0,
        "study_date_range": None,
        "modality_breakdown": [],
        "non_imaging": {},
    }
    assert result["patients"] == []


def test_non_dicom_files_counted_as_skipped(tmp_path: Path) -> None:
    """Non-DICOM files increment skipped_files, not instances."""
    (tmp_path / "report.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "image.jpg").write_bytes(b"\xff\xd8\xff fake")
    result = explore_data(tmp_path)
    assert result["summary"]["skipped_files"] == 2
    assert result["summary"]["instances"] == 0


def test_nonexistent_directory_raises(tmp_path: Path) -> None:
    """Non-existent root_dir raises ValueError instead of silently returning empty."""
    with pytest.raises(ValueError, match="does not exist"):
        explore_data(tmp_path / "does_not_exist")


def test_recursive_scan(tmp_path: Path) -> None:
    """DICOM files in nested subdirectories are included in the scan."""
    subdir = tmp_path / "subdir" / "nested"
    subdir.mkdir(parents=True)
    uid = pydicom.uid.generate_uid()
    _write_dicom(
        subdir / "slice.dcm", patient_id="P1", study_uid=uid, series_uid=pydicom.uid.generate_uid()
    )
    result = explore_data(tmp_path)
    assert result["summary"]["instances"] == 1


def test_patients_sorted_by_id(tmp_path: Path) -> None:
    """Patient order is deterministic (sorted by patient_id), not by scan order."""
    for pid in ("C001", "A001", "B001"):
        _write_dicom(
            tmp_path / f"{pid}.dcm",
            patient_id=pid,
            study_uid=pydicom.uid.generate_uid(),
            series_uid=pydicom.uid.generate_uid(),
        )
    result = explore_data(tmp_path, include_phi=True, summary_only=False)
    ids = [p["patient_id"] for p in result["patients"]]
    assert ids == ["A001", "B001", "C001"]


def test_studies_sorted_by_date(tmp_path: Path) -> None:
    """Studies within a patient are ordered chronologically by study_date."""
    for date in ("20230601", "20210101"):
        _write_dicom(
            tmp_path / f"study_{date}.dcm",
            patient_id="P1",
            study_uid=pydicom.uid.generate_uid(),
            series_uid=pydicom.uid.generate_uid(),
            study_date=date,
        )
    result = explore_data(tmp_path, include_phi=True, summary_only=False)
    dates = [s["study_date"] for s in result["patients"][0]["studies"]]
    assert dates == ["2021-01-01", "2023-06-01"]


def test_patient_name_formatted(tmp_path: Path) -> None:
    """PatientName is returned as 'Given Family', not raw DICOM 'Family^Given'."""
    uid = pydicom.uid.generate_uid()
    _write_dicom(
        tmp_path / "p.dcm",
        patient_id="P001",
        study_uid=uid,
        series_uid=pydicom.uid.generate_uid(),
    )
    result = explore_data(tmp_path, include_phi=True, summary_only=False)
    # _write_dicom sets PatientName = "Patient^P001" → formatted as "P001 Patient"
    assert result["patients"][0]["patient_name"] == "P001 Patient"


def test_series_sorted_by_series_number(tmp_path: Path) -> None:
    """Series within a study are returned ordered by SeriesNumber."""
    study_uid = pydicom.uid.generate_uid()
    for number in ("3", "1", "2"):
        _write_dicom(
            tmp_path / f"series_{number}.dcm",
            patient_id="P1",
            study_uid=study_uid,
            series_uid=pydicom.uid.generate_uid(),
            series_number=number,
        )
    result = explore_data(tmp_path, include_phi=True, summary_only=False)
    series = result["patients"][0]["studies"][0]["series"]
    numbers = [s["series_number"] for s in series]
    assert numbers == ["1", "2", "3"]
