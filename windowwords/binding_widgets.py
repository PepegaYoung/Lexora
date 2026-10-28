"""Shared binding matrix; the original input recorders keep ownership of input."""
from PySide6.QtCore import Qt,QSize,QRectF,QRect,QEvent
from PySide6.QtGui import QPainter,QColor,QPen,QPainterPath
from PySide6.QtWidgets import QWidget,QGridLayout,QLabel,QHBoxLayout,QVBoxLayout,QSizePolicy,QToolButton,QFrame,QAbstractButton
from .controls import HotkeyEdit
from .gamepad_controls import GamepadEdit
from .themes import palette
from .i18n import tr
from .ui_icons import device_icon
from .reading_widgets import divider
from .visual_shell import Surface


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
        limit=max(1,width-20-(32 if hasattr(self,'reset_button') else 0));lines=[]
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
        empty=self.fontMetrics().boundingRect(QRect(0,0,max(1,self.width()-18-(32 if hasattr(self,'reset_button') else 0)),10000),Qt.TextFlag.TextWrapAnywhere,tr('Не назначено')).height()+16
        self.setFixedHeight(max(48,self.fontMetrics().height()+24,empty,len(lines)*(height+5)+11))
        self.update()

    def sizeHint(self):
        return QSize(160,self.height())

    def minimumSizeHint(self):
        return QSize(0,self.fontMetrics().height()+26)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'reset_button'):
            self.reset_button.move(max(0,self.width()-38),max(0,(self.height()-34)//2))
        self.fit_keycaps()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange):self.fit_keycaps()

    def paintEvent(self,event):
        colors=palette(getattr(self.window(),'settings',{}).get('theme','dark'))
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(colors['raised']))
        highlighted=self.recording or (hasattr(self,'reset_button') and self.reset_button.underMouse())
        painter.setPen(QPen(QColor(colors['focus'] if highlighted else colors['line']),1.5 if highlighted else 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),6,6)
        reserve=40 if hasattr(self,'reset_button') else 0
        content=self.rect().adjusted(0,0,-reserve,0)
        painter.setClipRect(content.adjusted(5,4,-5,-4))
        waiting=self.recording and not self.assigned
        if waiting or not self.text():
            text=tr('Нажмите кнопки…') if waiting and self.device_kind=='gamepad' else tr('Нажмите клавиши…') if waiting and self.device_kind=='keyboard' else tr('Нажмите кнопку…') if waiting else tr('Не назначено')
            painter.setPen(QColor(colors['accent'] if waiting else colors['dim']))
            painter.drawText(content.adjusted(16,4,-3,-4),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter|Qt.TextFlag.TextWordWrap,text)
            return
        painter.setPen(QColor(colors['text']))
        text=self.text().replace('+',' + ')
        painter.drawText(content.adjusted(16,4,-3,-4),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter|Qt.TextFlag.TextWordWrap,text)


class ResetBindingButton(QToolButton):
    """A crisp vector reset arrow with an explicit hover target."""
    def __init__(self,parent):
        super().__init__(parent)
        self.setFixedSize(34,34);self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr('Вернуть по умолчанию'))
        self.setStyleSheet('QToolButton { border: 0; background: transparent; padding: 0; }')
    def enterEvent(self,event):super().enterEvent(event);self.update();self.parentWidget().update()
    def leaveEvent(self,event):super().leaveEvent(event);self.update();self.parentWidget().update()
    def paintEvent(self,event):
        colors=palette(getattr(self.window(),'settings',{}).get('theme','aurora'))
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse():
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(colors['hover']));p.drawRoundedRect(QRectF(2,2,30,30),6,6)
        pen=QPen(QColor(colors['accent'] if self.underMouse() else colors['muted']),2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap);pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin);p.setPen(pen);p.setBrush(Qt.BrushStyle.NoBrush)
        path=QPainterPath();path.moveTo(10,11);path.cubicTo(14,7,22,8,24,14)
        path.cubicTo(27,22,18,27,12,23);p.drawPath(path)
        p.drawLine(10,11,14,7);p.drawLine(10,11,15,12)


class GamepadSwitch(QAbstractButton):
    def __init__(self):
        super().__init__();self.setCheckable(True);self.setFixedSize(48,26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def paintEvent(self,event):
        colors=palette(getattr(self.window(),'settings',{}).get('theme','aurora'))
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(colors['primary'] if self.isChecked() else colors['line']))
        p.drawRoundedRect(QRectF(0,1,48,24),12,12)
        p.setBrush(QColor('#ffffff'));p.drawEllipse(QRectF(25 if self.isChecked() else 3,4,18,18))


class BindingKeyEdit(KeycapPaint,HotkeyEdit):
    def __init__(self,value,device):
        super().__init__(value,device);self.device_kind=device;self.init_keycaps()


class BindingGamepadEdit(KeycapPaint,GamepadEdit):
    def __init__(self,value):
        super().__init__(value);self.device_kind='gamepad';self.init_keycaps()


class BindingTable(QWidget):
    def __init__(self):
        super().__init__();self.setObjectName('bindingTable')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(12)
        self.matrix=Surface();outer.addWidget(self.matrix)
        self.grid=QGridLayout(self.matrix);self.grid.setContentsMargins(18,16,18,16)
        self.grid.setHorizontalSpacing(14);self.grid.setVerticalSpacing(16)
        for column,stretch in enumerate((2,3,3,3,3)):self.grid.setColumnStretch(column,stretch)
        self.headers={};self.icons={};self.action_labels={}
        self.grid.setRowMinimumHeight(0,110)
        self.gamepad_panel=QWidget();self.gamepad_panel.setObjectName('gamepadControls')
        self.gamepad_grid=QGridLayout(self.gamepad_panel);self.gamepad_grid.setContentsMargins(0,12,0,12)
        self.gamepad_grid.setHorizontalSpacing(14);self.gamepad_grid.setVerticalSpacing(10)
        for column,stretch in enumerate((2,3,3,3,3)):self.gamepad_grid.setColumnStretch(column,stretch)
        self.grid.addWidget(self.gamepad_panel,6,0,1,5)
        self.gamepad_grid.addWidget(divider(),1,0,1,5)
        for index,(device,title) in enumerate((('keyboard','Клавиатура'),('mouse','Мышь'),('gamepad','Геймпад'))):
            header=QWidget();row=QHBoxLayout(header);row.setContentsMargins(0,0,0,0);row.setSpacing(7)
            icon=QLabel();icon.setProperty('iconKind',device);icon.setFixedSize(28,28);icon.setPixmap(device_icon(device).pixmap(28,28))
            label=TableLabel(tr(title));label.setObjectName('subtitle')
            row.addWidget(icon);row.addWidget(label,1)
            if device=='gamepad':self.gamepad_grid.addWidget(header,0,0)
            else:self.grid.addWidget(header,2+index*2,0);self.grid.addWidget(divider(),3+index*2,0,1,5)
            self.headers[device]=header;self.icons[device]=icon
        self.grid.addWidget(divider(),1,0,1,5)

    def add_action(self,index,action,caption,icon_kind,fields,reset):
        heading=QWidget();row=QVBoxLayout(heading);row.setContentsMargins(0,0,0,0);row.setSpacing(7)
        icon=QLabel();icon.setObjectName('iconTile');icon.setAlignment(Qt.AlignmentFlag.AlignCenter);icon.setFixedSize(36,36);icon.setProperty('iconKind',icon_kind);icon.setPixmap(device_icon(icon_kind).pixmap(36,36))
        label=QLabel(caption);label.setAlignment(Qt.AlignmentFlag.AlignCenter);label.setWordWrap(True);label.setStyleSheet('font-weight: 600;')
        descriptions={'study':'Показать перевод слова под курсором в игре','region':'Выбрать область для перевода', 'toggle':'Распознавать и переводить текст','screen':'Распознать и перевести текст на экране игры'}
        description=QLabel(tr(descriptions[action]));description.setObjectName('subtitle');description.setWordWrap(True);description.setAlignment(Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop)
        row.addWidget(icon,0,Qt.AlignmentFlag.AlignHCenter);row.addWidget(label);row.addWidget(description);row.addStretch()
        self.action_labels[action]=label;self.grid.addWidget(heading,0,index+1)
        for device_index,field in enumerate(fields):
            device=('keyboard','mouse','gamepad')[device_index]
            restore=ResetBindingButton(field);field.reset_button=restore
            restore.setAccessibleName(tr('Вернуть по умолчанию')+' · '+caption)
            restore.clicked.connect(lambda checked=False,kind=device:reset(action,kind))
            field.fit_keycaps()
            if device_index==2:self.gamepad_grid.addWidget(field,0,index+1)
            else:self.grid.addWidget(field,2+device_index*2,index+1)

    def add_gamepad_controls(self,widget):
        panel=Surface();layout=QVBoxLayout(panel);layout.setContentsMargins(18,12,18,12);layout.addWidget(widget)
        self.layout().addWidget(panel)
