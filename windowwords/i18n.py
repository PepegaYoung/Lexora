"""Interface language only; game text and dictionary content stay untouched."""
from .i18n_en import TRANSLATIONS

_language='ru'


def set_language(language):
    global _language
    _language=language if language in ('ru','en') else 'ru'


def language():return _language


def tr(text):return TRANSLATIONS.get(text,text) if _language=='en' else text


def trf(template,*values):return tr(template).format(*values)


def original(text):
    if _language=='en':
        return next((source for source,target in TRANSLATIONS.items() if target==text),text)
    return text
