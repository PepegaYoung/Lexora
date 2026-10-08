import sys
try:
    # Load translation DLLs before Qt/WinRT on Windows.
    import sentencepiece
    import ctranslate2
    from windowwords.app import launch
except Exception:
    if '--self-test' in sys.argv:
        import json,traceback
        from pathlib import Path
        index = sys.argv.index('--self-test')
        Path(sys.argv[index+1]).write_text(json.dumps({'status':'failed','error':traceback.format_exc()},indent=2),encoding='utf-8')
        raise SystemExit(1)
    raise

if __name__ == '__main__':
    if '--self-test' in sys.argv:
        from windowwords.selftest import run
        index = sys.argv.index('--self-test')
        raise SystemExit(run(sys.argv[index+1],sys.argv[index+2] if len(sys.argv)>index+2 else None))
    raise SystemExit(launch())
