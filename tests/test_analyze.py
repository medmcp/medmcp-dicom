"""Tests for convert_to_nifti (Analyze 7.5 / NIfTI-1 pairs) with synthetic fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

from medmcp_dicom.tools.analyze import convert_to_nifti
from medmcp_dicom.tools.inspect_nifti import inspect_nifti


def _analyze(path: Path, shape: tuple[int, ...] = (4, 5, 6)) -> Any:
    data = np.arange(int(np.prod(shape)), dtype=np.int16).reshape(shape)
    img: Any = nib.AnalyzeImage(data, np.diag([2.0, 3.0, 4.0, 1.0]))  # type: ignore[reportUnknownMemberType]
    img.header.set_zooms((2.0, 3.0, 4.0, 2.5)[: len(shape)])
    nib.save(img, str(path))  # type: ignore[reportUnknownMemberType]
    return data


def _nifti_pair(path: Path) -> Any:
    data = np.arange(60, dtype=np.int16).reshape(3, 4, 5)
    affine = np.array([[0, 0, -1.5, 10], [1.0, 0, 0, -5], [0, -2.0, 0, 7], [0, 0, 0, 1]])
    img: Any = nib.Nifti1Pair(data, affine)  # type: ignore[reportUnknownMemberType]
    img.header.set_sform(affine, 1)
    img.header.set_slope_inter(2.5, 10.0)
    nib.save(img, str(path))  # type: ignore[reportUnknownMemberType]
    return affine


def _load(path: str) -> Any:
    return nib.load(path)  # type: ignore[reportUnknownMemberType]


def test_analyze_without_orientation_is_flagged(tmp_path: Path) -> None:
    """Analyze 7.5: data, zooms and dtype kept; orientation reported as assumed."""
    data = _analyze(tmp_path / "s1.hdr")
    r = convert_to_nifti(tmp_path / "s1.img", tmp_path / "out")
    (item,) = r["written"]
    assert item["header_type"] == "Analyze 7.5"
    assert item["orientation_assumed"] is True
    assert item["orientation"] == "LAS"
    assert any("left/right may be flipped" in t for t in r["tell_the_user"])
    assert all(len(t) <= 120 for t in r["tell_the_user"])
    out = _load(item["output"])
    assert out.get_data_dtype() == np.int16
    assert np.array_equal(np.asanyarray(out.dataobj), data)
    assert tuple(float(z) for z in out.header.get_zooms()) == (2.0, 3.0, 4.0)


def test_nifti_pair_keeps_sform_and_scaling(tmp_path: Path) -> None:
    """NIfTI-1 pair with sform: affine, scl_slope/inter and raw dtype preserved."""
    affine = _nifti_pair(tmp_path / "mpr-4.nifti.hdr")
    r = convert_to_nifti(tmp_path / "mpr-4.nifti.hdr", tmp_path / "out")
    (item,) = r["written"]
    assert Path(item["output"]).name == "mpr-4.nii.gz"
    assert item["header_type"] == "NIfTI-1 pair"
    assert item["sform_code"] == 1
    assert item["orientation_assumed"] is False
    assert item["orientation"] == "AIL"
    assert r["tell_the_user"] == []
    out = _load(item["output"])
    assert np.allclose(out.affine, affine)
    assert out.get_data_dtype() == np.int16
    assert (float(out.dataobj.slope), float(out.dataobj.inter)) == (2.5, 10.0)
    assert np.array_equal(out.dataobj.get_unscaled(), np.arange(60).reshape(3, 4, 5))


def test_4d_stays_4d_and_uppercase(tmp_path: Path) -> None:
    """A 4D pair with upper-case suffixes converts to a 4D .nii.gz."""
    _analyze(tmp_path / "run.hdr", shape=(3, 3, 3, 5))
    (tmp_path / "run.hdr").rename(tmp_path / "RUN.HDR")
    (tmp_path / "run.img").rename(tmp_path / "RUN.IMG")
    r = convert_to_nifti(tmp_path / "RUN.HDR", tmp_path / "out")
    (item,) = r["written"]
    assert _load(item["output"]).shape == (3, 3, 3, 5)


def test_spm_mat_sidecar_reported(tmp_path: Path) -> None:
    """An SPM .mat next to an Analyze pair is reported, not silently ignored."""
    _analyze(tmp_path / "a.hdr")
    (tmp_path / "a.mat").write_bytes(b"not read")
    r = convert_to_nifti(tmp_path / "a.hdr", tmp_path / "out")
    (item,) = r["written"]
    assert item["spm_mat_sidecar"] is True
    assert any(".mat" in t for t in r["tell_the_user"])


def test_folder_default_output_and_no_overwrite(tmp_path: Path) -> None:
    """Folder input: default sibling folder; existing outputs and orphans are skipped."""
    src = tmp_path / "raw"
    src.mkdir()
    _analyze(src / "a.hdr")
    _analyze(src / "b.hdr")
    (src / "lonely.img").write_bytes(b"\0" * 8)
    first = convert_to_nifti(src)
    assert first["output_dir"] == str(tmp_path / "raw_nifti")
    assert len(first["written"]) == 2
    out_a = tmp_path / "raw_nifti" / "a.nii.gz"
    out_a.write_bytes(b"keep me")
    (tmp_path / "raw_nifti" / "b.nii.gz").unlink()
    second = convert_to_nifti(src)
    assert [Path(w["output"]).name for w in second["written"]] == ["b.nii.gz"]
    reasons = {Path(s["source"]).name: s["reason"] for s in second["skipped"]}
    assert reasons["a.hdr"].startswith("output exists")
    assert reasons["lonely.img"] == "no matching .hdr"
    assert out_a.read_bytes() == b"keep me"
    assert sorted(p.name for p in src.iterdir()) == [
        "a.hdr",
        "a.img",
        "b.hdr",
        "b.img",
        "lonely.img",
    ]


def test_inspect_nifti_accepts_pairs(tmp_path: Path) -> None:
    """inspect_nifti reports the format of .hdr/.img pairs."""
    _analyze(tmp_path / "s.hdr")
    _nifti_pair(tmp_path / "p.nifti.hdr")
    a = inspect_nifti(tmp_path / "s.img")
    assert a["format"] == "Analyze 7.5"
    assert a["orientation_assumed"] is True
    assert a["nifti_version"] is None
    p = inspect_nifti(tmp_path / "p.nifti.hdr")
    assert p["format"] == "NIfTI-1 pair"
    assert p["orientation_assumed"] is False
