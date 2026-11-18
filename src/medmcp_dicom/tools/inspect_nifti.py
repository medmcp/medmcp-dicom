"""NIfTI file inspection tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import nibabel as nib

from medmcp_dicom.tools.analyze import describe_pair, load_pair, pair_header, pair_partner


def inspect_nifti(path: Path) -> dict[str, Any]:
    """Inspect a NIfTI file's header and return structured image metadata.

    Reads only the file header and affine — pixel data is never loaded into memory.
    Supports NIfTI-1 (.nii, .nii.gz), NIfTI-2 and .hdr/.img pairs (Analyze 7.5 or
    NIfTI-1 pair; ``format`` says which, and whether orientation is only assumed).

    Args:
        path: Path to a .nii or .nii.gz file, or the .hdr/.img of a pair.

    Returns:
        Dict with keys: path, shape, voxel_size_mm, tr_sec, n_volumes, dtype,
        orientation, file_size_mb, nifti_version, format, orientation_assumed, and _render.
        tr_sec and n_volumes are null for 3D images.

    Raises:
        FileNotFoundError: If path does not exist.
    """
    resolved = Path(path).resolve()
    # img typed as Any: nibabel's py.typed stubs are incomplete, causing Pyright
    # to propagate Unknown through all attribute accesses on FileBasedImage.
    pair_hdr = pair_header(resolved)
    if pair_hdr is not None:
        img, mat_present = load_pair(pair_hdr)
        pair_info: dict[str, Any] | None = describe_pair(img, mat_present)
    else:
        img: Any = nib.load(str(resolved))  # type: ignore[reportUnknownMemberType]
        pair_info = None

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
    nifti_version: int | None = 2 if isinstance(img, nib.Nifti2Image) else 1  # type: ignore[reportUnknownMemberType]
    fmt = f"NIfTI-{nifti_version}"
    assumed = False
    if pair_info is not None and pair_hdr is not None:
        fmt, assumed = pair_info["header_type"], bool(pair_info["orientation_assumed"])
        if fmt == "Analyze 7.5":
            nifti_version = None
        file_size_mb = round(
            sum(p.stat().st_size for p in (pair_hdr, pair_partner(pair_hdr)) if p) / 2**20, 2
        )

    shape_str = " × ".join(str(d) for d in shape)  # noqa: RUF001
    voxel_str = f"{voxel_size_mm[0]} × {voxel_size_mm[1]} × {voxel_size_mm[2]} mm"  # noqa: RUF001
    tr_row = f"| TR | {tr_sec} s |\n" if tr_sec is not None else ""
    volumes_row = f"| Volumes | {n_volumes} |\n" if is_4d else ""
    render = (
        "| Field | Value |\n"
        "|---|---|\n"
        f"| File | `{resolved}` |\n"
        f"| Shape | {shape_str} |\n"
        f"| Voxel size | {voxel_str} |\n" + tr_row + volumes_row + f"| Data type | {dtype} |\n"
        f"| Orientation | {orientation}{' (assumed)' if assumed else ''} |\n"
        f"| Format | {fmt} |\n"
        f"| File size | {file_size_mb} MB |\n"
        f"| NIfTI version | {nifti_version or '—'} |\n"
        "\nNEXT ACTION: Display the table above to the user."
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
        "format": fmt,
        "orientation_assumed": assumed,
        "_render": render,
    }
