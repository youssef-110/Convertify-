"""Office formats via headless LibreOffice."""
import contextlib
import msvcrt
import tempfile
import time
from pathlib import Path

from .tools import ConversionError, Timeout, require, run

# Own profile so a LibreOffice window you have open doesn't block conversions.
PROFILE = Path(tempfile.gettempdir()) / "convertify-lo-profile"
LOCK = Path(tempfile.gettempdir()) / "convertify-lo.lock"

FILTERS = {
    "pdf": "pdf",
    "docx": "docx:MS Word 2007 XML",
    "odt": "odt",
    "html": "html:XHTML Writer File:UTF8",
    "txt": "txt:Text (encoded):UTF8",
}


@contextlib.contextmanager
def one_at_a_time():
    """LibreOffice can't run two conversions on one profile. This lock works across processes
    (right-clicking 10 files starts 10 of them) and is released by Windows if a process dies."""
    with open(LOCK, "a+b") as fh:
        while True:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.3)
        try:
            yield
        finally:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def convert(src, out_dir, fmt, opts):
    soffice = require("soffice")
    work = Path(out_dir) / "_lo"
    work.mkdir(exist_ok=True)
    args = [soffice, f"-env:UserInstallation={PROFILE.as_uri()}", "--headless", "--norestore",
            "--convert-to", FILTERS.get(fmt, fmt), "--outdir", work, src]
    with one_at_a_time():
        try:
            # LibreOffice now and then hangs at start; a normal conversion takes seconds, so retry once.
            run(args, min(120, opts["_timeout"] / 2))
        except Timeout:
            run(args, opts["_timeout"] / 2)
    out = work / f"{Path(src).stem}.{fmt}"
    # LibreOffice exits 0 even when it fails, so the file is the only proof.
    if not out.exists() or out.stat().st_size == 0:
        raise ConversionError("LibreOffice could not convert this file (it may be damaged or password-protected).")
    return [out.replace(Path(out_dir) / out.name)]


def to_pdf_then(src, out_dir, fmt, opts, then):
    """Office file -> PDF (temporary) -> `then(pdf, out_dir, fmt, opts)`."""
    tmp = Path(out_dir) / "_pdf"
    tmp.mkdir(exist_ok=True)
    pdf = convert(src, tmp, "pdf", opts)[0]
    return then(pdf, out_dir, fmt, opts)
