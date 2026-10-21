"""OCR with Tesseract: scanned PDF or image -> searchable PDF or text."""
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageSequence

from . import images  # registers the HEIC opener
from .pdf_tools import _open, parse_range
from .tools import require


def _pages(src, opts):
    if Path(src).suffix.lower() == ".pdf":
        doc = _open(src)
        for i in parse_range(opts.get("pages"), len(doc)):
            pix = doc[i].get_pixmap(dpi=300)
            yield Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    else:
        for frame in ImageSequence.Iterator(images._load(src, {})):
            yield frame.convert("RGB")


def convert(src, out_dir, fmt, opts):
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = require("tesseract")
    lang = opts.get("lang") or "eng"
    stem = Path(src).stem
    if fmt == "txt":
        text = "\n\f".join(pytesseract.image_to_string(p, lang=lang, timeout=opts["_timeout"]) for p in _pages(src, opts))
        out = Path(out_dir) / f"{stem}_ocr.txt"
        out.write_text(text, encoding="utf-8")
        return [out]
    result = fitz.open()
    for page in _pages(src, opts):
        pdf = pytesseract.image_to_pdf_or_hocr(page, extension="pdf", lang=lang, timeout=opts["_timeout"])
        result.insert_pdf(fitz.open("pdf", pdf))
    out = Path(out_dir) / f"{stem}_ocr.pdf"
    result.save(out, garbage=3, deflate=True)
    return [out]
