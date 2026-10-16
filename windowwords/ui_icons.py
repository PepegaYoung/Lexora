"""Small painted device icons; no font-dependent emoji or extra runtime."""
from PySide6.QtCore import Qt,QSize,QPointF,QRectF
from PySide6.QtGui import QIcon,QPixmap,QPainter,QPen,QColor,QPainterPath,QFont

def theme_swatch(colors):
    pixmap=QPixmap(58,16);pixmap.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pixmap);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    for index,role in enumerate(('bg','raised','primary','accent','text')):
        painter.setBrush(QColor(colors[role]));painter.drawRoundedRect(QRectF(index*12,2,10,12),3,3)
    painter.end();return QIcon(pixmap)


def device_icon(kind,light=False,accent=None):
    pixmap=QPixmap(24,24);pixmap.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pixmap);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen=QPen(QColor(accent or ('#186a61' if light else '#7de0cc')),1.7);pen.setCapStyle(Qt.PenCapStyle.RoundCap);pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin);painter.setPen(pen)
    if kind in ('lock','unlock'):
        painter.drawRoundedRect(QRectF(5,11,14,10),2,2)
        if kind=='lock':
            painter.drawArc(QRectF(8,3,8,14),0,180*16);painter.drawLine(8,10,8,12);painter.drawLine(16,10,16,12)
        else:
            painter.drawArc(QRectF(10,2,10,12),0,180*16);painter.drawLine(10,8,10,11)
        painter.drawLine(12,15,12,17)
    elif kind=='keyboard':
        painter.drawRoundedRect(QRectF(2,5,20,14),3,3)
        for y in (9,12):
            for x in (6,10,14,18):painter.drawPoint(QPointF(x,y))
        painter.drawLine(7,16,17,16)
    elif kind=='mouse':
        painter.drawRoundedRect(QRectF(6,2,12,20),6,6)
        painter.drawLine(6,10,18,10);painter.drawLine(12,3,12,9)
    elif kind=='dictionary':
        painter.drawRoundedRect(QRectF(2,4,10,16),2,2);painter.drawRoundedRect(QRectF(12,4,10,16),2,2)
        painter.drawLine(12,5,12,21)
    elif kind in ('frame','ocr'):
        for x,y,dx,dy in ((3,3,5,5),(21,3,-5,5),(3,21,5,-5),(21,21,-5,-5)):
            painter.drawLine(x,y,x+dx,y);painter.drawLine(x,y,x,y+dy)
        for y in (8,12,16):painter.drawLine(8,y,16,y)
    elif kind in ('auto','review'):
        painter.drawArc(QRectF(4,4,16,16),35*16,280*16)
        painter.drawLine(19,4,20,10);painter.drawLine(20,10,14,9)
    elif kind=='game':
        painter.drawRoundedRect(QRectF(2,3,20,14),2,2);painter.drawLine(12,17,12,21);painter.drawLine(7,21,17,21)
    elif kind=='monitor':
        painter.drawRoundedRect(QRectF(2,3,20,14),2,2);painter.drawLine(12,17,12,21);painter.drawLine(7,21,17,21)
    elif kind=='region':
        pen.setStyle(Qt.PenStyle.DashLine);painter.setPen(pen);painter.drawRoundedRect(QRectF(3,3,18,18),2,2)
    elif kind=='layers':
        for offset in (0,5):
            path=QPainterPath();path.moveTo(2,9+offset);path.lineTo(12,3+offset);path.lineTo(22,9+offset);path.lineTo(12,15+offset);path.closeSubpath();painter.drawPath(path)
    elif kind=='window':
        painter.drawRoundedRect(QRectF(2,3,20,18),2,2);painter.drawLine(2,8,22,8)
    elif kind=='text_above':
        painter.setFont(QFont('Segoe UI',12));painter.drawText(QRectF(3,1,18,18),Qt.AlignmentFlag.AlignCenter,'A');painter.drawLine(4,22,20,22)
    elif kind=='translate':
        painter.drawRoundedRect(QRectF(2,2,14,11),2,2)
        painter.drawLine(4,13,4,16);painter.drawLine(4,16,7,13)
        painter.drawLine(5,6,12,6);painter.drawLine(5,9,9,9)
        painter.drawRoundedRect(QRectF(10,12,12,9),2,2)
        painter.drawLine(20,21,20,23);painter.drawLine(20,23,17,21)
        painter.drawLine(13,16,19,16);painter.drawLine(17,14,19,16);painter.drawLine(19,16,17,18)
    elif kind=='words':
        path=QPainterPath();path.moveTo(6,3);path.lineTo(18,3);path.lineTo(18,21);path.lineTo(12,17);path.lineTo(6,21);path.closeSubpath();painter.drawPath(path)
    elif kind=='safety':
        path=QPainterPath();path.moveTo(12,2);path.lineTo(21,6);path.lineTo(19,15);path.quadTo(17,20,12,22);path.quadTo(7,20,5,15);path.lineTo(3,6);path.closeSubpath();painter.drawPath(path)
        painter.drawLine(8,12,11,15);painter.drawLine(11,15,17,9)
    elif kind=='history':
        painter.drawEllipse(QRectF(3,3,18,18));painter.drawLine(12,6,12,12);painter.drawLine(12,12,16,15)
    elif kind=='settings':
        for y,x in ((6,8),(12,16),(18,10)):
            painter.drawLine(3,y,x-2,y);painter.drawLine(x+2,y,21,y);painter.drawEllipse(QPointF(x,y),2,2)
    elif kind=='image':
        painter.drawRoundedRect(QRectF(2,3,20,18),2,2);painter.drawEllipse(QPointF(8,8),2,2)
        painter.drawLine(3,19,10,12);painter.drawLine(10,12,14,16);painter.drawLine(14,16,18,11);painter.drawLine(18,11,21,14)
    else:
        painter.drawRoundedRect(QRectF(2,6,20,13),5,5)
        painter.drawLine(5,12,11,12);painter.drawLine(8,9,8,15)
        painter.drawEllipse(QPointF(16,10),.7,.7);painter.drawEllipse(QPointF(19,13),.7,.7)
    painter.end();return QIcon(pixmap)
