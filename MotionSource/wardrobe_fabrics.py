"""Draw the Shino fabric repeats in UV space; preserve the painted lighting on the uniform."""
import io
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def image_from_model(doc, binary, name):
    image = next(i for i in doc['images'] if i['name'] == name)
    view = doc['bufferViews'][image['bufferView']]
    start = view.get('byteOffset',0)
    return Image.open(io.BytesIO(binary[start:start+view['byteLength']])).convert('RGBA')


def uniforms(doc, binary, output):
    jobs = [('F00_001_Tops_01','shirt'),('F00_001_Bottoms_01','plaid'),
            ('F00_001_Accessory_01','bow'),('F00_001_Shoes_01','loafers'),
            ('F00_000_EyeIris_00','iris'),('F00_000_Body_00','stockings')]
    for source, part in jobs:
        tex = np.array(image_from_model(doc,binary,source))
        rgb = tex[:,:,:3].astype('float32')
        lum = rgb @ np.array([.299,.587,.114],dtype='float32')
        h,w = lum.shape
        x = (np.arange(w,dtype='float32')[None,:]+.5)/w
        y = (np.arange(h,dtype='float32')[:,None]+.5)/h
        def tint(color, light):
            return np.asarray(color,dtype='float32')*light[:,:,None]
        if part=='shirt':
            shirt = (y<.3645) | (abs(x-.5)<np.maximum(0,(.467-y)*.66))
            cream = tint([247,229,207], np.clip((lum/224)**.50, .20, 1.07))
            weave = 1+.012*np.cos(x*w*math.pi/2)*np.cos(y*h*math.pi/3)
            knit = tint([103,42,59], np.clip(((lum+5)/53)**.73, .21, 1.52)*weave)
            rgb = np.where(shirt[:,:,None],cream,knit)
        elif part=='bow':
            rgb = tint([181,119,134], (.26+.76*(lum/139)**.81))
        elif part=='loafers':
            rgb = tint([76,52,41], np.clip(((lum+3)/35)**.70,.27,1.9))
        elif part=='stockings':
            dark = (rgb[:,:,0]<110)&(rgb[:,:,1]<99)&(tex[:,:,3]>0)
            rgb[dark] = tint([86,61,55],np.clip((lum/53)**.85,.46,1.32))[dark]
        elif part=='iris':
            # A graduated amber undertone leaves the dark pupil and printed glints intact.
            keys=[0,14,29,48,72,104,150,206,255]
            colors=np.array([[8,6,12],[20,12,21],[49,27,30],[94,47,30],[139,75,38],
                             [178,108,44],[219,153,68],[249,198,109],[255,247,214]])
            rgb=np.stack([np.interp(lum,keys,colors[:,k]) for k in range(3)],axis=-1)
        else:
            def stripe(coord,period,center,width):
                distance=abs((coord/period-center+.5)%1-.5)
                return np.clip((width/2-distance)*min(h,w)*period+0.5,0,1)
            # Several yarn widths in the same repeat remain legible on folded pleats.
            period=1/13
            base=np.empty((h,w,3),dtype='float32');base[:]=[97,70,55]
            for coord,period_axis in [(x,period),(y,1/5.0)]:
                for center,width,color,opacity in [(.46,.26,[46,35,37],.63),(.83,.10,[164,122,88],.52),
                        (.17,.038,[191,148,107],.68),(.24,.025,[145,111,88],.66),(.58,.032,[42,31,32],.64)]:
                    amount=(opacity*stripe(coord,period_axis,center,width))[:,:,None]
                    base=base*(1-amount)+np.array(color)*amount
            grain=1+.025*np.sin((x*w+y*h)*math.pi*.67)
            rgb=base*(np.clip(((lum+6)/46)**.63,.33,1.5)*grain)[:,:,None]
        tex[:,:,:3]=np.clip(rgb,0,255).astype('uint8')
        Image.fromarray(tex).save(output/('cherry-'+part+'.png'))


def floral(path):
    rng=random.Random(669)
    size=1024
    yy,xx=np.mgrid[:size,:size]
    grain=(.65*np.sin((xx+yy)*math.pi*.50)+.48*np.cos(yy*math.pi*.33))
    base=np.clip(np.array([46,52,73])+grain[:,:,None],0,255).astype('uint8')
    tile=Image.fromarray(base);draw=ImageDraw.Draw(tile)
    # Each sprig is a small asymmetric stem with leaves and two or three florets.
    for row in range(4):
        for column in range(4):
            ox=(column+.30+.37*(row%2)+rng.uniform(-.19,.19))*size/4
            oy=(row+.45+rng.uniform(-.25,.25))*size/4
            angle=rng.uniform(-1.1,1.0); scale=rng.uniform(.87,1.32)
            flower_count=(3,5,4)[(column+row)%3]
            ca,sa=math.cos(angle)*scale,math.sin(angle)*scale
            for tx in (-size,0,size):
                for ty in (-size,0,size):
                    def pt(x,y):
                        return (ox+tx+ca*x-sa*y,oy+ty+sa*x+ca*y)
                    def stroke(coords, color, width):
                        draw.line([pt(x,y) for x,y in coords],fill=color,width=width,joint='curve')
                    def leaf(x,y,dx,dy,color):
                        normal=math.hypot(dx,dy);sx=-dy/normal;sy=dx/normal
                        draw.polygon([pt(x,y),pt(x+dx*.43+sx*3.0,y+dy*.43+sy*3.0),
                                      pt(x+dx,y+dy),pt(x+dx*.55-sx*2.1,y+dy*.55-sy*2.1)],fill=color)
                    stroke([(0,48),(3,24),(1,10),(-7,-12),(-16,-36)],(103,132,129),2)
                    stroke([(2,29),(14,12),(20,-6)],(99,128,125),2)
                    stroke([(-4,-4),(-20,-10),(-29,-23)],(114,132,124),2)
                    stroke([(2,16),(16,1),(29,-14),(31,-31)],(128,146,132),2)
                    stroke([(-8,-15),(-3,-29),(-5,-44)],(139,147,128),2)
                    for x,y,dx,dy,c in [(2,32,-15,-15,(91,123,120)),(1,19,11,-18,(140,154,136)),
                                           (-6,-8,5,-18,(101,136,128)),(14,11,12,-13,(146,153,128)),
                                           (26,-11,10,-12,(134,151,137)),(-4,-29,6,-10,(138,153,132))]:
                        leaf(x,y,dx,dy,c)
                    florets=[(-16,-37,7.8),(20,-8,6.3),(-29,-24,5.8),(31,-31,5.9),(-5,-44,4.4)]
                    for f,(cx,cy,rad) in enumerate(florets[:flower_count]):
                        for k in range(5):
                            a=math.tau*k/5+f*.42; dx,dy=math.cos(a),math.sin(a)
                            verts=[(cx,cy),(cx+dx*rad*.52-dy*rad*.33,cy+dy*rad*.52+dx*rad*.33),
                                   (cx+dx*rad,cy+dy*rad),(cx+dx*rad*.54+dy*rad*.35,cy+dy*rad*.54-dx*rad*.35)]
                            draw.polygon([pt(*p) for p in verts],fill=[(234,216,181),(204,184,155),(198,213,215)][(f+k//3)%3])
                        x,y=pt(cx,cy);draw.ellipse((x-1.6,y-1.6,x+1.6,y+1.6),fill=(222,177,106))
    tile.save(path)


def knit(path):
    # A seamless stockinette swatch. Slanted stitches alternate about each wale.
    yy,xx=np.mgrid[:256,:256];u=xx/16.;v=yy/12.8
    x=(u+.5)%1-.5
    strand=np.cos(math.tau*(v-np.abs(x)*1.55))
    weave=2.3*strand+1.8*np.cos(math.tau*u)+.65*np.cos(math.tau*(u*3+v*2))
    Image.fromarray(np.clip(np.array([242,230,211])+weave[:,:,None],0,255).astype('uint8')).save(path)


def bare_skin(doc,binary,uv,faces,output):
    tex=np.array(image_from_model(doc,binary,'F00_000_Body_00'))
    h,w=tex.shape[:2]; canvas=Image.new('L',(w,h));d=ImageDraw.Draw(canvas)
    for face in faces:
        d.polygon([tuple(p) for p in uv[face]*[w,h]],fill=255)
    painted=np.asarray(canvas.filter(ImageFilter.MaxFilter(9)))>0
    rgb=tex[:,:,:3].astype('float32')
    # Keep the base model's opaque underlayer at the hips. Restore the skin
    # hidden by the old shirt, and recolor the old dark socks down to the toes.
    dark=painted & ((tex[:,:,3]<230) | ((rgb[:,:,0]<145) & (np.arange(h)[:,None]>.74*h)))
    intensity=np.clip((rgb[:,:,0]-38)/270,-.035,.055)
    rgb[dark]=(np.array([245,215,198])*(1+intensity[dark,None]))
    # The source stops painting the clavicles at the shirt collar. Continue its
    # neck gradient across that UV island, feathering into the original skin.
    x=(np.arange(w)+.5)/w; y=(np.arange(h)+.5)/h
    chest=painted & (x[None,:]>.28) & (x[None,:]<.72) & (y[:,None]<.36)
    ramp=np.clip((y-.076)/.083,0,1);ramp=ramp*ramp*(3-2*ramp)
    tone=np.stack([np.interp(y,[.04,.095,.15,.25,.36],chan) for chan in
                    ([231,239,246,246,244],[172,199,217,221,218],[150,180,201,207,204])],axis=1)
    blend=np.maximum(ramp[:,None],1-tex[:,:,3]/255.)*chest
    rgb=rgb*(1-blend[:,:,None])+tone[:,None,:]*blend[:,:,None]
    tex[:,:,:3]=np.clip(rgb,0,255).astype('uint8');tex[:,:,3][painted]=255
    Image.fromarray(tex).save(output/'cardigan-skin.png')
