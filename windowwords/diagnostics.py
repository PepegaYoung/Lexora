from .i18n import tr,trf
import threading,time

class Measurements:
    def __init__(self):
        self.lock=threading.Lock()
        self.rows={}
    def run(self,stage,function):
        start=time.perf_counter()
        error=''
        try:return function()
        except Exception as failure:
            message=str(failure).casefold()
            error='canceled' if any(s in message for s in ('больше не актуален','no longer relevant')) else ('limit' if any(s in message for s in ('лимит','квот','429','quota','limit')) else 'operation')
            raise
        finally:
            elapsed=round((time.perf_counter()-start)*1000)
            with self.lock:
                row=self.rows.setdefault(stage,{'count':0,'errors':0,'last_ms':0,'total_ms':0,'error_kind':''})
                row['count']+=1;row['errors']+=bool(error and error!='canceled')
                row['last_ms']=elapsed;row['total_ms']+=elapsed;row['error_kind']='' if error=='canceled' else error
    def snapshot(self):
        with self.lock:return {stage:dict(value) for stage,value in self.rows.items()}

def diagnosis(rows):
    translate=rows.get('translate',{})
    ocr=rows.get('ocr',{})
    if translate.get('error_kind')=='limit':return tr('Сервис достиг лимита. Дождись восстановления квоты или выбери другой переводчик.')
    if translate.get('error_kind'):return tr('Ошибка перевода. Проверь выбранный сервис, подключение и модель.')
    if ocr.get('error_kind'):return tr('Ошибка распознавания. Проверь область и английский компонент Windows OCR.')
    if translate.get('last_ms',0)>1500:return tr('Больше времени занимает перевод: сетевой ответ или вычисление офлайн-модели.')
    if ocr.get('last_ms',0)>500:return tr('Больше времени занимает OCR. Попробуй узкую область субтитров вместо всего экрана.')
    return tr('Задержек в последних измерениях не обнаружено.') if rows else tr('Запусти распознавание или перевод, чтобы увидеть время работы.')
