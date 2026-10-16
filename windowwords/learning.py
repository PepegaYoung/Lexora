from .i18n import tr,trf
from collections import deque
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QPlainTextEdit

class ReviewPage(QWidget):
    speak=Signal(str)
    stop_speech=Signal()
    def __init__(self,store):
        super().__init__()
        self.store=store
        self.queue=deque()
        self.current=None
        self.completed=0
        self.revealed=False
        layout=QVBoxLayout(self)
        self.summary=QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        start=QPushButton(tr('Начать повторение · до 20 слов'))
        start.clicked.connect(self.start)
        layout.addWidget(start)
        self.term=QLabel(tr('Сохраняй слова из карточки — они появятся здесь.'))
        self.term.setWordWrap(True)
        self.term.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.term)
        self.context=QPlainTextEdit()
        self.context.setReadOnly(True)
        self.context.setPlaceholderText(tr('Контекст из игры'))
        layout.addWidget(self.context,1)
        self.answer=QPlainTextEdit()
        self.answer.setReadOnly(True)
        self.answer.setPlaceholderText(tr('Сначала вспомни перевод, затем нажми «Показать перевод».'))
        layout.addWidget(self.answer,1)
        row=QHBoxLayout()
        self.reveal_button=QPushButton(tr('Показать перевод'))
        self.reveal_button.clicked.connect(self.reveal)
        row.addWidget(self.reveal_button)
        self.listen_button=QPushButton(tr('Произнести'))
        self.listen_button.clicked.connect(lambda:self.speak.emit(self.current[1]) if self.current else None)
        row.addWidget(self.listen_button)
        stop=QPushButton(tr('Стоп'))
        stop.clicked.connect(self.stop_speech.emit)
        row.addWidget(stop)
        layout.addLayout(row)
        row=QHBoxLayout()
        self.again=QPushButton(tr('Повторить'))
        self.known=QPushButton(tr('Знаю'))
        self.again.clicked.connect(lambda:self.rate(False))
        self.known.clicked.connect(lambda:self.rate(True))
        row.addWidget(self.again);row.addWidget(self.known)
        layout.addLayout(row)
        self.refresh()
        self.enable(False)
    def refresh(self):
        total,due=self.store.review_stats()
        self.summary.setText(trf('Сохранено: {0} · к повторению: {1} · пройдено в тренировке: {2}',total,due,self.completed))
    def enable(self,revealed):
        active=self.current is not None
        self.reveal_button.setEnabled(active and not revealed)
        self.listen_button.setEnabled(active)
        self.again.setEnabled(active and revealed)
        self.known.setEnabled(active and revealed)
    def start(self):
        self.queue=deque(self.store.due_words())
        self.completed=0
        self.next_word()
    def next_word(self):
        self.stop_speech.emit()
        existing={row[0] for row in self.store.words()}
        self.current=None
        while self.queue:
            candidate=self.queue.popleft()
            if candidate[0] in existing:self.current=candidate;break
        self.answer.clear();self.context.clear();self.revealed=False
        if self.current:
            self.term.setText(self.current[1])
            self.context.setPlainText(self.current[3])
        else:self.term.setText(tr('На сегодня всё. «Повторить» вернёт слово через 10 минут; «Знаю» — через день или позже.'))
        self.enable(False);self.refresh()
    def reveal(self):
        if not self.current:return
        self.answer.setPlainText(self.current[2])
        self.revealed=True
        self.enable(True)
    def rate(self,known):
        if not self.current or not self.revealed:return
        if self.store.review_word(self.current[0],known):self.completed+=1
        self.next_word()
