"""Place a card next to the source, in physical desktop coordinates."""
from .core import Box

def place_card(bounds,anchor,width,height,gap=16,margin=12):
    width=max(1,min(width,bounds.w-2*margin))
    height=max(1,min(height,bounds.h-2*margin))
    left_edge,top_edge=bounds.x+margin,bounds.y+margin
    right_edge,bottom_edge=bounds.x+bounds.w-margin,bounds.y+bounds.h-margin
    left=max(left_edge,min(anchor.x+gap,right_edge-width))
    below=anchor.y+anchor.h+gap
    above=anchor.y-gap-height
    if below+height<=bottom_edge:top=below
    elif above>=top_edge:top=above
    else:
        # At the middle of a short display, try a side before reducing height.
        right=anchor.x+anchor.w+gap
        side_left=anchor.x-gap-width
        if right+width<=right_edge:left=right
        elif side_left>=left_edge:left=side_left
        else:
            below_space=max(1,bottom_edge-below)
            above_space=max(1,anchor.y-gap-top_edge)
            if above_space>below_space:
                height=min(height,above_space);top=anchor.y-gap-height
            else:
                height=min(height,below_space);top=below
            return Box(left,max(top_edge,min(top,bottom_edge-height)),width,height)
        top=max(top_edge,min(anchor.y-height/2,bottom_edge-height))
    return Box(left,top,width,height)
