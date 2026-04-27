"""Tests for convert_dcm_to_nifti."""

from pathlib import Path
from unittest.mock import patch

import pydicom
import pydicom.uid
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset

from medmcp_dicom.tools.convert import convert_dcm_to_nifti


def _write_dicom(
    path: Path,
    *,
    patient_id: str = "P001",
    study_uid: str | None = None,
    series_uid: str | None = None,
    modality: str = "CT",
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
    ds.StudyDate = "20240101"
    ds.SeriesNumber = "1"
    ds.SeriesDescription = "Test"
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


def test_raises_when_dcm2niix_missing(tmp_path: Path) -> None:
    """RuntimeError is raised with install instructions when dcm2niix is absent."""
    with (
        patch("medmcp_dicom.tools.convert.find_dcm2niix", return_value=None),
        pytest.raises(RuntimeError, match="dcm2niix"),
    ):
        convert_dcm_to_nifti(tmp_path, tmp_path / "out")


def test_raises_on_missing_input_dir(tmp_path: Path) -> None:
    """ValueError is raised when input_dir does not exist."""
    with (
        patch("medmcp_dicom.tools.convert.find_dcm2niix", return_value="/fake/dcm2niix"),
        pytest.raises(ValueError, match="does not exist"),
    ):
        convert_dcm_to_nifti(tmp_path / "no_such_dir", tmp_path / "out")


def test_output_dir_created_if_absent(tmp_path: Path) -> None:
    """output_dir is created even if dcm2niix produces nothing."""
    _write_dicom(tmp_path / "slice.dcm")
    out = tmp_path / "new" / "output"
    with (
        patch("medmcp_dicom.tools.convert.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch("medmcp_dicom.tools.convert.subprocess.run"),
    ):
        result = convert_dcm_to_nifti(tmp_path, out)
    assert out.is_dir()
    assert result["total_series"] == 0


def test_result_has_render_key(tmp_path: Path) -> None:
    """Result always contains a '_render' key."""
    with (
        patch("medmcp_dicom.tools.convert.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch("medmcp_dicom.tools.convert.subprocess.run"),
    ):
        result = convert_dcm_to_nifti(tmp_path, tmp_path / "out")
    assert "_render" in result
    assert "NEXT ACTION" in result["_render"]


def test_integration_converts_dicom(tmp_path: Path) -> None:
    """Integration: actual DICOM files are converted to NIfTI by dcm2niix."""
    series_uid = pydicom.uid.generate_uid()
    study_uid = pydicom.uid.generate_uid()
    for i in range(3):
        _write_dicom(
            tmp_path / f"slice_{i}.dcm",
            study_uid=study_uid,
            series_uid=series_uid,
            slice_index=i,
        )
    out = tmp_path / "nifti"
    result = convert_dcm_to_nifti(tmp_path, out)
    assert result["total_series"] >= 1
    nifti_files = list(out.glob("*.nii.gz"))
    assert len(nifti_files) >= 1
