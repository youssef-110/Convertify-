"""Finds the external programs (LibreOffice, Pandoc, FFmpeg, Tesseract) and runs them."""
import functools
import glob
import os
import shutil
import subprocess


class MissingTool(Exception):
    pass


class ConversionError(Exception):
    pass


# tool -> (display name, winget command, fallback locations when it is not on PATH)
SPECS = {
    "soffice": ("LibreOffice", "winget install TheDocumentFoundation.LibreOffice", [
        r"%ProgramFiles%\LibreOffice\program\soffice.exe",
        r"%ProgramFiles(x86)%\LibreOffice\program\soffice.exe",
    ]),
    "pandoc": ("Pandoc", "winget install JohnMacFarlane.Pandoc", [
        r"%LOCALAPPDATA%\Pandoc\pandoc.exe",
        r"%ProgramFiles%\Pandoc\pandoc.exe",
    ]),
    "ffmpeg": ("FFmpeg", "winget install Gyan.FFmpeg", [
        r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe",
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ]),
    "tesseract": ("Tesseract OCR", "winget install UB-Mannheim.TesseractOCR", [
        r"%ProgramFiles%\Tesseract-OCR\tesseract.exe",
        r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe",
    ]),
}


@functools.cache
def find(tool):
    found = shutil.which(tool)
    if found:
        return found
    for pattern in SPECS[tool][2]:
        hits = sorted(glob.glob(os.path.expandvars(pattern)))
        if hits:
            return hits[-1]  # newest version folder sorts last
    return None


def require(tool):
    path = find(tool)
    if not path:
        name, cmd, _ = SPECS[tool]
        raise MissingTool(f"{name} is not installed. Install it with:  {cmd}  then restart the app.")
    return path


def status():
    return {t: {"name": s[0], "install": s[1], "found": bool(find(t))} for t, s in SPECS.items()}


class Timeout(ConversionError):
    pass


def kill_tree(pid):
    # LibreOffice's soffice.exe starts soffice.bin; killing only the parent leaves it hanging.
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def run(args, timeout):
    p = subprocess.Popen([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(p.pid)
        p.communicate()
        raise Timeout(f"Took longer than {int(timeout)} seconds and was stopped.")
    if p.returncode != 0:
        msg = (err or out).strip().splitlines()
        raise ConversionError(msg[-1] if msg else f"Program exited with code {p.returncode}.")
    return out
