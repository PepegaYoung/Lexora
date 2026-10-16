from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QColor,QBrush,QLinearGradient
from PySide6.QtWidgets import QWidget
from .core import Box
from .screen_layout import layout
from .screen import intersection,field_columns
from .screen_text import measure_text,wrapped_text
from . import native
from .themes import overlay_palette


class ScreenOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.Tool|
            Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.labels=()
        self.settings={}
        self.entries=()
        self.layer_foreground=None
        self.layer_recoveries=0

    def keep_above_game(self,target):
        active=native.foreground()
        changed=active!=self.layer_foreground
        self.layer_foreground=active
        if not target or active!=target or not self.isVisible() or not self.labels:return
        if changed or not native.window_above(self,target):
            if native.promote_overlay(self):
                self.layer_recoveries+=1
                self.update()

    def display_segments(self,entries,region,monitor,settings,source_lines=(),bounds=None,target=None,protected=()):
        style_changed=self.settings!=settings
        self.entries,self.region,self.monitor,self.settings=entries,region,dict(monitor),dict(settings)
        bounds=intersection(bounds or region,Box(monitor['x'],monitor['y'],monitor['w'],monitor['h']))
        if bounds.w<=0 or bounds.h<=0:self.labels=();self.hide();return len(entries)
        self.viewport=bounds
        position=(bounds.x,bounds.y,bounds.w,bounds.h)
        if not self.isVisible() or getattr(self,'position',None)!=position:
            self.show()
            native.place(self,Box(*position))
            self.position=position
        if not getattr(self,'capture_excluded',False) and not native.exclude_capture(self):
            self.hide()
            raise RuntimeError('Windows не исключил оверлей из захвата. Переводы доступны в истории; оверлей выключен, чтобы не читать себя.')
        self.capture_excluded=True
        scale=self.devicePixelRatioF()
        def local(line):return Box(region.x-bounds.x+line.box.x,region.y-bounds.y+line.box.y,line.box.w,line.box.h)
        positioned=[(local(line),text) for line,text in entries if bounds.contains(region.x+line.box.x+line.box.w/2,region.y+line.box.y+line.box.h/2)]
        obstacles=[local(line) for line in source_lines]
        if settings.get('screen_mode','above')!='replace':obstacles.extend(local(line) for line in protected)
        fields={Box(region.x-bounds.x+box.x,region.y-bounds.y+box.y,box.w,box.h):
                (region.x-bounds.x+left,region.x-bounds.x+right)
                for box,(left,right) in field_columns(source_lines).items()}
        layout_key=(position,scale,settings.get('screen_mode','above'),settings['font_size'],settings['offset'])
        previous=self.labels if getattr(self,'layout_key',None)==layout_key else ()
        self.layout_key=layout_key
        labels,skipped=layout(positioned,bounds.w,bounds.h,settings.get('screen_mode','above'),
            settings['font_size']*scale,settings['offset']*scale,measure_text,obstacles,previous,fields)
        if self.labels!=labels or style_changed:
            self.labels=labels
            self.text_layouts=[wrapped_text(label.text,label.size,label.box.w-8)[0] for label in labels]
            self.update()
        if not self.labels:self.hide()
        else:self.keep_above_game(target)
        return skipped

    def paintEvent(self,event):
        if not self.labels:return
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width()/self.viewport.w,self.height()/self.viewport.h)
        p.setClipRect(QRectF(0,0,self.viewport.w,self.viewport.h))
        mode=self.settings.get('screen_mode','above')
        alpha=round(255*self.settings.get('overlay_background',.58))
        colors=overlay_palette(self.settings.get('overlay_theme','standard'),self.settings.get('theme','aurora'))
        background_alpha=255 if mode=='replace' else alpha
        def backdrop(rect):
            stops=colors.get('gradient')
            if stops:
                gradient=QLinearGradient(rect.topLeft(),rect.bottomRight())
                for index,value in enumerate(stops):
                    color=QColor(value);color.setAlpha(background_alpha)
                    gradient.setColorAt(index/(len(stops)-1),color)
                return QBrush(gradient)
            color=QColor(colors['bg']);color.setAlpha(background_alpha)
            return QBrush(color)
        if mode=='replace':
            # Detector padding can overlap the next row. Mask every original
            # field first, then draw all translations in their separate slots.
            # No tall enclosing panel, and no English descender tails at seams.
            for label in self.labels:
                if label.placement=='field':
                    box=label.source
                    rect=QRectF(box.x-2,box.y-2,box.w+4,box.h+4)
                    p.fillRect(rect,backdrop(rect))
        for label,text_layout in zip(self.labels,self.text_layouts):
            box=label.box
            rect=QRectF(box.x,box.y,box.w,box.h)
            # Replacement must mask the English completely. Above mode may be translucent.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(backdrop(rect))
            p.drawRoundedRect(rect,4,4)
            content=rect.adjusted(4,3 if mode=='above' else 4,-4,-3 if mode=='above' else -4)
            p.save();p.setClipRect(content,Qt.ClipOperation.IntersectClip)
            p.setPen(QColor(255,255,255,240) if colors['light'] else QColor(0,0,0,240))
            for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):text_layout.draw(p,content.topLeft()+QPointF(dx,dy))
            foreground=QColor(colors['text']);foreground.setAlpha(round(255*self.settings.get('opacity',.9)))
            p.setPen(foreground)
            text_layout.draw(p,content.topLeft());p.restore()
