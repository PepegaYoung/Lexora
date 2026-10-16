from .i18n import tr,trf
from PySide6.QtCore import Qt,QRectF,QTimer,Signal,QPointF,QRect
from PySide6.QtGui import QImage,QPainter,QColor,QPen,QFont,QPainterPath,QLinearGradient,QGradient,QBrush
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QBoxLayout,QScrollArea,QSizePolicy,QLabel,QPushButton,
                             QPlainTextEdit,QLineEdit,QSizeGrip,QApplication)
from .core import Box,map_selection,selected_text
from . import native

CARD_DEFAULT=(600,700)
CARD_SIZES={'default':CARD_DEFAULT,'small':(480,560),'large':(720,840)}


class CardResizeHandle(QWidget):
    """Resize only this Qt window; input never comes from a global hook."""
    def __init__(self,card,edges):
        super().__init__(card);self.edges=edges;self.origin=None
        horizontal=bool(edges & (Qt.Edge.LeftEdge|Qt.Edge.RightEdge))
        vertical=bool(edges & (Qt.Edge.TopEdge|Qt.Edge.BottomEdge))
        diagonal=edges in (Qt.Edge.LeftEdge|Qt.Edge.TopEdge,Qt.Edge.RightEdge|Qt.Edge.BottomEdge)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if horizontal and vertical and diagonal else
                       Qt.CursorShape.SizeBDiagCursor if horizontal and vertical else
                       Qt.CursorShape.SizeHorCursor if horizontal else Qt.CursorShape.SizeVerCursor)
    def mousePressEvent(self,event):
        if getattr(self.parentWidget(),'size_locked',False):return
        if event.button()==Qt.MouseButton.LeftButton:
            self.origin=(event.globalPosition().toPoint(),QRect(self.parentWidget().geometry()));event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if getattr(self.parentWidget(),'size_locked',False):self.origin=None;return
        if self.origin is None:return
        point,rect=self.origin;delta=event.globalPosition().toPoint()-point;card=self.parentWidget()
        x,y,width,height=rect.x(),rect.y(),rect.width(),rect.height()
        if self.edges & (Qt.Edge.LeftEdge|Qt.Edge.RightEdge):
            left=bool(self.edges & Qt.Edge.LeftEdge)
            width=max(card.minimumWidth(),min(card.maximumWidth(),width+(-delta.x() if left else delta.x())))
            if left:x=rect.right()+1-width
        if self.edges & (Qt.Edge.TopEdge|Qt.Edge.BottomEdge):
            top=bool(self.edges & Qt.Edge.TopEdge)
            height=max(card.minimumHeight(),min(card.maximumHeight(),height+(-delta.y() if top else delta.y())))
            if top:y=rect.bottom()+1-height
        card.setGeometry(x,y,width,height);event.accept()
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.origin is not None:
            self.mouseMoveEvent(event);self.origin=None;card=self.parentWidget()
            card.preferred_size_changed.emit(card.width(),card.height());event.accept()
        else:super().mouseReleaseEvent(event)
    def paintEvent(self,event):
        # A barely visible alpha keeps rounded corners hit-testable on Windows.
        painter=QPainter(self);painter.fillRect(self.rect(),QColor(0,0,0,1))


def qimage(image):
    rgb = image.convert('RGB')
    return QImage(rgb.tobytes(),rgb.width,rgb.height,rgb.width*3,QImage.Format.Format_RGB888).copy()


class Freeze(QWidget):
    selected = Signal(object,object,str,str)
    selection_started=Signal()
    closed = Signal()
    hovered=Signal(str,str)

    def __init__(self, image, monitor, mode='study',content_box=None):
        super().__init__()
        self.image,self.monitor,self.mode = image,monitor,mode
        self.picture = qimage(image)
        self.content_box=content_box
        if content_box:self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.lines = ()
        self.start = self.end = None
        self.hover_word = None
        self.hover_sentence=''
        self.auto_card=True
        self.word_timer=QTimer(self)
        self.word_timer.setSingleShot(True)
        self.word_timer.setInterval(450)
        self.word_timer.timeout.connect(self.preview_word)
        self.notice = tr('Выдели область. Escape — закрыть.')
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
        self.notice = tr('Нажми на слово или выдели выражение. Escape — закрыть.') if lines else tr('Текст не найден. Выдели нужный фрагмент для повторного OCR.')
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
        p.fillRect(self.rect(),QColor(12,20,32,130) if self.content_box else QColor('#0c1420'))
        image_rect=self.image_rect()
        sx,sy = image_rect.width()/self.image.width,image_rect.height()/self.image.height
        p.save()
        if self.content_box:
            b=self.content_box
            p.setClipRect(QRectF(image_rect.x()+b.x*sx,image_rect.y()+b.y*sy,b.w*sx,b.h*sy))
        p.drawImage(image_rect,self.picture);p.restore()
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
        p.drawText(QRectF(self.width()-190,18,170,45),Qt.AlignmentFlag.AlignCenter,tr('Закрыть · Esc'))

    def mousePressEvent(self, event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.word_timer.stop()
            if QRectF(self.width()-190,18,170,45).contains(event.position()):
                self.close()
                return
            self.selection_started.emit()
            self.hover_word=None;self.hover_sentence=''
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
            self.notice = tr('Не удалось выбрать слово. Выдели фрагмент прямоугольником.')
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
    preferred_size_changed=Signal(int,int)
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr('Lexora · слово'))
        self.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.background_alpha=.72
        self.light=False
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(*CARD_DEFAULT)
        self.setMinimumSize(320,320);self.setMaximumSize(1000,1100)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(7,7,7,7)
        outer.setSpacing(3)
        header_row=QHBoxLayout()
        header_row.setContentsMargins(8,4,8,0)
        self.header=CardHeader(self)
        header_row.addWidget(self.header,1)
        self.close_button=QPushButton('×')
        self.close_button.setAccessibleName(tr('Закрыть карточку'))
        self.close_button.setToolTip(tr('Закрыть экранный словарь'))
        self.close_button.setFixedSize(26,26)
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
        layout.setContentsMargins(10,4,10,4)
        layout.setSpacing(4)
        label = QLabel(tr('Слово или фраза'))
        layout.addWidget(label)
        self.term = QLineEdit()
        self.term.setPlaceholderText(tr('Слово или выражение — можно исправить'))
        layout.addWidget(self.term)
        layout.addWidget(QLabel(tr('Контекст')))
        self.sentence = QPlainTextEdit()
        self.sentence.setPlaceholderText(tr('Исходная реплика'))
        self.sentence.setMaximumHeight(70)
        self.sentence.setMinimumHeight(40)
        self.sentence.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Ignored)
        layout.addWidget(self.sentence,1)
        self.dictionary = QPlainTextEdit()
        self.dictionary.setReadOnly(True)
        self.dictionary.setMinimumHeight(65)
        self.dictionary.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Ignored)
        layout.addWidget(self.dictionary,2)
        self.answer = QPlainTextEdit()
        self.answer.setMinimumHeight(55)
        self.answer.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Ignored)
        self.answer.setPlaceholderText(tr('Перевод — можно исправить'))
        layout.addWidget(self.answer,2)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        for title, signal in [(tr('Перевести'),self.translate_sentence),(tr('Объяснить'),self.analyze)]:
            button = QPushButton(title)
            button.clicked.connect(signal.emit)
            if title==tr('Объяснить'):
                self.explain_button = button
            buttons.addWidget(button)
        layout.addLayout(buttons)
        row = QHBoxLayout()
        for title,signal in [(tr('Контекст'),self.translate_source),(tr('Сохранить'),self.save)]:
            button = QPushButton(title)
            button.setToolTip(tr('Перевести всю исходную реплику') if title==tr('Контекст') else tr('Сохранить слово и перевод в «Мои слова»'))
            button.clicked.connect(signal.emit)
            row.addWidget(button)
        layout.addLayout(row)
        self.action_rows = (buttons,row)
        speech_row=QHBoxLayout()
        for title,signal in [(tr('▶ Слово'),self.speak_word),(tr('▶ Фраза'),self.speak_context),('■',self.stop_speech)]:
            item=QPushButton(title)
            item.setToolTip(tr('Остановить произношение') if title=='■' else tr('Произнести ')+(tr('слово') if title==tr('▶ Слово') else tr('исходную реплику')))
            if title=='■':item.setFixedWidth(30)
            item.clicked.connect(signal.emit)
            speech_row.addWidget(item)
        layout.addLayout(speech_row)
        self.action_rows+= (speech_row,)
        self.resize_handles=[CardResizeHandle(self,edges) for edges in (
            Qt.Edge.LeftEdge,Qt.Edge.RightEdge,Qt.Edge.TopEdge,Qt.Edge.BottomEdge,
            Qt.Edge.LeftEdge|Qt.Edge.TopEdge,Qt.Edge.RightEdge|Qt.Edge.TopEdge,
            Qt.Edge.LeftEdge|Qt.Edge.BottomEdge,Qt.Edge.RightEdge|Qt.Edge.BottomEdge)]
        self.position_resize_handles()
        self.apply_background(self.background_alpha)

    def apply_background(self,alpha,theme='aurora'):
        from .themes import card_palette,stylesheet,SCROLLBAR_STYLE
        colors=card_palette(theme)
        self.theme_key=theme
        self.background_alpha=max(.15,min(1,alpha))
        self.light=colors['light']
        self.card_surface=QColor(colors['bg']);self.card_border=QColor(colors['line'])
        self.card_border.setAlpha(170)
        self.surface_brush=QBrush(self.card_surface)
        stops=colors.get('gradient')
        if stops:
            gradient=QLinearGradient(0,0,1,1)
            gradient.setCoordinateMode(QGradient.CoordinateMode.ObjectBoundingMode)
            for index,color in enumerate(stops):
                tone=QColor(color);tone.setAlpha(round(255*self.background_alpha))
                gradient.setColorAt(index/(len(stops)-1),tone)
            self.surface_brush=QBrush(gradient)
        else:
            fill=QColor(self.card_surface);fill.setAlpha(round(255*self.background_alpha));self.surface_brush=QBrush(fill)
        tone=QColor(colors['field']);field=f'{tone.red()},{tone.green()},{tone.blue()}'
        text=colors['text'];border=colors['line'];hover=colors['primary']
        self.setStyleSheet(f'''Card {{ background:transparent; }}
            QWidget {{ background:transparent; color:{text}; }}
            QScrollArea,QScrollArea > QWidget > QWidget,QLabel,QSizeGrip {{ background:transparent; }}
            QLineEdit,QPlainTextEdit {{ background:rgba({field},42); border:1px solid {border}; padding:4px; }}
            QPushButton {{ background:rgba({field},165); border:1px solid {border}; padding:4px 7px; border-radius:5px; }}
            QPushButton:hover {{ background:{hover}; color:white; }}'''+stylesheet(SCROLLBAR_STYLE,theme))
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(self.card_border)
        p.setBrush(self.surface_brush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),10,10)

    def resizeEvent(self,event):
        if hasattr(self,'action_rows'):
            available=max(1,self.content_area.viewport().width()-24)
            for row in self.action_rows:
                widgets=[row.itemAt(i).widget() for i in range(row.count()) if row.itemAt(i).widget() is not None]
                required=sum(widget.sizeHint().width() for widget in widgets)+max(0,len(widgets)-1)*row.spacing()
                row.setDirection(QBoxLayout.Direction.TopToBottom if available<required else QBoxLayout.Direction.LeftToRight)
        super().resizeEvent(event)
        if hasattr(self,'resize_handles'):self.position_resize_handles()

    def position_resize_handles(self):
        size=7;width,height=self.width(),self.height()
        boxes=((0,size,size,height-2*size),(width-size,size,size,height-2*size),
               (size,0,width-2*size,size),(size,height-size,width-2*size,size),
               (0,0,size,size),(width-size,0,size,size),(0,height-size,size,size),(width-size,height-size,size,size))
        for handle,box in zip(self.resize_handles,boxes):handle.setGeometry(*box);handle.raise_()

    def set_size_locked(self,locked):
        self.size_locked=bool(locked)
        if locked:self.setFixedSize(self.size())
        else:self.setMinimumSize(320,320);self.setMaximumSize(1000,1100)
        for handle in self.resize_handles:
            handle.origin=None;handle.setVisible(not locked)

    def populate(self,term,sentence,meaning):
        self.term.setText(term)
        self.sentence.setPlainText(sentence)
        self.dictionary.setPlainText(meaning or tr('Слово не найдено. Проверь написание.'))
        self.answer.clear()
        self.status.setText('')
        self.show()
        native.exclude_capture(self)

    def closeEvent(self,event):
        self.dismissed.emit()
        super().closeEvent(event)


class CardHeader(QLabel):
    def __init__(self,card):
        super().__init__(tr('  Lexora · слово'),card)
        self.setToolTip(tr('Потяни, чтобы переместить карточку'))
        self.setMinimumHeight(24)
        self.setWordWrap(True)
        self.drag=None

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.drag=event.globalPosition().toPoint()-self.window().pos()

    def mouseMoveEvent(self,event):
        if self.drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint()-self.drag)

    def mouseReleaseEvent(self,event):self.drag=None

