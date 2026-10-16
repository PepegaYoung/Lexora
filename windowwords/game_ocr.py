"""Optional local game OCR. Training libraries are never imported here."""
from pathlib import Path
import threading
import re
import numpy as np
from .core import Box,Line,Word
from .storage import base_dir
from .i18n import tr

_lock=threading.RLock()
_engine=None
_engine_key=None
_generation=0
_state={}


def status():
    return dict(_state)


def reset():
    """Release an idle session; invalidate a busy one without blocking the UI."""
    global _generation,_engine,_engine_key,_state
    _generation+=1;_state={}
    if _lock.acquire(blocking=False):
        try:_engine=None;_engine_key=None
        finally:_lock.release()


def apply_settings(engine,device,retry=False):
    """Keep a matching preview session warm; release an unwanted GPU session."""
    if engine!='game' or _state.get('requested')!=device or (retry and _state.get('fallback')):reset()


def bounds(points,width,height):
    points=np.asarray(points,dtype=float)
    if points.shape!=(4,2) or not np.isfinite(points).all():return None
    x=max(0,float(points[:,0].min()));y=max(0,float(points[:,1].min()))
    right=min(width,float(points[:,0].max()));bottom=min(height,float(points[:,1].max()))
    return Box(x,y,right-x,bottom-y) if right>x and bottom>y else None


def convert(results,width,height):
    lines=[]
    for row in results or ():
        if len(row)<6:continue
        polygon,text,confidence,word_boxes,words,scores=row[:6]
        if not isinstance(text,str) or not text.strip() or confidence<.5:continue
        box=bounds(polygon,width,height)
        if box is None:continue
        pieces=[];invalid_alignment=False
        for points,word,score in zip(word_boxes,words,scores):
            word_box=bounds(points,width,height)
            if word_box:
                # CTC padding for the final punctuation can extend far beyond
                # the detector polygon. A word cannot occupy another UI field.
                from .screen import intersection
                word_box=intersection(word_box,box)
                if word_box.w<=0 or word_box.h<=0:word_box=None
            if word_box is None and isinstance(word,str) and word.strip():invalid_alignment=True
            if word_box and isinstance(word,str) and word.strip():pieces.append(Word(word,word_box))
        # Do not invent word positions: single-line selection still works if
        # the recognition backend cannot provide CTC word alignment.
        if not pieces or invalid_alignment:pieces=[Word(text,box)]
        else:pieces=aligned_words(text,pieces)
        lines.append(Line(text,box,tuple(pieces)))
    return tuple(sorted(lines,key=lambda line:(line.box.y,line.box.x)))


def aligned_words(text,pieces):
    """RapidOCR can return character fragments; restore whitespace-delimited words.

    Reuse CTC geometry, never divide a line into equal-width invented boxes.
    If the backend fragments disagree with the decoded text, retain its boxes.
    """
    tokens=re.findall(r'\S+',text)
    characters=[(char,piece.box) for piece in pieces for char in piece.text if not char.isspace()]
    if ''.join(char for char,_ in characters)!=''.join(tokens):return pieces
    from .screen import union
    words=[];position=0
    for token in tokens:
        boxes=[box for _,box in characters[position:position+len(token)]]
        words.append(Word(token,union(boxes)));position+=len(token)
    return words


def create_engine(device='cpu'):
    from onnxruntime import disable_telemetry_events
    disable_telemetry_events()
    from ._vendor.rapidocr import RapidOCR
    folder=base_dir()/'assets/ocr'
    if not (folder/'game-en-v1.onnx').is_file():
        raise RuntimeError(tr('Модель Lexora Game OCR не найдена. Переустанови полную сборку приложения.'))
    return RapidOCR(rec_model_path=str(folder/'game-en-v1.onnx'),rec_keys_path=str(folder/'characters.txt'),
        det_model_path=str(folder/'detection-v4.onnx'),cls_model_path=str(folder/'orientation-v2.onnx'),
        det_use_dml=device=='gpu',rec_use_dml=device=='gpu',
        intra_op_num_threads=2,inter_op_num_threads=1,det_limit_type='max',det_limit_side_len=1600,
        use_cls=False,max_side_len=2560,rec_batch_num=6,text_score=.5)


def uses_gpu(engine):
    return all(session.get_providers()[0]=='DmlExecutionProvider'
        for session in (engine.text_det.infer.session,engine.text_rec.session.session))


def prepare_engine(device):
    """Publish actual provider use, including explicit CPU fallback."""
    global _state
    _state={'requested':device,'loading':True}
    fallback=''
    if device=='gpu':
        from onnxruntime import get_available_providers
        if 'DmlExecutionProvider' not in get_available_providers():fallback='unavailable'
        else:
            try:
                engine=create_engine('gpu')
                if uses_gpu(engine):
                    _state={'requested':'gpu','active':'gpu','backend':'directml','fallback':'','loading':False}
                    return engine
                fallback='initialization'
                del engine
            except Exception:fallback='initialization'
    engine=create_engine('cpu')
    _state={'requested':device,'active':'cpu','backend':'cpu','fallback':fallback,'loading':False}
    return engine


def recognize(engine,image):
    # PIL is RGB; ndarray input to RapidOCR is OpenCV BGR.
    pixels=np.ascontiguousarray(np.asarray(image.convert('RGB'))[:,:,::-1])
    result,_=engine(pixels,use_cls=False,return_word_box=True)
    # A close crop of one line can lose text in the detector's border
    # expansion. Read the complete crop, retaining real CTC alignment.
    if image.height<=64 and image.width>=image.height*2 and len(result or ())<=1:
        recognized,_=engine.text_rec([pixels],return_word_box=True)
        polygon=np.array([[0,0],[image.width,0],[image.width,image.height],[0,image.height]],dtype=np.float32)
        aligned=engine.cal_rec_boxes([pixels],[polygon],recognized)
        if aligned and aligned[0][1]>=.5:result=[[polygon.tolist(),*aligned[0]]]
    return convert(result,image.width,image.height)


def read(image,device='cpu'):
    global _engine,_engine_key,_state
    if device not in ('cpu','gpu'):raise ValueError('Unknown OCR device')
    with _lock:
        key=(device,_generation)
        try:
            if _engine is None or _engine_key!=key:
                _engine=None;_engine_key=None
                _engine=prepare_engine(device);_engine_key=key
            engine=_engine
            try:return recognize(engine,image)
            except Exception:
                if _state.get('active')!='gpu':raise
                engine=None;_engine=None
                _engine=create_engine('cpu');_engine_key=key
                _state={'requested':device,'active':'cpu','backend':'cpu','fallback':'inference','loading':False}
                return recognize(_engine,image)
        except Exception:
            _state={'requested':device,'error':'initialization','loading':False}
            raise
        finally:
            if key[1]!=_generation:_engine=None;_engine_key=None;_state={}
