"""Tests for inspect_nifti."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
import numpy.typing as npt
import pytest

from medmcp_dicom.tools.inspect_nifti import inspect_nifti


def _save_nifti(
    path: Path,
    shape: tuple[int, ...],
    *,
    dtype: npt.DTypeLike = np.int16,
    voxel_size: tuple[float, ...] = (1.0, 1.0, 1.0),
    tr: float | None = None,
    version: int = 1,
) -> None:
    data = np.zeros(shape, dtype=dtype)
    affine = np.diag([*list(voxel_size[:3]), 1.0])
    img: nib.Nifti1Image | nib.Nifti2Image = (  # type: ignore[reportUnknownMemberType]
        nib.Nifti2Image(data, affine) if version == 2 else nib.Nifti1Image(data, affine)
    )
    zooms: list[float] = list(voxel_size[:3])
    if tr is not None:
        zooms.append(tr)
    img.header.set_zooms(zooms)
    nib.save(img, str(path))  # type: ignore[reportUnknownMemberType]


def test_3d_basic(tmp_path: Path) -> None:
    """3D image returns correct shape with no TR and no volume count."""
    p = tmp_path / "brain.nii.gz"
    _save_nifti(p, (256, 256, 176), voxel_size=(1.0, 1.0, 1.0))
    result = inspect_nifti(p)
    assert result["shape"] == [256, 256, 176]
    assert result["tr_sec"] is None
    assert result["n_volumes"] is None
    assert result["nifti_version"] == 1


def test_4d_tr_and_volumes(tmp_path: Path) -> None:
    """4D image returns TR in seconds and volume count."""
    p = tmp_path / "bold.nii.gz"
    _save_nifti(p, (64, 64, 36, 200), voxel_size=(2.0, 2.0, 3.0), tr=2.5)
    result = inspect_nifti(p)
    assert result["shape"] == [64, 64, 36, 200]
    assert result["n_volumes"] == 200
    assert result["tr_sec"] == pytest.approx(2.5, abs=1e-3)  # type: ignore[reportUnknownMemberType]


def test_voxel_size_rounded(tmp_path: Path) -> None:
    """Voxel sizes are rounded to 3 decimal places."""
    p = tmp_path / "img.nii"
    _save_nifti(p, (64, 64, 32), voxel_size=(1.123456, 1.123456, 2.456789))
    result = inspect_nifti(p)
    assert result["voxel_size_mm"] == [1.123, 1.123, 2.457]


def test_orientation_string(tmp_path: Path) -> None:
    """Orientation is a 3-character string."""
    p = tmp_path / "img.nii.gz"
    _save_nifti(p, (64, 64, 32))
    result = inspect_nifti(p)
    assert isinstance(result["orientation"], str)
    assert len(result["orientation"]) == 3


def test_dtype_name(tmp_path: Path) -> None:
    """Dtype reflects the numpy dtype name of the stored array."""
    p = tmp_path / "float.nii.gz"
    _save_nifti(p, (32, 32, 16), dtype=np.float32)
    result = inspect_nifti(p)
    assert result["dtype"] == "float32"


def test_render_key_present(tmp_path: Path) -> None:
    """Result always contains _render with NEXT ACTION."""
    p = tmp_path / "img.nii.gz"
    _save_nifti(p, (64, 64, 32))
    result = inspect_nifti(p)
    assert "_render" in result
    assert "NEXT ACTION" in result["_render"]


def test_render_omits_tr_line_for_3d(tmp_path: Path) -> None:
    """_render omits the TR line for a 3D image."""
    p = tmp_path / "img.nii.gz"
    _save_nifti(p, (64, 64, 32))
    result = inspect_nifti(p)
    assert "| TR |" not in result["_render"]


def test_render_includes_tr_line_for_4d(tmp_path: Path) -> None:
    """_render includes the TR line for a 4D image."""
    p = tmp_path / "bold.nii.gz"
    _save_nifti(p, (64, 64, 36, 100), tr=2.0)
    result = inspect_nifti(p)
    assert "| TR |" in result["_render"]


def test_nifti2_version_detected(tmp_path: Path) -> None:
    """NIfTI-2 files are reported as nifti_version == 2."""
    p = tmp_path / "v2.nii.gz"
    _save_nifti(p, (32, 32, 16), version=2)
    result = inspect_nifti(p)
    assert result["nifti_version"] == 2


def test_file_size_mb_non_negative(tmp_path: Path) -> None:
    """file_size_mb is a non-negative float."""
    p = tmp_path / "img.nii.gz"
    _save_nifti(p, (64, 64, 32))
    result = inspect_nifti(p)
    assert isinstance(result["file_size_mb"], float)
    assert result["file_size_mb"] >= 0.0


def test_raises_on_missing_file(tmp_path: Path) -> None:
    """FileNotFoundError is raised for a nonexistent path."""
    with pytest.raises(FileNotFoundError):
        inspect_nifti(tmp_path / "no_such_file.nii.gz")
