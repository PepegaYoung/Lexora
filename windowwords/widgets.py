from PySide6.QtCore import Qt,QRectF,QTimer,Signal,QPointF
from PySide6.QtGui import QImage,QPainter,QColor,QPen,QFont,QPainterPath
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QBoxLayout,QScrollArea,QSizePolicy,QLabel,QPushButton,
                             QPlainTextEdit,QLineEdit,QSizeGrip,QApplication)
from .core import Box,map_selection,selected_text
from . import native


def qimage(image):
    rgb = image.convert('RGB')
    return QImage(rgb.tobytes(),rgb.width,rgb.height,rgb.width*3,QImage.Format.Format_RGB888).copy()


class Freeze(QWidget):
    selected = Signal(object,object,str,str)
    closed = Signal()
    hovered=Signal(str,str)

    def __init__(self, image, monitor, mode='study'):
        super().__init__()
        self.image,self.monitor,self.mode = image,monitor,mode
        self.picture = qimage(image)
        self.lines = ()
        self.start = self.end = None
        self.hover_word = None
        self.hover_sentence=''
        self.auto_card=True
        self.word_timer=QTimer(self)
        self.word_timer.setSingleShot(True)
        self.word_timer.setInterval(450)
        self.word_timer.timeout.connect(self.preview_word)
        self.notice = 'Выдели область. Escape — закрыть.'
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def show_on_monitor(self,topmost=True,fullscreen=False):
        self.show()
        if fullscreen:
            screen=next((s for s in QApplication.screens() if s.name()==self.monitor['name']),None)
            if screen:self.windowHandle().setScreen(screen)
            self.showFullScreen()
        native.place(self,Box(self.monitor['x'],self.monitor['y'],self.monitor['w'],self.monitor['h']),True,topmost=topmost)
        self.raise_()
        self.activateWindow()
        native.exclude_capture(self)

    def set_auto_card(self,enabled):
        self.auto_card=bool(enabled)
        if not self.auto_card:self.word_timer.stop()

    def preview_word(self):
        if self.auto_card and self.mode=='study' and self.hover_word and not QApplication.mouseButtons():
            self.hovered.emit(self.hover_word.text,self.hover_sentence)

    def set_lines(self, lines):
        self.lines = lines
        self.notice = 'Нажми на слово или выдели выражение. Escape — закрыть.' if lines else 'Текст не найден. Выдели нужный фрагмент для повторного OCR.'
        self.update()

    def image_point(self, point):
        rect=self.image_rect()
        return (point.x()-rect.x())*self.image.width/rect.width(),(point.y()-rect.y())*self.image.height/rect.height()

    def image_rect(self):
        factor=min(self.width()/self.image.width,self.height()/self.image.height)
        width,height=self.image.width*factor,self.image.height*factor
        return QRectF((self.width()-width)/2,(self.height()-height)/2,width,height)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(),QColor('#0c1420'))
        image_rect=self.image_rect()
        p.drawImage(image_rect,self.picture)
        sx,sy = image_rect.width()/self.image.width,image_rect.height()/self.image.height
        if self.hover_word:
            b = self.hover_word.box
            p.fillRect(QRectF(image_rect.x()+b.x*sx,image_rect.y()+b.y*sy,b.w*sx,b.h*sy),QColor(81,192,255,90))
            p.setPen(QPen(QColor('#69d5ff'),2))
            p.drawRect(QRectF(image_rect.x()+b.x*sx,image_rect.y()+b.y*sy,b.w*sx,b.h*sy))
        if self.start and self.end:
            selection = QRectF(self.start,self.end).normalized()
            p.fillRect(selection,QColor(96,190,255,45))
            p.setPen(QPen(QColor('#69d5ff'),2))
            p.drawRect(selection)
        notice_width = max(0,min(self.width()-220,800))
        p.fillRect(QRectF(20,18,notice_width,45),QColor(12,20,32,230))
        p.setFont(QFont('Segoe UI',11))
        p.setPen(QColor('#f4f6fb'))
        notice = p.fontMetrics().elidedText(self.notice,Qt.TextElideMode.ElideRight,max(0,int(notice_width-28)))
        p.drawText(QRectF(34,18,max(0,notice_width-28),45),Qt.AlignmentFlag.AlignVCenter,notice)
        p.fillRect(QRectF(self.width()-190,18,170,45),QColor('#205779'))
        p.drawText(QRectF(self.width()-190,18,170,45),Qt.AlignmentFlag.AlignCenter,'Закрыть · Esc')

    def mousePressEvent(self, event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.word_timer.stop()
            if QRectF(self.width()-190,18,170,45).contains(event.position()):
                self.close()
                return
            self.start = self.end = event.position()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.start:
            self.word_timer.stop()
            self.end = event.position()
        else:
            x,y = self.image_point(event.position())
            found=next(((w,line.text) for line in self.lines for w in line.words if w.box.contains(x,y)),None)
            word,sentence=found if found else (None,'')
            if word!=self.hover_word or sentence!=self.hover_sentence:
                self.word_timer.stop()
                self.hover_word,self.hover_sentence=word,sentence
                if word and self.auto_card and self.mode=='study':self.word_timer.start()
        self.update()

    def leaveEvent(self,event):
        self.word_timer.stop()
        self.hover_word=None
        self.hover_sentence=''
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.start or event.button()!=Qt.MouseButton.LeftButton:
            return
        self.end = event.position()
        rect = QRectF(self.start,self.end).normalized()
        if rect.width()<5 and rect.height()<5 and self.mode=='study':
            x,y = self.image_point(self.end)
            for line in self.lines:
                for word in line.words:
                    if word.box.contains(x,y):
                        self.selected.emit(None,None,word.text,line.text)
                        return
            self.notice = 'Не удалось выбрать слово. Выдели фрагмент прямоугольником.'
            self.update()
            return
        image_rect=self.image_rect()
        rect=rect.intersected(image_rect)
        if rect.isEmpty():return
        box = map_selection((rect.x()-image_rect.x(),rect.y()-image_rect.y(),rect.width(),rect.height()),self.image.width,self.image.height,image_rect.width(),image_rect.height())
        if box.w<5 or box.h<5:
            return
        crop = self.image.crop((box.x,box.y,box.x+box.w,box.y+box.h))
        chosen = selected_text(self.lines,box)
        sentence = '\n'.join(line.text for line in self.lines if any(
            box.contains(w.box.x+w.box.w/2,w.box.y+w.box.h/2) for w in line.words))
        self.selected.emit(crop,box,chosen,sentence)

    def keyPressEvent(self, event):
        if event.key()==Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, event):
        self.word_timer.stop()
        self.closed.emit()
        super().closeEvent(event)


class Card(QWidget):
    analyze = Signal()
    translate_sentence = Signal()
    save = Signal()
    dismissed = Signal()
    translate_source = Signal()
    wiktionary=Signal()
    speak_word=Signal()
    speak_context=Signal()
    stop_speech=Signal()
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Lexora · слово')
        self.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.background_alpha=.72
        self.light=False
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(560,600)
        self.setMinimumSize(400,400)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        header_row=QHBoxLayout()
        header_row.setContentsMargins(8,4,8,0)
        self.header=CardHeader(self)
        header_row.addWidget(self.header,1)
        self.close_button=QPushButton('×')
        self.close_button.setAccessibleName('Закрыть карточку')
        self.close_button.setToolTip('Закрыть разбор')
        self.close_button.setFixedSize(30,30)
        self.close_button.setStyleSheet('QPushButton { padding:0; border-radius:7px; }')
        self.close_button.clicked.connect(self.dismissed.emit)
        header_row.addWidget(self.close_button,0,Qt.AlignmentFlag.AlignTop)
        outer.addLayout(header_row)
        self.content_area = QScrollArea()
        self.content_area.setWidgetResizable(True)
        self.content_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.content_area.viewport().setAutoFillBackground(False)
        content = QWidget()
        content.setObjectName('cardContent')
        content.setAutoFillBackground(False)
        self.content_area.setWidget(content)
        outer.addWidget(self.content_area)
        layout = QVBoxLayout(content)
        label = QLabel('Слово или фраза')
        layout.addWidget(label)
        self.term = QLineEdit()
        self.term.setPlaceholderText('Слово или выражение — можно исправить')
        layout.addWidget(self.term)
        layout.addWidget(QLabel('Контекст'))
        self.sentence = QPlainTextEdit()
        self.sentence.setPlaceholderText('Исходная реплика')
        self.sentence.setMaximumHeight(95)
        self.sentence.setMinimumHeight(60)
        self.sentence.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Ignored)
        layout.addWidget(self.sentence,1)
        self.dictionary = QPlainTextEdit()
        self.dictionary.setReadOnly(True)
        self.dictionary.setMinimumHeight(80)
        self.dictionary.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Ignored)
        layout.addWidget(self.dictionary,2)
        source=QPushButton('Статья в Викисловаре ↗')
        source.setToolTip('Открыть статью на ru.wiktionary.org в браузере. Нужен интернет.')
        source.clicked.connect(self.wiktionary.emit)
        layout.addWidget(source)
        self.answer = QPlainTextEdit()
        self.answer.setMinimumHeight(70)
        self.answer.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Ignored)
        self.answer.setPlaceholderText('Перевод — можно исправить')
        layout.addWidget(self.answer,2)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        for title, signal in [('Перевести',self.translate_sentence),('Объяснить',self.analyze)]:
            button = QPushButton(title)
            button.clicked.connect(signal.emit)
            if title=='Объяснить':
                self.explain_button = button
            buttons.addWidget(button)
        layout.addLayout(buttons)
        row = QHBoxLayout()
        for title,signal in [('Перевести контекст',self.translate_source),('Сохранить слово',self.save)]:
            button = QPushButton(title)
            button.clicked.connect(signal.emit)
            row.addWidget(button)
        layout.addLayout(row)
        self.action_rows = (buttons,row)
        speech_row=QHBoxLayout()
        for title,signal in [('Произнести слово',self.speak_word),('Произнести реплику',self.speak_context),('Стоп',self.stop_speech)]:
            item=QPushButton(title)
            item.clicked.connect(signal.emit)
            speech_row.addWidget(item)
        layout.addLayout(speech_row)
        self.action_rows+= (speech_row,)
        self.grip=QSizeGrip(self)
        outer.addWidget(self.grip,0,Qt.AlignmentFlag.AlignRight)

    def apply_background(self,alpha,theme='dark'):
        self.background_alpha=max(.15,min(1,alpha))
        self.light=theme=='light'
        field='255,255,255' if self.light else '8,15,26'
        text='#16263a' if self.light else '#edf5ff'
        self.setStyleSheet(f'''Card {{ background:transparent; }}
            QWidget {{ background:transparent; color:{text}; }}
            QScrollArea,QScrollArea > QWidget > QWidget,QLabel,QSizeGrip {{ background:transparent; }}
            QLineEdit,QPlainTextEdit {{ background:rgba({field},42); border:1px solid rgba(140,166,196,160); }}
            QPushButton {{ background:rgba({field},165); border:1px solid rgba(140,166,196,200); }}
            QPushButton:hover {{ background:rgba(30,120,170,220); color:white; }}''')
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(150,185,212,170))
        p.setBrush(QColor(*( (240,246,253) if self.light else (13,23,38) ),round(255*self.background_alpha)))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),10,10)

    def resizeEvent(self,event):
        if hasattr(self,'action_rows'):
            required = self.fontMetrics().horizontalAdvance('Перевести выделенноеОбъяснить значение')+100
            direction = QBoxLayout.Direction.TopToBottom if self.width()<required else QBoxLayout.Direction.LeftToRight
            for row in self.action_rows:row.setDirection(direction)
        super().resizeEvent(event)

    def populate(self,term,sentence,meaning):
        self.term.setText(term)
        self.sentence.setPlainText(sentence)
        self.dictionary.setPlainText(meaning or 'Слово не найдено. Проверь написание.')
        self.answer.clear()
        self.status.setText('')
        self.show()
        native.exclude_capture(self)

    def closeEvent(self,event):
        self.dismissed.emit()
        super().closeEvent(event)


class CardHeader(QLabel):
    def __init__(self,card):
        super().__init__('  Lexora · слово',card)
        self.setToolTip('Потяни, чтобы переместить карточку')
        self.setMinimumHeight(35)
        self.setWordWrap(True)
        self.drag=None

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.drag=event.globalPosition().toPoint()-self.window().pos()

    def mouseMoveEvent(self,event):
        if self.drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint()-self.drag)

    def mouseReleaseEvent(self,event):self.drag=None

