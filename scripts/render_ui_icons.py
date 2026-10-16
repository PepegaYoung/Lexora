"""Render the source SVG to PNG; the portable app needs no SVG plugin."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

def main():
    app=QApplication.instance() or QApplication([])
    icons=Path(__file__).resolve().parent.parent/'assets/icons'
    for name in ('check','chevron'):
        source=QSvgRenderer(str(icons/(name+'.svg')))
        if not source.isValid():raise RuntimeError('Invalid UI icon: '+name)
        image=QImage(16,16,QImage.Format.Format_ARGB32_Premultiplied);image.fill(Qt.GlobalColor.transparent)
        painter=QPainter(image);source.render(painter);painter.end()
        if not image.save(str(icons/(name+'.png'))):raise RuntimeError('Cannot save UI icon: '+name)

if __name__=='__main__':main()
