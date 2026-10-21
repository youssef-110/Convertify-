"""Creates one small sample file per supported input format in tests/samples/.

Run on its own (`python tests/make_samples.py`) or let pytest call it. Files that already
exist are kept. Formats that need a missing program (e.g. .doc needs LibreOffice) are skipped.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from converters.tools import find, run  # noqa: E402

SAMPLES = Path(__file__).parent / "samples"
TEXT = "Hello from the Convertify test. The quick brown fox jumps over the lazy dog 12345."


def _lo(src, filter_):
    """Make another office format from `src` with LibreOffice."""
    from converters.libreoffice import PROFILE
    ext = filter_.split(":")[0]
    if (SAMPLES / f"sample.{ext}").exists() or not find("soffice"):
        return
    run([find("soffice"), f"-env:UserInstallation={PROFILE.as_uri()}", "--headless", "--norestore",
         "--convert-to", filter_, "--outdir", SAMPLES, src], 180)


def _ff(out, *args):
    if not out.exists() and find("ffmpeg"):
        run([find("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *args, out], 120)


def make():
    SAMPLES.mkdir(exist_ok=True)
    s = SAMPLES

    import pymupdf as fitz
    if not (s / "sample.pdf").exists():
        doc = fitz.open()
        for n in (1, 2):
            page = doc.new_page()
            page.insert_text((72, 90), f"Page {n}", fontsize=28)
            page.insert_text((72, 140), TEXT, fontsize=12)
        # a picture on page 2, so extracting images and compressing have something to work on
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (1200, 800), "#C6F432").save(buf, "PNG")
        doc[1].insert_image(fitz.Rect(72, 200, 372, 400), stream=buf.getvalue())
        doc.save(s / "sample.pdf")

    import docx
    if not (s / "sample.docx").exists():
        d = docx.Document()
        d.add_heading("Sample document", 1)
        d.add_paragraph(TEXT)
        t = d.add_table(rows=2, cols=2)
        for i, cell in enumerate(t._cells):
            cell.text = f"cell {i}"
        d.save(s / "sample.docx")
    _lo(s / "sample.docx", "doc:MS Word 97")
    _lo(s / "sample.docx", "odt")
    _lo(s / "sample.docx", "rtf")

    from pptx import Presentation
    if not (s / "sample.pptx").exists():
        prs = Presentation()
        for n in (1, 2):
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            slide.shapes.title.text = f"Slide {n}"
            slide.placeholders[1].text = TEXT
        prs.save(s / "sample.pptx")
    _lo(s / "sample.pptx", "ppt:MS PowerPoint 97")
    _lo(s / "sample.pptx", "odp")

    import openpyxl
    if not (s / "sample.xlsx").exists():
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "People"
        ws.append(["Name", "Age", "City"])
        ws.append(["Ali", 31, "Cairo"])
        ws.append(["Mona", 27, "Amman"])
        wb.create_sheet("Totals").append(["Count", 2])
        wb.save(s / "sample.xlsx")
    _lo(s / "sample.xlsx", "xls:MS Excel 97")
    _lo(s / "sample.xlsx", "ods")
    (s / "sample.csv").write_text("Name,Age,City\nAli,31,Cairo\nMona,27,Amman\n", encoding="utf-8")

    (s / "sample.md").write_text(f"# Sample\n\n{TEXT}\n\n- one\n- **two**\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
                                 encoding="utf-8")
    (s / "sample.html").write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>Sample</title></head>"
                                   f"<body><h1>Sample</h1><p>{TEXT}</p><ul><li>one</li><li>two</li></ul></body></html>",
                                   encoding="utf-8")
    (s / "sample.txt").write_text(f"Sample\n\n{TEXT}\n", encoding="utf-8")
    (s / "sample.tsv").write_text("Name\tAge\tCity\nAli\t31\tCairo\nMona\t27\tAmman\n", encoding="utf-8")
    (s / "sample.json").write_text('[{"Name": "Ali", "Age": 31}, {"Name": "Mona", "Age": 27}]', encoding="utf-8")
    import zipfile
    with zipfile.ZipFile(s / "sample.zip", "w") as z:
        z.writestr("notes/readme.txt", TEXT)
        z.writestr("data.csv", "a,b\n1,2\n")
    if find("pandoc") and not (s / "sample.epub").exists():
        run([find("pandoc"), "-s", "--metadata", "title=Sample", "-o", s / "sample.epub", s / "sample.md"], 60)

    from PIL import Image, ImageDraw
    from pillow_heif import register_heif_opener
    register_heif_opener()
    img = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((10, 10, 120, 120), fill="#F5C542")
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", 40)
    except OSError:
        font = None
    draw.text((140, 120), "Hello OCR 12345", fill="black", font=font)
    for ext, fmt in [("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP"), ("avif", "AVIF"), ("bmp", "BMP"), ("gif", "GIF"),
                     ("tiff", "TIFF"), ("heic", "HEIF"), ("ico", "ICO")]:
        if not (s / f"sample.{ext}").exists():
            img.save(s / f"sample.{ext}", fmt)

    lavfi_v = ["-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
               "-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    _ff(s / "sample.mp4", *lavfi_v, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest")
    _ff(s / "sample.mov", *lavfi_v, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest")
    _ff(s / "sample.avi", *lavfi_v, "-c:v", "mpeg4", "-c:a", "mp3", "-shortest")
    _ff(s / "sample.mkv", *lavfi_v, "-c:v", "libx264", "-c:a", "aac", "-shortest")
    _ff(s / "sample.webm", *lavfi_v, "-c:v", "libvpx-vp9", "-deadline", "realtime", "-c:a", "libopus", "-shortest")
    sine = ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    for ext in ("mp3", "wav", "m4a", "ogg", "flac", "aac", "opus", "wma"):
        _ff(s / f"sample.{ext}", *sine)
    return SAMPLES


if __name__ == "__main__":
    make()
    print("\n".join(sorted(p.name for p in SAMPLES.iterdir())))
