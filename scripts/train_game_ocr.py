"""Fine-tune a PP-OCRv4 English CTC recognizer; training deps stay outside Lexora.

Dataset JSON: [{"image":"crops/line.png", "text":"Verified text", "screen":"source-id"}].
Train and validation must contain disjoint source screenshots, not just crops.
Requires a pinned PaddleOCR checkout, PaddlePaddle GPU, OpenCV and rapidfuzz.
"""
import argparse,copy,hashlib,json,math,random,re,sys,time
from pathlib import Path
import numpy as np
import cv2
import paddle
from paddle import nn
from rapidfuzz.distance import Levenshtein


def arguments():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--paddleocr',type=Path,required=True)
    parser.add_argument('--pretrained',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--epochs',type=int,default=4)
    parser.add_argument('--batch',type=int,default=8)
    parser.add_argument('--device',default='gpu')
    parser.add_argument('--export-only',action='store_true')
    parser.add_argument('--resume',action='store_true',help='Load a previous Lexora recognizer checkpoint')
    parser.add_argument('--learning-rate',type=float,default=1e-5)
    parser.add_argument('--seed',type=int,default=632)
    parser.add_argument('--selection-normalized',action='store_true',help='Select by case/whitespace-normalized CER')
    parser.add_argument('--no-export',action='store_true',help='Export later in the separate CPU environment')
    parser.add_argument('--freeze-backbone',action='store_true',help='Preserve generic glyph features')
    parser.add_argument('--anchor-weight',type=float,default=0,help='Anchor predictions to the starting recognizer')
    parser.add_argument('--blend-checkpoint',type=Path,help='Blend an adapted checkpoint into --pretrained during export')
    parser.add_argument('--blend-fraction',type=float,default=.25,help='Adapted weight fraction, selected on validation before export')
    args=parser.parse_args()
    if args.blend_checkpoint and (not args.export_only or not 0<=args.blend_fraction<=1):
        parser.error('--blend-checkpoint requires --export-only and a fraction between zero and one')
    return args


def make_model(upstream):
    sys.path.insert(0,str(upstream))
    from ppocr.modeling.backbones.rec_lcnetv3 import PPLCNetV3
    from ppocr.modeling.necks.rnn import SequenceEncoder
    from ppocr.modeling.heads.rec_ctc_head import CTCHead
    characters=['']+(upstream/'ppocr/utils/en_dict.txt').read_text(encoding='utf-8').splitlines()+[' ']
    class Recognizer(nn.Layer):
        def __init__(self):
            super().__init__()
            self.backbone=PPLCNetV3(scale=.95)
            self.encoder=SequenceEncoder(in_channels=self.backbone.out_channels,encoder_type='svtr',
                dims=120,depth=2,hidden_dims=120,kernel_size=[1,3],use_guide=True)
            self.head=CTCHead(in_channels=120,out_channels=len(characters),fc_decay=1e-5)
        def forward(self,image):
            logits=self.head.fc(self.encoder(self.backbone(image)))
            return logits if self.training else paddle.nn.functional.softmax(logits,axis=-1)
    return Recognizer(),characters


def load_pretrained(model,file):
    original=paddle.load(str(file));state={}
    for key,value in original.items():
        if key.startswith('backbone.'):state[key]=value
        elif key.startswith('head.ctc_encoder.'):state[key.replace('head.ctc_encoder.','encoder.',1)]=value
        elif key.startswith('head.ctc_head.'):state[key.replace('head.ctc_head.','head.',1)]=value
    own=model.state_dict()
    assert set(own)==set(state),{'missing':list(set(own)-set(state))}
    assert all(own[k].shape==state[k].shape for k in own)
    model.set_state_dict(state)


def image_tensor(path,width=None):
    image=cv2.imread(str(path));assert image is not None,str(path)
    h,w=image.shape[:2]
    width=width or max(320,min(1600,math.ceil((48*w/h)/320)*320))
    resized=min(width,max(1,math.ceil(48*w/h)))
    image=cv2.resize(image,(resized,48)).astype('float32')/127.5-1
    result=np.zeros((3,48,width),dtype='float32');result[:,:,:resized]=image.transpose(2,0,1)
    return result


def decode(prediction,characters):
    output=[]
    for row in prediction.argmax(-1):
        previous=-1;letters=[]
        for index in row:
            if index and index!=previous:letters.append(characters[index])
            previous=index
        output.append(''.join(letters))
    return output


def evaluate(model,rows,root,characters):
    model.eval();predictions=[]
    start=time.perf_counter()
    with paddle.no_grad():
        for row in rows:
            image=cv2.imread(str(root/row['image']));h,w=image.shape[:2]
            width=max(320,min(1600,math.ceil((48*w/h)/8)*8))
            result=model(paddle.to_tensor(image_tensor(root/row['image'],width)[None])).numpy()
            predictions.append(decode(result,characters)[0])
    errors=sum(Levenshtein.distance(row['text'],text) for row,text in zip(rows,predictions))
    def normalized(text):return re.sub(r'\s+',' ',text.casefold()).strip()
    report={'samples':len(rows),'exact':sum(row['text']==text for row,text in zip(rows,predictions)),
            'character_errors':errors,'characters':sum(len(row['text']) for row in rows),
            'cer':errors/max(1,sum(len(row['text']) for row in rows)),
            'recognition_ms_per_crop':(time.perf_counter()-start)*1000/max(1,len(rows)),
            'predictions':[{'image':row['image'],'expected':row['text'],'actual':text} for row,text in zip(rows,predictions)]}
    normalized_characters=sum(len(normalized(row['text'])) for row in rows)
    normalized_errors=sum(Levenshtein.distance(normalized(row['text']),normalized(text)) for row,text in zip(rows,predictions))
    report.update(normalized_errors=normalized_errors,normalized_characters=normalized_characters,
                  normalized_cer=normalized_errors/max(1,normalized_characters),
                  normalized_exact=sum(normalized(row['text'])==normalized(text) for row,text in zip(rows,predictions)))
    report['groups']={}
    for prefix in ('witcher-','skyrim-','hades-'):
        pairs=[(row,text) for row,text in zip(rows,predictions) if row['screen'].startswith(prefix)]
        report['groups'][prefix]={'samples':len(pairs),'errors':sum(Levenshtein.distance(normalized(row['text']),normalized(text)) for row,text in pairs)}
    return report


def main():
    args=arguments();args.output.mkdir(parents=True,exist_ok=True)
    random.seed(args.seed);np.random.seed(args.seed);paddle.seed(args.seed);paddle.set_device(args.device)
    model,characters=make_model(args.paddleocr)
    if args.export_only:
        state=paddle.load(str(args.pretrained))
        if args.blend_checkpoint:
            adapted=paddle.load(str(args.blend_checkpoint))
            assert state.keys()==adapted.keys(),'checkpoint architectures differ'
            assert all(state[k].shape==adapted[k].shape for k in state),'checkpoint shapes differ'
            state={k:state[k]+args.blend_fraction*(adapted[k]-state[k]) for k in state}
        model.set_state_dict(state)
        export_model(model,characters,args.output)
        return
    if args.resume:model.set_state_dict(paddle.load(str(args.pretrained)))
    else:load_pretrained(model,args.pretrained)
    teacher=None
    if args.anchor_weight:
        teacher,_=make_model(args.paddleocr);teacher.set_state_dict(copy.deepcopy(model.state_dict()));teacher.eval()
        for parameter in teacher.parameters():parameter.stop_gradient=True
    if args.freeze_backbone:
        for parameter in model.backbone.parameters():parameter.stop_gradient=True
    training=json.loads((args.dataset/'train.json').read_text(encoding='utf-8'))
    validation=json.loads((args.dataset/'validation.json').read_text(encoding='utf-8'))
    testing=json.loads((args.dataset/'test.json').read_text(encoding='utf-8')) if (args.dataset/'test.json').exists() else []
    assert not ({r['screen'] for r in training}&{r['screen'] for r in validation})
    assert not ({r['screen'] for r in training+validation}&{r['screen'] for r in testing})
    mapping={char:i for i,char in enumerate(characters) if i}
    assert all(all(c in mapping for c in row['text']) for row in training+validation)
    history=[];baseline=evaluate(model,validation,args.dataset,characters)
    metric='normalized_cer' if args.selection_normalized else 'cer'
    best=baseline[metric];best_epoch=0
    paddle.save(model.state_dict(),str(args.output/'best.pdparams'))
    print(json.dumps({'baseline':{k:v for k,v in baseline.items() if k!='predictions'}}),flush=True)
    scheduler=paddle.optimizer.lr.CosineAnnealingDecay(args.learning_rate,max(1,args.epochs*math.ceil(len(training)/args.batch)))
    optimizer=paddle.optimizer.AdamW(learning_rate=scheduler,parameters=[p for p in model.parameters() if not p.stop_gradient],weight_decay=1e-6,
        grad_clip=nn.ClipGradByGlobalNorm(5))
    loss_fn=nn.CTCLoss(blank=0,reduction='mean')
    cached=[image_tensor(args.dataset/row['image']) for row in training]
    started=time.perf_counter()
    for epoch in range(1,args.epochs+1):
        # Bucket similar aspect ratios; pad each batch to its actual widest
        # crop, matching inference rather than diluting short text in 960px.
        order=sorted(range(len(training)),key=lambda i:cached[i].shape[2]+random.uniform(-80,80))
        batches=[order[i:i+args.batch] for i in range(0,len(order),args.batch)];random.shuffle(batches)
        order=[i for batch in batches for i in batch];losses=[];model.train()
        # Preserve generic running statistics on this small adaptation dataset.
        for layer in model.sublayers():
            if isinstance(layer,nn.BatchNorm2D):layer.eval()
        if args.freeze_backbone:model.backbone.eval()
        for start in range(0,len(order),args.batch):
            indices=order[start:start+args.batch];labels=[[mapping[c] for c in training[i]['text']] for i in indices]
            maximum=max(map(len,labels));targets=np.zeros((len(indices),maximum),dtype='int32')
            for i,label in enumerate(labels):targets[i,:len(label)]=label
            width=max(cached[i].shape[2] for i in indices)
            tensors=np.zeros((len(indices),3,48,width),dtype='float32')
            for j,index in enumerate(indices):tensors[j,:,:,:cached[index].shape[2]]=cached[index]
            images=paddle.to_tensor(tensors);logits=model(images)
            log_probs=paddle.nn.functional.log_softmax(logits,axis=-1).transpose([1,0,2])
            loss=loss_fn(log_probs,paddle.to_tensor(targets),
                paddle.full([len(indices)],logits.shape[1],dtype='int64'),
                paddle.to_tensor([len(x) for x in labels],dtype='int64'))
            if teacher is not None:
                with paddle.no_grad():reference=teacher(images)
                anchored=paddle.nn.functional.kl_div(paddle.nn.functional.log_softmax(logits,axis=-1),reference,reduction='batchmean')/logits.shape[1]
                loss=loss+args.anchor_weight*anchored
            assert bool(paddle.isfinite(loss).item()),'non-finite loss'
            loss.backward();optimizer.step();scheduler.step();optimizer.clear_grad();losses.append(float(loss.item()))
            if start%(args.batch*25)==0 and args.device.startswith('gpu'):paddle.device.cuda.empty_cache()
            if start%(args.batch*25)==0:print(json.dumps({'epoch':epoch,'batch':start//args.batch,'loss':losses[-1]}),flush=True)
        result=evaluate(model,validation,args.dataset,characters)
        summary={k:v for k,v in result.items() if k!='predictions'};summary.update(epoch=epoch,loss=float(np.mean(losses)))
        history.append(summary);print(json.dumps(summary),flush=True)
        regression_ok=result['groups']['witcher-']['errors']<=baseline['groups']['witcher-']['errors']
        if result[metric]<best and regression_ok:
            best=result[metric];best_epoch=epoch;paddle.save(model.state_dict(),str(args.output/'best.pdparams'))
        paddle.save(model.state_dict(),str(args.output/'last.pdparams'))
    model.set_state_dict(paddle.load(str(args.output/'best.pdparams')));final=evaluate(model,validation,args.dataset,characters)
    report={'seed':args.seed,'learning_rate':args.learning_rate,'selection_metric':metric,'resumed':args.resume,
        'frozen_backbone':args.freeze_backbone,'anchor_weight':args.anchor_weight,
        'training_examples':len(training),'validation_examples':len(validation),
        'real_training_crops':sum(r['kind']=='real' for r in training),'synthetic_examples':sum(r['kind']=='synthetic' for r in training),
        'source_screens_disjoint':True,'base_checkpoint_sha256':hashlib.sha256(args.pretrained.read_bytes()).hexdigest(),
        'paddle_version':paddle.__version__,'device':args.device,'epochs':args.epochs,'selected_epoch':best_epoch,
        'training_seconds':time.perf_counter()-started,'baseline':baseline,'final':final,'history':history}
    (args.output/'training-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if testing:
        # The independent test never affects optimizer or checkpoint choice.
        report['independent_test']=evaluate(model,testing,args.dataset,characters)
        if args.resume:model.set_state_dict(paddle.load(str(args.pretrained)))
        else:load_pretrained(model,args.pretrained)
        report['independent_test_baseline']=evaluate(model,testing,args.dataset,characters)
        model.set_state_dict(paddle.load(str(args.output/'best.pdparams')))
        (args.output/'training-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    if not args.no_export:export_model(model,characters,args.output)
    print(json.dumps({'selected_epoch':best_epoch,'baseline_cer':baseline['cer'],'final_cer':final['cer'],'exported':not args.no_export}),flush=True)


def export_model(model,characters,output):
    # Convert the saved static graph to ONNX; inference is Paddle-free.
    paddle.set_device('cpu');model.eval()
    for layer in list(model.sublayers()):
        if hasattr(layer,'rep') and not getattr(layer,'is_repped',False):layer.rep()
    static=paddle.jit.to_static(model,input_spec=[paddle.static.InputSpec([None,3,48,None],'float32','image')],full_graph=True)
    paddle.jit.save(static,str(output/'recognition'))
    (output/'characters.txt').write_text('\n'.join(characters[1:-1])+'\n',encoding='utf-8')


if __name__=='__main__':main()
