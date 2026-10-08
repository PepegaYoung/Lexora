"""English Windows desktop TTS. Selected text is stdin data, never script code."""
import base64,json,os,subprocess,threading
from pathlib import Path
from .auth import ServiceError

SCRIPT=r'''
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
try {
  Add-Type -AssemblyName System.Speech
  $voiceSynth=New-Object System.Speech.Synthesis.SpeechSynthesizer
  $payload=[Console]::In.ReadToEnd() | ConvertFrom-Json
  $englishVoice=$voiceSynth.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'en-*' } | Select-Object -First 1
  if (!$englishVoice) { [Console]::Out.Write('NO_ENGLISH_VOICE'); exit 2 }
  $voiceSynth.SelectVoice($englishVoice.VoiceInfo.Name)
  if ($payload.mode -eq 'probe') { [Console]::Out.Write($englishVoice.VoiceInfo.Name); exit 0 }
  if ($payload.mode -eq 'verify') { $voiceSynth.SetOutputToNull() }
  $voiceSynth.Speak([string]$payload.text)
  $voiceSynth.Dispose()
  [Console]::Out.Write('OK')
} catch { [Console]::Out.Write('TTS_FAILED'); exit 3 }
'''

class Speaker:
    def __init__(self):
        self.lock=threading.Lock()
        self.process=None
        self.revision=0
        self.closed=False
    def stop(self,closing=False):
        with self.lock:
            self.revision+=1
            if closing:self.closed=True
            process,self.process=self.process,None
            if process and process.poll() is None:process.terminate()
    def speak(self,text,mode='speak'):
        text=text.strip()
        if not text and mode!='probe':return ''
        if len(text)>4000:raise ServiceError('Для произношения выбери фрагмент до 4000 символов.')
        executable=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        with self.lock:
            if self.closed:return ''
            self.revision+=1
            revision=self.revision
            if self.process and self.process.poll() is None:self.process.terminate()
            process=subprocess.Popen([str(executable),'-NoProfile','-NonInteractive','-EncodedCommand',
                base64.b64encode(SCRIPT.encode('utf-16le')).decode('ascii')],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
            self.process=process
        try:
            output,_=process.communicate(json.dumps({'text':text,'mode':mode}).encode('ascii'),timeout=120)
            output=output.decode('utf-8',errors='replace')
        except subprocess.TimeoutExpired:
            process.kill();process.communicate()
            raise ServiceError('Произношение не завершилось. Повтори короткий фрагмент.') from None
        finally:
            with self.lock:
                if self.process is process:self.process=None
        with self.lock:
            if revision!=self.revision or self.closed:return ''
        if process.returncode or output=='NO_ENGLISH_VOICE':
            if output=='NO_ENGLISH_VOICE':raise ServiceError('Английский голос Windows не найден. Добавь английский голос в настройках речи Windows.')
            raise ServiceError('Windows не смог произнести текст. Проверь английский голос и устройство вывода звука.')
        return output
