"""Draft the rider, sailor and wrap looks at full scale on Shino's original rest skeleton."""
import argparse
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from tailor_shino import (ROOT, OUT, TAU, Cut, Dress, Piece, body_collider, clamp, cos, sin, exp,
                          json, linear, mix, smooth, steps, struct, weights)
from wardrobe_fabrics import image_from_model
from atelier_hair import hair_style, spring_chain, chain_weights
from coral_hair import make_waves
from coral_maps import fabric_maps, strand_maps, painted_hair
from coral_tailoring import make_outfit

PI=math.pi


def profile(rows,value):
    i=max(0,min(len(rows)-2,int(np.searchsorted(rows[:,0],value,side='right')-1)))
    return mix(rows[i,1:],rows[i+1,1:],clamp((value-rows[i,0])/(rows[i+1,0]-rows[i,0])))


def unit(v):
    return v/max(1.e-9,np.linalg.norm(v))


def cord(piece,path,width,color,weight,count=25,sides=7):
    points=np.array([path(t) for t in steps(0,1,count)])
    tangent=np.array([unit(p) for p in np.gradient(points,axis=0)])
    axis=np.eye(3)[np.argmin(abs(tangent[0]))]
    normal=[]
    for t in tangent:
        axis=unit(axis-np.dot(t,axis)*t)
        normal.append(axis)
    def tube(a,i):
        q=points[i]+width*(normal[i]*cos(a)+np.cross(normal[i],tangent[i])*sin(a))
        return q,weight(q),(a/TAU,i/(count-1)),color
    piece.grid(steps(0,TAU,sides+1),range(count),tube,loop=True)


def disc(piece,p,radius,color,weight,n=(0,0,-1)):
    n=unit(np.asarray(n,dtype=float));across=unit(np.cross([0,1,0],n));up=np.cross(n,across)
    def vertex(a,v):
        r,d,g=((.02,.26,1.22),(.66,.31,1.10),(.89,.37,1.24),(1,.12,.90),(.95,-.05,.76))[v]
        q=p+radius*((across*cos(a)+up*sin(a))*r+n*d)
        return q,weight(q),(a/TAU,v/4),color*g
    piece.grid(steps(0,TAU,15),range(5),vertex,loop=True)


def skin_atlas(cut):
    # The original knee socks include an inked top edge and a knitted normal map.
    # Repaint only the UV islands belonging to bare calves, fading into the knees.
    source=np.array(Image.open(OUT/'cardigan-skin.png').convert('RGBA'))
    normal=np.array(image_from_model(cut.doc,cut.binary,'F00_001_01_Body_00_nml'))
    h,w=source.shape[:2];mask=Image.new('L',(w,h));pen=ImageDraw.Draw(mask)
    for part in cut.doc['meshes'][cut.body['mesh']]['primitives']:
        if part['material']!=9:continue
        attrs=part['attributes'];pos=cut.read(attrs['POSITION']);uv=cut.read(attrs['TEXCOORD_0'])
        for tri in cut.read(part['indices']).reshape(-1,3):
            y=pos[tri,1].mean()
            if y<.665:
                pen.polygon([tuple(v) for v in uv[tri]*[w,h]],fill=round(255*smooth((.665-y)/.096)))
    mask=mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(3))
    blend=np.asarray(mask,dtype=float)[:,:,None]/255
    tone=np.array([246,215,199]);source[:,:,:3]=np.uint8(source[:,:,:3]*(1-blend)+tone*blend)
    Image.fromarray(source).save(OUT/'atelier-skin.png')
    small=np.asarray(mask.resize((normal.shape[1],normal.shape[0]),Image.Resampling.BILINEAR))[:,:,None]/255
    normal[:,:,:3]=normal[:,:,:3]*(1-small)+np.array([128,128,255])*small
    Image.fromarray(normal).save(OUT/'atelier-skin-n.png')


def textiles(doc,binary):
    yy,xx=np.mgrid[:256,:256];rng=np.random.default_rng(6542)
    for name in ['ribs','leather','silk','serge','locks']:
        a,b=TAU*xx/256,TAU*yy/256
        if name=='ribs':h=.56*np.cos(16*a)+.18*np.cos(32*a)+.15*np.cos(32*b+2*np.sin(16*a))
        elif name=='leather':h=.32*rng.normal(size=a.shape)+.11*np.sin(11*a+4*np.cos(7*b))
        elif name=='silk':h=.32*np.sin(43*a+25*b)+.11*np.sin(40*b)
        elif name=='serge':h=.45*np.cos(37*a+37*b)*(.67+.33*np.cos(40*a))
        else:h=.46*np.cos(22*a+.9*np.sin(b)+.38*np.sin(3*b+4*a))+.27*np.sin(38*a+.7*np.sin(2*b))+.14*np.cos(60*a)
        base={'ribs':235,'leather':242,'silk':243,'serge':244,'locks':233}[name]
        shade=np.clip(base+h*({'ribs':19,'leather':9,'silk':7,'serge':8,'locks':25}[name]),0,255).astype('uint8')
        if name=='locks':
            glint=np.exp(-((np.sin((b-1.2-.21*np.cos(a))*.5))/.22)**2)
            glint+=.48*np.exp(-((np.sin((b-3.9+.17*np.sin(a))*.5))/.29)**2)
            ribbons=np.cos(3*a+.44*np.sin(1.9*b))+.4*np.sin(7*a+.53*np.cos(b))
            shade=np.uint8(np.clip(218+17*h+9*ribbons+23*glint,0,255))
        Image.fromarray(shade).save(OUT/('atelier-'+name+'.png'))
        dx=(np.roll(h,-1,1)-np.roll(h,1,1))*.36;dy=(np.roll(h,-1,0)-np.roll(h,1,0))*.36
        normal=np.stack((-dx,dy,np.ones_like(dx)),-1);normal/=np.linalg.norm(normal,axis=-1)[:,:,None]
        Image.fromarray(np.uint8((normal*.5+.5)*255)).save(OUT/('atelier-'+name+'-n.png'))
    skin_atlas(Cut(doc,binary))
    tex=np.array(image_from_model(doc,binary,'F00_000_EyeIris_00'));lum=tex[:,:,:3]@[.299,.587,.114]
    for name,colors in [('marine',[(4,13,27),(10,37,51),(15,84,98),(25,153,166),(95,218,221),(247,255,242)]),
                        ('bordeaux',[(17,7,19),(48,21,32),(103,50,55),(160,91,69),(210,151,111),(255,239,204)])]:
        for c in range(3):tex[:,:,c]=np.interp(lum,[0,25,58,105,177,255],np.array(colors)[:,c])
        Image.fromarray(tex).save(OUT/(name+'-iris.png'))
    shoe=np.array(image_from_model(doc,binary,'F00_001_Shoes_01'));lum=shoe[:,:,:3]@[.299,.587,.114]
    shoe[:,:,:3]=np.clip(np.array([33,91,94])*np.clip(((lum+3)/35)**.72,.24,2.1)[:,:,None],0,255)
    Image.fromarray(shoe).save(OUT/'marine-loafers.png')


TORSO=np.array([(1.005,.119,-.118,.061),(1.032,.115,-.123,.056),(1.065,.108,-.125,.047),
 (1.101,.104,-.127,.045),(1.143,.108,-.131,.047),(1.181,.122,-.143,.060),
 (1.205,.128,-.146,.064),(1.242,.137,-.120,.073),(1.272,.151,-.097,.076),
 (1.300,.151,-.082,.076),(1.315,.138,-.065,.071),(1.333,.104,-.048,.065),(1.349,.049,-.030,.053)])


class Look:
    def __init__(self,cut,kind):
        self.cut,self.kind=cut,kind
        self.pieces=[]
    def cloth(self,name,rgb,rough,texture=None,metal=0,*,ease=None,sheen=None):
        p=Piece(self.cut,name,rough,'atelier-'+texture+'.png' if texture else None,metal)
        if texture:p.info.update(normal='atelier-'+texture+'-n.png',normalScale=.35 if texture=='leather' else .43)
        if sheen:p.info['sheen']=sheen
        p.color=linear(rgb);self.pieces.append((p,ease))
        return p
    def torso_weight(self,q):return self.cut.torso(q[0],q[1])
    def shell(self,a,y,ease=0):
        w,front,back=profile(TORSO,y);c,s=cos(a),sin(a)
        relief=.0021*sin(6*a+13*y)+.0012*sin(12*a-20*y)
        return np.array([(w+ease+relief)*s,y,(front+back)/2-math.copysign(abs(c)**.86,c)*(back-front)/2-(ease+relief)*c])
    def upper(self,p,bottom,neck,ease=0,opening=None):
        def surface(u,t):
            gap=opening(t) if opening else 0
            a=gap+(TAU-2*gap)*u
            y=mix(bottom,neck(a),t)
            q=self.shell(a,y,ease)
            rip=.0015*sin(43*y+3*a)*sin(PI*t)**2
            q+=[rip*sin(a),0,-rip*cos(a)]
            return q,a
        def point(u,t):
            q,a=surface(u,t)
            return q,self.torso_weight(q),(a/TAU*5,(1.37-q[1])*4.8),p.color*(.965+.035*cos(7*a+10*t))
        p.grid(steps(0,1,79),steps(0,1,31),point,reverse=True,loop=opening is None)
        return surface
    def front(self,x,y,ease):
        w=profile(TORSO,y)[0]+ease
        a=math.asin(np.clip(x/w,-.999,.999))
        q=self.shell(a,y,ease);q[0]=x
        return q
    def sleeves(self,p,end,style):
        rows=np.array([(.066,.030,.035,1.306,.008),(.098,.049,.056,1.304,.006),
          (.139,.060,.065,1.299,.006),(.182,.054,.058,1.298,.005),(.234,.050,.053,1.294,.005),
          (.294,.045,.049,1.292,.004),(.332,.042,.046,1.290,.003),(.378,.039,.044,1.289,.000),
          (.428,.036,.041,1.288,-.004),(.472,.033,.037,1.288,-.007),(.501,.029,.033,1.289,-.010),
          (.536,.025,.029,1.290,-.014)])
        for side in (-1,1):
            def sleeve(a,t):
                x=mix(.066,end,t);ry,rz,cy,cz=profile(rows,x)
                if style=='bishop':
                    puff=.018*smooth((x-.22)/.23)*(1-smooth((x-.467)/.031))
                    rib=smooth((x-.491)/.008)
                else:puff=.0025;rib=smooth((x-.47)/.01)
                wrinkle=(.0026*cos(5*a+13*x)+.0017*sin(8*a-21*x))*sin(t*PI)**.67
                if style=='bishop':wrinkle+=.002*cos(9*a+18*x)*exp(-((x-.47)/.035)**2)
                q=(side*x,cy+(ry+puff+wrinkle)*cos(a)-puff*.23,cz+(rz+puff+wrinkle)*sin(a))
                gain=1+.052*cos(5*a+13*x)-.08*exp(-((x-(end-(.038 if style=='bishop' else .024)))/.0035)**2)
                return q,self.cut.arm(q[0],q[1]),(a/TAU*(1+rib*.6),(x-.06)*4.8),p.color*gain
            p.grid(steps(0,TAU,41),steps(0,1,45),sleeve,reverse=side<0,loop=True)
    def trim(self,p,surface,y_steps=(0,1),width=.004):
        def vertex(u,t):
            q,a=surface(u,mix(*y_steps,t))
            q=q+np.array([sin(a)*.0015,0,-cos(a)*.0015])
            return q,self.torso_weight(q),(u*5,t*.2),p.color*(.88+.11*sin(t*PI))
        p.grid(steps(0,1,83),steps(0,1,4),vertex,reverse=True,loop=True)
    def boots(self,p,rider=False):
        maker=Dress.__new__(Dress);maker.cut=self.cut;maker.leather=p;maker.boots()
        old=np.array(p.colors);p.colors=list(p.color*np.clip(np.mean(old,1)/.030,.42,1.3)[:,None])
        if rider:details=self.cloth('Boot welts, tongues and lacing',(53,49,54),.64,ease=False)
        metal=self.cloth('Brushed boot eyelets' if rider else 'Antique brass ankle zips',
                         (161,151,156) if rider else (193,152,98),.34,metal=.52,ease=False)
        for side,S in [(-1,'L'),(1,'R')]:
            foot=self.cut.joint(S+'_Foot');leg=self.cut.joint(S+'_LowerLeg')
            def w(q):
                t=smooth((q[1]-.070)/.088);return weights((foot,1-t),(leg,t))
            if rider:
                def shaft(a,t):
                    y=mix(.170,.265,t);r=.034+.006*t
                    q=np.array([side*.047+r*sin(a),y,.034-(r+.006)*cos(a)])
                    return q,w(q),(a/TAU,t),p.color*(.85+.15*cos(a)-.19*exp(-((t-.93)/.032)**2))
                p.grid(steps(0,TAU,37),steps(0,1,13),shaft,reverse=True,loop=True)
                for i in range(9):
                    y=.080+.019*i;z=np.interp(y,[.07,.102,.171,.265],[-.067,-.033,-.010,-.013])
                    for s in (-1,1):
                        a=np.array([side*.047+s*.018,y,z])
                        disc(metal,a,.0037,metal.color,w)
                        if i<8:
                            b=np.array([side*.047-s*.018,y+.019,np.interp(y+.019,[.07,.102,.171,.265],[-.067,-.033,-.010,-.013])])
                            cord(details,lambda t:mix(a,b,t)+[0,0,-.005*sin(t*PI)],.002,details.color,w,7,5)
            else:
                a=np.array([side*.078,.085,.017]);b=np.array([side*.083,.188,.030])
                cord(metal,lambda t:mix(a,b,t),.0013,metal.color,w,19,6)
                def pull(t):
                    return b+np.array([side*(.0015+.002*sin(PI*t)),-.016*sin(PI*t),.0026*sin(TAU*t)])
                cord(metal,pull,.00125,metal.color,w,22,7)
    def pleated_skirt(self,body,faces):
        cut=self.cut;d=Dress.__new__(Dress);d.cut=cut
        d.levels=[1.037,.993,.940,.883,.821,.755,.686,.608,.557]
        d.sectors=20;d.guides=[[cut.add_guide(f'DressGuide_{r}_{j}','J_Bip_C_Hips') for j in range(d.sectors)] for r in range(len(d.levels))]
        radii=np.array([(.285,.266,.155,.004),(.480,.223,.138,.007),(.66,.190,.121,.000),
         (.81,.174,.111,-.003),(.91,.161,.110,-.008),(.99,.134,.110,-.022),(1.055,.112,.090,-.037)])
        def skirt_point(a,y):
            w,zr,zc=profile(radii,y);f=clamp((d.levels[0]-y)/(d.levels[0]-d.levels[-1]))
            w+=.025*f;phase=(a/TAU*14+.10*f)%1
            fold=np.interp(phase,[0,.12,.17,.97,1],[.013,.013,-.013,.011,.013])*(.08+.92*f**.67)
            return np.array([(w+fold)*sin(a),y,zc-(zr+fold)*cos(a)])
        d.skirt_point=skirt_point
        cut.fit=dict(levels=d.levels,sectors=d.sectors,shell=[[skirt_point(TAU*j/d.sectors,y)[[0,2]].round(6).tolist() for j in range(d.sectors)] for y in d.levels],
          body=body_collider(cut,body,faces),origin=(-cut.matrices[cut.hip][12:15]).tolist(),gaitScale=.92,liftScale=1,sleevePadding=.010,ties=[])
        fabric=self.cloth('Graphite knife pleats',(65,61,71),.72,'serge',ease=False)
        def fabric_point(a,t,over=False):
            hem=(.609+.014*sin(3*a+.4)-.034*max(0,cos(a+.2)))
            if over:hem+=.039+.022*sin(a+.7)
            y=mix(d.levels[0]+.002,hem,t);q=skirt_point(a,y)
            if over:q+=np.array([sin(a)*.004,-.001,-cos(a)*.004])
            return q
        def panel(a,t):
            q=fabric_point(a,t);phase=(a/TAU*14+.10*t)%1
            shade=(.88+.18*smooth((phase-.17)/.72)-.18*exp(-((phase-.18)/.067)**2))
            return q,d.drape(a,q[1]),(a/TAU*5,t*2.7),fabric.color*shade
        angles=np.array(sorted({TAU*(i+k)/14 for i in range(14) for k in [0,.065,.105,.118,.127,.153,.168,.18,.225,.31,.50,.72,.97,1]}))
        fabric.grid(angles,steps(0,1,32),panel,loop=True)
        def overlay(u,t):
            a=-1.36+u*(1.38-.24*t);q=fabric_point(a,t,True)
            return q,d.drape(a,q[1]),(u*1.1,t*1.8),fabric.color*(.97+.04*cos(u*PI))
        fabric.grid(steps(0,1,38),steps(0,1,29),overlay)
        return d
    def biker(self,body,faces):
        d=self.pleated_skirt(body,faces)
        tee=self.cloth('Raspberry cotton jersey',(222,55,113),.91,'serge',ease=.008)
        leather=self.cloth('Black grained moto leather',(49,46,53),.52,'leather',ease=.013)
        lapel=self.cloth('Turned nappa lapels and belt',(57,53,61),.47,'leather',ease=.017)
        silver=self.cloth('Antique silver zip and snaps',(222,217,219),.34,metal=.33,ease=.020)
        # The tee's exposed inset runs under the lapels. Its hem follows the
        # same drape controls as the skirt where the fabrics actually overlap.
        def inset(u,t):
            x=u*(.042+.035*t)
            y=mix(1.033,1.296+.022*u*u,t)
            q=self.front(x,y,.003)
            return q,self.torso_weight(q),(u,t),tee.color
        tee.grid(steps(-1,1,28),steps(0,1,26),inset,reverse=True)
        def jersey_band(a,t):
            y=mix(.995,1.055,t);q=d.skirt_point(a,y)
            r=.011+.0017*sin(PI*t);q+=[r*sin(a),0,-r*cos(a)]
            fitted=self.shell(a,y,.005)
            q=mix(q,fitted,smooth((t-.64)/.36))
            return q,d.drape(a,y),(a/TAU*4,t*.29),tee.color*(.97+.06*sin(t*PI))
        tee.grid(steps(0,TAU,83),steps(0,1,11),jersey_band,reverse=True,loop=True)
        shell=self.upper(leather,1.046,lambda a:1.344-.022*abs(sin(a)),.009,lambda t:.20+.55*t**2)
        self.sleeves(leather,.531,'biker')
        def front_point(x,y):return self.front(x,y,.015)
        for s in (-1,1):
            vertices=np.array([[s*.056,1.330],[s*.116,1.298],[s*.092,1.276],[s*.109,1.267],[s*.029,1.173],[s*.044,1.273]])
            for j in range(1,len(vertices)-1):
                def patch(u,t):
                    x,y=mix(vertices[0],mix(vertices[j],vertices[j+1],u),t)
                    q=front_point(x,y);q[2]-=.003+.005*sin(PI*t)
                    return q,self.torso_weight(q),(x*7,y*7),lapel.color*(1+.15*sin(PI*t))
                lapel.grid(steps(0,1,7),steps(0,1,9),patch)
            disc(silver,front_point(s*.088,1.284)-[0,0,.008],.0049,silver.color,self.torso_weight)
            for x0,y0,x1,y1 in [(s*.087,1.11,s*.100,1.176)]+([(s*.050,1.205,s*.098,1.241)] if s<0 else []):
                cord(silver,lambda t:front_point(mix(x0,x1,t),mix(y0,y1,t))-[0,0,.003],.0018,silver.color,self.torso_weight,24,7)
        # Two asymmetric front panels meet off-centre along the functional zipper.
        def panel(u,t):
            y=mix(1.046,1.284,t);left=mix(-.041,.076,smooth((t-.23)/.77));right=.110-.017*t
            x=mix(left,right,u);q=front_point(x,y);return q,self.torso_weight(q),(u*1.3,t*1.7),leather.color*(1+.05*sin(PI*u))
        leather.grid(steps(0,1,18),steps(0,1,27),panel)
        def zipline(t):
            return front_point(mix(-.041,.076,smooth((t-.23)/.77)),mix(1.046,1.284,t))-[0,0,.004]
        cord(silver,zipline,.0024,silver.color,self.torso_weight,38)
        for i in range(35):
            q=zipline((i+.4)/36);q[0]+=.0012*(-1)**i
            disc(silver,q,.0019,silver.color,self.torso_weight)
        for x,y in [(-.088,1.166),(.090,1.169),(-.053,1.209)]:
            top=front_point(x,y)-[0,0,.005]
            cord(silver,lambda t:top+[.0017*sin(PI*t),-.014*t,-.0015*t],.0016,silver.color,self.torso_weight,6)
        self.trim(lapel,shell,(0,.085))
        for a,b in [((-.026,1.054),(.018,1.054)),((-.026,1.079),(.018,1.079)),((-.026,1.054),(-.026,1.079)),((.018,1.054),(.018,1.079))]:
            cord(silver,lambda t:front_point(*mix(np.array(a),np.array(b),t))-[0,0,.006],.0021,silver.color,self.torso_weight,9)
        def ring(t):
            a=-.85;y=.921+.017*cos(TAU*t);q=d.skirt_point(a,y);q[0]+=.013*sin(TAU*t);return q+[0,0,-.008]
        ringmetal=self.cloth('Skirt D-ring',(165,157,166),.36,metal=.55,ease=False)
        cord(ringmetal,ring,.0024,ringmetal.color,lambda q:d.drape(-.85,q[1]),33)
        boots=self.cloth('Stacked combat boots',(51,45,52),.48,'leather',ease=.004);self.boots(boots,True)
    def sailor(self):
        knit=self.cloth('Ivory rib-knit sweater',(245,229,202),.94,'ribs',ease=.013)
        neck=lambda a:1.318-.041*max(0,cos(a))**2-.008*max(0,-cos(a))**2-.014*abs(sin(a))
        shell=self.upper(knit,1.034,neck,.005);self.sleeves(knit,.531,'bishop')
        self.trim(knit,shell,(.93,1));self.trim(knit,shell,(0,.075))
        serge=self.cloth('Navy sailor gabardine',(50,52,76),.84,'serge',ease=False)
        welt=self.cloth('Navy waistband and folded hems',(47,48,69),.80,'serge',ease=False)
        buttons=self.cloth('Sailor double-breasted pearl buttons',(207,195,165),.41,metal=.25,ease=False)
        # Two leg tubes divide at the saddle, then form the left/right halves of one waist.
        rows=np.array([(.115,.081,.079,.103,.023),(.20,.077,.074,.099,.024),(.35,.075,.070,.094,.025),
            (.51,.071,.062,.085,.015),(.60,.074,.067,.086,.007),(.70,.079,.075,.089,-.002),
            (.79,.080,.079,.095,-.004),(.86,.081,.076,.093,-.004),(.94,.071,.071,.089,-.004),(1.052,.055,.055,.087,-.032)])
        waist=np.array([(.76,.158,.092,-.002),(.84,.165,.106,-.005),(.91,.156,.109,-.009),
                       (.97,.143,.110,-.017),(1.014,.124,.099,-.026),(1.057,.110,.089,-.036)])
        fork=.805
        levels=sorted([*steps(1.052,.119,55),fork],reverse=True)
        across=steps(0,1,60)
        left_edges=[]
        for s,side in [(-1,'L'),(1,'R')]:
            upper=self.cut.joint(side+'_UpperLeg');lower=self.cut.joint(side+'_LowerLeg')
            chain=spring_chain(self.cut,'TrouserHem_'+side,'J_Bip_'+side+'_LowerLeg',[[s*.053,.385,.025],[s*.051,.255,.028],[s*.05,.13,.028],[s*.05,.104,.028]],1.55,.13,.62,[])
            other=self.cut.joint(('R' if side=='L' else 'L')+'_UpperLeg')
            def leg(u,y):
                cx,rx,rz,cz=profile(rows,y);angle=TAU*u-PI/2
                creases=.0034*(cos(4*angle+1)+.6*sin(7*angle+4*y))*(.5+.5*smooth((.73-y)/.6))
                q=np.array([s*(cx+(rx+creases)*sin(angle)),y,cz-(rz+creases)*cos(angle)])
                wide,depth,z=profile(waist,y);a=PI*u
                high=np.array([s*wide*sin(a),y,z-depth*cos(a)])
                # Close each leg up to the fork. Above it the front and back edges
                # diverge in depth but meet the opposite panel on the midline.
                inner=cx-rx-.0034*(cos(1)+.6*sin(-7*PI/2+4*y))*(.5+.5*smooth((.73-y)/.6))
                clearance=max(.002,inner)*(1-smooth((y-.745)/(fork-.745)))
                q[0]+=s*(clearance-inner)*(1-sin(PI*u))**6
                saddle=smooth((y-fork)/(.877-fork))
                q=mix(q,high,saddle)
                hip=smooth((y-.826)/.180);knee=smooth((.59-y)/.123)
                sway=.43*smooth((.36-y)/.23)
                dynamic=chain_weights(chain,clamp((.385-y)/.281))
                shared=.5*smooth((y-.70)/(fork-.70))*(1-smooth(abs(q[0])/.075))
                thigh=(1-hip)*(1-knee)
                ws=weights((self.cut.hip,hip),(upper,thigh*(1-shared)),(other,thigh*shared),(lower,(1-hip)*knee*(1-sway)),
                      *[(j,v*(1-hip)*knee*sway) for j,v in dynamic])
                return q,ws
            def pant(u,level):
                y=level+.004*cos(TAU*u+.5)*smooth((.48-level)/(.48-.119))
                t=(1.052-level)/(1.052-.119)
                q,ws=leg(u,y)
                return q,ws,(u*2,t*3.9),serge.color*(.96+.044*cos(4*TAU*u+4*t))
            start=len(serge.pos)
            serge.grid(across,levels,pant,reverse=s<0)
            for row,level in enumerate(levels):
                first=start+row*len(across);last=first+len(across)-1
                if s<0:left_edges.append((first,last))
                if level<=fork:serge.seams.append((first,last))
                if s>0 and level>=fork:
                    serge.seams.extend(zip(left_edges[row],(first,last)))
            def fold(u,t):
                y=.120+.012*t+.004*cos(TAU*u+.5);q,w=leg(u,y);q[0]+=s*.0009*sin(TAU*u-PI/2);q[2]-=.0013*cos(TAU*u-PI/2)
                return q,w,(u,t),welt.color*(.94+.12*sin(t*PI))
            welt.grid(steps(0,1,47),[0,.33,1],fold,reverse=s>0)
            for y in [1.016,.974,.933]:
                u=.172;q,w=leg(u,y);disc(buttons,q+[0,0,-.004],.0074,buttons.color,lambda p:w)
        def belt(a,t):
            y=mix(1.029,1.055,t);w,d,z=profile(waist,y)
            q=(sin(a)*(w+.002),y,z-(d+.002)*cos(a))
            return q,[(self.cut.hip,1)],(a,t),welt.color*(.97+.12*sin(t*PI))
        welt.grid(steps(0,TAU,65),[0,.12,.86,1],belt,reverse=True,loop=True)
        self.scarf()
    def scarf(self):
        p=self.cloth('Petrol silk scarf with ivory piping',(30,130,141),.55,'silk',ease=False,sheen=[.08,.18,.18])
        gold=linear((226,195,140));neck=self.cut.joint('C_Neck')
        def collar(a,t):
            y=1.348+.019*t-.011*max(0,cos(a));r=.041+.004*cos(t*PI)
            q=(r*sin(a),y,.009-r*cos(a))
            return q,[(neck,1)],(a,t),gold if t<.12 else p.color*(.96+.1*sin(a*3+t))
        p.grid(steps(0,TAU,49),steps(0,1,10),collar,reverse=True,loop=True)
        for i,(xend,yend) in enumerate([(-.074,1.13),(-.128,1.171)]):
            coords=[[-.038,1.336,-.036],[-.064,1.304,-.061],[-.079,1.254,-.108],[xend,yend,-.142]]
            chain=spring_chain(self.cut,'Neckerchief_'+str(i),'J_Bip_C_UpperChest',coords,1.6,.13,.62,[1])
            def tail(u,t):
                y=mix(1.337,yend,t)+.017*u*t**6;x=mix(-.040,xend,t)-.012*sin(t*PI)+u*(.006+.014*sin(PI*t*.83))
                q=self.front(x,y,.015+.005*i);q[2]-=.004*cos(u*PI)
                amt=.19+.22*t
                ws=weights(*[(j,v*(1-amt)) for j,v in self.torso_weight(q)],*[(j,v*amt) for j,v in chain_weights(chain,t)])
                stripe=.67<abs(u)<.85 or (.70+.10*u<t<.747+.10*u)
                return q,ws,(u,t),gold if stripe else p.color*(1+.10*cos(u*PI))
            p.grid(steps(-1,1,25),steps(0,1,55),tail)
        q=np.array([-.039,1.337,-.036])
        disc(p,q,.012,p.color,lambda _: [(neck,1)])
    def save(self):
        for p,ease in self.pieces:p.save(fit=ease is not False,ease=ease)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('styles',nargs='*');args=parser.parse_args()
    data=(ROOT/'Assets/Shino.vrm').read_bytes();n=struct.unpack_from('<I',data,12)[0]
    doc=json.loads(data[20:20+n]);binary=data[28+n:];textiles(doc,binary)
    for kind in (args.styles or ['rider','marine','bordeaux']):
        cut=Cut(doc,binary);body,faces=cut.skin(paint=False);cut.spring_groups=[]
        look=Look(cut,kind)
        if kind=='rider':look.biker(body,faces)
        elif kind=='marine':look.sailor()
        elif kind=='bordeaux':
            fabric_maps(OUT);strand_maps(OUT);painted_hair(OUT);make_outfit(look,body,faces)
        else:raise ValueError(kind)
        look.save()
        if kind=='bordeaux':
            make_waves(cut);hair=dict(groups=[],clip=False)
        else:hair=hair_style(cut,kind)
        extra={}
        if kind=='marine':
            body_parts=[p for p in cut.doc['meshes'][cut.body['mesh']]['primitives'] if p['material']==9]
            triangles=np.concatenate([cut.read(p['indices']).reshape(-1,3) for p in body_parts])
            # Opaque trousers enclose the legs. Keep the complete shared body buffer and
            # draw the exposed ankles, hands, neck and upper body for this outfit.
            heights=body[triangles,1]
            exposed=triangles[(heights.min(1)<.134)|(heights.max(1)>1.02)]
            extra['visibleBody']=cut.store(exposed.ravel(),'SCALAR','<u2',34963)
        cut.finish(kind,hair=hair,springGroups=cut.spring_groups,**extra)
        print(kind,len(cut.guides),'guides,',len(cut.pieces),'materials,',len(cut.data),'bytes',flush=True)


if __name__=='__main__':main()
