"""Saving results (next to the original, never overwriting), time limits, and the right-click menu."""
import hashlib
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402
import shell  # noqa: E402
from converters.tools import ConversionError  # noqa: E402
from tests.make_samples import make  # noqa: E402


@pytest.fixture
def folder(tmp_path):
    samples = make()
    for name in ("sample.png", "sample.pdf"):
        shutil.copy(samples / name, tmp_path / name)
    return tmp_path


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_saves_next_to_original_and_never_overwrites(folder):
    before = digest(folder / "sample.png")
    first = core.convert([folder / "sample.png"], "jpg")
    second = core.convert([folder / "sample.png"], "jpg")
    assert first == folder / "sample.jpg"
    assert second == folder / "sample (2).jpg"
    assert digest(folder / "sample.png") == before  # original untouched


def test_many_outputs_go_in_a_folder(folder):
    saved = core.convert([folder / "sample.pdf"], "png")
    assert saved.is_dir() and saved.name == "sample (png)"
    assert sorted(p.name for p in saved.iterdir()) == ["sample_page1.png", "sample_page2.png"]


def test_save_to_other_folder(folder, tmp_path_factory):
    dest = tmp_path_factory.mktemp("out")
    assert core.convert([folder / "sample.png"], "webp", dest_dir=dest) == dest / "sample.webp"


def test_merge(folder):
    saved = core.convert([folder / "sample.pdf", folder / "sample.pdf"], "merge-pdf")
    assert saved.name == "merged.pdf"


def test_stuck_conversion_is_stopped(folder, monkeypatch):
    monkeypatch.setattr(core, "timeout_for", lambda *a: 0.01)
    with pytest.raises(ConversionError, match="stopped"):
        core.convert([folder / "sample.pdf"], "docx")
    assert not (folder / "sample.docx").exists()


def test_clear_errors(folder):
    with pytest.raises(ConversionError, match="can't be converted"):
        core.convert([folder / "sample.png"], "docx")
    with pytest.raises(ConversionError, match="wasn't found"):
        core.convert([folder / "nope.png"], "jpg")
    (folder / "broken.pdf").write_bytes(b"%PDF-garbage")
    with pytest.raises(ConversionError, match="could not be opened"):
        core.convert([folder / "broken.pdf"], "txt")


def test_unique_names():
    assert core.unique(Path(__file__)) == Path(__file__).with_name("test_core (2).py")


def test_right_click_menu_entries():
    entries = shell.menu_entries()
    assert {"pdf", "docx", "jpeg", "mp4"} <= set(entries)  # aliases like .jpeg get a menu too
    pdf = dict((key, (label, cmd)) for key, label, cmd in entries["pdf"])
    assert pdf["00open"][0] == "Open in Convertify…"
    label, cmd = next(v for k, v in pdf.items() if k.endswith("docx"))
    assert label == "DOCX"
    assert cmd.endswith('--convert docx "%1"') and "pythonw.exe" in cmd and "gui.pyw" in cmd
    assert [label for _, label, _ in entries["docx"]] == ["Open in Convertify…", "PDF", "PPTX"]
    assert [label for _, label, _ in entries["mp3"]] == ["Open in Convertify…", "WAV"]  # no basics: falls back
