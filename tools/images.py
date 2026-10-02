"""Test pictures for Keshiki's real-Anki checks."""

from pathlib import Path

from aqt.qt import QColor, QImage, QPainter, QPoint


def make_test_image(path: Path, hue: int, w=1600, h=1000) -> Path:
    """A gradient crossed by thin diagonal lines: any offset or scale mismatch
    between two webviews breaks the lines at the seam."""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    for y in range(h):
        p.setPen(QColor.fromHsv(hue, 160, 90 + int(140 * y / h)))
        p.drawLine(0, y, w, y)
    p.setPen(QColor(255, 255, 255))
    for x in range(-h, w, 40):
        p.drawLine(QPoint(x, 0), QPoint(x + h, h))
    p.end()
    img.save(str(path))
    return path
