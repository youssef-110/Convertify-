"""Markdown / HTML / DOCX via Pandoc. PDF goes Pandoc -> DOCX -> LibreOffice (no LaTeX needed)."""
from pathlib import Path

from . import libreoffice
from .tools import require, run

READERS = {"md": "markdown", "html": "html", "docx": "docx", "odt": "odt", "epub": "epub"}
WRITERS = {"md": "gfm", "html": "html", "docx": "docx", "txt": "plain", "epub": "epub"}


def convert(src, out_dir, fmt, opts):
    src = Path(src)
    ext = src.suffix.lower().lstrip(".")
    if ext not in READERS:  # .doc / .rtf: let LibreOffice make a .docx Pandoc can read
        tmp = Path(out_dir) / "_docx"
        tmp.mkdir(exist_ok=True)
        src, ext = libreoffice.convert(src, tmp, "docx", opts)[0], "docx"
    if fmt == "pdf":
        tmp = Path(out_dir) / "_docx"
        tmp.mkdir(exist_ok=True)
        docx = convert(src, tmp, "docx", opts)[0]
        return libreoffice.convert(docx, out_dir, "pdf", opts)
    out = Path(out_dir) / f"{src.stem}.{fmt}"
    # --sandbox: a document can't pull other local files or URLs into the output
    args = [require("pandoc"), "--sandbox", "-f", READERS[ext], "-t", WRITERS[fmt], "-o", out, src]
    if fmt in ("html", "epub"):
        args[1:1] = ["-s", "--metadata", f"title={src.stem}"]
    run(args, opts["_timeout"])
    return [out]
