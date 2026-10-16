from dataclasses import dataclass
import math
from .core import Box
from .screen import intersects
from .screen_groups import grouped_layout
from .screen_vertical import vertical_label


@dataclass(frozen=True)
class Label:
    source:Box
    box:Box
    text:str
    size:int
    placement:str='above'


def layout(entries,width,height,mode,size,offset,measure,obstacles=(),previous=(),fields=()):
    """All coordinates stay inside the capture/game client area."""
    entries=tuple((source,' '.join(text.split())) for source,text in entries)
    labels=[];skipped=0
    sources=[s for s,t in entries]
    foreign=[b for b in obstacles if b not in sources]
    field_limits=dict(fields);field_slots={};field_fonts={}
    if mode=='replace':
        for source,(left,right) in field_limits.items():
            next_rows=[b.y for b,column in field_limits.items() if column==(left,right) and b.y>source.y+max(2,source.h*.4)]
            y=max(0,source.y-2)
            available=min(next_rows)-3-y if next_rows else source.h+max(8,round(size*.9))
            field_slots[source]=(max(0,left-2),y,min(width,max(0,right+2))-max(0,left-2),max(6,available))
        # One readable font for the whole item panel. It must fit each actual
        # row slot, including overlapping detector padding between properties.
        for source,(x,y,w,h) in field_slots.items():
            font=max(9,round(size))
            while font>9 and measure('Ag',font,max(1,w-8))[1]+6>h:font-=1
            column=field_limits[source];field_fonts[column]=min(field_fonts.get(column,font),font)
        for source,text in entries:
            if source not in field_slots:continue
            x,y,w,h=field_slots[source];font=max(9,round(size))
            while font>9 and (measure(text,font,max(1,w-8))[1]+6>h or max(measure(word,font,width)[0] for word in text.split())>w-8):font-=1
            column=field_limits[source];field_fonts[column]=min(field_fonts.get(column,font),font)
    def fits(box,barriers):
        return (box.x>=0 and box.y>=0 and box.x+box.w<=width and box.y+box.h<=height
                and not any(intersects(box,b,1) for b in barriers))
    def barriers_for(source):
        if mode=='replace':
            return [b for b in foreign if not (source in field_limits and field_limits.get(b)==field_limits[source])]+[s for s in sources if s!=source and not source.contains(s.x+s.w/2,s.y+s.h/2)
                    and not (source in field_limits and field_limits.get(s)==field_limits[source])]
        return sources+foreign
    grouped,blocked=grouped_layout(entries,obstacles,field_limits,width,height,size,offset,measure,Label,previous) if mode!='replace' else ({},set())
    # Pin valid placements before fitting newly translated neighbours. A slow
    # batch must not rearrange captions which the player is already reading.
    pinned={}
    for old in previous:
        if (old.source,old.text) not in entries:continue
        if old.source in grouped or old.source in blocked:continue
        if measure(old.text,old.size,max(1,old.box.w-8))[1]+6>old.box.h:continue
        if max(measure(word,old.size,width)[0] for word in old.text.split())>old.box.w-8:continue
        if old.source in field_slots:
            x,y,w,h=field_slots[old.source]
            if abs(old.box.x-x)>.5 or old.box.h>h or old.box.w>w or old.size!=field_fonts.get(field_limits[old.source]):continue
        if fits(old.box,barriers_for(old.source)+[p.box for p in pinned.values()]+[l.box for l in grouped.values()]):
            pinned[(old.source,old.text)]=old
    # Dense lists share a coherent placement rather than scattering rows.
    for source,text in sorted(entries,key=lambda e:(e[0].y,e[0].x)):
        text=' '.join(text.split())
        if not text or source.w<=0 or source.h<=0 or width<16 or height<16:
            skipped+=1;continue
        font=max(9,round(size));chosen=None
        if source in grouped:
            labels.append(grouped[source]);continue
        if source in blocked:
            skipped+=1;continue
        fixed=pinned.get((source,text))
        if fixed:labels.append(fixed);continue
        reserved=[p.box for p in pinned.values()]+[l.box for l in labels]+[l.box for l in grouped.values()]
        x=max(0,min(source.x-3,width-12));y=max(0,source.y-3)
        natural,_=measure(text,font,width-8)
        w=min(width-x,max(12,source.w+6,min(natural+8,source.w*1.25+24)))
        if mode=='replace' and source in field_slots:
            x,y,maximum_w,maximum_h=field_slots[source]
            font=field_fonts[field_limits[source]]
            natural,_=measure(text,font,width)
            w=min(maximum_w,max(source.x+source.w+2-x,natural+8))
            required=math.ceil(measure(text,font,max(1,w-8))[1])+6
            h=min(maximum_h,max(source.h+4,required))
            candidate=Box(x,y,w,h)
            if required<=h and fits(candidate,barriers_for(source)+reserved):
                labels.append(Label(source,candidate,text,font,'field'))
            else:skipped+=1
            continue
        if mode=='replace':
            # Paragraphs keep their column. Reduce font before growing vertically.
            w=min(width-x,max(12,source.w+6))
            barriers=barriers_for(source)+reserved
            # A short translated label can be wider than its English glyphs.
            # Use nearby free space before shrinking, without splitting words.
            if source.h<=font*2 and len(text)<60:
                desired=min(width,max(w,natural+8))
                expanded_x=max(0,min(source.x+source.w/2-desired/2,width-desired))
                expanded=Box(expanded_x,y,desired,max(source.h+6,math.ceil(measure(text,font,desired-8)[1])+8))
                if fits(expanded,barriers):chosen=Label(source,expanded,text,font,'replace')
            for smaller in range(font,8,-1):
                if chosen:break
                if max(measure(word,smaller,width)[0] for word in text.split())>w-8:continue
                h=max(source.h+6,math.ceil(measure(text,smaller,w-8)[1])+8)
                box=Box(x,y,w,h)
                # Glyph boxes omit the font's leading. Reserve one modest
                # leading allowance rather than shrinking a normal heading
                # to a tiny font just to accommodate Qt's line metrics.
                if h<=source.h+max(8,round(font*.9)) and fits(box,barriers):
                    chosen=Label(source,box,text,smaller,'replace');break
            if chosen is None:
                if max(measure(word,9,width)[0] for word in text.split())>w-8:
                    skipped+=1;continue
                h=max(source.h+6,math.ceil(measure(text,9,w-8)[1])+8)
                box=Box(x,min(y,max(0,height-h)),w,h)
                if fits(box,barriers):chosen=Label(source,box,text,9,'replace')
        else:
            barriers=barriers_for(source)+reserved
            chosen=vertical_label(source,text,width,height,font,offset,measure,barriers,Label)
            # Dense paragraphs use neighbouring space without hiding the English.
            if chosen is None:
                for side,available in (('right',width-source.x-source.w-8),('left',source.x-8)):
                    desired=max(source.w+8,natural+8) if len(text)<60 else max(source.w+8,min(width*.32,480))
                    side_w=min(available,desired)
                    if side_w<16:continue
                    side_x=source.x-8-side_w if side=='left' else source.x+source.w+8
                    for smaller in range(font,max(9,round(font*.65))-1,-1):
                        if max(measure(word,smaller,width)[0] for word in text.split())>side_w-8:continue
                        h=math.ceil(measure(text,smaller,side_w-8)[1])+6
                        side_y=max(0,min(source.y,height-h));box=Box(side_x,side_y,side_w,h)
                        if fits(box,barriers):chosen=Label(source,box,text,smaller,side);break
                    if chosen:break
        if chosen:labels.append(chosen)
        else:skipped+=1
    return tuple(labels),skipped
