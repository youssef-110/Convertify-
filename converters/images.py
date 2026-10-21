"""Images with Pillow (+ pillow-heif for HEIC)."""
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from .tools import ConversionError

register_heif_opener()

PIL_FORMAT = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP", "avif": "AVIF", "bmp": "BMP", "gif": "GIF",
              "tiff": "TIFF", "heic": "HEIF", "ico": "ICO", "pdf": "PDF"}
NO_ALPHA = {"jpg", "bmp", "pdf"}


def _load(src, opts):
    try:
        im = Image.open(src)
        im = ImageOps.exif_transpose(im)  # shortcut: animated GIF/WEBP keep only the first frame
    except (UnidentifiedImageError, OSError):
        raise ConversionError("This image could not be opened (it may be damaged or not really an image).")
    size = int(opts.get("max_size") or 0)
    if size:
        im.thumbnail((size, size))
    return im


def _flatten(im, fmt):
    if fmt in NO_ALPHA:
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, "white")
            bg.paste(im, mask=im.getchannel("A"))
            return bg
        return im.convert("RGB")
    if im.mode not in ("RGB", "RGBA", "L", "P"):
        return im.convert("RGBA")
    return im


def convert(src, out_dir, fmt, opts):
    im = _flatten(_load(src, opts), fmt)
    out = Path(out_dir) / f"{Path(src).stem}.{fmt}"
    kw = {}
    if fmt in ("jpg", "webp", "avif", "heic"):
        kw["quality"] = int(opts.get("quality") or 90)
    if fmt == "ico":
        im.thumbnail((256, 256))  # ICO tops out at 256 px
    im.save(out, PIL_FORMAT[fmt], **kw)
    return [out]


def combine(srcs, out_dir, opts):
    """Several images -> one PDF (a page each) or one animated GIF (a frame each, 0.6 s apiece)."""
    pages = [_flatten(_load(s, opts), "pdf") for s in srcs]
    if opts.get("_fmt") == "gif":
        frames = [ImageOps.pad(p, pages[0].size, color="white") for p in pages]  # GIF frames share one size
        out = Path(out_dir) / "images.gif"
        frames[0].save(out, "GIF", save_all=True, append_images=frames[1:], duration=600, loop=0)
        return [out]
    out = Path(out_dir) / "images.pdf"
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return [out]
