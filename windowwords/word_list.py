"""Saved words in a compact table; each cell retains the complete record."""
from .i18n import tr,trf
from datetime import datetime
from html import escape
from PySide6.QtCore import Qt,Signal,QSignalBlocker
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QTableWidget,QTableWidgetItem,QHeaderView,QStyledItemDelegate,QStyle


class WordDelegate(QStyledItemDelegate):
    def initStyleOption(self,option,index):
        super().initStyleOption(option,index)
        option.state &= ~QStyle.StateFlag.State_HasFocus


class WordList(QTableWidget):
    currentRowChanged=Signal(int)

    def __init__(self):
        super().__init__(0,5);self.setObjectName('wordList')
        self.setHorizontalHeaderLabels([tr('Слово'),tr('Перевод'),tr('Контекст'),tr('Игра'),tr('Дата')])
        self.setItemDelegate(WordDelegate(self))
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setShowGrid(False);self.setWordWrap(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalHeader().hide()
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header=self.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        header.setMinimumSectionSize(0)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.currentCellChanged.connect(lambda row,*_:self.currentRowChanged.emit(row))

    def count(self):return self.rowCount()

    def item(self,row,column=0):return super().item(row,column)

    def setCurrentRow(self,row):self.setCurrentCell(row,0)

    def set_records(self,records):
        selected=self.currentItem().data(Qt.ItemDataRole.UserRole)[0] if self.currentItem() else None
        with QSignalBlocker(self):
            self.setRowCount(0);self.setRowCount(len(records));current=0
            for row,record in enumerate(records):
                try:date=datetime.fromisoformat(str(record[5])).strftime('%d.%m.%Y')
                except (ValueError,TypeError):date=str(record[5])
                values=(record[1],record[2],record[3],record[4] or '—',date)
                for column,value in enumerate(values):
                    text=' '.join(str(value).split())
                    item=QTableWidgetItem(text);item.setData(Qt.ItemDataRole.UserRole,record)
                    # Tooltips parse rich text: encode values, preserving whitespace and lines.
                    tooltip='<p style="white-space:pre-wrap">'+escape(str(value)).replace('\n','<br>')+'</p>'
                    item.setToolTip(tooltip);self.setItem(row,column,item)
                if record[0]==selected:current=row
        if records:self.setCurrentRow(current)
        self.fit_columns()

    def fit_columns(self):
        width=self.viewport().width()
        # Give the phrase most of the space; elided cells retain full tooltips.
        weights=(18,23,31,16,12);used=0
        for column,weight in enumerate(weights):
            size=max(0,width-used) if column==4 else round(width*weight/100)
            self.setColumnWidth(column,size);used+=size
        height=QFontMetrics(self.font()).height()+20
        self.verticalHeader().setDefaultSectionSize(height)
        self.setMaximumHeight(self.horizontalHeader().height()+height*self.rowCount()+2*self.frameWidth())

    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_columns()
