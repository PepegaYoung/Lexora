from dataclasses import dataclass
from .core import Box
from .screen import intersects


@dataclass(frozen=True)
class Label:
    source:Box
    box:Box
    text:str
    size:int


def layout(entries,width,height,mode,size,offset,measure,obstacles=()):
    """measure(text,pixel_size,width) -> (natural_width, wrapped_height)."""
    sources=[s for s,t in entries]
    foreign=[b for b in obstacles if b not in sources]
    labels=[]
    skipped=0
    margin=4
    for source,text in sorted(entries,key=lambda e:(e[0].y,e[0].x)):
        text=' '.join(text.split())
        font=max(9,round(size))
        natural,_=measure(text,font,width-2*margin)
        w=min(width-2*margin,max(source.w+8,min(natural+12,max(source.w*1.5,width*.38))))
        x=max(margin,min(source.x,width-margin-w))
        if mode=='replace':
            others=[b for b in sources+foreign if b!=source and not source.contains(b.x+b.w/2,b.y+b.h/2)]
            # Expansion is only allowed into space unoccupied by other source text.
            y=max(0,source.y-3)
            w=max(source.w+6,w)
            w=min(width-x,w)
            h=min(height-y,max(source.h+6,measure(text,font,w-8)[1]+8))
            while font>9 and (h>source.h+8 or any(intersects(Box(x,y,w,h),b) for b in others)):
                font-=1
                h=max(source.h+6,measure(text,font,w-8)[1]+8)
            # Never cover neighbouring English UI text to fit a long translation.
            box=Box(x,y,w,h)
            if y+h>height or any(intersects(box,b) for b in others):
                w=min(width-x,source.w+6)
                h=max(source.h+6,measure(text,font,w-8)[1]+8)
                box=Box(x,y,w,h)
            if y+h>height or any(intersects(box,b) for b in others):skipped+=1;continue
        else:
            h=measure(text,font,w-8)[1]+4
            y=source.y-h-max(2,offset)
            box=Box(x,y,w,h)
            barriers=sources+foreign+[l.box for l in labels]
            if any(intersects(box,b,2) for b in barriers):
                # Menu rows often have just a small gap. First fit directly above
                # this row, rather than moving every choice above the whole menu.
                for smaller in range(font,max(10,round(size*.60))-1,-1):
                    compact_h=measure(text,smaller,w-8)[1]+4
                    candidate=Box(x,source.y-compact_h-2,w,compact_h)
                    if candidate.y>=margin and not any(intersects(candidate,b,1) for b in barriers):
                        font,h,y=smaller,compact_h,candidate.y
                        break
            # Search upwards: labels never obscure any English or each other.
            while y>=margin:
                box=Box(x,y,w,h)
                collisions=[b for b in sources+foreign+[l.box for l in labels] if intersects(box,b,1)]
                if not collisions:break
                y=min(b.y for b in collisions)-h-4
            if y<margin:skipped+=1;continue
        if any(intersects(box,l.box,1) for l in labels):skipped+=1;continue
        labels.append(Label(source,box,text,font))
    return tuple(labels),skipped
