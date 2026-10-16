"""Verify missing small labels with fresh local OCR, never guess their old text."""
import math
from . import ocr
from .core import Box,normalized
from .screen import blocks,intersection,intersects,same_text,paragraph_key


def crop_label(image,old,offset):
    dx,dy=offset;source=Box(old.box.x-dx,old.box.y-dy,old.box.w,old.box.h)
    padding=max(4,round(source.h*.25))
    bounds=intersection(Box(source.x-padding,source.y-padding,source.w+padding*2,source.h+padding*2),
                        Box(0,0,image.width,image.height))
    if bounds.w<source.w or bounds.h<source.h:return None
    return image.crop((math.floor(bounds.x),math.floor(bounds.y),math.ceil(bounds.x+bounds.w),math.ceil(bounds.y+bounds.h)))


def tracked_subtitle(image,previous,profile,engine,device,offset=(0,0)):
    """Fast verification between full scans; return None for any uncertainty."""
    if len(previous)!=1:return None
    old=previous[0];dx,dy=offset
    if (not paragraph_key(old.text) or old.box.w<image.width*.4 or old.box.y-dy<image.height*.6
            or old.box.h>220 or old.box.w*old.box.h>350000):return None
    crop=crop_label(image,old,offset)
    if crop is None:return None
    found=blocks(ocr.read(crop,profile,engine,device))
    if len(found)==1 and same_text(found[0].text,old.text):return (old,)
    return None


def recover_labels(image,lines,previous,profile,engine,device,offset=(0,0),limit=6):
    result=list(lines);dx,dy=offset;attempts=0
    grouped=blocks(result)
    if (grouped and previous and not any(intersects(new.box,old.box) for new in grouped for old in previous)
            and (len(grouped)>=3 or any(paragraph_key(line.text) for line in grouped))
            and (len(previous)>=3 or any(paragraph_key(line.text) for line in previous))):return lines
    # Verify doubtful reads in the same location before spending the budget on
    # absent HUD labels. A changed scene should not run six obsolete crops first.
    previous=sorted(previous,key=lambda old:not any(intersects(old.box,new.box) for new in grouped))
    for old in previous:
        key=normalized(old.text)
        if any(same_text(line.text,old.text) and intersects(line.box,old.box) for line in grouped):continue
        if len(key)>1200 or old.box.h>220 or old.box.w*old.box.h>350000 or old.box.w<8 or old.box.h<6:continue
        if attempts>=limit:break
        crop=crop_label(image,old,offset)
        if crop is None:continue
        attempts+=1
        found=blocks(ocr.read(crop,profile,engine,device))
        if not any(same_text(line.text,old.text) for line in found):continue
        # A different phrase is never retained just because the old one existed.
        # Remove only rows occupying this same label, leaving nearby HUD intact.
        result=[line for line in result if not (old.box.contains(line.box.x+line.box.w/2,line.box.y+line.box.h/2)
                                               and line.box.w<=old.box.w*1.9 and line.box.h<=old.box.h*1.9)]
        result.append(old)
        grouped=blocks(result)
    return tuple(sorted(result,key=lambda line:(line.box.y,line.box.x)))
