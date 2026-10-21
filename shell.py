"""Adds/removes the Explorer right-click menu ("Convert with Convertify"), Send To and Start Menu entries.

Everything goes under HKEY_CURRENT_USER, so no admin rights are needed and only your account is affected.
"""
import os
import subprocess
import sys
import winreg
from pathlib import Path

import converters
from core import FROZEN, HERE

ROOT = r"Software\Classes\SystemFileAssociations"
KEY = "Convertify"
SENDTO = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\SendTo\Convertify.lnk"
START_MENU = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Convertify.lnk"
SEPARATOR_AFTER = 0x40
APP_DIR = Path(__file__).parent
MENU_DIR = APP_DIR / "menu"
PACKAGE = "Convertify.Local"


def launcher():
    """The program + arguments that start the app (the .exe, or pythonw + gui.pyw from source)."""
    if FROZEN:
        return [sys.executable]
    return [str(Path(sys.executable).with_name("pythonw.exe")), str(Path(__file__).with_name("gui.pyw"))]


def _cmd(*args):
    return " ".join(f'"{a}"' for a in launcher()) + " " + " ".join(args)


BASICS = ["pdf", "docx", "pptx", "pdf-compress"]  # the right-click menu stays short; everything else is in the app
FALLBACK = ["jpg", "png", "mp4", "mp3", "wav", "xlsx", "csv"]  # for files that can't become any of the basics
MENU_NAMES = {"pdf-compress": "PDF (smaller file)", "pdf-split": "PDF (one per page)", "ocr-pdf": "PDF (searchable, OCR)", "ocr-txt": "TXT (from scan, OCR)"}


def menu_entries():
    """{extension: [(key name, label, command), ...]} for every input type in the map."""
    exts = {**{e: e for e in converters.MAP}, **{a: t for a, t in converters.ALIASES.items() if t in converters.MAP}}
    entries = {}
    for ext, real in sorted(exts.items()):
        outs = converters.MAP[real]
        targets = [t for t in BASICS if t in outs] or [t for t in FALLBACK if t in outs][:3]
        items = [("00open", "Open in Convertify…", _cmd('"%1"'))]
        items += [(f"{n:02d}{t}", MENU_NAMES.get(t, t.upper()), _cmd("--convert", t, '"%1"'))
                  for n, t in enumerate(targets, 1)]
        entries[ext] = items
    return entries


def icon():
    return str(sys.executable if FROZEN else HERE / "assets" / "icon.ico")


def is_installed():
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{ROOT}\.pdf\shell\{KEY}"))
        return True
    except OSError:
        return False


def install():
    uninstall()  # start clean, e.g. after the app moved to another folder
    for ext, items in menu_entries().items():
        base = rf"{ROOT}\.{ext}\shell\{KEY}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "Convert with Convertify")
            winreg.SetValueEx(k, "SubCommands", 0, winreg.REG_SZ, "")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon())
        for name, label, command in items:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\shell\{name}") as k:
                winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, label)
                if name == "00open":
                    winreg.SetValueEx(k, "CommandFlags", 0, winreg.REG_DWORD, SEPARATOR_AFTER)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\shell\{name}\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, command)
    # Send To passes every selected file at once, so it's how you open a batch (e.g. to merge PDFs).
    _shortcut(SENDTO)
    _shortcut(START_MENU)
    return install_win11_menu()


def _delete_tree(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            subkeys = []
            i = 0
            while True:
                try:
                    subkeys.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
        for s in subkeys:
            _delete_tree(rf"{path}\{s}")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass


def uninstall():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ROOT) as k:
            exts, i = [], 0
            while True:
                try:
                    exts.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
    except FileNotFoundError:
        exts = []
    for ext in exts:
        _delete_tree(rf"{ROOT}\{ext}\shell\{KEY}")
    SENDTO.unlink(missing_ok=True)
    START_MENU.unlink(missing_ok=True)
    if _win11_menu_installed():
        _powershell(f"Get-AppxPackage {PACKAGE} | Remove-AppxPackage")


# ---- Windows 11 top-level menu: menu\ConvertifyMenu.dll, registered through AppxManifest.xml.
def write_menu_txt():
    """The DLL reads this: how to start the app, then 'ext<TAB>target<TAB>label' per menu entry."""
    lines = [" ".join(f'"{a}"' for a in launcher())]
    for ext, items in menu_entries().items():
        for name, label, _ in items:
            lines.append(f"{ext}\t{'*more' if name == '00open' else name[2:]}\t{label}")
    (MENU_DIR / "menu.txt").write_text("\n".join(lines), encoding="utf-8")


def _powershell(command, **env):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                          capture_output=True, text=True, env={**os.environ, **env},
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _win11_menu_installed():
    return bool(_powershell(f"Get-AppxPackage {PACKAGE}").stdout.strip())


def install_win11_menu():
    """Returns None when the Windows 11 menu entry was added, else why not."""
    if FROZEN or not (MENU_DIR / "ConvertifyMenu.dll").exists():
        return r"the menu add-on (menu\ConvertifyMenu.dll) isn't there"
    write_menu_txt()
    r = _powershell("Add-AppxPackage -Register $env:MANIFEST -ExternalLocation $env:APPDIR -ForceUpdateFromAnyVersion",
                    MANIFEST=str(APP_DIR / "AppxManifest.xml"), APPDIR=str(APP_DIR))
    if r.returncode:
        err = (r.stderr or r.stdout).strip()
        if "developer" in err.lower() or "0x80073CFF" in err:
            return "turn on Developer Mode (Settings > System > For developers), then run install.bat again"
        return err.splitlines()[0] if err else "Windows refused the menu package"


def _shortcut(lnk):
    exe, *args = launcher()
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
          "$s.TargetPath=$env:EXE;$s.Arguments=$env:ARGS;$s.IconLocation=$env:ICO;$s.Save()")
    env = {**os.environ, "LNK": str(lnk), "EXE": exe, "ARGS": " ".join(f'"{a}"' for a in args), "ICO": icon()}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env, check=True,
                   capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


if __name__ == "__main__":
    problem = {"install": install, "uninstall": uninstall}[sys.argv[1]]()
    print("Right-click menu", "added." if is_installed() else "removed.")
    if sys.argv[1] == "install":
        print("Windows 11 top menu:", "added." if not problem else f"not added: {problem}")
