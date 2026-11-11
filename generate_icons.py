"""Generate logo.png and the Windows icon (app.ico) from logo.svg, the single source of the mark.

Usage: python generate_icons.py   (needs PySide6 and Pillow, both in requirements.txt)
"""
import io
import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image
from PySide6.QtCore import QBuffer, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(renderer, size):
    """The mark at `size` pixels, drawn directly at that size so small icons stay crisp."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGBA')


def main():
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(ROOT / 'logo.svg'))
    if not renderer.isValid():
        raise SystemExit('logo.svg could not be read')
    render(renderer, 512).save(ROOT / 'logo.png')
    frames = [render(renderer, size) for size in ICON_SIZES]
    frames[-1].save(ROOT / 'app.ico', format='ICO', sizes=[(size, size) for size in ICON_SIZES],
                    append_images=frames[:-1])
    del app


if __name__ == '__main__':
    main()
