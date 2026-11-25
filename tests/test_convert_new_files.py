"""convert_dcm_to_nifti reports only the files it wrote, not older ones in the folder."""

import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import jsonschema
from mcp.shared.memory import create_connected_server_and_client_session

from medmcp_dicom.server import mcp
from medmcp_dicom.tools.convert import convert_dcm_to_nifti


def _fake_dcm2niix(out: Path, name: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Mimic dcm2niix: never overwrite, append a letter to the name instead."""

    def run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        stem = name
        for suffix in ("", *"abcdefghij"):
            if not (out / f"{name}{suffix}.nii.gz").exists():
                stem = f"{name}{suffix}"
                break
        (out / f"{stem}.nii.gz").write_bytes(b"new")
        (out / f"{stem}.json").write_text('{"SeriesDescription": "Sag_T2", "Modality": "MR"}')
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return run


def _stale_folder(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "dicom"
    src.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    old = time.time() - 2 * 86400
    for name in ("001_Sag_T2.nii.gz", "segmentation.nii.gz"):
        (out / name).write_bytes(b"old")
        os.utime(out / name, (old, old))
    return src, out


def test_preexisting_files_are_not_reported_as_converted(tmp_path: Path) -> None:
    """Only the file written now is 'converted'; older ones are listed apart."""
    src, out = _stale_folder(tmp_path)
    with (
        patch("medmcp_dicom.tools.convert.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch(
            "medmcp_dicom.tools.convert.subprocess.run",
            side_effect=_fake_dcm2niix(out, "001_Sag_T2"),
        ),
    ):
        res = convert_dcm_to_nifti(src, out)
    assert [c["nifti"] for c in res["converted"]] == [str(out / "001_Sag_T2a.nii.gz")]
    assert res["total_series"] == 1
    assert res["already_in_output_dir"] == [
        str(out / "001_Sag_T2.nii.gz"),
        str(out / "segmentation.nii.gz"),
    ]
    note = res["converted"][0]["note"]
    assert "older 001_Sag_T2.nii.gz" in note and "Use 001_Sag_T2a.nii.gz" in note
    assert "NOT written by this call" in res["_render"]
    assert "new, empty output folder" in res["_render"]


def test_clean_folder_has_no_existing_files_note(tmp_path: Path) -> None:
    """A fresh output folder gives the plain result."""
    src = tmp_path / "dicom"
    src.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    with (
        patch("medmcp_dicom.tools.convert.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch(
            "medmcp_dicom.tools.convert.subprocess.run",
            side_effect=_fake_dcm2niix(out, "001_Sag_T2"),
        ),
    ):
        res = convert_dcm_to_nifti(src, out)
    assert res["total_series"] == 1 and res["already_in_output_dir"] == []
    assert "note" not in res["converted"][0]
    assert "NOT written" not in res["_render"]


def test_nothing_written_does_not_fall_back_to_old_files(tmp_path: Path) -> None:
    """dcm2niix wrote nothing (exit 0): nothing is 'converted', the old files are apart."""
    src, out = _stale_folder(tmp_path)

    def run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, "Warning: no images found\n", "")

    with (
        patch("medmcp_dicom.tools.convert.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch("medmcp_dicom.tools.convert.subprocess.run", side_effect=run),
    ):
        res = convert_dcm_to_nifti(src, out)
    assert res["converted"] == [] and len(res["already_in_output_dir"]) == 2
    assert "wrote no NIfTI file" in res["_render"]


async def test_mcp_output_validates_against_schema(tmp_path: Path) -> None:
    """Through an MCP client, the result validates against the tool's output schema."""
    src, out = _stale_folder(tmp_path)
    server = mcp._mcp_server  # pyright: ignore[reportPrivateUsage]
    with (
        patch("medmcp_dicom.tools.convert.find_dcm2niix", return_value="/fake/dcm2niix"),
        patch(
            "medmcp_dicom.tools.convert.subprocess.run",
            side_effect=_fake_dcm2niix(out, "001_Sag_T2"),
        ),
    ):
        async with create_connected_server_and_client_session(server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            res = await client.call_tool(
                "convert_dcm_to_nifti", {"input_dir": str(src), "output_dir": str(out)}
            )
    assert not res.isError, res.content
    assert res.structuredContent is not None
    schema = tools["convert_dcm_to_nifti"].outputSchema
    assert schema is not None
    jsonschema.validate(res.structuredContent, schema)
    data = res.structuredContent.get("result", res.structuredContent)
    assert data["already_in_output_dir"] and data["total_series"] == 1
