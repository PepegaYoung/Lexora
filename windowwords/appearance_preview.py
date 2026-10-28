"""Local previews reuse the real card and screen painters, without captures or requests."""
from PySide6.QtCore import Qt,QPoint,QRectF,QTimer
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QLinearGradient,QRegion
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QGridLayout,QSizePolicy,QScrollArea,QStackedWidget,QButtonGroup
from .i18n import tr,trf
from .core import Box
from .widgets import Card
from .screen_overlay import ScreenOverlay
from .screen_layout import layout
from .screen_text import measure_text,wrapped_text
from .reading_widgets import CompactRow
from . import native
from .in_app_dialog import InAppDialog
from .ui_icons import device_icon
from .themes import palette,mix


def configure_demo_capture(dialog,settings):
    dialog.setProperty('captureVisible',bool(settings.get('recording_visible',False)))
    # In-app panels inherit their host's capture policy; applying affinity to
    # a child would create a needless native child handle and fail on Windows.
    host=dialog.window();host.setProperty('captureVisible',dialog.property('captureVisible'))
    native.exclude_capture(host)


def render_widget(widget):
    image=QImage(widget.size(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
    widget.ensurePolished()
    if widget.layout():widget.layout().activate()
    widget.render(image,QPoint(),QRegion(),QWidget.RenderFlag.DrawChildren)
    return image


class PreviewCanvas(QWidget):
    def __init__(self,kind,settings,parent=None,full_size=False,compact=False):
        super().__init__(parent);self.kind=kind;self.settings=dict(settings);self.image=None;self.full_size=full_size;self.compact=compact
        self.setMinimumHeight(245);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.sample=None
        self.refresh_timer=QTimer(self);self.refresh_timer.setSingleShot(True);self.refresh_timer.timeout.connect(self.refresh)

    def create_sample(self):
        self.sample=Card() if self.kind=='card' else ScreenOverlay()
        # Keep the native widgets off screen and render only into an image.
        # Reparenting a translucent card as a regular child crashes Qt on
        # Windows, so retain a hidden tool surface owned by this canvas.
        self.sample.setParent(self,Qt.WindowType.Tool);self.sample.hide()
        self.sample.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        if self.kind=='card':
            self.sample.term.setText('sword');self.sample.sentence.setPlainText('He drew his sword.')
            self.sample.dictionary.setPlainText(tr('меч · существительное'))
            self.sample.answer.setPlainText(tr('Он обнажил свой меч.'))
            self.sample.status.setText(tr('Учебный пример'))

    def set_settings(self,settings):
        self.settings=dict(settings);self.fit_card();self.refresh_timer.start(0)

    def fit_card(self):
        if self.kind!='card' or self.full_size or self.compact:return
        # Allocate the full aspect ratio instead of squeezing a cropped card
        # into a short landscape scene. Never upscale the raster sample.
        width=self.settings.get('card_width',600);height=self.settings.get('card_height',700)
        self.setFixedHeight(round(min(1,max(1,self.width()-24)/width)*height)+20)

    def refresh(self):
        if not self.isVisible():return
        settings=self.settings
        key=(self.width(),self.height(),tuple((name,str(settings.get(name))) for name in
             ('theme','card_theme','card_width','card_height','card_background','overlay_theme',
              'overlay_background','font_size','offset','opacity','screen_mode','ui_scale')))
        if getattr(self,'render_key',None)==key:return
        if self.sample is None:self.create_sample()
        self.render_key=key
        if self.kind=='card':
            self.sample.resize(settings.get('card_width',600),settings.get('card_height',700))
            self.sample.apply_background(settings.get('card_background',.72),settings.get('card_theme') or settings.get('theme','aurora'))
            pixels=round(14*1.2*settings.get('ui_scale',100)/100)
            self.sample.setStyleSheet(self.sample.styleSheet()+f'\nQWidget {{ font-size:{pixels}px; }}')
            if self.compact:
                # Keep the demo readable at its actual displayed width instead
                # of shrinking the full 600x700 card into a small screenshot.
                width=max(320,min(settings.get('card_width',600),self.width()-32))
                self.sample.status.hide()
                for field in (self.sample.sentence,self.sample.dictionary,self.sample.answer):
                    field.setFixedHeight(pixels*3+14)
                self.sample.resize(width,900);self.sample.ensurePolished();self.sample.layout().activate()
                content=self.sample.content_area.widget()
                content.layout().activate()
                self.sample.resize(width,min(1100,content.layout().minimumSize().height()+64))
        else:
            width=max(280,self.width());height=max(180,self.height())
            self.sample.resize(width,height);self.sample.viewport=Box(0,0,width,height)
            font=QFont('Segoe UI');font.setPixelSize(20)
            from PySide6.QtGui import QFontMetricsF
            metrics=QFontMetricsF(font);text='He drew his sword.'
            source_width=metrics.horizontalAdvance(text);source_height=metrics.height()
            self.source=Box((width-source_width)/2,height*.66,source_width,source_height)
            mode=settings.get('screen_mode','above')
            labels,skipped=layout([(self.source,tr('Он обнажил свой меч.'))],width,height,mode,
                                  settings.get('font_size',22),settings.get('offset',14),measure_text,[self.source])
            self.sample.settings=settings;self.sample.labels=labels
            self.sample.text_layouts=[wrapped_text(l.text,l.size,l.box.w-8)[0] for l in labels]
        self.image=render_widget(self.sample);self.update()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'refresh_timer'):self.fit_card();self.refresh_timer.start(0)

    def showEvent(self,event):super().showEvent(event);self.refresh_timer.start(0)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        colors=palette(self.settings.get('theme','aurora'))
        scene=mix(colors['raised'],colors['accent'],.13 if not colors['light'] else .07)
        p.fillRect(self.rect(),QColor(scene))
        if self.kind=='screen' and hasattr(self,'source'):
            font=QFont('Segoe UI');font.setPixelSize(20);p.setFont(font);p.setPen(QColor('#ffffff'))
            p.drawText(QRectF(self.source.x,self.source.y,self.source.w+2,self.source.h+2),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop,'He drew his sword.')
        if self.image and not self.image.isNull():
            image=self.image
            target=QRectF(self.rect()).adjusted(12,10,-12,-10) if self.kind=='card' else QRectF(self.rect())
            if self.kind=='card':
                fitted=image.size().scaled(round(target.width()),round(target.height()),Qt.AspectRatioMode.KeepAspectRatio)
                target=QRectF((self.width()-fitted.width())/2,(self.height()-fitted.height())/2,fitted.width(),fitted.height())
            p.drawImage(target,image)


class PreviewBlocks(QWidget):
    def __init__(self,read_settings,parent=None):
        super().__init__(parent);self.read_settings=read_settings;self.dialogs=[];self.current_kind='card';self.stacked=None
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(10)
        heading=QLabel(tr('Примеры оформления'));heading.setObjectName('actionTitle');self.grid.addWidget(heading,0,0)
        self.choices=CompactRow();self.grid.addWidget(self.choices,1,0)
        self.buttons={};self.titles={};self.captions={};self.icon_labels={};self.canvases={};self.group=QButtonGroup(self)
        self.viewer=QFrame(self);self.viewer.setObjectName('previewFrame');body=QVBoxLayout(self.viewer);body.setContentsMargins(12,12,12,12);body.setSpacing(8)
        self.frame_title=QLabel(tr('Предпросмотр'));self.frame_title.setObjectName('previewFrameTitle');body.addWidget(self.frame_title)
        self.pages=QStackedWidget();body.addWidget(self.pages)
        for kind,title in (('card','Карточка слова'),('screen','Экранный перевод')):
            button=QPushButton();button.setCheckable(True);button.setObjectName('previewChoice');button.setAccessibleName(tr(title))
            row=QHBoxLayout(button);row.setContentsMargins(12,8,12,8);row.setSpacing(8)
            icon=QLabel();icon.setFixedSize(20,20);row.addWidget(icon)
            label=QLabel(tr(title));label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);row.addWidget(label)
            caption=QLabel();caption.setObjectName('subtitle');caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);caption.hide()
            icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            button.clicked.connect(lambda checked=False,key=kind:self.select(key));self.group.addButton(button);self.choices.addWidget(button)
            self.buttons[kind]=button;self.titles[kind]=label;self.captions[kind]=caption;self.icon_labels[kind]=icon
            canvas=PreviewCanvas(kind,read_settings(),self.pages,compact=True);self.pages.addWidget(canvas);self.canvases[kind]=canvas
        self.grid.addWidget(self.viewer,2,0)
        self.open_button=QPushButton(tr('Открыть пример'));self.open_button.clicked.connect(lambda:self.open_example(self.current_kind))
        actions=CompactRow();actions.addWidget(self.open_button);self.grid.addWidget(actions,3,0)
        self.style_caption=QLabel();self.style_caption.setObjectName('subtitle');self.style_caption.setWordWrap(True)
        self.style_caption.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed);body.addWidget(self.style_caption)
        self.buttons['card'].setChecked(True);self.fit();self.refresh()

    def select(self,kind):
        if kind not in self.canvases:return
        self.current_kind=kind;self.buttons[kind].setChecked(True)
        self.pages.setCurrentWidget(self.canvases[kind]);self.update_caption()
        self.canvases[kind].refresh_timer.start(0)

    def update_caption(self):
        settings=self.read_settings();kind=self.current_kind
        from .themes import card_palette,overlay_palette
        colors=(card_palette(settings.get('card_theme') or settings.get('theme','aurora')) if kind=='card' else
                overlay_palette(settings.get('overlay_theme','standard'),settings.get('theme','aurora')))
        opacity=settings.get('card_background',.72) if kind=='card' else settings.get('overlay_background',.85)
        self.style_caption.setText(trf('{0} · Фон {1}%',tr(colors['label']),round(opacity*100)))

    def fit(self):
        if not hasattr(self,'viewer'):return
        settings=self.read_settings();scale=settings.get('ui_scale',100)/100
        available=self.width();ancestor=self.parentWidget()
        while ancestor:
            if isinstance(ancestor,QScrollArea):available=min(available,max(1,ancestor.viewport().width()-48));break
            ancestor=ancestor.parentWidget()
        height=round(480*min(scale,1.35))
        for canvas in self.canvases.values():canvas.setFixedHeight(height)
        self.pages.setFixedHeight(height)
        self.style_caption.setFixedHeight(self.style_caption.fontMetrics().height()*2)
        for kind,button in self.buttons.items():
            metrics=self.titles[kind].fontMetrics()
            button.setMinimumSize(metrics.horizontalAdvance(self.titles[kind].text())+60,max(40,metrics.height()+16))
        self.stacked=available < sum(button.minimumWidth() for button in self.buttons.values())+8
        self.choices.fit()

    def resizeEvent(self,event):super().resizeEvent(event);self.fit()

    def refresh(self,*args):
        settings=self.read_settings()
        for canvas in self.canvases.values():canvas.set_settings(settings)
        self.captions['card'].setText(trf('{0} × {1} px',settings['card_width'],settings['card_height']))
        self.captions['screen'].setText(tr('Вместо оригинала') if settings.get('screen_mode')=='replace' else tr('Над оригиналом'))
        colors=palette(settings.get('theme','aurora'))
        frame=mix(colors['raised'],colors['accent'],.09 if not colors['light'] else .04)
        self.setStyleSheet(f'QFrame#previewFrame {{ background:{frame}; border:1px solid {colors["accent"]}; border-radius:10px; }}'
                          f'QLabel#previewFrameTitle {{ color:{colors["accent"]}; background:transparent; border:0; }}'
                          f'QPushButton#previewChoice {{ background:{colors["raised"]}; border:1px solid {colors["line"]}; border-radius:7px; padding:0; }}'
                          f'QPushButton#previewChoice:checked {{ background:{colors["selected"]}; border-color:{colors["accent"]}; }}'
                          f'QPushButton#previewChoice:hover {{ background:{colors["hover"]}; }}'
                          f'QPushButton#previewChoice QLabel {{ background:transparent; border:0; padding:0; }}')
        for kind,icon in self.icon_labels.items():icon.setPixmap(device_icon('dictionary' if kind=='card' else 'frame',colors['light'],colors['accent']).pixmap(20,20))
        self.stacked=None;self.fit();self.update_caption()

    def open_example(self,kind):
        settings=self.read_settings();dialog=InAppDialog(self.window(),tr('Пример карточки') if kind=='card' else tr('Пример экранного перевода'))
        body=dialog.body;area=QScrollArea();area.setWidgetResizable(True);body.addWidget(area,1)
        canvas=PreviewCanvas(kind,settings,full_size=True);area.setWidget(canvas)
        if kind=='card':
            canvas.setMinimumSize(settings['card_width']+24,settings['card_height']+20)
        else:canvas.setMinimumSize(700,300)
        close=QPushButton(tr('Закрыть'));close.clicked.connect(dialog.accept);body.addWidget(close,0,Qt.AlignmentFlag.AlignRight)
        self.dialogs.append(dialog)
        dialog.finished.connect(lambda *_ :self.dialogs.remove(dialog) if dialog in self.dialogs else None)
        dialog.open();configure_demo_capture(dialog,settings);canvas.refresh()
