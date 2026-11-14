"""convert_dcm_to_nifti keeps dcm2niix's warnings instead of dropping them."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from medmcp_dicom.tools.convert import convert_dcm_to_nifti, dcm2niix_messages


def test_messages_are_kept_and_deduplicated() -> None:
    """Warning and error lines are returned once each; chatter is not."""
    out = "Chris Rorden's dcm2niiX\nWarning: Missing images? Expected 64 got 63\n"
    err = "Warning: Missing images? Expected 64 got 63\nError: Unable to find any DICOM\n"
    assert dcm2niix_messages(out, err) == [
        "Warning: Missing images? Expected 64 got 63",
        "Error: Unable to find any DICOM",
    ]


def test_warnings_reach_the_result(tmp_path: Path) -> None:
    """A conversion that produced a volume reports dcm2niix's warning."""
    src = tmp_path / "dicom"
    src.mkdir()
    out = tmp_path / "out"

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        out.mkdir(parents=True, exist_ok=True)
        (out / "001_T1.nii.gz").write_bytes(b"x")
        return subprocess.CompletedProcess(cmd, 0, "Warning: Slice spacing varies\n", "")

    with (
        patch("medmcp_dicom.tools.convert.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch("medmcp_dicom.tools.convert.subprocess.run", side_effect=fake_run),
    ):
        res = convert_dcm_to_nifti(src, out)
    assert res["total_series"] == 1
    assert res["warnings"] == ["Warning: Slice spacing varies"]
    assert "word for word" in res["_render"]


def test_failed_conversion_raises_with_the_reason(tmp_path: Path) -> None:
    """No output and a non-zero exit is an error carrying dcm2niix's message."""
    src = tmp_path / "dicom"
    src.mkdir()

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 2, "", "Error: Unable to find any DICOM images\n")

    with (
        patch("medmcp_dicom.tools.convert.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch("medmcp_dicom.tools.convert.subprocess.run", side_effect=fake_run),
        pytest.raises(RuntimeError, match="Unable to find any DICOM"),
    ):
        convert_dcm_to_nifti(src, tmp_path / "out")
