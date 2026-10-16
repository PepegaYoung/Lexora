"""Native translucent surfaces; no game hooks or injected rendering."""
from PySide6.QtCore import Qt,QRectF,QSize,QRect,QEvent
from PySide6.QtGui import QColor,QPainter,QLinearGradient,QPen
from PySide6.QtWidgets import QFrame,QHBoxLayout,QPushButton,QLabel,QSizeGrip,QVBoxLayout,QAbstractButton,QSizePolicy,QComboBox,QStyle,QStyleOptionComboBox,QStylePainter,QStyleOptionButton,QCheckBox
from .themes import palette
from .ui_icons import device_icon
from .i18n import tr


class Surface(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('surface')
    def paintEvent(self,event):
        colors=palette(self.window().settings['theme'])
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient=QLinearGradient(0,0,self.width(),self.height())
        first=QColor(colors['raised']);first.setAlpha(210)
        last=QColor(colors['bg']);last.setAlpha(195)
        gradient.setColorAt(0,first);gradient.setColorAt(1,last)
        line=QColor(colors['line']);line.setAlpha(170)
        painter.setPen(QPen(line,1));painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),12,12)


class WindowHeader(QFrame):
    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.Resize:
            self.setGeometry(12,8,max(200,watched.width()-24),44);self.raise_()
        return False
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove();event.accept()
        else:super().mousePressEvent(event)
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            window=self.window();window.showNormal() if window.isMaximized() else window.showMaximized()
        else:super().mouseDoubleClickEvent(event)


class ToggleSwitch(QAbstractButton):
    def __init__(self,parent=None):
        super().__init__(parent);self.setCheckable(True);self.setFixedSize(56,32)
        self.setAccessibleName(tr('Автоперевод'));self.toggled.connect(lambda _:self.update())
    def sizeHint(self):return QSize(56,32)
    def paintEvent(self,event):
        colors=palette(self.window().settings['theme'])
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(colors['primary'] if self.isChecked() else colors['line']))
        painter.drawRoundedRect(QRectF(1,2,54,28),14,14)
        painter.setBrush(QColor('#ffffff'));painter.drawEllipse(QRectF(29 if self.isChecked() else 3,4,24,24))


class ReadableCombo(QComboBox):
    """OCR choices wrap at the available width, using the styled edit area."""
    def __init__(self,parent=None):
        super().__init__(parent);self.currentIndexChanged.connect(self.fit_text)
    def sizeHint(self):return QSize(round(320*self.fontMetrics().height()/24),self.text_height())
    def minimumSizeHint(self):return QSize(round(180*self.fontMetrics().height()/24),self.text_height())
    def text_height(self):
        option=QStyleOptionComboBox();self.initStyleOption(option)
        edit=self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,option,QStyle.SubControl.SC_ComboBoxEditField,self)
        bounds=self.fontMetrics().boundingRect(QRect(0,0,max(1,edit.width()-8),1000),Qt.TextFlag.TextWordWrap,self.currentText())
        padding=max(16,self.height()-edit.height()+4)
        return max(self.fontMetrics().height(),bounds.height())+padding
    def fit_text(self):self.setMinimumHeight(self.text_height());self.updateGeometry();self.update()
    def resizeEvent(self,event):super().resizeEvent(event);self.fit_text()
    def paintEvent(self,event):
        option=QStyleOptionComboBox();self.initStyleOption(option);option.currentText=''
        painter=QStylePainter(self);painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox,option)
        rect=self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,option,QStyle.SubControl.SC_ComboBoxEditField,self)
        painter.setPen(QColor(palette(self.window().settings['theme'])['text']))
        painter.drawText(rect.adjusted(4,2,-4,-2),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter|Qt.TextFlag.TextWordWrap,self.currentText())


def shell_header(window,layout,name):
    bar=WindowHeader();row=QHBoxLayout(bar);row.setContentsMargins(0,0,0,8);row.setSpacing(10)
    logo=QLabel();logo.setObjectName('brandLogo');logo.setProperty('iconKind','dictionary')
    logo.setPixmap(device_icon('dictionary').pixmap(40,40));logo.setFixedSize(40,40)
    title=QLabel(name);title.setObjectName('title')
    for label in (logo,title):label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    row.addWidget(logo);row.addWidget(title);row.addStretch()
    for text,tip,action in [('?',tr('Пояснения к этому разделу'),lambda:window.help.page()),
                            ('−',tr('Свернуть'),window.showMinimized),
                            ('□',tr('Развернуть'),lambda:window.showNormal() if window.isMaximized() else window.showMaximized()),
                            ('×',tr('Закрыть'),window.close)]:
        control=QPushButton(text);control.setObjectName('windowControl');control.setFixedSize(34,30)
        control.setAccessibleName(tip);control.setToolTip(tip);control.clicked.connect(action);row.addWidget(control)
    window.shell_header=bar
    bar.setParent(window.centralWidget());window.centralWidget().installEventFilter(bar)
    bar.setGeometry(12,8,window.width()-24,44);bar.show()


def panelize(page):
    """Wrap an existing page's controls without changing signals or ownership."""
    layout=page.layout()
    if not layout or page.property('panelized'):return
    surface=Surface();body=QVBoxLayout(surface);body.setContentsMargins(18,16,18,16);body.setSpacing(12)
    def reparent(item):
        if item.widget():item.widget().setParent(surface)
        elif item.layout():
            for index in range(item.layout().count()):reparent(item.layout().itemAt(index))
    while layout.count():
        item=layout.takeAt(0);reparent(item)
        if item.layout():
            nested=item.layout();nested.setParent(None);body.addLayout(nested)
        else:body.addItem(item)
    layout.addWidget(surface);page.setProperty('panelized',True)
    for button in surface.findChildren(QPushButton):button.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Fixed)


def paint_window(window):
    colors=palette(window.settings['theme'])
    painter=QPainter(window);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    fill=QColor(colors['bg']);fill.setAlpha(245 if colors['light'] else 232)
    painter.setPen(QPen(QColor(colors['line']),1));painter.setBrush(fill)
    painter.drawRoundedRect(QRectF(window.rect()).adjusted(.5,.5,-.5,-.5),14,14)
    if hasattr(window,'tabs'):
        line=QColor(colors['line']);line.setAlpha(100);painter.setPen(QPen(line,1))
        x=window.tabs.list.width()+24;painter.drawLine(x,54,x,window.height()-48)


class ProviderLink(QPushButton):
    def minimumSizeHint(self):return QSize(100,super().minimumSizeHint().height())
    def paintEvent(self,event):
        option=QStyleOptionButton();self.initStyleOption(option)
        option.text=self.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,max(1,self.width()))
        painter=QStylePainter(self);painter.drawControl(QStyle.ControlElement.CE_PushButton,option)


class WrappingCheckBox(QCheckBox):
    def __init__(self,*args):
        super().__init__(*args);self.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Preferred)
    def minimumSizeHint(self):return QSize(150,self.fontMetrics().height()+6)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        rect=self.fontMetrics().boundingRect(QRect(0,0,max(1,self.width()-38),1000),Qt.TextFlag.TextWordWrap,self.text())
        self.setMinimumHeight(max(28,rect.height()+6))
    def paintEvent(self,event):
        option=QStyleOptionButton();self.initStyleOption(option);option.text=''
        painter=QStylePainter(self);painter.drawControl(QStyle.ControlElement.CE_CheckBox,option)
        painter.setPen(QColor(palette(self.window().settings['theme'])['text']))
        painter.drawText(self.rect().adjusted(38,0,0,0),Qt.AlignmentFlag.AlignVCenter|Qt.TextFlag.TextWordWrap,self.text())
