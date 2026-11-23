"""Bake the 33C illustrated fabric panels and combed strand textures in garment UV space."""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

TAU=math.tau


def smooth(x):
    x=np.clip(x,0,1)
    return x*x*(3-2*x)


def lookup(image,x,y):
    h,w=image.shape[:2]
    x=np.clip(x,0,w-1.001);y=np.clip(y,0,h-1.001)
    i=x.astype(int);j=y.astype(int);fx=(x-i)[...,None];fy=(y-j)[...,None]
    return (image[j,i]*(1-fx)+image[j,i+1]*fx)*(1-fy)+(image[j+1,i]*(1-fx)+image[j+1,i+1]*fx)*fy


def extrapolate(image,mask,neutral):
    """Extend fabric under the knot and outside the cut; arms and ribbons never enter the atlas."""
    val=mask.astype(float)
    out=np.broadcast_to(np.array(neutral,dtype=float),image.shape).copy()
    weights=Image.fromarray(np.uint8(val*255))
    masked=Image.fromarray(np.uint8(image*val[:,:,None]))
    for radius in (30,12,5,2):
        w=np.asarray(weights.filter(ImageFilter.GaussianBlur(radius)),dtype=float)/255
        pix=np.asarray(masked.filter(ImageFilter.GaussianBlur(radius)),dtype=float)
        cover=smooth((w-.08)/.62)[:,:,None]
        out=out*(1-cover)+pix/np.maximum(.04,w[:,:,None])*cover
    return np.where(mask[:,:,None],image,out)


def fabric_maps(dest):
    source=np.asarray(Image.open(Path(__file__).with_name('coral-silk-reference.png')).convert('RGB'),dtype=float)
    r,g,b=source.transpose(2,0,1)
    srcy,srcx=np.mgrid[:r.shape[0],:r.shape[1]];srcy+=154;srcx+=34
    u,v=np.meshgrid((np.arange(1024)+.5)/1024,(np.arange(768)+.5)/768)
    a=(u-.5)*TAU;pos=(1-np.sin(a))*.5;front=smooth((np.cos(a)+.06)/.57)
    for skirt in (True,False):
        if skirt:
            valid=(b-g>6)&(g<r*.44)&(r>b*1.40)&(srcy>339)&(srcy<780)
            data=extrapolate(source,valid,[124,37,59])
            y=349+v*414
            knots=[348,366,398,446,491,556,620,691,725,763]
            left=np.interp(y,knots,[130,125,110,96,94,94,86,68,59,67])
            right=np.interp(y,knots,[216,226,242,259,264,263,270,281,287,278])
            # The long diagonal ridges come from the unobstructed panel of the selected drawing.
            sampled=lookup(data,left+(right-left)*pos-34,y-154)
            base=np.array([128,32,58]);relative=np.clip(sampled[:,:,0]/116,.37,1.78)
            flank=.98+.09*np.cos(6*a+.82*(1-v))+.035*np.sin(9*a-1.1*v)
            light=(1-front)*flank+front*(.22+.78*relative**.88)
            warm=front*np.clip((relative-1)*.17,-.09,.13)
            rgb=base*light[:,:,None];rgb[:,:,1]*=1+warm;rgb[:,:,2]*=1+.42*warm
            name='bordeaux-bias'
        else:
            valid=(srcy>181)&(srcy<319)&(srcx>111)&(srcx<238)&(r>133)&(r-g>42)&(g-b<18)&(b-g<12)
            data=extrapolate(source,valid,[228,146,139])
            # Soften the drawn edge of the collar. The new 3D facing supplies that edge on the model.
            data=np.asarray(Image.fromarray(np.uint8(data.clip(0,255))).filter(ImageFilter.GaussianBlur(1.5)))
            y=198+v*116
            left=np.interp(y,[198,228,256,285,314],[126,122,120,122,127])
            right=np.interp(y,[198,228,256,285,314],[220,230,229,226,219])
            sample=lookup(data,left+(right-left)*pos-34,y-154)
            base=np.array([213,111,96]);relative=np.clip(sample[:,:,1]/138,.57,1.30)
            gain=(1-front)+front*(1+(.15+.65*smooth((v-.27)/.45))*(relative-1))
            rgb=base*gain[:,:,None];name='bordeaux-crepe'
        grain=.75*np.sin(TAU*(157*u+89*v))+.42*np.sin(TAU*(193*u-135*v))
        Image.fromarray(np.uint8(np.clip(rgb+grain[:,:,None],0,255))).save(dest/(name+'.png'),optimize=True)


def strand_maps(dest):
    """Four different tapered clumps. Sparse edge fibres share the same map and skin as the lock."""
    width,height=192,768
    x,v=np.meshgrid((np.arange(width)+.5)/width,(np.arange(height)+.5)/height)
    colors=[];normals=[]
    for tile in range(4):
        rng=np.random.default_rng(703+tile)
        # Slowly-changing lateral coordinates make the fine lines follow a comb stroke.
        bend1=rng.uniform(0,TAU);bend2=rng.uniform(0,TAU)
        fibre=x+.014*np.sin(TAU*(v*.85+x*.68)+bend1)+.007*np.sin(TAU*(1.7*v-x*1.15)+bend2)
        coarse=.48*np.cos(TAU*(3.2*fibre+.06*np.sin(4*v)))+.28*np.sin(TAU*(6.4*fibre-.08*v))
        detail=np.zeros_like(x)
        for n in range(82):
            center=(n+rng.uniform(-.37,.37))/81
            strand=center+.008*np.sin(v*rng.uniform(3,7)+rng.uniform(0,TAU))+.004*np.sin(10*v+rng.uniform(0,TAU))
            sigma=rng.uniform(.0015,.0065);strength=rng.uniform(-.094,.073)
            detail+=strength*np.exp(-.5*((fibre-strand)/sigma)**2)
        broad=.20*np.exp(-((v-.25-.075*np.cos(4*fibre+bend2))/.095)**2)+.12*np.exp(-((v-.66+.06*np.sin(4*fibre))/.14)**2)
        h=.85+.095*coarse+detail+broad*.74
        rim=.018+.055*(.5+.5*np.sin(15*v+tile))
        edge=np.minimum(x,1-x)
        threshold=rim*(.57+.54*np.cos(65*TAU*fibre+.60*np.sin(9*v)))
        mask=smooth((edge-threshold)/.020)
        # Pointed sub-clumps and much finer single tips break up the lower silhouette.
        length=.73+.24*(.5+.5*np.sin(TAU*(2.65*x+.14*np.sin(7*x)+tile*.23)))+.032*np.sin(32*TAU*fibre)
        mask*=smooth((length-v)/.038)
        tone=np.clip(247*h+.5,45,255)
        rgb=np.stack((tone,np.clip(tone*.976,0,255),np.clip(tone*.990,0,255),255*mask),axis=2)
        colors.append(np.uint8(rgb))
        slope=np.gradient(coarse*.36+detail*.62,axis=1)*2.5
        nn=np.stack((-slope,np.zeros_like(x),np.ones_like(x)),axis=-1);nn/=np.linalg.norm(nn,axis=2)[:,:,None]
        normals.append(np.uint8((.5+.5*nn)*255))
    Image.fromarray(np.concatenate(colors,axis=1)).save(dest/'bordeaux-strands.png',optimize=True)
    Image.fromarray(np.concatenate(normals,axis=1)).save(dest/'bordeaux-strands-n.png',optimize=True)


def painted_hair(dest):
    """Follow the brush strokes of the approved 33C portrait from part to tips.
    Chart boundaries lie inside the hair silhouette. They contain no face pixels."""
    im=np.asarray(Image.open(Path(__file__).with_name('coral-hair-reference.png')).convert('RGB'),dtype=float)
    r,g,b=im.transpose(2,0,1)
    plum=extrapolate(im,(r<165)&(b>g*1.14)&(r>g*1.20)&(b>r*.59),[94,54,80])
    copper=extrapolate(im,(r>92)&(r>1.55*g)&(g>b*.78)&(b<r*.83),[202,98,99])
    u,v=np.meshgrid((np.arange(512)+.5)/512,(np.arange(640)+.5)/640)

    def panel(source,inner,outer,scale,plum=True):
        inner,outer=np.array(inner),np.array(outer)
        def line(points,axis):return np.interp(v, np.linspace(0,1,len(points)),points[:,axis])
        x=(1-u)*line(inner,0)+u*line(outer,0);y=(1-u)*line(inner,1)+u*line(outer,1)
        sampled=lookup(source,x,y)
        avg=np.array([98,53,82] if plum else [211,104,106])
        # Retain painted separation between clumps while leaving the bright moving
        # band to the live lights. Individual fine fibres vary over the whole length.
        grain=.024*np.sin(TAU*(83*u+.17*np.sin(7*v)))+.014*np.sin(TAU*(144*u+.27*np.cos(5*v+u)))
        return np.uint8(np.clip((sampled*.80+avg*.20)*scale*(1+grain[:,:,None]),0,255))
    crown_light=panel(plum,[(89,56),(71,59),(59,68),(55,83),(47,104),(37,119),(31,138)],
        [(117,18),(100,20),(81,25),(65,36),(48,58),(38,88),(31,126)],1.15)
    crown_swept=panel(plum,[(92,54),(101,65),(111,90),(128,110),(151,124),(172,132),(194,145)],
        [(136,20),(158,31),(181,52),(199,77),(211,101),(224,133),(232,167)],1.16)
    # The first row of both charts follows the same curved part. Cross-fade the
    # painted colour there so the part reads as a root, not an atlas seam.
    root=(crown_swept[0].astype(float)+crown_light[0].astype(float))*.49
    feather=smooth(v/.12)[:,:,None]
    halves=[np.uint8(root[None,:,:]*(1-feather)+chart*feather) for chart in (crown_swept,crown_light)]
    Image.fromarray(np.concatenate(halves,axis=1)).save(dest/'bordeaux-crown.png',optimize=True)
    dark=panel(plum,[(117,45),(129,73),(152,98),(172,120),(193,135),(210,163),(202,194),(213,217),(237,238),(254,259),(258,274)],
        [(144,39),(163,61),(181,82),(202,105),(213,126),(229,154),(224,191),(222,206),(249,224),(264,246),(267,263)],1.17)
    copper_lane=panel(copper,[(173,172),(169,188),(168,208),(173,224),(188,238),(206,246),(223,258),(234,277),(232,291)],
        [(184,179),(181,193),(181,210),(191,224),(206,232),(222,243),(237,253),(248,273),(246,293)],1.10,False)
    Image.fromarray(np.concatenate([dark,copper_lane],axis=1)).save(dest/'bordeaux-wave.png',optimize=True)
