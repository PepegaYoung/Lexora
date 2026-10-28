"""Shared binding matrix; the original input recorders keep ownership of input."""
from PySide6.QtCore import Qt,QSize,QRectF,QRect,QEvent
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QWidget,QGridLayout,QLabel,QHBoxLayout,QSizePolicy,QStyle,QStyleOptionFrame,QToolButton
from .controls import HotkeyEdit
from .gamepad_controls import GamepadEdit
from .themes import palette
from .i18n import tr
from .ui_icons import device_icon
from .reading_widgets import divider


class TableLabel(QLabel):
    """Allow a long device name to wrap instead of clipping at large scales."""
    def __init__(self,text):
        super().__init__(text);self.setWordWrap(True)
        policy=QSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True);self.setSizePolicy(policy)

    def minimumSizeHint(self):return QSize(0,self.fontMetrics().height())
    def wrap_flags(self,width):
        return Qt.TextFlag.TextWordWrap if max((self.fontMetrics().horizontalAdvance(word) for word in self.text().split()),default=0)<=width else Qt.TextFlag.TextWrapAnywhere
    def heightForWidth(self,width):
        return self.fontMetrics().boundingRect(QRect(0,0,max(1,width),10000),self.wrap_flags(width),self.text()).height()+4
    def resizeEvent(self,event):
        super().resizeEvent(event);self.setMinimumHeight(self.heightForWidth(self.width()))
    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(),Qt.AlignmentFlag.AlignVCenter|self.wrap_flags(self.width()),self.text())


class KeycapPaint:
    """Paint keycaps without changing the recorder's canonical text or signals."""
    def init_keycaps(self):
        self.setObjectName('bindingKeycap')
        self.setMinimumWidth(0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.textChanged.connect(self.fit_keycaps)
        self.recordingChanged.connect(self.fit_keycaps)
        self.fit_keycaps()

    def keycap_lines(self,width):
        metrics=self.fontMetrics();gap=metrics.horizontalAdvance(' + ')
        limit=max(1,width-20);lines=[]
        for chord in self.text().split(';'):
            if not chord.strip():continue
            line=[];used=0
            for token in chord.strip().split('+'):
                token=token.strip()
                size=min(limit,metrics.horizontalAdvance(token)+14)
                if line and used+gap+size>limit:
                    lines.append(line);line=[];used=0
                line.append((token,size));used+=size+(gap if len(line)>1 else 0)
            if line:lines.append(line)
        return lines

    def fit_keycaps(self,*args):
        if not hasattr(self,'recording'):return
        lines=self.keycap_lines(self.width())
        height=self.fontMetrics().height()+10
        empty=self.fontMetrics().boundingRect(QRect(0,0,max(1,self.width()-18),10000),Qt.TextFlag.TextWrapAnywhere,tr('Не назначено')).height()+16
        self.setFixedHeight(max(height+16,empty,len(lines)*(height+5)+11))
        self.update()

    def sizeHint(self):
        return QSize(160,self.height())

    def minimumSizeHint(self):
        return QSize(0,self.fontMetrics().height()+26)

    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_keycaps()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange):self.fit_keycaps()

    def paintEvent(self,event):
        colors=palette(getattr(self.window(),'settings',{}).get('theme','dark'))
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        option=QStyleOptionFrame();self.initStyleOption(option)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_PanelLineEdit,option,painter,self)
        painter.setClipRect(self.rect().adjusted(5,4,-5,-4))
        waiting=self.recording and not self.assigned
        if waiting or not self.text():
            text=tr('Нажмите кнопки…') if waiting and self.device_kind=='gamepad' else tr('Нажмите клавиши…') if waiting and self.device_kind=='keyboard' else tr('Нажмите кнопку…') if waiting else tr('Не назначено')
            painter.setPen(QColor(colors['accent'] if waiting else colors['dim']))
            painter.drawText(self.rect().adjusted(9,4,-9,-4),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWrapAnywhere,text)
            return
        metrics=self.fontMetrics();height=metrics.height()+10;gap=metrics.horizontalAdvance(' + ')
        lines=self.keycap_lines(self.width())
        y=(self.height()-len(lines)*(height+5)+5)/2
        for line in lines:
            x=(self.width()-sum(size for _,size in line)-gap*(len(line)-1))/2
            for index,(token,size) in enumerate(line):
                if index:
                    painter.setPen(QColor(colors['muted']))
                    painter.drawText(QRectF(x,y,gap,height),Qt.AlignmentFlag.AlignCenter,'+')
                    x+=gap
                rect=QRectF(x,y,size,height)
                painter.setBrush(QColor(colors['raised']))
                painter.setPen(QPen(QColor(colors['line']),1))
                painter.drawRoundedRect(rect.adjusted(.5,.5,-.5,-.5),4,4)
                painter.setPen(QColor(colors['text']))
                painter.drawText(rect.adjusted(5,0,-5,0),Qt.AlignmentFlag.AlignCenter,metrics.elidedText(token,Qt.TextElideMode.ElideRight,max(1,int(size-10))))
                x+=size
            y+=height+5


class BindingKeyEdit(KeycapPaint,HotkeyEdit):
    def __init__(self,value,device):
        super().__init__(value,device);self.device_kind=device;self.init_keycaps()


class BindingGamepadEdit(KeycapPaint,GamepadEdit):
    def __init__(self,value):
        super().__init__(value);self.device_kind='gamepad';self.init_keycaps()


class BindingTable(QWidget):
    def __init__(self):
        super().__init__();self.setObjectName('bindingTable')
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0)
        self.grid.setHorizontalSpacing(14);self.grid.setVerticalSpacing(10)
        for column,stretch in enumerate((4,3,3,3,3)):self.grid.setColumnStretch(column,stretch)
        self.headers={};self.icons={};self.action_labels={}
        title=TableLabel(tr('Устройство'));title.setObjectName('subtitle');self.grid.addWidget(title,0,0)
        self.gamepad_panel=QWidget();self.gamepad_panel.setObjectName('gamepadControls')
        self.gamepad_grid=QGridLayout(self.gamepad_panel);self.gamepad_grid.setContentsMargins(0,12,0,12)
        self.gamepad_grid.setHorizontalSpacing(14);self.gamepad_grid.setVerticalSpacing(10)
        for column,stretch in enumerate((4,3,3,3,3)):self.gamepad_grid.setColumnStretch(column,stretch)
        self.grid.addWidget(self.gamepad_panel,6,0,1,5)
        self.gamepad_grid.addWidget(divider(),1,0,1,5)
        for index,(device,title) in enumerate((('keyboard','Клавиатура'),('mouse','Мышь'),('gamepad','Геймпад'))):
            header=QWidget();row=QHBoxLayout(header);row.setContentsMargins(0,0,0,0);row.setSpacing(7)
            icon=QLabel();icon.setProperty('iconKind',device);icon.setFixedSize(20,20);icon.setPixmap(device_icon(device).pixmap(20,20))
            label=TableLabel(tr(title));label.setObjectName('subtitle')
            row.addWidget(icon);row.addWidget(label,1)
            if device=='gamepad':self.gamepad_grid.addWidget(header,0,0)
            else:self.grid.addWidget(header,2+index*2,0);self.grid.addWidget(divider(),3+index*2,0,1,5)
            self.headers[device]=header;self.icons[device]=icon
        self.grid.addWidget(divider(),1,0,1,5)

    def add_action(self,index,action,caption,icon_kind,fields,reset):
        heading=QWidget();row=QHBoxLayout(heading);row.setContentsMargins(0,0,0,0);row.setSpacing(9)
        icon=QLabel();icon.setFixedSize(20,20);icon.setProperty('iconKind',icon_kind);icon.setPixmap(device_icon(icon_kind).pixmap(20,20))
        label=TableLabel(caption);row.addWidget(icon);row.addWidget(label,1)
        self.action_labels[action]=label;self.grid.addWidget(heading,0,index+1)
        for device_index,field in enumerate(fields):
            device=('keyboard','mouse','gamepad')[device_index]
            cell=QWidget();line=QHBoxLayout(cell);line.setContentsMargins(0,0,0,0);line.setSpacing(4)
            line.addWidget(field,1)
            restore=QToolButton();restore.setText('↺');restore.setFixedSize(28,28)
            restore.setToolTip(tr('Вернуть стандартную привязку'))
            restore.setAccessibleName(tr('Вернуть стандартную привязку')+' · '+caption)
            restore.clicked.connect(lambda checked=False,kind=device:reset(action,kind))
            line.addWidget(restore)
            if device_index==2:self.gamepad_grid.addWidget(cell,0,index+1)
            else:self.grid.addWidget(cell,2+device_index*2,index+1)

    def add_gamepad_controls(self,widget):self.gamepad_grid.addWidget(widget,2,0,1,5)
