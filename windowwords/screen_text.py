"""Use exactly the same Qt line wrapping for measurement and painting."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont,QFontMetricsF,QTextLayout,QTextOption
from functools import lru_cache


def wrapped_text(text,size,width):
    font=QFont('Segoe UI');font.setPixelSize(max(9,round(size)));font.setBold(True)
    result=QTextLayout(text,font)
    option=QTextOption();option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    result.setTextOption(option);result.beginLayout();height=0
    while True:
        line=result.createLine()
        if not line.isValid():break
        line.setLineWidth(max(1,width));line.setPosition(QPointF(0,height));height+=line.height()
    result.endLayout()
    return result,height


@lru_cache(maxsize=4096)
def measure_text(text,size,width):
    result,height=wrapped_text(text,size,width)
    natural,_=wrapped_text(text,size,1000000)
    # The integer-quantized QFontMetrics advance can be a fraction narrower
    # than QTextLayout. That fraction would unexpectedly wrap a menu label.
    return max((natural.lineAt(i).naturalTextWidth() for i in range(natural.lineCount())),default=0),height
