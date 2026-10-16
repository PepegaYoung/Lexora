"""Keep translations close to their source, above first and below second."""
import math
from .core import Box
from .screen import intersects


def vertical_label(source,text,width,height,size,offset,measure,barriers,label_type):
    minimum=max(9,round(size*.65))
    # Direction takes precedence over font size: a slightly smaller caption
    # above its source is preferable to full-size text off to the side.
    for side in ('above','below'):
        for font in range(max(9,round(size)),minimum-1,-1):
            natural=measure(text,font,width)[0]+8
            cap=min(width,max(source.w+6,width*.6))
            preferred=min(cap,max(12,natural))
            widths=tuple(dict.fromkeys((preferred,min(width,max(12,source.w+6)))))
            for w in widths:
                if max(measure(word,font,width)[0] for word in text.split())>w-8:continue
                h=math.ceil(measure(text,font,w-8)[1])+6
                ys=(source.y-h-max(2,offset),source.y-h-2) if side=='above' else (source.y+source.h+max(2,offset),source.y+source.h+2)
                for y in dict.fromkeys(ys):
                    if y<0 or y+h>height:continue
                    anchors=[source.x-3,source.x+source.w/2-w/2,source.x+source.w+3-w]
                    # A nearby speaker name can occupy just one end of the
                    # line above. Slide within the source span, never across
                    # unrelated parts of the screen, before choosing a side.
                    for obstacle in barriers:
                        if obstacle.y<y+h and obstacle.y+obstacle.h>y:
                            anchors.extend((obstacle.x+obstacle.w+2,obstacle.x-w-2))
                    for x in dict.fromkeys(max(0,min(x,width-w)) for x in anchors):
                        overlap=min(x+w,source.x+source.w)-max(x,source.x)
                        if overlap<min(source.w,w)*.5:continue
                        box=Box(x,y,w,h)
                        if not any(intersects(box,b,1) for b in barriers):
                            return label_type(source,box,text,font,side)
    return None
