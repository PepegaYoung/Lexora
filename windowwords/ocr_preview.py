"""One OCR pass with bounded thumbnails; no persistent capture or extra window."""
import time
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,QPushButton,QSizePolicy
from . import ocr
from .i18n import tr,trf
from .widgets import qimage


def inspect_frame(image,profile,engine='windows',device='cpu'):
    start=time.perf_counter();lines=ocr.read(image,profile,engine,device)
    thumbnails=[]
    for picture in (image,ocr.prepare(image,profile)):
        thumbnail=picture.copy();thumbnail.thumbnail((400,230),Image.Resampling.BILINEAR)
        thumbnails.append(thumbnail)
    return (*thumbnails,lines,round((time.perf_counter()-start)*1000))


class PreviewImage(QLabel):
    def __init__(self):
        super().__init__();self.original=QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter);self.setFixedHeight(190)
        self.setMinimumWidth(1);self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)

    def display(self,picture):self.original=QPixmap.fromImage(qimage(picture));self.fit()
    def fit(self):
        if not self.original.isNull():self.setPixmap(self.original.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def resizeEvent(self,event):super().resizeEvent(event);self.fit()
    def clear(self):self.original=QPixmap();super().clear()


class OCRPreview(QWidget):
    def __init__(self):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(0,8,0,8)
        images=QHBoxLayout();self.images=[]
        for caption in (tr('Исходный кадр'),tr('После обработки')):
            column=QVBoxLayout();column.addWidget(QLabel(caption))
            image=PreviewImage();column.addWidget(image);images.addLayout(column);self.images.append(image)
        layout.addLayout(images)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.text=QPlainTextEdit();self.text.setReadOnly(True);self.text.setMaximumHeight(110);layout.addWidget(self.text)
        close=QPushButton(tr('Закрыть предпросмотр'));close.clicked.connect(self.clear)
        layout.addWidget(close,0,Qt.AlignmentFlag.AlignLeft)

    def display(self,result):
        original,processed,lines,elapsed=result
        for label,picture in zip(self.images,(original,processed)):label.display(picture)
        self.summary.setText(trf('{0} строк · {1} мс. Проверь, сохранились ли буквы и обводка.',len(lines),elapsed))
        self.text.setPlainText('\n'.join(line.text for line in lines) or tr('Текст не найден. Попробуй другой профиль.'))
        self.show()

    def clear(self):
        self.hide()
        for image in self.images:image.clear()
        self.text.clear();self.summary.clear()
