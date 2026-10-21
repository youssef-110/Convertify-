"""Zip archives with the standard library."""
import zipfile
from pathlib import Path

from .tools import ConversionError


def _free_name(name, taken):
    """'a.txt' -> 'a (2).txt' when two files share a name."""
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, n = name, 1
    while candidate in taken:
        n += 1
        candidate = f"{stem} ({n}){suffix}"
    return candidate


def pack(srcs, out_dir, opts):
    out = Path(out_dir) / "files.zip"
    names = set()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src in srcs:
            name = _free_name(Path(src).name, names)
            names.add(name)
            z.write(src, name)
    return [out]


def unzip(src, out_dir, fmt, opts):
    try:
        with zipfile.ZipFile(src) as z:
            if any(i.flag_bits & 0x1 for i in z.infolist()):
                raise ConversionError("This .zip is password-protected.")
            outs = []
            for info in z.infolist():
                if info.is_dir():
                    continue
                # shortcut: subfolders are flattened (only the file name is kept, which also blocks
                # '..' paths); keep the tree if people unzip nested projects with it.
                out = Path(out_dir) / _free_name(Path(info.filename).name, {o.name for o in outs})
                out.write_bytes(z.read(info))
                outs.append(out)
    except zipfile.BadZipFile:
        raise ConversionError("This .zip could not be opened (it may be damaged).")
    if not outs:
        raise ConversionError("This .zip is empty.")
    return outs
