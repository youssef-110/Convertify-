"""Runs a conversion safely and saves the result next to the original, never overwriting anything."""
import logging
import multiprocessing as mp
import os
import queue
import shutil
import sys
import tempfile
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

import converters
from converters.tools import ConversionError, MissingTool

FROZEN = getattr(sys, "frozen", False)
HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))  # bundled files (assets/) in the .exe
# Running from source: logs\ next to the code. Installed .exe: %LOCALAPPDATA%\Convertify\logs.
LOG_DIR = (Path(os.environ["LOCALAPPDATA"]) / "Convertify" / "logs") if FROZEN else Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "converter.log"

LOG_DIR.mkdir(parents=True, exist_ok=True)
log = logging.getLogger("converter")
if not log.handlers:
    log.setLevel(logging.INFO)
    _h = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8", delay=True)
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(_h)


def timeout_for(target, srcs):
    if target in converters.MULTI:
        return 600
    needs = converters.MAP[converters.ext_of(srcs[0])][target].needs
    return 3600 if "ffmpeg" in needs else 600  # minutes of video can take a while


def unique(path):
    """report.docx -> 'report (2).docx' if report.docx already exists."""
    path, n = Path(path), 1
    candidate = path
    while candidate.exists():
        n += 1
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
    return candidate


def _worker(q, target, srcs, out_dir, opts):
    try:
        q.put(("ok", [str(p) for p in converters.run(target, [Path(s) for s in srcs], Path(out_dir), opts)]))
    except (ConversionError, MissingTool) as e:
        q.put(("err", str(e), ""))
    except Exception as e:
        q.put(("err", f"Conversion failed: {e}", traceback.format_exc()))


def _run_isolated(target, srcs, out_dir, opts, limit):
    """Converts in a child process so a stuck file can be killed at the time limit."""
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_worker, args=(q, target, [str(s) for s in srcs], str(out_dir),
                                          {**opts, "_timeout": limit * 0.95}), daemon=True)
    p.start()
    try:
        result = q.get(timeout=limit)
    except queue.Empty:
        from converters.tools import kill_tree
        kill_tree(p.pid)  # also stops LibreOffice/FFmpeg started by the child
        raise ConversionError(f"Took longer than {limit / 60:g} minutes and was stopped.")
    finally:
        p.join(5)
    if result[0] == "err":
        if result[2]:
            log.error("%s %s\n%s", target, [Path(s).name for s in srcs], result[2])
        raise ConversionError(result[1])
    return [Path(r) for r in result[1]]


def convert(srcs, target, opts=None, dest_dir=None):
    """Convert `srcs` (one file, or several for merge actions) to `target`.

    Saves into `dest_dir`, or the first file's folder. One output -> one file; several outputs
    (pages, sheets) -> a new folder holding them. Returns the saved file or folder.
    """
    srcs = [Path(s) for s in srcs]
    opts = {k: v for k, v in (opts or {}).items() if not k.startswith("_")}
    if target not in converters.MULTI:
        if len(srcs) != 1:
            raise ConversionError("Convert one file at a time with this format.")
        if target not in converters.MAP.get(converters.ext_of(srcs[0].name), {}):
            raise ConversionError(f"{srcs[0].suffix or 'This file'} can't be converted to {target}.")
    for s in srcs:
        if not s.is_file():
            raise ConversionError(f"{s.name} wasn't found. Was it moved or deleted?")
    dest = Path(dest_dir) if dest_dir else srcs[0].parent

    work = Path(tempfile.mkdtemp(prefix="convertify-"))
    try:
        # Work on copies: programs like LibreOffice leave lock files (~$report.docx) next to what they open.
        copies = []
        for i, s in enumerate(srcs):
            (work / "in" / str(i)).mkdir(parents=True)
            copies.append(Path(shutil.copy2(s, work / "in" / str(i) / s.name)))
        (work / "out").mkdir()
        outs = _run_isolated(target, copies, work / "out", opts, timeout_for(target, srcs))
        if not outs or any(not o.exists() or o.stat().st_size == 0 for o in outs):
            raise ConversionError("The conversion produced an empty file.")
        try:
            dest.mkdir(parents=True, exist_ok=True)
            if len(outs) == 1:
                saved = unique(dest / outs[0].name)
                shutil.move(outs[0], saved)
            else:
                saved = unique(dest / f"{srcs[0].stem} ({target})")
                saved.mkdir()
                for o in outs:
                    shutil.move(o, saved / o.name)
        except PermissionError:
            raise ConversionError(f"Can't save in {dest}. Pick another folder to save to.")
    except ConversionError as e:
        log.warning("failed %s -> %s: %s", [s.name for s in srcs], target, e)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    log.info("converted %s -> %s", [s.name for s in srcs], saved)
    return saved
