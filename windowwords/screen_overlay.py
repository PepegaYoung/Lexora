from PySide6.QtCore import Qt,QRectF,QRect
from PySide6.QtGui import QPainter,QColor,QFont,QFontMetrics
from PySide6.QtWidgets import QWidget
from .core import Box
from .screen_layout import layout
from . import native


class ScreenOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool|
            Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.labels=()
        self.settings={}
        self.entries=()

    def display_segments(self,entries,region,monitor,settings,source_lines=()):
        style_changed=self.settings!=settings
        self.entries,self.region,self.monitor,self.settings=entries,region,dict(monitor),dict(settings)
        position=(monitor['x'],monitor['y'],monitor['w'],monitor['h'])
        if not self.isVisible() or getattr(self,'position',None)!=position:
            self.show()
            native.place(self,Box(*position))
            self.position=position
        if not getattr(self,'capture_excluded',False) and not native.exclude_capture(self):
            self.hide()
            raise RuntimeError('Windows не исключил оверлей из захвата. Переводы доступны в истории; оверлей выключен, чтобы не читать себя.')
        self.capture_excluded=True
        scale=self.devicePixelRatioF()
        def measure(text,size,width):
            font=QFont('Segoe UI');font.setPixelSize(size);font.setBold(True)
            fm=QFontMetrics(font)
            rect=fm.boundingRect(QRect(0,0,max(1,round(width)),10000),int(Qt.TextFlag.TextWordWrap),text)
            return fm.horizontalAdvance(text),rect.height()
        positioned=[(Box(region.x-monitor['x']+line.box.x,region.y-monitor['y']+line.box.y,line.box.w,line.box.h),text) for line,text in entries]
        obstacles=[Box(region.x-monitor['x']+l.box.x,region.y-monitor['y']+l.box.y,l.box.w,l.box.h) for l in source_lines]
        labels,skipped=layout(positioned,monitor['w'],monitor['h'],settings.get('screen_mode','above'),
            settings['font_size']*scale,settings['offset']*scale,measure,obstacles)
        if self.labels!=labels or style_changed:self.labels=labels;self.update()
        if not self.labels:self.hide()
        return skipped

    def paintEvent(self,event):
        if not self.labels:return
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width()/self.monitor['w'],self.height()/self.monitor['h'])
        mode=self.settings.get('screen_mode','above')
        alpha=round(255*self.settings.get('overlay_background',.58))
        for label in self.labels:
            box=label.box
            rect=QRectF(box.x,box.y,box.w,box.h)
            # Replacement must mask the English completely. Above mode may be translucent.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(10,17,28,255 if mode=='replace' else alpha))
            p.drawRoundedRect(rect,4,4)
            if mode=='above' and label.source.y-box.y-box.h>self.settings.get('offset',14)+15:
                p.setPen(QColor(130,203,240,160))
                p.drawLine(round(box.x+box.w/2),round(box.y+box.h),round(label.source.x+label.source.w/2),round(label.source.y-2))
            font=QFont('Segoe UI');font.setPixelSize(label.size);font.setBold(True)
            p.setFont(font)
            content=rect.adjusted(4,2 if mode=='above' else 4,-4,-2 if mode=='above' else -4)
            flags=int(Qt.TextFlag.TextWordWrap|Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
            p.setPen(QColor(0,0,0,240))
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):p.drawText(content.translated(dx,dy),flags,label.text)
            p.setPen(QColor(229,246,255,round(255*self.settings.get('opacity',.9))))
            p.drawText(content,flags,label.text)
