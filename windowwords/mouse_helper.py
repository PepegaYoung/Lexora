"""Run the low-level mouse hook outside Python's process and interpreter lock."""
import os
from pathlib import Path
import subprocess
import threading

from .storage import base_dir


class MouseHelper:
    def __init__(self, bindings, thread_id, post, failure, singles, card):
        self.bindings=bindings
        self.parent_thread=thread_id
        self.post=post
        self.failure=failure
        self.singles=bool(singles)
        self.card=bool(card)
        self.thread_id=None
        self.process=None
        self.stopping=False
        self.lock=threading.Lock()

    def start(self):
        executable=base_dir()/'assets'/'MouseHook.exe'
        args=[str(executable),str(os.getpid()),str(self.parent_thread),str(int(self.singles)),str(int(self.card))]
        args += [f'{mods}:{key}:{ident}' for mods,key,ident in self.bindings]
        try:
            self.process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,text=True,encoding='ascii',creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError:
            self.failure('Не удалось запустить обработчик кнопок мыши. Проверь целостность portable-сборки.')
            return
        threading.Thread(target=self._watch,daemon=True).start()

    def _watch(self):
        line=self.process.stdout.readline().strip()
        with self.lock:
            if line.startswith('READY ') and line[6:].isdigit():
                self.thread_id=int(line[6:])
                self.post(self.thread_id,0x8002,int(self.singles),0)
                self.post(self.thread_id,0x8003,int(self.card),0)
                if self.stopping:self.post(self.thread_id,0x12,0,0)
            elif not self.stopping:
                self.failure('Не удалось включить обработчик кнопок мыши.')
        self.process.wait()
        if not self.stopping and self.thread_id:
            self.failure('Обработчик кнопок мыши остановился. Перезапусти Lexora.')

    def set_state(self,singles=None,card=None):
        with self.lock:
            if singles is not None:self.singles=bool(singles)
            if card is not None:self.card=bool(card)
            if self.thread_id:
                if singles is not None:self.post(self.thread_id,0x8002,int(self.singles),0)
                if card is not None:self.post(self.thread_id,0x8003,int(self.card),0)

    def stop(self):
        with self.lock:
            self.stopping=True
            if self.thread_id:self.post(self.thread_id,0x12,0,0)
        if self.process:
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
