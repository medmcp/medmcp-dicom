"""NIfTI file inspection tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import nibabel as nib


def inspect_nifti(path: Path) -> dict[str, Any]:
    """Inspect a NIfTI file's header and return structured image metadata.

    Reads only the file header and affine — pixel data is never loaded into memory.
    Supports both NIfTI-1 (.nii, .nii.gz) and NIfTI-2 files.

    Args:
        path: Path to a .nii or .nii.gz file.

    Returns:
        Dict with keys: path, shape, voxel_size_mm, tr_sec, n_volumes, dtype,
        orientation, file_size_mb, nifti_version, and _render.
        tr_sec and n_volumes are null for 3D images.

    Raises:
        FileNotFoundError: If path does not exist.
    """
    resolved = Path(path).resolve()
    # img typed as Any: nibabel's py.typed stubs are incomplete, causing Pyright
    # to propagate Unknown through all attribute accesses on FileBasedImage.
    img: Any = nib.load(str(resolved))  # type: ignore[reportUnknownMemberType]

    shape: list[int] = [int(d) for d in img.shape]
    is_4d = len(shape) == 4

    zooms: tuple[float, ...] = tuple(float(z) for z in img.header.get_zooms())
    voxel_size_mm: list[float] = [round(z, 3) for z in zooms[:3]]

    tr_sec: float | None = None
    if is_4d and len(zooms) > 3:
        tr_sec = round(zooms[3], 3)
    n_volumes: int | None = shape[3] if is_4d else None

    dtype: str = str(img.get_data_dtype().name)

    _raw_codes: Any = nib.aff2axcodes(img.affine)  # type: ignore[reportUnknownMemberType]
    codes: tuple[str, ...] = tuple(str(c) for c in _raw_codes)
    orientation = "".join(codes)

    file_size_mb = round(resolved.stat().st_size / (1024 * 1024), 2)
    nifti_version: int = 2 if isinstance(img, nib.Nifti2Image) else 1  # type: ignore[reportUnknownMemberType]

    volumes_clause = f" ({n_volumes} volumes)" if is_4d else ""
    tr_line = f"  TR: {tr_sec} s\n" if tr_sec is not None else ""
    render = (
        "DISPLAY RULES — follow exactly:\n"
        "Report the following fields as a compact key-value list:\n"
        f"  File: {resolved}\n"
        f"  Shape: {shape}{volumes_clause}\n"
        f"  Voxel size: {voxel_size_mm[0]} × {voxel_size_mm[1]} × {voxel_size_mm[2]} mm\n"  # noqa: RUF001
        + tr_line
        + f"  Data type: {dtype}\n"
        f"  Orientation: {orientation}\n"
        f"  File size: {file_size_mb} MB\n"
        f"  NIfTI version: {nifti_version}\n"
        "NEXT ACTION: Report these values to the user, "
        "then ask what they would like to do with this image."
    )

    return {
        "path": str(resolved),
        "shape": shape,
        "voxel_size_mm": voxel_size_mm,
        "tr_sec": tr_sec,
        "n_volumes": n_volumes,
        "dtype": dtype,
        "orientation": orientation,
        "file_size_mb": file_size_mb,
        "nifti_version": nifti_version,
        "_render": render,
    }
