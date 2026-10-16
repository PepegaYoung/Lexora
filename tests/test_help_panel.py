import sentencepiece,ctranslate2
import re,unittest,io
from contextlib import redirect_stderr
from shiboken6 import delete
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QScrollArea,QLabel,QComboBox
from windowwords.design import HelpPanel,ContextHelp,Navigation,PAGE_HELP,PROVIDER_HELP,STYLE

class HelpPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.window=QWidget()
        self.window.resize(900,650)
        layout=QVBoxLayout(self.window)
        self.window.tabs=Navigation()
        for name in PAGE_HELP:self.window.tabs.addTab(QWidget(),name)
        layout.addWidget(self.window.tabs,1)
        self.panel=HelpPanel()
        layout.addWidget(self.panel)
        self.help=ContextHelp(self.window,self.panel)
        self.window.provider=QComboBox()
        for name in PROVIDER_HELP:self.window.provider.addItem(name,name)
        self.window.show()
    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.app.setStyleSheet(STYLE)
    def assert_fully_visible(self):
        self.app.processEvents()
        label=self.panel.text
        self.assertGreaterEqual(label.contentsRect().height(),label.heightForWidth(label.width()))
        self.assertLessEqual(self.window.tabs.geometry().bottom(),self.panel.geometry().top())
        self.assertFalse(self.panel.findChildren(QScrollArea))
    def test_all_page_and_service_hints_fit_without_scroll_at_every_scale(self):
        for scale in (75,100,175):
            self.app.setStyleSheet(re.sub(r'font-size:(\d+)px',lambda m:f'font-size:{round(int(m[1])*scale/100)}px',STYLE))
            for text in (*PAGE_HELP.values(),*PROVIDER_HELP.values()):
                with self.subTest(scale=scale,text=text):
                    self.help.show(text,force=True)
                    self.assert_fully_visible()
                    self.assertLessEqual(self.panel.height(),130)
    def test_resize_shows_entire_hint_and_returns_space_for_short_hint(self):
        text=max(PROVIDER_HELP.values(),key=len)
        self.help.show(text)
        self.window.resize(450,650)
        self.assert_fully_visible()
        self.window.resize(900,650)
        self.assert_fully_visible()
        before=self.panel.height()
        self.help.show('Короткая подсказка.')
        self.assert_fully_visible()
        self.assertLessEqual(self.panel.height(),before)
    def test_section_help_is_one_short_hint_instead_of_all_hidden_notes(self):
        label=QLabel('Старое длинное пояснение. '*100,self.window.tabs.widget(0))
        label.setProperty('contextNote',True)
        self.help.page()
        self.assertEqual(self.panel.text.text(),PAGE_HELP['Игровой экран'])
        self.window.tabs.setCurrentIndex(list(PAGE_HELP).index('Перевод'))
        self.window.provider.setCurrentIndex(self.window.provider.findData('yandex_web'))
        self.help.page(source=self.window.provider)
        self.assertEqual(self.panel.text.text(),PROVIDER_HELP['yandex_web'])
        self.assert_fully_visible()
    def test_pending_resize_is_canceled_when_panel_is_destroyed(self):
        panel=HelpPanel()
        panel.fit_timer.start(0)
        errors=io.StringIO()
        with redirect_stderr(errors):
            delete(panel)
            self.app.processEvents()
        self.assertEqual(errors.getvalue(),'')
