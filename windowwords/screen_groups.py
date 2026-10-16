"""Place dense related labels together, preserving their reading order."""
import math
from statistics import median
from .core import Box
from .screen import intersects


def grouped_layout(entries,obstacles,fields,width,height,size,offset,measure,label_type,previous=()):
    if width<16 or height<16:return {},set()
    texts=dict(entries);sources=tuple(dict.fromkeys([s for s,t in entries]+list(obstacles)))
    groups=[];claimed=set()
    for column in dict.fromkeys(fields.values()):
        group=sorted((s for s,c in fields.items() if c==column),key=lambda s:s.y)
        if len(group)>=3:groups.append(group);claimed.update(group)
    chains=[]
    for source in sorted((s for s in sources if s not in claimed),key=lambda s:(s.y,s.x)):
        if source.w>max(320,width*.3) or source.h>size*2.5+8:continue
        candidates=[g for g in chains if .65<=source.h/max(1,g[-1].h)<=1.55
                    and min(source.h,g[-1].h)*.7<source.y-g[-1].y<=max(source.h,g[-1].h)*3
                    and (abs(source.x-g[-1].x)<=max(14,min(source.h,g[-1].h)*.7)
                         or abs(source.x+source.w/2-g[-1].x-g[-1].w/2)<=14)]
        if candidates:min(candidates,key=lambda g:source.y-g[-1].y).append(source)
        else:chains.append([source])
    for group in chains:
        gaps=[b.y-a.y-a.h for a,b in zip(group,group[1:])]
        if len(group)>=3 and median(gaps)<measure('Ag',size,width)[1]+8:
            groups.append(group);claimed.update(group)
    planned={};blocked=set();reserved=[]
    for group in groups:
        active=[s for s in group if texts.get(s) and s.w>0 and s.h>0]
        if not active:continue
        left=min(s.x for s in group);right=max(s.x+s.w for s in group)
        top=min(s.y for s in group);bottom=max(s.y+s.h for s in group)
        barriers=list(sources)+reserved
        structured=any(s in fields for s in group)
        # A predictable width from all detected rows prevents late translations
        # from moving a partially translated list to the opposite side.
        cap=min(width*.34,520)
        preferred=max(right-left+8,min(cap,size*10),max(measure(texts[s],size,width)[0]+8 for s in active))
        found=None
        old_sides=[old.placement.removeprefix('group-') for old in previous
                   if old.source in active and old.text==texts[old.source] and old.placement.startswith('group-')]
        sides=list(dict.fromkeys(old_sides+['above','below','right','left']))
        for side in sides:
            for font in range(max(9,round(size)),max(9,round(size*.7))-1,-1):
                vertical=side in ('above','below')
                available=width if vertical else width-right-10 if side=='right' else left-10
                column_w=min(available,cap,preferred)
                if column_w<40:continue
                if any(max(measure(word,font,width)[0] for word in texts[s].split())>column_w-8 for s in active):continue
                heights={s:math.ceil(measure(texts.get(s,'Ag'),font,column_w-8)[1])+6 for s in group}
                positions={};cursor=0
                for index,source in enumerate(group):
                    relative=0 if vertical else source.y-top
                    cursor=max(cursor,relative)
                    positions[source]=cursor;cursor+=heights[source]+4
                total=cursor-4
                x=max(0,min((left+right-column_w)/2,width-column_w)) if vertical else right+10 if side=='right' else left-10-column_w
                y=top-total-max(2,offset) if side=='above' else bottom+max(2,offset) if side=='below' else max(0,min(top,height-total))
                if y<0 or y+total>height:continue
                labels=[label_type(s,Box(x,y+positions[s],min(column_w,max(40,measure(texts[s],font,width)[0]+8)),heights[s]),texts[s],font,'group-'+side) for s in active]
                if any(any(intersects(label.box,b,1) for b in barriers) for label in labels):continue
                found=labels;break
            if found:break
        if found:
            for label in found:planned[label.source]=label
            reserved.extend(label.box for label in found)
        else:
            # Never scatter one inventory description across unrelated areas.
            # The caller reports unplaced translations in its normal history.
            blocked.update(active)
    return planned,blocked
