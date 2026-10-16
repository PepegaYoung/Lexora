"""Screen text tracking in physical image coordinates; no GUI or network work here."""
from dataclasses import dataclass
import re
from statistics import median
from .core import Box,Line,normalized


def intersects(a,b,padding=0):
    return (a.x < b.x+b.w+padding and a.x+a.w+padding > b.x and
            a.y < b.y+b.h+padding and a.y+a.h+padding > b.y)


def union(boxes):
    x,y=min(b.x for b in boxes),min(b.y for b in boxes)
    return Box(x,y,max(b.x+b.w for b in boxes)-x,max(b.y+b.h for b in boxes)-y)


_NUMBER=r'\d+(?:[.,]\d+)?'
_UNIT=r'(?:FPS|ms|%|[MG]B|[MG]Hz|°\s*C|C)'
_PERFORMANCE=re.compile(
    rf'(?:{_NUMBER}\s*(?:FPS|ms)|'
    rf'(?:FPS|FRAME\s*RATE|FRAME\s*TIME|CPU|GPU|VRAM|RAM|PING|LATENCY)'
    rf'\s*[:=]?\s*{_NUMBER}\s*(?:{_UNIT})?|FPS)'
    rf'(?:\s*[|,;]?\s*(?:{_NUMBER}\s*(?:FPS|ms)|'
    rf'(?:FPS|FRAME\s*RATE|FRAME\s*TIME|CPU|GPU|VRAM|RAM|PING|LATENCY)'
    rf'\s*[:=]?\s*{_NUMBER}\s*(?:{_UNIT})?))*',re.IGNORECASE)


def without_metrics(lines):
    """Remove performance counters before they can join game text or a batch.

    A whole diagnostic row can be skipped directly. Inside a mixed OCR row,
    require different glyph size or a large spatial gap so ordinary dialogue
    such as 'This runs at 60 FPS' stays intact.
    """
    result=[]
    def metric(text):return bool(_PERFORMANCE.fullmatch(text.strip(' []|')))
    for line in lines:
        if metric(line.text):continue
        words=line.words;removed=set()
        for start in range(len(words)):
            if start in removed:continue
            for end in range(min(len(words),start+12),start,-1):
                span=words[start:end]
                if not metric(' '.join(w.text for w in span)):continue
                others=words[:start]+words[end:]
                if not others:removed.update(range(start,end));break
                small=median(w.box.h for w in span)<median(w.box.h for w in others)*.75
                gap=max((span[0].box.x-words[start-1].box.x-words[start-1].box.w if start else 0),
                        (words[end].box.x-span[-1].box.x-span[-1].box.w if end<len(words) else 0))
                if small or gap>max(40,median(w.box.h for w in span)*2.5):
                    removed.update(range(start,end));break
        if not removed:result.append(line);continue
        kept=tuple(word for index,word in enumerate(words) if index not in removed)
        if kept:result.append(Line(' '.join(w.text for w in kept),union([w.box for w in kept]),kept))
    return tuple(result)


def blocks(lines):
    # Windows sometimes joins two distant UI columns into one OCR line.
    split=[]
    for line in without_metrics(lines):
        chunks=[[]]
        for word in line.words:
            if chunks[-1]:
                last=chunks[-1][-1]
                gap=word.box.x-last.box.x-last.box.w
                key=bool(re.fullmatch(r'\[?(?:[A-Z]|Space|Tab|Enter|Shift|Ctrl|Alt|Esc(?:ape)?|F\d{1,2})\]?',word.text))
                button=key and len(chunks[-1])>=2 and gap>max(12,min(last.box.h,word.box.h)*.65)
                if gap>max(40,line.box.h*2.5) or button:chunks.append([])
            chunks[-1].append(word)
        parts=[Line(' '.join(w.text for w in c),union([w.box for w in c]),tuple(c)) for c in chunks if c] or [line]
        split.extend(p for p in parts if text_label(p.text))
    return paragraphs(split)


def text_label(text):
    """Only screen translation filters icon-like tokens; dictionary OCR keeps them."""
    letters=re.findall('[A-Za-z]',text)
    if len(letters)<2:return False
    if re.fullmatch(r'[xX\u00d7\u2715\u2716+*|/\\\s.,:_-]+',text):return False
    return True


def protected_lines(lines):
    """Numbers, key icons and counters remain visible in above-original mode."""
    retained=without_metrics(lines)
    return tuple(line for line in lines if not text_label(line.text) or line not in retained)


def property_row(text):
    return bool(re.match(r'^\s*[+\-−]?\s*\d+(?:[.,]\d+)?\s*%',text))


def field_columns(lines):
    """Find a structured stats column from repeated percentage rows."""
    groups=[]
    for line in sorted((line for line in lines if property_row(line.text)),key=lambda line:line.box.y):
        matches=[group for group in groups if abs(line.box.x-group[-1].box.x)<=max(20,line.box.h*.8)
                 and 0<line.box.y-group[-1].box.y<=max(line.box.h,group[-1].box.h)*3]
        if matches:matches[-1].append(line)
        else:groups.append([line])
    result={}
    for group in groups:
        if len(group)<2:continue
        leading=median(line.box.h for line in group)
        left=min(line.box.x for line in group);right=max(line.box.x+line.box.w for line in group)
        top=group[0].box.y-leading*6;bottom=group[-1].box.y+group[-1].box.h+leading*4
        members=[line for line in lines if abs(line.box.x-left)<=max(20,leading*.8) and top<=line.box.y<=bottom]
        column=(min([left]+[line.box.x for line in members]),right)
        for line in members:result[line.box]=column
    return result


def paragraphs(lines):
    """Group a wrapped column before translation, preserving headings and choices.

    OCR boxes measure visible glyphs, not line height: a row without descenders
    can be much shorter than its neighbours. Use nearby row heights for spacing
    and keep the last physical row of a chain separate from its growing bounds.
    """
    rows=sorted(lines,key=lambda l:(l.box.y,l.box.x));chains=[]
    def numbered(line):return bool(re.match(r'^\s*\d+[.)]',line.text))
    def aligned(a,b):
        tolerance=max(12,max(a.box.h,b.box.h)*.65)
        return (abs(a.box.x-b.box.x)<tolerance or
                abs(a.box.x+a.box.w/2-b.box.x-b.box.w/2)<tolerance)
    def continuation(a,b):
        start=b.text.strip().lstrip('"\'“‘(')
        return bool(re.match(r'^[a-z]',start) and not re.search(r'[.!?:]$',a.text.strip()))
    for row in rows:
        nearby=[other.box.h for other in rows if aligned(other,row)
                and abs(other.box.y-row.box.y)<max(160,row.box.h*8)
                and .55<=other.box.h/max(1,row.box.h)<=1.85]
        leading=median(nearby) if nearby else row.box.h
        candidates=[]
        for chain in chains:
            last=chain[-1];gap=row.box.y-last.box.y-last.box.h
            # Detector polygons include padding and can overlap neighbouring
            # rows. They must still progress down the column, not share a row.
            padding=min(last.box.h,row.box.h)*.45
            heading=(len(last.text.strip())<30 and last.box.h>leading*1.18
                     and gap>max(4,leading*.5))
            if (not numbered(last) and not numbered(row) and aligned(last,row)
                    and .55<=last.box.h/max(1,row.box.h)<=1.85
                    and row.box.y-last.box.y>max(2,min(last.box.h,row.box.h)*.4)
                    and not heading and -padding<=gap<=max(leading,row.box.h,last.box.h)*.95):
                candidates.append(chain)
        if candidates:min(candidates,key=lambda c:row.box.y-c[-1].box.y).append(row)
        else:chains.append([row])
    result=[]
    for chain in chains:
        structured=sum(property_row(row.text) for row in chain)>=2
        # Several wrap continuations establish a paragraph. Once established,
        # punctuation and capital letters inside it do not create new panels.
        wraps=sum(continuation(a,b) for a,b in zip(chain,chain[1:]))
        long_rows=sum(len(row.text.strip())>=30 for row in chain)
        word_count=sum(len(row.text.split()) for row in chain)
        paragraph=len(chain)>=3 and (wraps>=2 or long_rows>=2 or (wraps>=1 and word_count>=12))
        chunks=[[]]
        for row in chain:
            if chunks[-1]:
                last=chunks[-1][-1]
                if structured:
                    join=(not property_row(row.text) and continuation(last,row)
                          and row.box.x-last.box.x>max(8,last.box.h*.35))
                else:join=paragraph or continuation(last,row) or len(last.text.strip())>=30
                if not join:chunks.append([])
            chunks[-1].append(row)
        for chunk in chunks:
            result.append(Line('\n'.join(row.text for row in chunk),union([row.box for row in chunk]),
                               tuple(word for row in chunk for word in row.words)))
    return tuple(sorted(result,key=lambda l:(l.box.y,l.box.x)))


def intersection(first,second):
    x,y=max(first.x,second.x),max(first.y,second.y)
    return Box(x,y,max(0,min(first.x+first.w,second.x+second.w)-x),max(0,min(first.y+first.h,second.y+second.h)-y))


@dataclass
class Track:
    id:int
    line:Line
    first:float
    seen:float
    stable:bool=False


def paragraph_key(text):
    # Only long prose tolerates OCR punctuation/spacing flicker. Short choices
    # keep exact punctuation, and letters and numbers are never guessed.
    if len(text)<80 or len(text.split())<8:return None
    return ''.join(char for char in text.casefold() if char.isalnum())


def numeric_tokens(text):
    return tuple(re.findall(r'[-+]?\d+(?:[.,]\d+)*(?:[-–]\d+(?:[.,]\d+)*)?',text.casefold()))


def same_text(first,second):
    if normalized(first)==normalized(second):return True
    key=paragraph_key(first)
    return key is not None and key==paragraph_key(second) and numeric_tokens(first)==numeric_tokens(second)


def same_location(first,second):
    overlap=intersection(first,second)
    return overlap.w*overlap.h>=min(first.w*first.h,second.w*second.h)*.5


class Tracker:
    def __init__(self,delay=.25,grace=1.5):
        self.delay,self.grace=delay,grace
        self.items=[]
        self.serial=0
        self.cache={}

    def update(self,lines,now,instant=False):
        used=set();matched=set();existing={t.id for t in self.items}
        for line in blocks(lines):
            choices=[t for t in self.items if t.id not in used and same_location(t.line.box,line.box)
                     and same_text(t.line.text,line.text)]
            old=min(choices,key=lambda t:abs(t.line.box.x-line.box.x)+abs(t.line.box.y-line.box.y)) if choices else None
            if old is not None:
                if old.stable:matched.add(old.id)
                a,b=old.line.box,line.box
                jitter=(max(abs(a.x-b.x),abs(a.y-b.y))<=6 and
                        abs(a.h-b.h)<=max(6,a.h*.2) and abs(a.w-b.w)<=max(24,a.w*.1))
                # Keep the translated wording and its geometry across harmless
                # punctuation changes. Real movement still follows the source.
                line=Line(old.line.text,a if jitter else b,line.words)
                old.line,old.seen=line,now
            else:
                # A detector dropout may expose only part of a paragraph.
                # Hold its complete version for the existing grace period;
                # partial evidence never extends the old phrase's lifetime.
                partial=paragraph_key(line.text)
                if partial:
                    covered=[t for t in self.items if t.stable and now-t.seen<=self.grace
                             and paragraph_key(t.line.text) and partial in paragraph_key(t.line.text)
                             and len(partial)<len(paragraph_key(t.line.text))
                             and len(partial)>=len(paragraph_key(t.line.text))*.35
                             and all(number in numeric_tokens(t.line.text) for number in numeric_tokens(line.text))
                             and same_location(t.line.box,line.box)]
                    if covered:
                        used.add(covered[0].id);matched.add(covered[0].id);continue
                self.serial+=1
                old=Track(self.serial,line,now,now)
                self.items.append(old)
            old.stable=old.stable or instant or now-old.first>=self.delay
            used.add(old.id)
        # New stable text removes the old phrase occupying the same location.
        current=[t for t in self.items if t.id in used and t.stable]
        # A stable, wholly different menu/prose scene invalidates old captions
        # even when the new text occupies a different part of the screen.
        unseen=[t for t in self.items if t.id in existing and t.id not in used and t.stable]
        changed=[t for t in current if t.id not in matched]
        scene_changed=(changed and unseen and
                       ((len(changed)>=3 and len(changed)>=len(matched)) or
                        (any(paragraph_key(t.line.text) for t in changed) and
                         (len(unseen)>=3 or any(paragraph_key(t.line.text) for t in unseen)))))
        # An unchanged HUD counter is not evidence that the old story/menu
        # still exists. Pending readings must also recur consecutively: a
        # reappearing OCR typo cannot become stable just by ageing in memory.
        self.items=[t for t in self.items if now-t.seen<=self.grace and (t.stable or t.id in used) and
                    (t.id in used or (not scene_changed and not any(same_location(t.line.box,n.line.box) for n in current)))]

    def missing(self):
        unique={}
        for t in self.items:
            key=normalized(t.line.text)
            if t.stable and key not in self.cache:unique.setdefault(key,t.line.text)
        return list(unique.values())

    def remember(self,texts,translations):
        if len(texts)!=len(translations):raise ValueError('Translation count mismatch')
        for source,target in zip(texts,translations):
            key=normalized(source)
            self.cache.pop(key,None)
            self.cache[key]=target
        protected={normalized(t.line.text) for t in self.items}
        # Evict old, invisible phrases without blanking the current screen.
        excess=len(self.cache)-2000
        for key in tuple(self.cache):
            if excess<=0:break
            if key not in protected:
                del self.cache[key];excess-=1

    def ready(self):
        return tuple((t.line,self.cache[normalized(t.line.text)]) for t in self.items if t.stable and normalized(t.line.text) in self.cache)
