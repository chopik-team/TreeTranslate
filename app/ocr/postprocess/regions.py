"""Conservative flat-background space and adjacent OCR lines for the shared reflow."""
from dataclasses import replace
import numpy as np


def reading_order(segments,region):
    ordered=sorted(segments,key=lambda s:(-round(s.bbox[3]/4),s.bbox[0]))
    if any(s.region_kind=='table_cell' for s in ordered):return ordered
    middle=(region[0]+region[2])/2
    left=[s for s in ordered if s.bbox[2]<middle-4]
    right=[s for s in ordered if s.bbox[0]>middle+4]
    if min(len(left),len(right))<3:return ordered
    top=min(max(s.bbox[3] for s in left),max(s.bbox[3] for s in right))
    bottom=max(min(s.bbox[1] for s in left),min(s.bbox[1] for s in right))
    spanning=[s for s in ordered if s not in left and s not in right]
    if top-bottom<max(30,(region[3]-region[1])*.5) or any(s.bbox[1]<top and s.bbox[3]>bottom for s in spanning):return ordered
    header=[s for s in ordered if s.bbox[1]>top]
    footer=[s for s in spanning if s.bbox[3]<=bottom]
    body=[s for s in ordered if s not in header and s not in footer]
    result=header+[s for s in body if s in left]+[s for s in body if s in right]+footer
    return result if len(result)==len(ordered) else ordered


def allocate(segments,image,region):
    pixels=np.asarray(image,dtype=np.int16)
    width,height=image.size
    left,bottom,right,top=region
    sx,sy=width/(right-left),height/(top-bottom)
    for s in segments:
        s.raster_boxes=(s.bbox,)
        if s.rotation or s.region_kind=='table_cell':
            continue
        x,y,r,t=s.bbox
        px=max(0,int((x-left)*sx)); py=max(0,int((top-t)*sy))
        pr=min(width,int((r-left)*sx)+2); pb=min(height,int((top-y)*sy)+2)
        color=np.array(s.background_color[:3])
        # Search only through uniform adjacent pixels. Borders, diagrams and
        # other glyphs stop expansion, including raster table grid lines.
        maxr=min(width,max(pr,int(px+max((pr-px)*2,width*.5))))
        if pb>py and maxr>pr:
            ink=np.max(np.abs(pixels[py:pb,pr:maxr]-color),axis=2)>35
            occupied=np.flatnonzero(ink.mean(axis=0)>.07)
            pr+=max(0,int(occupied[0])-2) if len(occupied) else maxr-pr
        maxb=min(height,pb+max(4,int((t-y)*sy*2)))
        if pr>px and maxb>pb:
            ink=np.max(np.abs(pixels[pb:maxb,px:pr]-color),axis=2)>35
            occupied=np.flatnonzero(ink.mean(axis=1)>.015)
            pb+=max(0,int(occupied[0])-2) if len(occupied) else maxb-pb
        s.available_bbox=(x,max(bottom,top-pb/sy),min(right,left+pr/sx),t)


def merge_lines(segments,max_chars):
    result=[]
    for s in segments:
        previous=result[-1] if result else None
        if previous and previous.region_kind=='ocr_region' and s.region_kind=='ocr_region' and not previous.rotation and not s.rotation:
            gap=previous.bbox[1]-s.bbox[3]
            height=s.bbox[3]-s.bbox[1]
            aligned=abs(previous.bbox[0]-s.bbox[0])<12
            short_heading=len(previous.text)<15 and previous.bbox[2]-previous.bbox[0]<(s.bbox[2]-s.bbox[0])*.6
            if (0<=gap<=height*1.1 and aligned and not short_heading
                    and previous.background_color==s.background_color and len(previous.text)+len(s.text)<max_chars):
                previous.text+=' '+s.text
                previous.bbox=(min(previous.bbox[0],s.bbox[0]),s.bbox[1],max(previous.bbox[2],s.bbox[2]),previous.bbox[3])
                a,b=previous.available_bbox,s.available_bbox
                previous.available_bbox=(min(a[0],b[0]),b[1],min(a[2],b[2]),a[3])
                previous.raster_boxes+=s.raster_boxes
                previous.confidence=min(previous.confidence,s.confidence)
                continue
        result.append(s)
    return result
