from PySide6.QtCore import Qt,QEvent,QTimer,QSize,QObject
from PySide6.QtWidgets import QWidget,QGridLayout,QVBoxLayout,QHBoxLayout,QLabel,QToolButton,QPushButton,QSizePolicy,QFrame,QComboBox,QScrollArea
from .ui_icons import device_icon

def divider():
    line=QFrame();line.setObjectName('divider');line.setFixedHeight(1)
    return line

class StableModeRow(QWidget):
    """Aligned label and mode buttons; wrap below the label on narrow views."""
    def __init__(self):
        super().__init__();self.items=[]
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(8)
    def addWidget(self,widget):
        widget.setParent(self);widget.show();self.items.append(widget);self.fit()
    def fit(self):
        while self.grid.count():self.grid.takeAt(0)
        visible=self.items[:1]+[item for item in self.items[1:] if not item.isHidden()]
        if not visible:return
        label=visible[0];label.setWordWrap(True)
        controls=visible[1:];available=max(1,self.width())
        ancestor=self.parentWidget()
        while ancestor:
            if isinstance(ancestor,QScrollArea):
                available=min(available,max(1,ancestor.viewport().width()-48));break
            ancestor=ancestor.parentWidget()
        label_width=round(200*self.fontMetrics().height()/20)
        required=sum(item.minimumSizeHint().width() for item in controls)+8*len(controls)
        wrap=available<label_width+required
        stacked=wrap and required>available
        self.grid.addWidget(label,0,0,1,1 if stacked else max(1,len(controls)) if wrap else 1)
        for index,widget in enumerate(controls):
            if isinstance(widget,QPushButton) and widget.objectName()=='segment':
                widget.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            self.grid.addWidget(widget,index+1 if stacked else 1 if wrap else 0,0 if stacked else index if wrap else index+1)
        for index in range(5):
            self.grid.setColumnStretch(index,1 if (stacked and index==0) or (wrap and index<len(controls)) or (not wrap and 0<index<len(visible)) else 0)
            self.grid.setColumnMinimumWidth(index,label_width if index==0 and not wrap else 0)
        height=max((item.sizeHint().height() for item in controls),default=32)
        rows=len(controls) if stacked else 1
        self.setMinimumHeight(rows*max(height+4,round(49*self.fontMetrics().height()/24))+(label.sizeHint().height()+8 if wrap else 0))
    def resizeEvent(self,event):super().resizeEvent(event);self.fit()

class CompactFieldSizer(QObject):
    """Content-sized controls that keep the same proportions at larger fonts."""
    def __init__(self,widget,width):
        super().__init__(widget);self.widget=widget;self.width=width
        widget.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Fixed)
        if isinstance(widget,QComboBox):
            widget.setMinimumContentsLength(14)
            widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        widget.installEventFilter(self);self.fit()
    def fit(self):self.widget.setMaximumWidth(round(self.width*self.widget.fontMetrics().height()/17))
    def eventFilter(self,widget,event):
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange):self.fit()
        return False

class CompactRow(QWidget):
    """Wrap short controls instead of forcing a horizontal scrollbar."""
    def __init__(self):
        super().__init__();self.items=[];self.signature=None
        self.grid=QVBoxLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(8)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.fit)
    def addWidget(self,widget):
        self.items.append(widget);widget.installEventFilter(self);self.grid.addWidget(widget)
        self.timer.start(0)
    def fit(self):
        available=max(1,self.width());row=column=used=0;positions=[]
        for widget in self.items:
            if widget.isHidden():continue
            width=max(widget.minimumWidth(),min(widget.maximumWidth(),widget.sizeHint().width()))
            if column and used+8+width>available:row+=1;column=used=0
            positions.append((widget,row,column));column+=1;used+=width+8
        signature=tuple((id(w),r,c) for w,r,c in positions)
        if signature==self.signature:return
        self.signature=signature
        while self.grid.count():
            item=self.grid.takeAt(0)
            if item.layout():
                while item.layout().count():item.layout().takeAt(0)
                item.layout().deleteLater()
        for r in range(max((r for _,r,_ in positions),default=-1)+1):
            line=QHBoxLayout();line.setSpacing(8)
            for widget,widget_row,_ in positions:
                if widget_row==r:
                    if self.objectName()=='pageHeading' and widget is self.items[-1]:line.addStretch()
                    line.addWidget(widget,1 if self.objectName()=='cardChecks' else 0)
            if self.objectName() not in ('cardChecks','pageHeading'):line.addStretch()
            self.grid.addLayout(line)
    def resizeEvent(self,event):super().resizeEvent(event);self.fit()
    def eventFilter(self,widget,event):
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange,QEvent.Type.Show,QEvent.Type.Hide):self.timer.start(0)
        return False

class ActionButton(QPushButton):
    """The shortcut is part of the same clickable action, as in the mockup."""
    def __init__(self,title,action,primary=False):
        super().__init__()
        if primary:self.setObjectName('primary')
        self.body=QHBoxLayout(self);self.body.setContentsMargins(10,5,10,5);self.body.setSpacing(10)
        self.caption=QLabel(title);self.shortcut=QLabel();self.shortcut.setObjectName('buttonShortcut')
        for label in (self.caption,self.shortcut):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);self.body.addWidget(label)
        self.clicked.connect(action);self.setText(title)
        self.shortcut_only=False
    def set_shortcut_only(self):
        self.shortcut_only=True;self.caption.hide();self.setObjectName('shortcutAction')
        self.body.setContentsMargins(12,6,12,6)
        self.shortcut.setAlignment(Qt.AlignmentFlag.AlignCenter)
    def setText(self,title):
        self.caption.setText(title);self.update_name();self.updateGeometry()
    def text(self):return self.caption.text()
    def set_shortcut(self,text):
        self.shortcut.setText(text);self.shortcut.setVisible(bool(text));self.update_name();self.updateGeometry()
    def update_name(self):self.setAccessibleName(self.caption.text()+' '+self.shortcut.text())
    def sizeHint(self):
        if getattr(self,'shortcut_only',False):
            return QSize(max(round(108*self.fontMetrics().height()/17),self.shortcut.fontMetrics().horizontalAdvance(self.shortcut.text())+26),max(40,self.shortcut.fontMetrics().height()+16))
        return self.body.sizeHint().expandedTo(QSize(80,32))
    def minimumSizeHint(self):return self.sizeHint()

class ActionRow(QWidget):
    """Keep actions aligned; move the button below text when fonts need room."""
    def __init__(self,title,description,kind,button):
        super().__init__();self.setObjectName('actionRow')
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,14,0,14);self.grid.setHorizontalSpacing(16)
        self.icon=QLabel();self.icon.setPixmap(device_icon(kind).pixmap(24,24));self.icon.setFixedSize(24,24)
        self.icon.setProperty('iconKind',kind)
        self.text=QWidget();column=QVBoxLayout(self.text);column.setContentsMargins(0,0,0,0);column.setSpacing(4)
        self.title=QLabel(title);self.title.setObjectName('actionTitle');self.title.setWordWrap(True)
        self.description=QLabel(description);self.description.setObjectName('subtitle');self.description.setWordWrap(True)
        column.addWidget(self.title);column.addWidget(self.description)
        self.controls=QWidget();controls=QVBoxLayout(self.controls);controls.setContentsMargins(0,0,0,0)
        controls.addWidget(button)
        self.shortcut=button.shortcut
        self.controls.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Preferred)
        self.grid.addWidget(self.icon,0,0,Qt.AlignmentFlag.AlignVCenter);self.grid.addWidget(self.text,0,1);self.grid.addWidget(self.controls,0,2)
        self.grid.setColumnStretch(1,1);self.wrapped=False
        self.fit_timer=QTimer(self);self.fit_timer.setSingleShot(True);self.fit_timer.timeout.connect(self.fit)

    def fit(self):
        desired=self.title.fontMetrics().horizontalAdvance(self.title.text())+self.controls.sizeHint().width()+80
        wrap=self.width()<desired
        if wrap==self.wrapped:return
        self.wrapped=wrap;self.grid.removeWidget(self.text);self.grid.removeWidget(self.controls)
        self.grid.addWidget(self.text,0,1,1,2 if wrap else 1)
        self.grid.addWidget(self.controls,1 if wrap else 0,1 if wrap else 2,1,2 if wrap else 1,Qt.AlignmentFlag.AlignLeft if wrap else Qt.AlignmentFlag.AlignRight)

    def resizeEvent(self,event):super().resizeEvent(event);self.fit()
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange) and hasattr(self,'fit_timer'):self.fit_timer.start(0)

class DevicePanels(QWidget):
    """Full-width lists with a heading above each device."""
    def __init__(self):
        super().__init__();self.panels=[];self.columns=0
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(10)
        self.fit_timer=QTimer(self);self.fit_timer.setSingleShot(True);self.fit_timer.timeout.connect(self.fit)
    def add_panel(self,panel):self.panels.append(panel);self.columns=0;self.fit()
    def fit(self):
        columns=1
        for panel in self.panels:
            grid=panel.layout()
            if panel.property('headingWrapped') is True:continue
            panel.setProperty('headingWrapped',True)
            grid.removeItem(panel.binding_heading);grid.removeWidget(panel.binding_fields)
            grid.setColumnMinimumWidth(0,0)
            grid.addLayout(panel.binding_heading,0,0,1,2,Qt.AlignmentFlag.AlignTop)
            grid.addWidget(panel.binding_fields,1,0,1,2)
            if panel.binding_extras:
                grid.removeWidget(panel.binding_extras)
                grid.addWidget(panel.binding_extras,2,0,1,2)
        if columns==self.columns:return
        self.columns=columns
        for panel in self.panels:self.grid.removeWidget(panel)
        for i,panel in enumerate(self.panels):
            self.grid.addWidget(panel,i*2,0)
            if i and not self.grid.itemAtPosition(i*2-1,0):self.grid.addWidget(divider(),i*2-1,0)
        for i in range(3):self.grid.setColumnStretch(i,1 if i<columns else 0)
    def resizeEvent(self,event):super().resizeEvent(event);self.fit()
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange) and hasattr(self,'fit_timer'):self.fit_timer.start(0)

class BindingFields(QWidget):
    """One action per row, with its binding beside the label."""
    def __init__(self):
        super().__init__();self.entries=[];self.columns=0
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(7)
        self.fit_timer=QTimer(self);self.fit_timer.setSingleShot(True);self.fit_timer.timeout.connect(self.fit)
    def add_field(self,label,field):
        entry=QWidget();entry.setObjectName('bindingRow');body=QGridLayout(entry);body.setContentsMargins(0,7,0,7);body.setHorizontalSpacing(12);body.setColumnStretch(0,1)
        field.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        title=QLabel(label);title.setWordWrap(True)
        body.addWidget(title,0,0);body.addWidget(field,0,1);self.entries.append(entry);self.columns=0;self.fit()
    def fit(self):
        scale=self.fontMetrics().height()/17
        for entry in self.entries:
            body=entry.layout();body.setColumnMinimumWidth(0,0)
            field=body.itemAtPosition(0,1).widget()
            field.setFixedWidth(round(150*scale))
        columns=1
        if columns==self.columns:return
        self.columns=columns
        for entry in self.entries:self.grid.removeWidget(entry)
        for i,entry in enumerate(self.entries):self.grid.addWidget(entry,i,0)
        for i in range(4):self.grid.setColumnStretch(i,1 if i<columns else 0)
    def resizeEvent(self,event):super().resizeEvent(event);self.fit()
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange) and hasattr(self,'fit_timer'):self.fit_timer.start(0)

class Foldout(QWidget):
    def __init__(self,title):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.toggle=QToolButton();self.toggle.setText(title);self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        layout.addWidget(self.toggle,0,Qt.AlignmentFlag.AlignLeft)
        self.content=QWidget();self.body=QVBoxLayout(self.content);self.body.setContentsMargins(0,10,0,10)
        layout.addWidget(self.content);self.content.hide();self.toggle.toggled.connect(self.set_expanded)
    def set_expanded(self,expanded):
        self.toggle.setChecked(expanded);self.content.setVisible(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
