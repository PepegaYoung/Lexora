"""A process-name picker; no executable paths, process handles or memory access."""
from .i18n import tr,trf
from collections import Counter
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLineEdit,QListWidget,QListWidgetItem,QLabel,QPushButton,QFileDialog
from .processes import process_snapshot
from .safety import executable_name

class ProcessPicker(QDialog):
    def __init__(self,parent):
        super().__init__(parent)
        self.setWindowTitle(tr('Привязать игру'));self.resize(560,480);self.selected_exe=''
        layout=QVBoxLayout(self)
        self.search=QLineEdit();self.search.setPlaceholderText(tr('Найти игру по имени EXE'));self.search.textChanged.connect(self.filter)
        layout.addWidget(self.search)
        self.list=QListWidget();layout.addWidget(self.list,1)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout()
        refresh=QPushButton(tr('Обновить'));refresh.clicked.connect(self.refresh)
        file=QPushButton(tr('Выбрать файл…'));file.clicked.connect(self.choose_file)
        self.confirm=QPushButton(tr('Привязать'));self.confirm.setObjectName('primary');self.confirm.setEnabled(False);self.confirm.clicked.connect(self.choose)
        cancel=QPushButton(tr('Отмена'));cancel.clicked.connect(self.reject)
        for button in (refresh,file,self.confirm,cancel):row.addWidget(button)
        layout.addLayout(row)
        self.list.currentItemChanged.connect(lambda item,previous:self.confirm.setEnabled(item is not None and not item.isHidden()))
        self.list.itemDoubleClicked.connect(lambda item:self.choose())
        self.refresh()
    def refresh(self):
        previous=self.list.currentItem().data(Qt.ItemDataRole.UserRole) if self.list.currentItem() else ''
        self.list.clear();self.confirm.setEnabled(False)
        try:names=Counter(name.casefold() for name in process_snapshot().values() if name.lower().endswith('.exe'))
        except OSError:self.status.setText(tr('Не удалось получить список. Нажми «Обновить» или выбери файл.'));return
        for name,count in sorted(names.items()):
            try:executable_name(name)
            except ValueError:continue
            item=QListWidgetItem(name+(trf(' · процессов: {0}',count) if count>1 else ''))
            item.setData(Qt.ItemDataRole.UserRole,name);self.list.addItem(item)
            if name==previous:self.list.setCurrentItem(item)
        self.status.setText(tr('Выбери запущенную игру. Если её ещё нет в списке — запусти и обнови.'))
        self.filter()
    def filter(self,*args):
        text=self.search.text().strip().casefold()
        for i in range(self.list.count()):
            item=self.list.item(i);item.setHidden(text not in item.data(Qt.ItemDataRole.UserRole))
        item=self.list.currentItem();self.confirm.setEnabled(item is not None and not item.isHidden())
    def choose(self):
        item=self.list.currentItem()
        if item is None or item.isHidden():return
        self.selected_exe=item.data(Qt.ItemDataRole.UserRole);self.accept()
    def choose_file(self):
        path,_=QFileDialog.getOpenFileName(self,tr('Выбрать игру'),'',tr('Приложения (*.exe)'))
        if path:self.selected_exe=executable_name(path);self.accept()
