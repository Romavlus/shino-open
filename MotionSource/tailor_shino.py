"""Author the two outfits on the rest skeleton in Assets/Shino.vrm (NumPy and Pillow)."""
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np
from body_sections import body_collider, GarmentFit
from wardrobe_fabrics import uniforms, floral, knit, bare_skin

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'Assets'/'Wardrobe'
TAU = math.tau
sin, cos, exp = math.sin, math.cos, math.exp
steps = np.linspace


def clamp(value):
    return max(0.,min(1.,value))


def smooth(value):
    t=clamp(value)
    return t*t*(3-2*t)


def mix(a,b,t):
    return a*(1-t)+b*t


def linear(rgb, gain=1):
    c=np.asarray(rgb,dtype=float)/255
    return np.where(c<.04045,c/12.92,((c+.055)/1.055)**2.4)*gain


def weights(*items):
    merged=defaultdict(float)
    for index,value in items:
        if value>1e-5: merged[index]+=value
    top=sorted(merged.items(),key=lambda p:-p[1])[:4]
    total=sum(v for _,v in top)
    return [(i,v/total) for i,v in top]


class Cut:
    def __init__(self,doc,binary):
        self.doc,self.binary=doc,binary
        self.data=bytearray()
        self.views,self.accessors,self.pieces,self.guides=[],[],[],[]
        self.body=next(n for n in doc['nodes'] if n.get('name')=='Body')
        skin=doc['skins'][self.body['skin']]
        self.bones=[doc['nodes'][i]['name'] for i in skin['joints']]
        self.matrices=list(self.read(skin['inverseBindMatrices']))
        self.hip=self.bones.index('J_Bip_C_Hips')
        self.fit={}
    def read(self,i):
        a=self.doc['accessors'][i];view=self.doc['bufferViews'][a['bufferView']]
        width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
        dtype={5125:'<u4',5123:'<u2',5126:'<f4',5121:'u1'}[a['componentType']]
        return np.frombuffer(self.binary,dtype,count=a['count']*width,
               offset=view.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,width)
    def store(self,values,kind,dtype='<f4',target=None):
        data=np.ascontiguousarray(values,dtype=dtype)
        view=dict(byteOffset=len(self.data),byteLength=data.nbytes)
        if target:view['target']=target
        entry=dict(bufferView=len(self.views),componentType={'<f4':5126,'<u2':5123,'<u4':5125}[dtype],
                   type=kind,count=len(data))
        if kind=='VEC3':
            entry.update(min=data.min(0).tolist(),max=data.max(0).tolist())
        self.views.append(view);self.accessors.append(entry)
        self.data.extend(data.tobytes());self.data.extend(bytes(-len(self.data)%4))
        return len(self.accessors)-1
    def joint(self,short):
        return self.bones.index('J_Bip_'+short)
    def add_guide(self,name,parent):
        self.guides.append([name,parent])
        self.matrices.append(self.matrices[self.hip])
        self.bones.append(name)
        return len(self.bones)-1
    def torso(self,x,y):
        stops=[(1.043,self.hip),(1.10,self.joint('C_Spine')),(1.19,self.joint('C_Chest')),(1.278,self.joint('C_UpperChest'))]
        ws=[(stops[-1][1],1.)]
        for (a,i),(b,j) in zip(stops,stops[1:]):
            if y<=b:
                t=smooth((y-a)/(b-a));ws=[(i,1-t),(j,t)];break
        side='R' if x>0 else 'L'
        shoulder=.58*smooth((abs(x)-.059)/.060)*smooth((y-1.237)/.075)
        cap=.49*smooth((abs(x)-.092)/.048)*smooth((y-1.235)/.070)
        return weights(*[(j,w*(1-shoulder)*(1-cap)) for j,w in ws],
                       (self.joint(side+'_Shoulder'),shoulder*(1-cap)),(self.joint(side+'_UpperArm'),cap))
    def arm(self,x,y):
        a=abs(x);side='R' if x>0 else 'L'
        if a<.150:
            t=smooth((a-.064)/.083)
            return weights(*[(i,v*(1-t)) for i,v in self.torso(x,y)],(self.joint(side+'_UpperArm'),t))
        t=smooth((a-.284)/.084);hand=.16*smooth((a-.511)/.032)
        return weights((self.joint(side+'_UpperArm'),1-t),(self.joint(side+'_LowerArm'),t*(1-hand)),(self.joint(side+'_Hand'),t*hand))
    def skin(self):
        primitive=next(p for p in self.doc['meshes'][self.body['mesh']]['primitives'] if p['material']==9)
        attrs=primitive['attributes'];pos=self.read(attrs['POSITION']);uv=self.read(attrs['TEXCOORD_0'])
        triangles=np.concatenate([self.read(p['indices']).reshape(-1,3) for p in self.doc['meshes'][self.body['mesh']]['primitives'] if p['material']==9])
        bare_skin(self.doc,self.binary,uv,triangles,OUT)
        self.source_joints=self.read(attrs['JOINTS_0'])
        self.source_weights=self.read(attrs['WEIGHTS_0'])
        # The old shirt collar covered a very sharp ridge. Relax only the front
        # clavicles on welded vertices, then smooth their normals across UV seams.
        normals=self.read(attrs['NORMAL']).copy()
        welded,remap=np.unique(np.round(pos,6),axis=0,return_inverse=True)
        faces=remap[triangles]
        sides=np.vstack((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]))
        pairs=np.unique(np.sort(sides,axis=1),axis=0)
        first,last=np.r_[pairs[:,0],pairs[:,1]],np.r_[pairs[:,1],pairs[:,0]]
        degree=np.maximum(1,np.bincount(first,minlength=len(welded)))
        x,y,z=welded.T.copy()
        amount=np.exp(-((y-1.318)/.024)**4)*np.clip((.111-abs(x))/.030,0,1)*np.clip((.011-z)/.026,0,1)
        for _ in range(10):
            total=np.zeros_like(welded);np.add.at(total,first,welded[last])
            welded+=(total/degree[:,None]-welded)*(.46*amount[:,None])
        change=amount[remap]>.0001
        fitted=pos.copy();fitted[change]=welded[remap[change]]
        sums=np.zeros_like(welded);xyz=welded[faces]
        normal=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0])
        for k in range(3):np.add.at(sums,faces[:,k],normal)
        sums/=np.maximum(1e-12,np.linalg.norm(sums,axis=1))[:,None]
        normal=sums[remap[change]]
        blend=amount[remap[change],None]
        normals[change]=normals[change]*(1-blend)+normal*blend
        normals[change]/=np.maximum(1e-12,np.linalg.norm(normals[change],axis=1))[:,None]
        self.skin_attributes=dict(POSITION=self.store(fitted,'VEC3',target=34962),NORMAL=self.store(normals,'VEC3',target=34962))
        self.surface=GarmentFit(self,fitted,normals,triangles)
        return pos,triangles
    def finish(self):
        bind=self.store(self.matrices,'MAT4')
        spec=dict(bytes=len(self.data),views=self.views,accessors=self.accessors,pieces=self.pieces,
                  guides=self.guides,fit=self.fit,skinAttributes=self.skin_attributes,bind=bind)
        (OUT/'cardigan-cut.bin').write_bytes(self.data)
        (OUT/'cardigan-cut.json').write_text(json.dumps(spec,separators=(',',':')))


class Piece:
    def __init__(self,cut,name,roughness,texture=None,metal=0):
        self.cut=cut;self.info=dict(name=name,roughness=roughness)
        if texture:self.info['texture']=texture
        if metal:self.info['metal']=metal
        self.pos=[];self.weights=[];self.uv=[];self.colors=[];self.faces=[];self.seams=[]
    def grid(self,us,vs,vertex,reverse=False,loop=False):
        start=len(self.pos);w=len(us)
        for row,v in enumerate(vs):
            for col,u in enumerate(us):
                p,joints,uv,color=vertex(u,v)
                self.pos.append(p);self.weights.append(joints);self.uv.append(uv);self.colors.append(np.broadcast_to(color,(3,)))
                if col and row:
                    d=start+row*w+col;b=d-w;c=d-1;a=b-1
                    self.faces.extend([(a,c,b),(b,c,d)] if reverse else [(a,b,c),(b,d,c)])
            if loop:self.seams.append((start+row*w,start+(row+1)*w-1))
    def save(self):
        p=np.array(self.pos);f=np.asarray(self.faces)
        self.cut.surface.tailor(p,self.weights,self.info['name'])
        cross=np.cross(p[f[:,1]]-p[f[:,0]],p[f[:,2]]-p[f[:,0]])
        normals=np.zeros_like(p)
        for i in range(3):np.add.at(normals,f[:,i],cross)
        for i,j in self.seams:normals[i]=normals[j]=normals[i]+normals[j]
        mag=np.linalg.norm(normals,axis=1);normals[mag==0]=(0,1,0);normals/=np.maximum(1e-12,np.linalg.norm(normals,axis=1))[:,None]
        joints=np.zeros((len(p),4),dtype='<u2'); ws=np.zeros((len(p),4),dtype='<f4')
        for row,influences in enumerate(self.weights):
            for col,(index,weight) in enumerate(influences):joints[row,col]=index;ws[row,col]=weight
        assert np.allclose(ws.sum(1),1)
        store=self.cut.store
        self.info['attributes']=dict(POSITION=store(p,'VEC3',target=34962), NORMAL=store(normals,'VEC3',target=34962),
                                     TEXCOORD_0=store(self.uv,'VEC2',target=34962), COLOR_0=store(self.colors,'VEC3',target=34962),
                                     JOINTS_0=store(joints,'VEC4','<u2',34962),WEIGHTS_0=store(ws,'VEC4',target=34962))
        self.info['indices']=store(f.ravel(),'SCALAR','<u2' if len(p)<65536 else '<u4',34963)
        self.cut.pieces.append(self.info)


class Dress:
    def __init__(self,cut,body,triangles):
        self.cut=cut
        self.flowers=Piece(cut,'Shino Botanical Crepe CLOTH',.86,'cardigan-floral.png')
        self.trim=Piece(cut,'Shino Bias Binding and Sash CLOTH',.73)
        self.wool=Piece(cut,'Shino Oatmeal Knit CLOTH',.97,'cardigan-knit.png')
        self.buttons=Piece(cut,'Shino Shell Buttons',.43)
        self.leather=Piece(cut,'Shino Ankle Boot Leather',.64)
        self.levels=[1.038,.975,.908,.825,.740,.650,.563,.478,.402,.348]
        self.sectors=20;self.guides=[]
        for r in range(len(self.levels)):
            self.guides.append([cut.add_guide(f'DressGuide_{r}_{i}','J_Bip_C_Hips') for i in range(self.sectors)])
        shell=[]
        for y in self.levels:
            shell.append([[round(float(x),5) for x in self.skirt_point(TAU*i/self.sectors,y)[[0,2]]] for i in range(self.sectors)])
        cut.fit=dict(levels=self.levels,sectors=self.sectors,shell=shell,body=body_collider(cut,body,triangles),
                     origin=(-cut.matrices[cut.hip][12:15]).tolist(),gaitScale=1,liftScale=1,sleevePadding=.014,ties=[])
    def skirt_point(self,a,y):
        rows=[(.339,.224,.127,.009),(.49,.210,.122,.006),(.66,.192,.116,.003),(.81,.172,.110,-.002),
              (.91,.157,.108,-.010),(.975,.137,.103,-.020),(1.043,.113,.089,-.035)]
        rx,rz,cz=[np.interp(y,[p[0] for p in rows],[p[j] for p in rows]) for j in (1,2,3)]
        f=clamp((1.037-y)/.683)
        fold=(.010*sin(10*a+.54+.63*f)+.006*sin(7*a-1.3*f)+.004*cos(4*a+.9*f))*(.11+.89*f**.82)
        fan=.0036*sin(58*f+3*a)*exp(-((f-.13)/.17)**2)*exp(-((a%TAU-5.01)/.82)**2)
        return np.array([(rx+fold+fan)*sin(a),y,cz-(rz+fold+fan)*cos(a)])
    def drape(self,a,y):
        if y>=self.levels[0]:return [(self.cut.hip,1)]
        place=(a%TAU)*self.sectors/TAU;j=int(place);u=place-j
        r=next((i for i in range(len(self.levels)-1) if y>=self.levels[i+1]),len(self.levels)-2)
        t=clamp((self.levels[r]-y)/(self.levels[r]-self.levels[r+1]))
        grid=self.guides;k=(j+1)%self.sectors
        return weights((grid[r][j],(1-t)*(1-u)),(grid[r][k],(1-t)*u),(grid[r+1][j],t*(1-u)),(grid[r+1][k],t*u))
    def skirt(self):
        def point(u,t):
            # The overleaf runs diagonally down from her left hip.
            start=-.86+.80*t-.14*sin(math.pi*t);a=start+u*(TAU+1.24)
            hem=.35+.009*sin(5*a+.65)+.005*cos(8*a)+.022*exp(-(u/.065)**2)
            y=mix(1.046,hem,t)
            p=self.skirt_point(a,y)
            depth=(.0012+.0068*(1-smooth(u/.67))+.0025*exp(-(u/.022)**2))*(.26+.74*smooth(t/.15))
            p+=np.array([sin(a)*depth,0,-cos(a)*depth])
            return a,p
        def fabric(u,t):
            a,p=point(u,t);return p,self.drape(a,p[1]),(u*3.5,t*2.06),1-.13*exp(-(u/.009)**2)-.075*exp(-(t/.026)**2)
        vs=steps(0,1,42)
        self.flowers.grid(steps(0,1,117),vs,fabric)
        def facing(w,t):
            a,p=point(0,t);p+=np.array([cos(a)*.004*w,-.0015*w,sin(a)*.004*w])
            return p,self.drape(a,p[1]),(w,t),linear([55,58,72],.85+.18*sin(math.pi*w))
        self.trim.grid(steps(-1,1,4),vs,facing)
        def inside(u,v):
            a,p=point(u,1);p+=np.array([-sin(a)*.0022*v,.006*v,cos(a)*.0022*v])
            return p,self.drape(a,p[1]),(u,v),linear([39,40,54])
        self.trim.grid(steps(0,1,101),[0,1],inside)
    def bodice(self):
        rows=[(1.018,.108,-.122,.053),(1.06,.107,-.123,.040),(1.11,.108,-.125,.042),
              (1.165,.116,-.132,.052),(1.205,.126,-.139,.066),(1.242,.134,-.111,.069),
              (1.283,.141,-.086,.073),(1.309,.140,-.068,.073),(1.331,.099,-.049,.060),(1.346,.058,-.024,.048)]
        def point(a,t):
            s,c=sin(a),cos(a)
            top=1.337-.105*max(0,c)**2*max(0,1-abs(s)/.68)-.008*max(0,-c)
            top-=.062*smooth((abs(s)-.68)/.32)
            y=mix(1.018,top,t)
            rx,front,back=[np.interp(y,[r[0] for r in rows],[r[i] for r in rows]) for i in (1,2,3)]
            frontmin=(front+back)/2-math.copysign(abs(c)**.82,c)*(back-front)/2
            x=rx*s
            seam=x+.096*smooth((1.238-y)/.205)
            relief=.0028*exp(-(seam/.008)**2)*max(0,c)
            return np.array([x,y,frontmin-relief])
        def vertex(a,t):
            p=point(a,t)
            return p,self.cut.torso(*p[:2]),(a/TAU*2.06,(1.337-p[1])*2.9),.97
        loop=steps(0,TAU,89)
        self.flowers.grid(loop,steps(0,1,33),vertex,reverse=True,loop=True)
        def neck(a,t):
            p=point(a,1-.022*t);p+=[.0016*sin(a),.0007,-.0019*cos(a)]
            return p,self.cut.torso(*p[:2]),(a,t),linear([48,50,67],.91+.15*sin(t*math.pi))
        self.trim.grid(loop,steps(0,1,4),neck,loop=True)
        def bound(u,t):
            y=mix(1.233,1.038,t);x=-.097*t**.91+.0028*u
            rx,front,back=[np.interp(y,[r[0] for r in rows],[r[i] for r in rows]) for i in (1,2,3)]
            a=math.asin(np.clip(x/rx,-.999,.999));z=(front+back)/2-cos(a)**.82*(back-front)/2-.003
            return [x,y,z],self.cut.torso(x,y),(u,t),linear([54,55,69],1+.09*cos(u*math.pi))
        self.trim.grid([-1,0,1],steps(0,1,41),bound)
    def sash(self):
        def belt(a,t):
            y=1.016+.035*t-.004*max(0,cos(a+.79))
            p=self.skirt_point(a,min(y,1.038));p[1]=y
            radius=.006+.0017*sin(math.pi*t)+.0013*sin(3*math.pi*t+.8*sin(a))
            p+=[sin(a)*radius,0,-cos(a)*radius]
            return p,[(self.cut.hip,1)],(a,t),linear([47,51,69],.89+.14*sin(t*math.pi))
        self.trim.grid(steps(0,TAU,83),steps(0,1,7),belt,reverse=True,loop=True)
        # Small folded loops stand off the waistband, with two separately weighted tails below.
        center=self.skirt_point(-.77,1.032)+[-.005,0,-.012]
        def bow(a,t):
            p=center+np.array([.013*sin(a)*sin(t),.014*cos(t),.009*cos(a)*sin(t)])
            return p,[(self.cut.hip,1)],(a,t),linear([49,50,65],1+.19*sin(a))
        self.trim.grid(steps(0,TAU,19),steps(.015,math.pi-.015,12),bow,loop=True)
        for sign in (-1,1):
            def loop(a,t):
                p=center+np.array([sign*(.003+.043*sin(math.pi*t)),.002+.021*sin(math.pi*t)+.013*sin(TAU*t),
                                   -.002-.016*sin(math.pi*t)+.006*sin(TAU*t)])
                p+=[0,cos(a)*(.002+.005*sin(math.pi*t)),sin(a)*.004]
                return p,[(self.cut.hip,1)],(a,t),linear([54,57,74],.93+.13*cos(a))
            self.trim.grid(steps(0,TAU,17),steps(0,1,22),loop,loop=True)
        for j,(length,lean) in enumerate([(.121,-.24),(.191,.21)]):
            nodes=[self.cut.hip]
            for k in range(1,4):
                t=k/3;a=-.77+lean*t;y=1.029-length*t
                r=min(range(len(self.levels)),key=lambda i:abs(self.levels[i]-y))
                sector=round((a%TAU)*self.sectors/TAU)%self.sectors
                name=f'DressTie_{j}_{k}'
                nodes.append(self.cut.add_guide(name,f'DressGuide_{r}_{sector}'))
                self.cut.fit['ties'].append(dict(name=name,length=t,side=j*2-1))
            def tail(u,t):
                a=-.77+lean*t+.042*sin(6*t+j)*t+u*(.055+.019*t)
                y=1.03-length*t+.008*u*t**7
                p=self.skirt_point(a,y);radius=.015+.007*sin(2.4*math.pi*t+j)*t+.002*cos(u*math.pi)
                p+=[radius*sin(a),0,-radius*cos(a)]
                f=t*3;i=min(2,int(f));f-=i
                return p,weights((nodes[i],1-f),(nodes[i+1],f)),(.17+j*.28+u*.033,.12+t*length*3),.90+.12*cos(u*math.pi)
            self.flowers.grid(steps(-1,1,7),steps(0,1,25),tail)
    def cardigan(self):
        # A cropped, open-front shell narrows from the shoulder crown into the back neck.
        rings=[(1.060,.128,-.132,.073),(1.066,.131,-.136,.076),(1.079,.133,-.138,.078),
               (1.092,.140,-.140,.080),(1.115,.141,-.142,.077),(1.159,.142,-.146,.081),
               (1.202,.148,-.154,.085),(1.236,.157,-.136,.085),(1.273,.165,-.108,.085),
               (1.302,.162,-.090,.084),(1.319,.145,-.079,.083),(1.333,.117,-.066,.076),
               (1.339,.089,-.051,.065),(1.337,.060,-.034,.059)]
        def point(u,v):
            i=min(len(rings)-2,int(v));t=v-i
            y,w,front,back=np.asarray(rings[i])*(1-t)+np.asarray(rings[i+1])*t
            opening=.50+.105*sin(min(v/12,1)*math.pi)+.50*smooth((v-9)/4)
            a=opening+(TAU-2*opening)*u;s,c=sin(a),cos(a)
            # The front panels drop a little below the back ribbing.
            y+=.007*(1-c)*.5-.008*exp(-((abs(s)-.50)/.25)**2)*max(0,c)*exp(-(v/3)**2)-.010*max(0,c)*smooth((v-9)/4)
            fold=.0027*sin(9*a+v*.18)*sin(math.pi*min(1,v/13))+.0014*cos(5*a+v*.31)
            z=(front+back)*.5-math.copysign(abs(c)**.82,c)*(back-front)*.5
            return np.array([(w+fold)*s,y,z-fold*c]),a
        def render(u,v):
            p,a=point(u,v)
            rib=smooth((2.75-v)/1.0)
            p+=[.0009*sin(a)*cos(a*108)*rib,0,-.0009*cos(a)*cos(a*108)*rib]
            shade=.97+.035*cos(a*108)*rib-.07*exp(-((v-2.15)/.29)**2)-.08*exp(-((min(u,1-u)-.042)/.012)**2)
            return p,self.cut.torso(*p[:2]),(a/TAU*8.,(p[1]-1.)*8.),shade
        self.wool.grid(steps(0,1,105),steps(0,13,53),render,reverse=True)
        # Plackets are separate turned strips: four shell buttons on one edge,
        # matching small bound buttonholes on the other.
        for side in (-1,1):
            def band(w,v):
                u=.045*w if side>0 else 1-.045*w
                p,a=point(u,v)
                rad=.0028+.0013*sin(math.pi*w)
                p+=[sin(a)*rad,0,-cos(a)*rad]
                return p,self.cut.torso(*p[:2]),(w*.32,(p[1]-1)*9.1),.97-.045*cos(w*TAU*5)
            self.wool.grid(steps(0,1,11),steps(0,13,54),band,reverse=side>0)
            for v in [1.55,3.95,5.63,8.1]:
                p,a=point(.020 if side>0 else .980,v)
                normal=np.array([sin(a),0,-cos(a)]);along=np.array([cos(a),0,sin(a)])
                up=np.array([0.,1.,0.]);p+=normal*.0061
                if side<0:
                    def button(az,r):
                        rad,z,shade=np.asarray([(0,.0028,.85),(.0048,.0028,.94),(.0061,.0041,1.10),
                                              (.007,.003,1.02),(.0072,.0008,.85),(.0068,-.0001,.80)])[r]
                        pos=p+(along*cos(az)+up*sin(az))*rad+normal*z
                        return pos,self.cut.torso(*pos[:2]),(0,0),linear([186,159,126],shade)
                    self.buttons.grid(steps(0,TAU,19),range(6),button,loop=True)
                    for h in (-1,1):
                        def hole(az,r):
                            pos=p+along*(.00165*h+.00074*r*cos(az))+up*.00115*r*sin(az)+normal*.0029
                            return pos,self.cut.torso(*pos[:2]),(0,0),linear([95,78,68])
                        self.buttons.grid(steps(0,TAU,9),[0,1],hole,loop=True)
                else:
                    def slit(t,w):
                        pos=p+along*(w*.00095*sin(math.pi*t))+up*((t-.5)*.012)
                        return pos,self.cut.torso(*pos[:2]),(0,0),linear([138,119,100])
                    self.buttons.grid(steps(0,1,8),[-1,1],slit)
        # Sleeve width is bound to the native elbow and tapered into a ribbed wrist.
        sleeve=[(.060,.026,.030,1.308,.008),(.088,.045,.047,1.307,.007),
                (.120,.055,.060,1.304,.006),(.153,.059,.064,1.300,.006),
                (.196,.054,.057,1.298,.005),(.245,.052,.054,1.295,.004),
                (.295,.047,.051,1.294,.004),(.329,.044,.047,1.292,.003),
                (.365,.047,.048,1.290,.000),(.404,.045,.048,1.288,-.002),
                (.446,.046,.047,1.288,-.005),(.474,.046,.045,1.288,-.008),
                (.487,.041,.042,1.288,-.009),(.496,.030,.033,1.289,-.010),
                (.501,.029,.032,1.289,-.010),(.526,.027,.030,1.289,-.013),
                (.536,.027,.029,1.290,-.014),(.537,.022,.024,1.290,-.014),
                (.534,.016,.017,1.290,-.014),(.528,.013,.015,1.290,-.014)]
        for sign in (-1,1):
            def arm(a,v):
                i=min(len(sleeve)-2,int(v));f=v-i
                x,ry,rz,cy,cz=np.asarray(sleeve[i])*(1-f)+np.asarray(sleeve[i+1])*f
                wrist=smooth((v-13)/.9)
                folds=(.0028*sin(6*a+v*.37)+.0018*sin(4*a-v*.67))*(.3+.70*smooth((v-4)/7))*(1-wrist)
                folds+=.0021*cos(a*9+.45*v)*exp(-((v-12.0)/1.55)**2)+.0007*cos(a*33)*wrist
                p=(sign*x,cy+(ry+folds)*cos(a),cz+(rz+folds)*sin(a))
                gain=1-.105*exp(-((v-13.6)/.33)**2)-.075*exp(-((v-3.62)/.22)**2)+.043*cos(6*a+.41*v)*(1-wrist)+.042*cos(a*33)*wrist
                return p,self.cut.arm(p[0],cy),(a/TAU*2.2,x*8.5),gain
            self.wool.grid(steps(0,TAU,57),steps(0,len(sleeve)-1,72),arm,reverse=sign<0,loop=True)
    def boots(self):
        # Rounded almond toe and a separate block heel, with an elastic side gore.
        rows=[(.003,.038,-.137,.080),(.009,.040,-.137,.081),(.019,.041,-.137,.081),
              (.023,.042,-.135,.081),(.030,.041,-.133,.080),(.041,.041,-.125,.078),
              (.051,.040,-.112,.076),(.063,.038,-.090,.073),(.079,.035,-.061,.072),
              (.101,.032,-.030,.074),(.132,.032,-.010,.075),(.164,.033,-.006,.077),
              (.188,.035,-.006,.079),(.195,.035,-.006,.079),(.197,.029,-.001,.072)]
        for sign,side in [(-1,'L'),(1,'R')]:
            foot=self.cut.joint(side+'_Foot');toe=self.cut.joint(side+'_ToeBase');leg=self.cut.joint(side+'_LowerLeg')
            def foot_point(a,v):
                i=min(len(rows)-2,int(v));f=v-i
                h,w,front,back=np.asarray(rows[i])*(1-f)+np.asarray(rows[i+1])*f
                c,s=cos(a),sin(a)
                z=(front+back)*.5-math.copysign(abs(c)**.81,c)*(back-front)*.5
                heel=.015*smooth((z+.072)/.06)*(1-smooth(v/5))
                width=w*(1-.14*smooth((z+.018)/.07))
                center=.047+.002*cos(a)*smooth((.11-h)/.08)
                p=np.array([sign*(center+width*math.copysign(abs(s)**.76,s)),h+heel,z])
                toe_weight=.66*smooth((-.071-z)/.051)*(1-smooth((h-.030)/.045))
                leg_weight=.985*smooth((h-.077)/.085)
                return p,weights((foot,1-toe_weight-leg_weight),(toe,toe_weight),(leg,leg_weight))
            def boot(a,v):
                p,ws=foot_point(a,v)
                base=[53,43,43] if v>3.35 else [44,37,37]
                gain=.97+.09*cos(a+.7)*sin(min(1,v/11)*math.pi)+.18*exp(-((v-3.07)/.28)**2)-.14*exp(-((v-2.35)/.36)**2)
                if v>13.25:gain-=.22*smooth((v-13.25)/.75)
                return p,ws,(a,v),linear(base,gain)
            self.leather.grid(steps(0,TAU,57),steps(0,14,43),boot,reverse=sign>0,loop=True)
            def heel(a,t):
                cx=sign*.047;cz=.052
                p=[cx+.027*math.copysign(abs(sin(a))**.53,sin(a)),.0008+t*.031,
                   cz-.028*math.copysign(abs(cos(a))**.53,cos(a))]
                return p,[(foot,1)],(a,t),linear([45,38,38],.83+.11*t)
            self.leather.grid(steps(0,TAU,33),[0,.12,.86,1],heel,reverse=True,loop=True)
            def sole(a,t):
                p,ws=foot_point(a,0)
                p[0]=mix(sign*.047,p[0],t);p[2]=mix(-.014,p[2],t)
                return p,ws,(a,t),linear([43,37,36])
            self.leather.grid(steps(0,TAU,49),[0,.85,1],sole,reverse=sign<0,loop=True)
            def gusset(u,t):
                a=math.pi*.5+u*(.23+.22*t)
                p,ws=foot_point(a,9.1+3.85*t)
                p[0]+=sign*(.00085+.0004*cos(u*math.pi*15))
                return p,ws,(u,t),linear([47,40,43],1+.12*cos(u*math.pi*15))
            self.leather.grid(steps(-1,1,29),steps(0,1,14),gusset,reverse=sign>0)
    def save(self):
        self.skirt();self.bodice();self.sash();self.cardigan();self.boots()
        for piece in (self.flowers,self.trim,self.wool,self.buttons,self.leather):piece.save()


def main():
    OUT.mkdir(exist_ok=True)
    source=(ROOT/'Assets'/'Shino.vrm').read_bytes()
    size=struct.unpack_from('<I',source,12)[0];doc=json.loads(source[20:20+size]);binary=source[28+size:]
    uniforms(doc,binary,OUT);floral(OUT/'cardigan-floral.png');knit(OUT/'cardigan-knit.png')
    cut=Cut(doc,binary);body,triangles=cut.skin()
    Dress(cut,body,triangles).save();cut.finish()
    print(f"{len(cut.pieces)} materials, {len(cut.guides)} skirt and ribbon controls, {len(cut.data):,} bytes of tailoring")


if __name__=='__main__':main()
