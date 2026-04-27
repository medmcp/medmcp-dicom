"""Tests for BIDS dataset tools — classification, label assignment, filename generation."""

from pathlib import Path
from unittest.mock import patch

import pydicom
import pydicom.uid
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset

from medmcp_dicom.tools._dicom import SeriesRecord, scan_series
from medmcp_dicom.tools.bids import (
    assign_labels,
    build_bids_dataset,
    classify_series,
    make_bids_filename,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_dicom(
    path: Path,
    *,
    patient_id: str = "P001",
    study_uid: str | None = None,
    series_uid: str | None = None,
    modality: str = "CT",
    study_date: str = "20240101",
    series_description: str = "Test Series",
    series_number: str = "1",
    slice_index: int = 0,
) -> None:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\x00" * 128)
    ds.PatientID = patient_id
    ds.StudyInstanceUID = study_uid or pydicom.uid.generate_uid()
    ds.SeriesInstanceUID = series_uid or pydicom.uid.generate_uid()
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    ds.SOPClassUID = pydicom.uid.CTImageStorage
    ds.Modality = modality
    ds.StudyDate = study_date
    ds.SeriesDescription = series_description
    ds.SeriesNumber = series_number
    ds.Rows = 64
    ds.Columns = 64
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.InstanceNumber = str(slice_index + 1)
    ds.ImagePositionPatient = [0.0, 0.0, float(slice_index)]
    ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    ds.PixelSpacing = [1.0, 1.0]
    ds.SliceThickness = 1.0
    ds.PixelData = bytes(64 * 64 * 2)
    pydicom.dcmwrite(str(path), ds)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# classify_series
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("modality", "description", "expected_datatype", "expected_suffix"),
    [
        ("MR", "T1w MPR", "anat", "T1w"),
        ("MR", "MPRAGE", "anat", "T1w"),
        ("MR", "t2_spc_1mm", "anat", "T2w"),
        ("MR", "FLAIR 3D", "anat", "FLAIR"),
        ("MR", "DWI b1000", "dwi", "dwi"),
        ("MR", "DTI 64 dirs", "dwi", "dwi"),
        ("MR", "resting state BOLD", "func", "bold"),
        ("MR", "task-memory_epi", "func", "bold"),
        ("MR", "fieldmap B0", "fmap", "magnitude"),
        ("MR", "TOF angio", "anat", "angio"),
        ("CT", "Head CT", "anat", "CT"),
        ("PT", "FDG-PET", "pet", "pet"),
        ("MG", "mammography", "anat", "MG"),
    ],
)
def test_classify_known_series(
    modality: str,
    description: str,
    expected_datatype: str,
    expected_suffix: str,
) -> None:
    """Known modality/description combinations map to the expected BIDS entities."""
    datatype, suffix, classified = classify_series(modality, description)
    assert datatype == expected_datatype
    assert suffix == expected_suffix
    assert classified is True


def test_classify_unknown_mr_returns_fallback() -> None:
    """Unrecognized MR series falls back to anat/T1w with classified=False."""
    datatype, suffix, classified = classify_series("MR", "localizer_scout")
    assert datatype == "anat"
    assert suffix == "T1w"
    assert classified is False


def test_classify_unknown_modality_returns_fallback() -> None:
    """Completely unknown modality falls back with classified=False."""
    _, _, classified = classify_series("XB", "weird sequence")
    assert classified is False


# ---------------------------------------------------------------------------
# make_bids_filename
# ---------------------------------------------------------------------------


def test_bids_filename_no_run() -> None:
    """No run index produces a simple sub_ses_suffix filename."""
    assert make_bids_filename("001", "01", "T1w", ".nii.gz") == "sub-001_ses-01_T1w.nii.gz"


def test_bids_filename_with_run() -> None:
    """run=2 inserts a zero-padded _run-02 entity."""
    assert (
        make_bids_filename("001", "01", "T1w", ".nii.gz", run=2)
        == "sub-001_ses-01_run-02_T1w.nii.gz"
    )


def test_bids_filename_json_extension() -> None:
    """JSON extension variant produces a valid BIDS sidecar filename."""
    assert make_bids_filename("002", "03", "bold", ".json") == "sub-002_ses-03_bold.json"


def test_bids_filename_empty_extension_produces_stem() -> None:
    """Empty extension returns the bare BIDS stem (useful for directory naming)."""
    stem = make_bids_filename("001", "01", "dwi", "")
    assert stem == "sub-001_ses-01_dwi"


# ---------------------------------------------------------------------------
# assign_labels
# ---------------------------------------------------------------------------


def _make_record(**kwargs: str) -> SeriesRecord:
    defaults = dict(
        patient_id="P001",
        study_uid="S001",
        study_date="20240101",
        series_uid="SR001",
        series_number="1",
        modality="CT",
        series_description="Test",
    )
    defaults.update(kwargs)
    return SeriesRecord(**defaults)  # type: ignore[arg-type]


def testassign_labels_single_patient_study() -> None:
    """Single patient/study produces sub-001 and ses-01."""
    records = [_make_record()]
    sub_map, ses_map = assign_labels(records)
    assert sub_map["P001"] == "001"
    assert ses_map["S001"] == "01"


def testassign_labels_subjects_are_sorted_alphabetically() -> None:
    """Subject labels are assigned in alphabetical order of patient_id."""
    records = [
        _make_record(patient_id="C", study_uid="S1"),
        _make_record(patient_id="A", study_uid="S2"),
        _make_record(patient_id="B", study_uid="S3"),
    ]
    sub_map, _ = assign_labels(records)
    assert sub_map["A"] == "001"
    assert sub_map["B"] == "002"
    assert sub_map["C"] == "003"


def testassign_labels_sessions_sorted_by_date() -> None:
    """Session labels within a subject reflect chronological study order."""
    records = [
        _make_record(patient_id="P", study_uid="S_later", study_date="20240601"),
        _make_record(patient_id="P", study_uid="S_earlier", study_date="20230101"),
    ]
    _, ses_map = assign_labels(records)
    assert ses_map["S_earlier"] == "01"
    assert ses_map["S_later"] == "02"


# ---------------------------------------------------------------------------
# scan_series (from _dicom.py)
# ---------------------------------------------------------------------------


def test_scan_series_groups_by_series_uid(tmp_path: Path) -> None:
    """Files sharing a SeriesInstanceUID are grouped into one SeriesRecord."""
    uid = pydicom.uid.generate_uid()
    for i in range(3):
        _write_dicom(tmp_path / f"slice_{i}.dcm", series_uid=uid)
    records, skipped = scan_series(tmp_path)
    assert len(records) == 1
    assert len(records[0].files) == 3
    assert skipped == 0


def test_scan_series_skips_non_dicom(tmp_path: Path) -> None:
    """Non-DICOM files are counted in skipped, not in records."""
    _write_dicom(tmp_path / "real.dcm")
    (tmp_path / "not_dicom.txt").write_text("ignore")
    records, skipped = scan_series(tmp_path)
    assert len(records) == 1
    assert skipped == 1


def test_scan_series_empty_directory(tmp_path: Path) -> None:
    """Empty directory returns empty records and zero skipped."""
    records, skipped = scan_series(tmp_path)
    assert records == []
    assert skipped == 0


def test_scan_series_captures_metadata(tmp_path: Path) -> None:
    """SeriesRecord carries the expected metadata fields from DICOM headers."""
    _write_dicom(
        tmp_path / "s.dcm",
        patient_id="PATIENT_A",
        study_date="20240315",
        modality="MR",
        series_description="T1w MPR",
        series_number="2",
    )
    records, _ = scan_series(tmp_path)
    rec = records[0]
    assert rec.patient_id == "PATIENT_A"
    assert rec.study_date == "20240315"
    assert rec.modality == "MR"
    assert rec.series_description == "T1w MPR"
    assert rec.series_number == "2"


# ---------------------------------------------------------------------------
# build_bids_dataset — unit tests (dcm2niix mocked)
# ---------------------------------------------------------------------------


def test_build_raises_when_dcm2niix_missing(tmp_path: Path) -> None:
    """RuntimeError is raised with install instructions when dcm2niix is absent."""
    with (
        patch("medmcp_dicom.tools.bids.find_dcm2niix", return_value=None),
        pytest.raises(RuntimeError, match="dcm2niix"),
    ):
        build_bids_dataset(tmp_path, tmp_path / "bids")


def test_build_raises_on_missing_dicom_root(tmp_path: Path) -> None:
    """ValueError is raised when dicom_root does not exist."""
    with (
        patch("medmcp_dicom.tools.bids.find_dcm2niix", return_value="/fake/dcm2niix"),
        pytest.raises(ValueError, match="does not exist"),
    ):
        build_bids_dataset(tmp_path / "no_such", tmp_path / "bids")


def test_build_raises_when_output_inside_dicom_root(tmp_path: Path) -> None:
    """ValueError is raised when output_dir is nested inside dicom_root."""
    with (
        patch("medmcp_dicom.tools.bids.find_dcm2niix", return_value="/fake/dcm2niix"),
        pytest.raises(ValueError, match="must not be inside"),
    ):
        build_bids_dataset(tmp_path, tmp_path / "bids")


def test_build_empty_directory_returns_zero_subjects(tmp_path: Path) -> None:
    """Empty dicom_root returns a result with zero subjects without error."""
    dicom_root = tmp_path / "dicom"
    dicom_root.mkdir()
    with patch("medmcp_dicom.tools.bids.find_dcm2niix", return_value="/fake/dcm2niix"):
        result = build_bids_dataset(dicom_root, tmp_path / "bids")
    assert result["subjects"] == 0
    assert result["sessions"] == 0
    assert "NEXT ACTION" in result["_render"]


def test_build_creates_dataset_description(tmp_path: Path) -> None:
    """dataset_description.json is written to the BIDS root."""
    dicom_root = tmp_path / "dicom"
    dicom_root.mkdir()
    _write_dicom(dicom_root / "s.dcm", series_description="T1w MPR", modality="MR")
    bids_root = tmp_path / "bids"

    # Mock _convert_series so no dcm2niix subprocess is launched
    with (
        patch("medmcp_dicom.tools.bids.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch("medmcp_dicom.tools.bids._convert_series", return_value=[]),
    ):
        build_bids_dataset(dicom_root, bids_root, dataset_name="TestDS")

    import json

    desc = json.loads((bids_root / "dataset_description.json").read_text())
    assert desc["Name"] == "TestDS"
    assert desc["BIDSVersion"] == "1.9.0"


def test_build_default_dataset_name_derived_from_root(tmp_path: Path) -> None:
    """dataset_name defaults to <dicom_root.name>_bids when not provided."""
    dicom_root = tmp_path / "my_study"
    dicom_root.mkdir()
    _write_dicom(dicom_root / "s.dcm", series_description="T1w MPR", modality="MR")
    bids_root = tmp_path / "bids"

    import json

    with (
        patch("medmcp_dicom.tools.bids.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch("medmcp_dicom.tools.bids._convert_series", return_value=[]),
    ):
        build_bids_dataset(dicom_root, bids_root)

    desc = json.loads((bids_root / "dataset_description.json").read_text())
    assert desc["Name"] == "my_study_bids"


def test_build_creates_participants_tsv_anonymized(tmp_path: Path) -> None:
    """participants.tsv contains only sub-XXX labels when anonymize=True."""
    dicom_root = tmp_path / "dicom"
    dicom_root.mkdir()
    _write_dicom(
        dicom_root / "s.dcm", patient_id="REAL_ID", modality="MR", series_description="T1w"
    )
    bids_root = tmp_path / "bids"

    with (
        patch("medmcp_dicom.tools.bids.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch("medmcp_dicom.tools.bids._convert_series", return_value=[]),
    ):
        build_bids_dataset(dicom_root, bids_root, anonymize=True)

    tsv_text = (bids_root / "participants.tsv").read_text()
    assert "REAL_ID" not in tsv_text
    assert "sub-001" in tsv_text


def test_build_participants_tsv_non_anonymized(tmp_path: Path) -> None:
    """participants.tsv includes source_patient_id column when anonymize=False."""
    dicom_root = tmp_path / "dicom"
    dicom_root.mkdir()
    _write_dicom(
        dicom_root / "s.dcm", patient_id="REAL_ID", modality="MR", series_description="T1w"
    )
    bids_root = tmp_path / "bids"

    with (
        patch("medmcp_dicom.tools.bids.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch("medmcp_dicom.tools.bids._convert_series", return_value=[]),
    ):
        build_bids_dataset(dicom_root, bids_root, anonymize=False)

    tsv_text = (bids_root / "participants.tsv").read_text()
    assert "source_patient_id" in tsv_text
    assert "REAL_ID" in tsv_text


def test_build_assigns_run_numbers_for_duplicate_suffixes(tmp_path: Path) -> None:
    """Two MR series with the same unrecognized description both get _run-NN labels."""
    dicom_root = tmp_path / "dicom"
    dicom_root.mkdir()
    study_uid = pydicom.uid.generate_uid()
    for i in range(2):
        _write_dicom(
            dicom_root / f"localizer_{i}.dcm",
            patient_id="P",
            study_uid=study_uid,
            series_uid=pydicom.uid.generate_uid(),  # different series
            modality="MR",
            series_description="localizer",  # same description → same fallback suffix
            series_number=str(i + 1),
        )
    bids_root = tmp_path / "bids"

    def fake_convert(
        files: list[Path], out_dir: Path, stem: str, exe: str, *, multi_label: str = "echo"
    ) -> list[Path]:
        nii = out_dir / f"{stem}.nii.gz"
        nii.touch()
        return [nii]

    with (
        patch("medmcp_dicom.tools.bids.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch("medmcp_dicom.tools.bids._convert_series", side_effect=fake_convert),
    ):
        build_bids_dataset(dicom_root, bids_root)

    nii_files = list(bids_root.rglob("*.nii.gz"))
    run_files = [f for f in nii_files if "run-" in f.name]
    assert len(run_files) == 2


def test_build_result_has_render_key(tmp_path: Path) -> None:
    """Result always contains a '_render' key with NEXT ACTION."""
    dicom_root = tmp_path / "dicom"
    dicom_root.mkdir()
    with patch("medmcp_dicom.tools.bids.find_dcm2niix", return_value="/fake/dcm2niix"):
        result = build_bids_dataset(dicom_root, tmp_path / "bids")
    assert "_render" in result
    assert "NEXT ACTION" in result["_render"]


# ---------------------------------------------------------------------------
# build_bids_dataset — integration test (requires dcm2niix)
# ---------------------------------------------------------------------------


def test_integration_full_bids_pipeline(tmp_path: Path) -> None:
    """Integration: DICOM files are converted and organised into a BIDS tree."""
    dicom_root = tmp_path / "dicom"
    dicom_root.mkdir()
    study_uid = pydicom.uid.generate_uid()
    series_uid = pydicom.uid.generate_uid()
    for i in range(3):
        _write_dicom(
            dicom_root / f"slice_{i}.dcm",
            patient_id="P001",
            study_uid=study_uid,
            series_uid=series_uid,
            modality="MR",
            series_description="T1w MPR",
            slice_index=i,
        )
    bids_root = tmp_path / "bids"
    result = build_bids_dataset(dicom_root, bids_root, dataset_name="IntegrationTest")

    assert result["subjects"] == 1
    assert result["sessions"] == 1
    assert (bids_root / "dataset_description.json").exists()
    assert (bids_root / "participants.tsv").exists()
    niftis = list(bids_root.rglob("*.nii.gz"))
    assert len(niftis) >= 1
    assert "sub-001" in niftis[0].parts
