#!/usr/bin/env python3
"""make_cover.py: typografisches Cover-Bild (quadratisches JPEG) fuer ein Musik-Release.

Stil: fast schwarzer Hintergrund, duenne Einfassung, Akzentblock oben links,
grosser Titel, geletterter Kuenstlername in Akzentfarbe, Trennlinie, Meta-Zeile
(z.B. Release-Datum). Die Ausgabe landet als ``featured.jpg`` in einem Hugo
Page Bundle (HugoBlox erkennt den Namen automatisch fuer Cards/Hero).

Beispiel — Cover des Singles "Genosse" neu erzeugen:

    python3 tools/make_cover.py \
        --title GENOSSE --artist "Ma Paix" --meta "SINGLE · 13 JUNE 2026" \
        --out content/blog/2026-11-17-genosse-single/featured.jpg

Voraussetzung: Pillow (``pip install pillow``) und die DejaVu-Schriften
(``fonts-dejavu`` auf Debian/Ubuntu).
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT_DIR = "/usr/share/fonts/TTF"


def hex_color(value: str) -> tuple:
    value = value.lstrip("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError(f"erwartet #rrggbb, bekommen: {value!r}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def load_font(font_dir: str, name: str, size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(font_dir, name)
    if not os.path.exists(path):
        sys.exit(f"Schrift nicht gefunden: {path} (--font-dir setzen)")
    return ImageFont.truetype(path, size)


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[0], bbox[1]


def draw_centered(draw, cx, y, text, font, fill):
    w, h, ox, oy = text_size(draw, text, font)
    draw.text((cx - w / 2 - ox, y - oy), text, font=font, fill=fill)


def draw_tracked(draw, cx, y, text, font, fill, tracking):
    """Text zentriert bei cx zeichnen, mit zusaetzlichem Letter-Spacing (tracking in px)."""
    chars = list(text)
    widths = [text_size(draw, c, font)[0] for c in chars]
    total = sum(widths) + tracking * (len(chars) - 1)
    x = cx - total / 2
    for c, w in zip(chars, widths):
        _, _, ox, oy = text_size(draw, c, font)
        draw.text((x - ox, y - oy), c, font=font, fill=fill)
        x += w + tracking


def make_cover(title, artist, meta, out, size=1200, bg="#111318",
               accent="#d43a2f", fg="#f0f0f2", muted="#969aa2",
               frame="#3c4048", quality=92, font_dir=DEFAULT_FONT_DIR):
    s = size
    img = Image.new("RGB", (s, s), bg)
    d = ImageDraw.Draw(img)

    m = round(s * 40 / 1200)                       # aeusserer Rand
    d.rectangle([m, m, s - m, s - m], outline=frame, width=max(2, round(s * 3 / 1200)))

    # Akzentblock, oben links
    d.rectangle([m, m, m + round(s * 300 / 1200), m + round(s * 92 / 1200)], fill=accent)

    f_title = load_font(font_dir, "DejaVuSans-Bold.ttf", round(s * 190 / 1200))
    draw_centered(d, s / 2, s * 430 / 1200, title, f_title, fg)

    if artist:
        f_artist = load_font(font_dir, "DejaVuSans.ttf", round(s * 64 / 1200))
        draw_tracked(d, s / 2, s * 700 / 1200, artist.upper(),
                     f_artist, accent, tracking=round(s * 18 / 1200))

    # Trennlinie
    d.line([s / 2 - s * 0.15, s * 830 / 1200, s / 2 + s * 0.15, s * 830 / 1200],
           fill=muted, width=max(2, round(s * 3 / 1200)))

    if meta:
        f_meta = load_font(font_dir, "DejaVuSans.ttf", round(s * 40 / 1200))
        draw_centered(d, s / 2, s * 880 / 1200, meta.upper(), f_meta, muted)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out, quality=quality)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--title", required=True, help="Release-Titel, z.B. GENOSSE")
    ap.add_argument("--artist", default="", help="Kuenstlername, z.B. 'Ma Paix'")
    ap.add_argument("--meta", default="", help="Meta-Zeile, z.B. 'SINGLE · 13 JUNE 2026'")
    ap.add_argument("--out", required=True, help="Ausgabe-JPEG (im Page Bundle featured.jpg verwenden)")
    ap.add_argument("--size", type=int, default=1200, help="Kantenlaenge in px (Default 1200)")
    ap.add_argument("--bg", type=hex_color, default=hex_color("#111318"), help="Hintergrund #rrggbb")
    ap.add_argument("--accent", type=hex_color, default=hex_color("#d43a2f"), help="Akzentfarbe #rrggbb")
    ap.add_argument("--fg", type=hex_color, default=hex_color("#f0f0f2"), help="Titel-Farbe #rrggbb")
    ap.add_argument("--muted", type=hex_color, default=hex_color("#969aa2"), help="Meta/Trennlinien-Farbe #rrggbb")
    ap.add_argument("--frame", type=hex_color, default=hex_color("#3c4048"), help="Rahmen-Farbe #rrggbb")
    ap.add_argument("--quality", type=int, default=92, help="JPEG-Qualitaet (Default 92)")
    ap.add_argument("--font-dir", default=DEFAULT_FONT_DIR)
    args = ap.parse_args()

    out = make_cover(args.title, args.artist, args.meta, args.out, size=args.size,
                     bg=args.bg, accent=args.accent, fg=args.fg, muted=args.muted,
                     frame=args.frame, quality=args.quality, font_dir=args.font_dir)
    print(f"Cover geschrieben: {out}")


if __name__ == "__main__":
    main()
