from .i18n import tr,trf
# Load native translation runtimes before WinRT; they share C++ runtime libraries.
import sentencepiece
import ctranslate2
import asyncio
import numpy as np
from PIL import Image,ImageOps,ImageEnhance,ImageFilter
from winrt.windows.globalization import Language
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.graphics.imaging import SoftwareBitmap,BitmapPixelFormat,BitmapAlphaMode
from winrt.windows.storage.streams import Buffer
from .core import Box, Word, Line

PROFILES = (
    ('raw','Универсальный','Исходные цвета. Подходит для большинства субтитров; обычно самый надёжный первый выбор.'),
    ('white','Белые субтитры','Оставляет светлые нейтральные буквы. Цветные элементы интерфейса отбрасываются.'),
    ('yellow','Жёлтые субтитры','Оставляет жёлтые буквы и убирает чёрную обводку.'),
    ('witcher','Жёлтый текст с обводкой','Более строгий отбор ярких жёлтых букв; меньше коричневого фона.'),
    ('auto','Белый + жёлтый','Для области, где одновременно есть субтитры и варианты ответа разных цветов.'),
    ('contrast','Бледный текст · усилить контраст','Чёрно-белое изображение с усилением контраста и резкости.'),
    ('dark','Тёмные буквы на светлом фоне','Инвертирует яркость. Для чёрного текста на светлых панелях.'),
    ('small','Мелкий текст · увеличить','Увеличивает кадр до 2.8× и усиливает резкость. Может работать медленнее.'),
    ('threshold','Пороговый · убрать полутона','Чёрно-белый порог для чётких букв. На сложном фоне может потерять детали.'),
)

ENGINES=(('windows','Windows OCR'),('game','Lexora Game OCR · экспериментальный'))


def prepare(image, mode):
    if mode=='raw':
        return image.convert('RGB')
    if mode=='small':
        return image.convert('RGB').filter(ImageFilter.UnsharpMask(radius=1,percent=160,threshold=3))
    if mode in ('contrast','dark','threshold'):
        gray = ImageOps.autocontrast(ImageOps.grayscale(image))
        if mode=='dark':
            return ImageOps.invert(gray).convert('RGB')
        if mode=='threshold':
            return gray.point(lambda p:0 if p>160 else 255).convert('RGB')
        return ImageEnhance.Contrast(gray).enhance(1.7).filter(ImageFilter.SHARPEN).convert('RGB')
    if mode not in {'white','yellow','witcher','auto'}:
        raise ValueError('Unknown OCR profile')
    pixels = np.asarray(image.convert('RGB')).astype(np.int16)
    r,g,b = (pixels[:,:,i] for i in range(3))
    white = (np.minimum(np.minimum(r,g),b)>160)&(np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b)<70)
    yellow = (r>105)&(g>85)&(b<g*.86)&(r>g*.75)&(r<g*1.7)
    witcher = yellow & (r-b>75)&(g-b>55)&(r>145)&(g>120)
    mask = white if mode=='white' else yellow if mode=='yellow' else witcher if mode=='witcher' else white|yellow
    return Image.fromarray(np.where(mask,0,255).astype(np.uint8)).convert('RGB')


async def recognize(image, mode='raw'):
    engine = OcrEngine.try_create_from_language(Language('en-US'))
    if engine is None:
        raise RuntimeError(tr('Windows OCR для английского не установлен. Добавь английский язык и его OCR-компонент в параметрах Windows.'))
    processed = prepare(image,mode)
    scale = min(2.8 if mode=='small' else 1.6, OcrEngine.max_image_dimension/max(processed.size))
    width,height = max(1,round(processed.width*scale)),max(1,round(processed.height*scale))
    rgba = processed.resize((width,height),Image.Resampling.BILINEAR).convert('RGBA')
    data = rgba.tobytes('raw','BGRA')
    buffer = Buffer(len(data))
    buffer.length = len(data)
    memoryview(buffer)[:] = data
    bitmap = SoftwareBitmap.create_copy_with_alpha_from_buffer(buffer,BitmapPixelFormat.BGRA8,width,height,BitmapAlphaMode.IGNORE)
    sx,sy = width/image.width,height/image.height
    try:
        result = await engine.recognize_async(bitmap)
        lines = []
        for detected in result.lines:
            words = tuple(Word(w.text,Box(w.bounding_rect.x/sx,w.bounding_rect.y/sy,
                                         w.bounding_rect.width/sx,w.bounding_rect.height/sy)) for w in detected.words)
            if not words:
                continue
            x,y = min(w.box.x for w in words),min(w.box.y for w in words)
            right,bottom = max(w.box.x+w.box.w for w in words),max(w.box.y+w.box.h for w in words)
            lines.append(Line(detected.text,Box(x,y,right-x,bottom-y),words))
        return tuple(lines)
    finally:
        bitmap.close()


def read(image, mode='raw', engine='windows',device='cpu'):
    from .screen import without_metrics
    if engine=='game':
        from .game_ocr import read as game_read
        return without_metrics(game_read(prepare(image,mode),device))
    if engine!='windows':raise ValueError('Unknown OCR engine')
    return without_metrics(asyncio.run(recognize(image,mode)))
