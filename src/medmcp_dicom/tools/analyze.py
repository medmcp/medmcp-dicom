"""Analyze 7.5 / NIfTI-1 pair (.hdr/.img) to .nii.gz conversion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from nibabel.fileholders import FileHolder
from nibabel.openers import ImageOpener
from nibabel.volumeutils import array_to_file

_HDR, _IMG = ".hdr", ".img"


def _pair_stem(path: Path) -> str | None:
    """Base name without .hdr/.img (any case), or None for other files."""
    suffix = path.suffix.lower()
    return path.name[: -len(suffix)] if suffix in (_HDR, _IMG) else None


def _partner(path: Path, want: str) -> Path | None:
    """The sibling with the same stem and suffix *want* (.hdr/.img), in any case."""
    stem = _pair_stem(path)
    if stem is None:
        return None
    for cand in (path.with_name(stem + want), path.with_name(stem + want.upper())):
        if cand.is_file():
            return cand
    for cand in path.parent.iterdir():
        if cand.is_file() and cand.name.lower() == (stem + want).lower():
            return cand
    return None


def pair_header(path: Path) -> Path | None:
    """The .hdr of the pair *path* belongs to, or None if *path* is not part of a pair."""
    if _pair_stem(path) is None:
        return None
    return path if path.suffix.lower() == _HDR else _partner(path, _HDR)


def pair_partner(hdr: Path) -> Path | None:
    """The .img that goes with *hdr*."""
    return _partner(hdr, _IMG)


def _out_name(hdr: Path) -> str:
    """``mpr-4.nifti.hdr`` -> ``mpr-4.nii.gz``; ``s002.HDR`` -> ``s002.nii.gz``."""
    stem = _pair_stem(hdr) or hdr.stem
    if stem.lower().endswith(".nifti"):
        stem = stem[: -len(".nifti")]
    return stem + ".nii.gz"


def load_pair(hdr: Path) -> tuple[Any, bool]:
    """Load a pair without applying an SPM ``.mat`` sidecar; return (image, mat_present)."""
    mat = hdr.with_suffix(".mat")
    mat_present = mat.is_file() or hdr.with_suffix(".MAT").is_file()
    if not mat_present:
        img: Any = nib.load(str(hdr))  # type: ignore[reportUnknownMemberType]
        return img, False
    with hdr.open("rb") as fh:
        is_nifti = fh.read(348)[344:347] in (b"ni1", b"n+1")
    if is_nifti:  # NIfTI pairs ignore .mat files anyway
        return nib.load(str(hdr)), True  # type: ignore[reportUnknownMemberType]
    # Analyze + SPM .mat: load the header alone; the .mat is reported, not applied.
    fmap: Any = nib.Spm2AnalyzeImage.filespec_to_file_map(str(hdr))  # type: ignore[reportUnknownMemberType]
    fmap["mat"] = FileHolder(filename=str(hdr.with_name(hdr.name + ".no-mat")))
    return nib.Spm2AnalyzeImage.from_file_map(fmap), True  # type: ignore[reportUnknownMemberType]


def describe_pair(img: Any, mat_present: bool = False) -> dict[str, Any]:
    """Header type, qform/sform codes, orientation and whether orientation is only assumed."""
    is_nifti = isinstance(img, nib.Nifti1Pair | nib.Nifti2Pair)  # type: ignore[reportUnknownMemberType]
    hdr: Any = img.header
    qcode = int(hdr["qform_code"]) if is_nifti else 0
    scode = int(hdr["sform_code"]) if is_nifti else 0
    codes: Any = nib.aff2axcodes(img.affine)  # type: ignore[reportUnknownMemberType]
    orientation = "".join(str(c) for c in codes)
    assumed = qcode == 0 and scode == 0
    warnings: list[str] = []
    if is_nifti:
        header_type = "NIfTI-2 pair" if isinstance(img, nib.Nifti2Pair) else "NIfTI-1 pair"  # type: ignore[reportUnknownMemberType]
        if assumed:
            warnings.append(
                "orientation unknown: NIfTI pair has no qform/sform; left/right may be flipped"
            )
    else:
        header_type = "Analyze 7.5"
        warnings.append(
            f"left/right may be flipped: Analyze 7.5 carries no orientation (assumed {orientation})"
        )
    if mat_present:
        warnings.append("SPM .mat sidecar found but not applied: orientation may differ from SPM's")
    return {
        "header_type": header_type,
        "qform_code": qcode,
        "sform_code": scode,
        "orientation": orientation,
        "orientation_assumed": assumed,
        "spm_mat_sidecar": mat_present,
        "warnings": warnings,
    }


def _write_nii_gz(img: Any, out: Path) -> None:
    """Write *img* as .nii.gz keeping the stored dtype, scl_slope/scl_inter and shape."""
    proxy: Any = img.dataobj
    raw: Any = np.asanyarray(proxy.get_unscaled())
    slope = float(proxy.slope)
    inter = float(proxy.inter)
    hdr: Any = nib.Nifti1Header.from_header(img.header)  # type: ignore[reportUnknownMemberType]
    if hdr.endianness != "<":
        hdr = hdr.as_byteswapped("<")
    hdr["magic"] = b"n+1"
    hdr["vox_offset"] = 0
    hdr.set_data_shape(raw.shape)
    hdr.set_data_dtype(img.get_data_dtype().newbyteorder("<"))
    hdr.set_zooms(img.header.get_zooms())
    if isinstance(img, nib.Nifti1Pair):  # type: ignore[reportUnknownMemberType]
        hdr.set_qform(img.header.get_qform(), int(img.header["qform_code"]))
        hdr.set_sform(img.header.get_sform(), int(img.header["sform_code"]))
    else:  # Analyze: store the (assumed) affine nibabel derives, as "aligned"
        hdr.set_qform(img.affine, 2)
        hdr.set_sform(img.affine, 2)
    if (slope in (0.0, 1.0) and inter == 0.0) or not np.isfinite(slope):
        hdr.set_slope_inter(np.nan, np.nan)
    else:
        hdr["scl_slope"], hdr["scl_inter"] = slope, inter
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(".part-" + out.name)  # keeps .nii.gz so it is gzipped
    fobj: Any
    with ImageOpener(str(tmp), "wb") as fobj:
        hdr.write_to(fobj)
        array_to_file(raw, fobj, hdr.get_data_dtype(), int(hdr["vox_offset"]), order="F")
    tmp.replace(out)


def convert_to_nifti(
    input_path: Path,
    output_dir: Path | None = None,
    recursive: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Convert Analyze 7.5 / NIfTI-1 pairs (.hdr + .img) to .nii.gz.

    Use this for hdr/img pairs (Analyze, SPM, OASIS ``*.nifti.hdr``) instead of writing a
    script. For DICOM use ``convert_dcm_to_nifti``. Keeps voxel size, data type, scaling
    and 4D shape; reports per file whether the orientation is real or only assumed.
    Never touches the source files; existing outputs are skipped unless ``overwrite``.

    Args:
        input_path: A .hdr or .img file of a pair, or a folder of pairs.
        output_dir: Where to write. Default: a new sibling folder ``<folder>_nifti``.
        recursive: For a folder, also convert pairs in subfolders (layout kept).
        overwrite: Replace existing .nii.gz outputs.

    Returns:
        Dict with tell_the_user (plain warnings, say first), written (only files this
        call wrote, with header_type, orientation, orientation_assumed, qform/sform
        codes), skipped (with reason), output_dir and _render.
    """
    src = Path(input_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"input_path does not exist: {src}")
    root = src if src.is_dir() else src.parent
    out_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir
        else root.parent / f"{root.name}_nifti"
    )

    if src.is_dir():
        files = src.rglob("*") if recursive else src.iterdir()
        hdrs = sorted(p for p in files if p.is_file() and p.suffix.lower() == _HDR)
        orphans = sorted(
            p
            for p in (src.rglob("*") if recursive else src.iterdir())
            if p.is_file() and p.suffix.lower() == _IMG and _partner(p, _HDR) is None
        )
    else:
        if _pair_stem(src) is None:
            raise ValueError(f"not a .hdr/.img file: {src}")
        hdr = src if src.suffix.lower() == _HDR else _partner(src, _HDR)
        hdrs = [hdr] if hdr else []
        orphans = [] if hdr else [src]

    written: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = [
        {"source": str(p), "reason": "no matching .hdr"} for p in orphans
    ]
    for hdr in hdrs:
        if _partner(hdr, _IMG) is None:
            skipped.append({"source": str(hdr), "reason": "no matching .img"})
            continue
        out = out_dir / hdr.parent.relative_to(root) / _out_name(hdr)
        if out.exists() and not overwrite:
            skipped.append({"source": str(hdr), "reason": f"output exists: {out}"})
            continue
        try:
            img, mat_present = load_pair(hdr)
            info = describe_pair(img, mat_present)
            _write_nii_gz(img, out)
        except Exception as exc:
            skipped.append({"source": str(hdr), "reason": f"could not convert: {exc}"})
            continue
        written.append(
            {
                "source": str(hdr),
                "output": str(out),
                "shape": [int(d) for d in img.shape],
                "dtype": str(img.get_data_dtype().name),
                **info,
            }
        )

    tell: list[str] = []
    for item in written:
        for w in item["warnings"]:
            if w not in tell:
                tell.append(w)
    if skipped:
        tell.append(f"{len(skipped)} file(s) skipped; see 'skipped' for reasons")
    tell = [t[:120] for t in tell[:5]]

    render = (
        f"Converted {len(written)} pair(s) to .nii.gz in: {out_dir}\n"
        "Say each 'tell_the_user' line first, word for word.\n"
        "Then a table: Source | Output | Header type | Orientation | Assumed?\n"
        "List 'skipped' with reasons if any. NEXT ACTION: show this, then stop."
    )
    return {
        "tell_the_user": tell,
        "output_dir": str(out_dir),
        "written": written,
        "skipped": skipped,
        "_render": render,
    }
