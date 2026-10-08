"""Screen text tracking in physical image coordinates; no GUI or network work here."""
from dataclasses import dataclass
import re
from .core import Box,Line,normalized


def intersects(a,b,padding=0):
    return (a.x < b.x+b.w+padding and a.x+a.w+padding > b.x and
            a.y < b.y+b.h+padding and a.y+a.h+padding > b.y)


def union(boxes):
    x,y=min(b.x for b in boxes),min(b.y for b in boxes)
    return Box(x,y,max(b.x+b.w for b in boxes)-x,max(b.y+b.h for b in boxes)-y)


def blocks(lines):
    # Windows sometimes joins two distant UI columns into one OCR line.
    split=[]
    for line in lines:
        chunks=[[]]
        for word in line.words:
            if chunks[-1]:
                last=chunks[-1][-1]
                if word.box.x-last.box.x-last.box.w > max(40,line.box.h*2.5):chunks.append([])
            chunks[-1].append(word)
        parts=[Line(' '.join(w.text for w in c),union([w.box for w in c]),tuple(c)) for c in chunks if c] or [line]
        split.extend(p for p in parts if re.search('[A-Za-z]',p.text))
    # Join clear wrapped continuations, but keep numbered choices separate.
    result=[]
    for line in sorted(split,key=lambda l:(l.box.y,l.box.x)):
        prev=result[-1] if result else None
        if (prev and re.match(r'^[a-z]',line.text.strip()) and not re.search(r'[.!?:]$',prev.text.strip())
            and not re.match(r'^\s*\d+[.)]',prev.text) and line.text.count('\n')<3
            and abs(prev.box.x-line.box.x)<max(12,line.box.h*.7)
            and 0 <= line.box.y-prev.box.y-prev.box.h < line.box.h*.8
            and prev.text.count('\n')<3):
            result[-1]=Line(prev.text+'\n'+line.text,union([prev.box,line.box]),prev.words+line.words)
        else:result.append(line)
    return tuple(result)


@dataclass
class Track:
    id:int
    line:Line
    first:float
    seen:float
    stable:bool=False


class Tracker:
    def __init__(self,delay=.25,grace=.75):
        self.delay,self.grace=delay,grace
        self.items=[]
        self.serial=0
        self.cache={}

    def update(self,lines,now,instant=False):
        used=set()
        for line in blocks(lines):
            key=normalized(line.text)
            choices=[t for t in self.items if t.id not in used and normalized(t.line.text)==key]
            old=min(choices,key=lambda t:abs(t.line.box.x-line.box.x)+abs(t.line.box.y-line.box.y)) if choices else None
            if old is not None:
                a,b=old.line.box,line.box
                if max(abs(a.x-b.x),abs(a.y-b.y),abs(a.h-b.h))<4 and abs(a.w-b.w)<8:
                    line=Line(line.text,a,line.words)
                old.line,old.seen=line,now
            else:
                self.serial+=1
                old=Track(self.serial,line,now,now)
                self.items.append(old)
            old.stable=instant or now-old.first>=self.delay
            used.add(old.id)
        # New stable text removes the old phrase occupying the same location.
        current=[t for t in self.items if t.id in used and t.stable]
        self.items=[t for t in self.items if now-t.seen<=self.grace and
                    (t.id in used or not any(intersects(t.line.box,n.line.box) for n in current))]

    def missing(self):
        unique={}
        for t in self.items:
            key=normalized(t.line.text)
            if t.stable and key not in self.cache:unique.setdefault(key,t.line.text)
        return list(unique.values())

    def remember(self,texts,translations):
        if len(texts)!=len(translations):raise ValueError('Translation count mismatch')
        if len(self.cache)>2000:self.cache.clear()
        self.cache.update((normalized(s),t) for s,t in zip(texts,translations))

    def ready(self):
        return tuple((t.line,self.cache[normalized(t.line.text)]) for t in self.items if t.stable and normalized(t.line.text) in self.cache)
