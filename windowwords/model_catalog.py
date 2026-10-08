"""Account-specific model choices, refreshed without running a translation."""
import re
import time
from PySide6.QtCore import QTimer,Signal
from PySide6.QtWidgets import QComboBox
from .auth import ServiceError,PLAN_SCOPE

def parse_catalog(payload,provider):
    if not isinstance(payload,dict):raise ServiceError('Сервис вернул неверный список моделей.')
    rows=payload.get('models' if provider=='subscription' else 'data')
    if not isinstance(rows,list):raise ServiceError('Сервис вернул неверный список моделей.')
    models=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):continue
        if provider=='subscription':
            if row.get('visibility')!='list':continue
            ident=row.get('slug');label=row.get('display_name') or ident
        else:
            ident=row.get('id');label=ident
            if not isinstance(ident,str) or not re.match(r'^(?:gpt-|chatgpt-|chat-|o\d(?:-|$))',ident):continue
            if any(part in ident.lower() for part in ('image','audio','realtime','transcribe','tts','embedding','moderation')):continue
        if not isinstance(ident,str) or not ident.strip() or ident in seen:continue
        if not isinstance(label,str):label=ident
        seen.add(ident);models.append((ident,label))
    if not models:raise ServiceError('Нет доступных текстовых моделей. Проверь разрешение подключения и доступ аккаунта.')
    return models

class ModelPicker(QComboBox):
    opening=Signal()
    def showPopup(self):
        self.opening.emit()
        super().showPopup()

class ModelCatalog:
    def init_model_catalog(self):
        self.model_catalogs={}
        self.model_requests={}
        self.model_revision={'subscription':0,'api':0}
        self.model_pick.opening.connect(lambda:self.get_models(force=False))
        self.model_pick.activated.connect(self.model_selected)
        self.tabs.list.currentRowChanged.connect(lambda _:self.refresh_models_if_visible())
        self.model_timer=QTimer(self)
        self.model_timer.setInterval(60_000)
        self.model_timer.timeout.connect(self.refresh_models_if_visible)
        self.model_timer.start()
        QTimer.singleShot(0,lambda:self.get_models(force=False))

    def model_connection_ready(self,provider):
        records=self.store.vault.read()
        if provider=='api':return bool(records.get('api_key'))
        profile=records.get('chatgpt',{})
        return bool(profile.get('access_token')) and PLAN_SCOPE in profile.get('scopes',[])

    def invalidate_models(self,provider):
        self.model_revision[provider]+=1
        self.model_catalogs.pop(provider,None)
        self.model_requests.pop(provider,None)
        if provider==self.provider.currentData():self.display_models(provider)

    def display_models(self,provider):
        self.model_pick.clear()
        cached=self.model_catalogs.get(provider)
        if cached:
            rows,updated=cached
            for ident,label in rows:self.model_pick.addItem(label,ident)
            previous=self.settings['models'].get(provider,'')
            index=self.model_pick.findData(previous)
            if index>=0:self.model_pick.setCurrentIndex(index)
            elif previous:
                self.model_pick.setCurrentIndex(-1)
                self.model_status.setText('Прежняя модель недоступна. Выбери модель из списка.')
            else:self.model_pick.setCurrentIndex(0)
            self.model_pick.setEnabled(True)
        else:
            self.model_pick.setPlaceholderText('Выбери модель после подключения')
            self.model_pick.setCurrentIndex(-1)
            self.model_pick.setEnabled(False)
            self.model_status.setText('Список загрузится автоматически после подключения.')

    def model_selected(self,*args):
        ident=self.model_pick.currentData()
        if ident:self.model_status.setText(ident+' · нажми «Использовать»')

    def refresh_models_if_visible(self):
        if not self.closing and self.isVisible() and not self.isMinimized() and self.tabs.list.currentItem().text()=='Перевод':
            self.get_models(force=False)

    def get_models(self,force=True):
        provider=self.provider.currentData()
        if self.closing or provider not in ('subscription','api'):return
        try:ready=self.model_connection_ready(provider)
        except Exception:
            self.model_status.setText('Не удалось прочитать подключение. Подключись заново.');return
        if not ready:
            self.model_status.setText('Подключи ChatGPT.' if provider=='subscription' else 'Сохрани API-ключ, чтобы загрузить модели.')
            return
        if provider in self.model_requests:return
        cached=self.model_catalogs.get(provider)
        if not force and cached and time.monotonic()-cached[1]<300:return
        revision=self.model_revision[provider]
        request=object()
        self.model_requests[provider]=request
        self.model_status.setText('Обновляю список моделей…')
        self.model_refresh_button.setEnabled(False)
        def current():return not self.closing and revision==self.model_revision[provider] and self.model_requests.get(provider) is request
        def done(rows):
            if not current():return
            self.model_requests.pop(provider,None)
            self.model_catalogs[provider]=(rows,time.monotonic())
            if provider!=self.provider.currentData():return
            selected=self.model_pick.currentData() or self.settings['models'].get(provider,'')
            self.display_models(provider)
            index=self.model_pick.findData(selected)
            if index>=0:self.model_pick.setCurrentIndex(index)
            elif selected:self.model_pick.setCurrentIndex(-1)
            self.model_status.setText(f'Список обновлён · моделей: {len(rows)}' if not selected or index>=0 else 'Прежняя модель недоступна. Выбери модель из списка.')
            self.model_refresh_button.setEnabled(True)
        def failed(error):
            if not current():return
            self.model_requests.pop(provider,None)
            if provider!=self.provider.currentData():return
            self.model_refresh_button.setEnabled(True)
            self.model_status.setText(('Показан предыдущий список. ' if cached else '')+error)
        self.task(lambda:self.translator.models(provider),done,failed)
