"""Help and demo surfaces confined to the main window's client area."""
from PySide6.QtCore import Qt,QEvent,Signal,QSize
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QMenu,QApplication,QLayout,QWidget
from .themes import stylesheet,palette
from .ui_icons import device_icon


class InAppDialog(QDialog):
    def __init__(self,host,title):
        super().__init__(host,Qt.WindowType.Widget)
        # QDialog's constructor adds Dialog even when passed Widget; remove
        # that default explicitly after construction to keep a real child.
        self.setWindowFlags(Qt.WindowType.Widget)
        self.host=host;self.previous_focus=host.focusWidget()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setObjectName('inAppShade')
        self.setStyleSheet(stylesheet('QDialog#inAppShade { background:rgba(0,0,0,125); }'
                           'QFrame#inAppPanel { background:#101821; border:1px solid #33475e; border-radius:12px; }',
                           host.settings.get('theme','aurora')))
        self.setWindowTitle(title)
        outer=QVBoxLayout(self);outer.setContentsMargins(16,16,16,16)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.panel=QFrame(self);self.panel.setObjectName('inAppPanel');self.panel.setMaximumSize(780,640)
        outer.addWidget(self.panel,1,Qt.AlignmentFlag.AlignCenter)
        self.body=QVBoxLayout(self.panel);self.body.setContentsMargins(20,16,20,16)
        header=QHBoxLayout();label=QLabel(title);label.setObjectName('actionTitle');label.setWordWrap(True);header.addWidget(label,1)
        close=QPushButton('×');close.setFixedSize(28,28);close.setAutoDefault(False);close.clicked.connect(self.reject);header.addWidget(close)
        self.body.addLayout(header)
        self.host.installEventFilter(self);self.fit()

    def fit(self):
        self.setGeometry(self.host.rect())
        self.panel.setFixedSize(max(1,min(780,self.width()-32)),max(1,min(640,self.height()-32)))

    def eventFilter(self,obj,event):
        if obj is self.host and event.type()==QEvent.Type.Resize:self.fit()
        return super().eventFilter(obj,event)

    def open(self):
        # A normal child surface intercepts clicks without creating an OS window
        # or moving focus away from the app (important during game capture).
        self.fit();self.show();self.raise_();self.setFocus()

    def done(self,result):
        super().done(result)
        if self.previous_focus is not None and self.previous_focus.isVisible():self.previous_focus.setFocus()


class InAppHelpMenu(QFrame):
    triggered=Signal(object)
    def __init__(self,host,button):
        super().__init__(host);self.host=host;self.button=button
        self.setObjectName('helpPopover');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.body=QVBoxLayout(self);self.body.setContentsMargins(8,8,8,8);self.body.setSpacing(4)
        self._actions=[];self.rows=[];self.hide()
        QApplication.instance().installEventFilter(self)

    def addAction(self,title,callback):
        action=QAction(title,self);self._actions.append(action)
        row=QPushButton(title,self);row.setObjectName('helpAction');row.setAutoDefault(False)
        row.clicked.connect(action.trigger);self.body.addWidget(row);self.rows.append(row)
        action.triggered.connect(lambda checked=False,a=action:self.activate(a))
        action.triggered.connect(callback)
        return action

    def actions(self):return list(self._actions)

    def activate(self,action):
        self.hide();self.button.setFocus();self.triggered.emit(action)

    def toggle(self):
        if self.isVisible():self.hide();return
        colors=palette(self.host.settings.get('theme','aurora'))
        self.setStyleSheet(f'QFrame#helpPopover {{ background:{colors["field"]}; border:1px solid {colors["line"]}; border-radius:12px; }}'
                          f'QPushButton#helpAction {{ background:transparent; color:{colors["text"]}; border:1px solid transparent; border-radius:7px; padding:10px 12px; text-align:left; }}'
                          f'QPushButton#helpAction:hover,QPushButton#helpAction:focus {{ background:{colors["hover"]}; border-color:{colors["line"]}; }}')
        for row,kind in zip(self.rows,('settings','dictionary')):
            row.setIcon(device_icon(kind,colors['light'],colors['accent']));row.setIconSize(QSize(20,20))
        self.ensurePolished();hint=self.sizeHint()
        self.resize(min(hint.width(),max(1,self.host.width()-24)),hint.height())
        point=self.button.mapTo(self.host,self.button.rect().bottomRight())
        self.move(max(12,min(point.x()-self.width(),self.host.width()-self.width()-12)),
                  max(12,min(point.y()+6,self.host.height()-self.height()-12)))
        self.show();self.raise_()
        if self.rows:self.rows[0].setFocus()

    def eventFilter(self,obj,event):
        if self.isVisible():
            if obj is self.host and event.type()==QEvent.Type.Resize:self.hide()
            # Windows first delivers a real click to QWindow, then to its
            # QWidget target. QWindow has no widget ancestry: treating that
            # first delivery as an outside click hides us before a row fires.
            elif (event.type()==QEvent.Type.MouseButtonPress and isinstance(obj,QWidget)
                  and obj is not self.button and obj is not self and not self.isAncestorOf(obj)):self.hide()
            elif event.type()==QEvent.Type.ApplicationDeactivate:self.hide()
            elif event.type()==QEvent.Type.KeyPress and (obj is self or obj in self.rows):
                if event.key()==Qt.Key.Key_Escape:self.hide();self.button.setFocus();return True
                if event.key() in (Qt.Key.Key_Up,Qt.Key.Key_Down):
                    index=next((i for i,row in enumerate(self.rows) if row.hasFocus()),0)
                    self.rows[(index+(1 if event.key()==Qt.Key.Key_Down else -1))%len(self.rows)].setFocus();return True
                if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
                    row=next((row for row in self.rows if row.hasFocus()),self.rows[0]);row.click();return True
        return super().eventFilter(obj,event)


class HelpButton(QPushButton):
    def menu(self):return self.help_menu
