"""The sewn 33C patterns. Measurements are metres on Shino's rest skeleton."""
import math

import numpy as np

from tailor_shino import Dress, Piece, TAU, body_collider, clamp, cos, exp, linear, mix, sin, smooth, steps, weights

PI=math.pi


class Sections:
    """Cubic cross-sections with continuous tangents at the bust, hip and calf."""
    def __init__(self,rows):
        table=np.asarray(rows,dtype=float)
        self.y,self.values=table[:,0],table[:,1:]
        slopes=np.diff(self.values,axis=0)/np.diff(self.y)[:,None]
        tangent=(slopes[:-1]+slopes[1:])*.5
        tangent[slopes[:-1]*slopes[1:]<=0]=0
        self.tangents=np.vstack((slopes[0],tangent,slopes[-1]))
    def __call__(self,y):
        i=np.searchsorted(self.y,y,side='right')-1;i=min(len(self.y)-2,max(0,i))
        span=self.y[i+1]-self.y[i];t=clamp((y-self.y[i])/span)
        return (1-t)**2*((1+2*t)*self.values[i]+t*span*self.tangents[i])+t*t*((3-2*t)*self.values[i+1]+(t-1)*span*self.tangents[i+1])


def fabric(cut,name,rough,texture=None,sheen=None):
    piece=Piece(cut,name,rough,texture)
    if sheen:piece.info.update(sheen=sheen,sheenRoughness=.62)
    return piece


class BiasSkirt(Dress):
    def __init__(self,cut,body,faces):
        self.cut=cut
        self.levels=[1.054,1.010,.951,.885,.807,.723,.636,.545,.450,.361,.279]
        self.sectors=20
        self.shape=Sections([(.276,.245,.149,.006),(.380,.225,.139,.007),(.52,.193,.121,.009),
            (.65,.177,.114,.006),(.77,.177,.113,.000),(.855,.170,.110,-.006),(.921,.154,.107,-.015),
            (.980,.134,.101,-.023),(1.027,.118,.093,-.031),(1.058,.111,.087,-.038)])
        self.guides=[[cut.add_guide(f'DressGuide_{r}_{i}','J_Bip_C_Hips') for i in range(self.sectors)] for r in range(len(self.levels))]
        # Simulate the smooth envelope. The weave and smaller shaped folds are carried
        # by this cage and do not create point loads in the collision constraints.
        shell=[[self.point(TAU*i/self.sectors,y,cage=True)[[0,2]].round(6).tolist()
                for i in range(self.sectors)] for y in self.levels]
        cut.fit=dict(levels=self.levels,sectors=self.sectors,shell=shell,body=body_collider(cut,body,faces),
                     origin=(-cut.matrices[cut.hip][12:15]).tolist(),gaitScale=.95,liftScale=1,sleevePadding=.011,ties=[])

    def point(self,a,y,cage=False):
        width,depth,center=self.shape(y)
        a=(a+PI)%TAU-PI;t=clamp((1.054-y)/.764)
        fan=(.018*sin(6*a+.83*(1-t))+.008*sin(4*a-.60*t)+.004*cos(9*a+.25))*(.035+.965*t**1.72)
        relief=fan
        if not cage:
            # Each bias fold opens out from the knot. The spaces between them stay smooth.
            run=a+.93
            if 0<run<3.4:
                fall=smooth(run/.35)*(1-smooth((run-2.05)/1.35))*smooth(t/.047)
                for slope,lift,width0 in [(.091,.0045,.018),(.204,.0075,.030),(.378,.010,.039)]:
                    mid=.030+slope*run+.014*run*run
                    w=width0*(.68+.43*run)
                    q=(t-mid)/w
                    relief+=fall*lift*(exp(-q*q)-.60*exp(-((q-.99)/.85)**2))
        return np.array([(width+relief)*sin(a),y,center-(depth+relief)*cos(a)])

    def hem_y(self,a):
        return .291+.010*sin(6*a+.36)+.004*sin(4*a-1.0)+.003*cos(9*a)

    def make(self):
        p=fabric(self.cut,'Garnet bias satin · shaped gores',.52,'bordeaux-bias.png',[.16,.038,.070])
        trim=fabric(self.cut,'Garnet turned hem and yoke',.63,'atelier-silk.png',[.09,.02,.03])
        def skirt(a,t):
            y=mix(1.050,self.hem_y(a),t);q=self.point(a,y)
            return q,self.drape(a,y),(.5+a/TAU,t),.98
        p.grid(steps(-PI,PI,141),steps(0,1,66),skirt,loop=True)
        def binding(a,v):
            y=self.hem_y(a);q=self.point(a,y)
            # A rolled edge with a visible inner facing, all on the same drape guides.
            h,r,c=[(.0011,.0003,(114,32,53)),(-.0008,-.0009,(102,29,51)),(.0012,-.0025,(94,32,50)),(.012,-.0031,(103,35,52))][v]
            q+=[r*sin(a),h,-r*cos(a)]
            return q,self.drape(a,q[1]),(a/TAU*6,v*.08),linear(c)
        trim.grid(steps(-PI,PI,113),range(4),binding,loop=True)
        def yoke(a,t):
            y=1.007+.045*t+.003*sin(a-.4)
            q=self.point(a,y);ease=.0028+.0013*sin(PI*t)
            q+=[sin(a)*ease,0,-cos(a)*ease]
            return q,self.drape(a,y),(a/TAU*6,t*.32),linear((114,34,55),.97+.14*sin(PI*t)-.11*exp(-((t-.10)/.05)**2))
        trim.grid(steps(-PI,PI,95),steps(0,1,10),yoke,reverse=True,loop=True)
        for a0 in (-1.50,1.50,PI-.015):
            def seam(u,t):
                a=a0+.005*u+.062*sin(PI*t);y=mix(1.008,self.hem_y(a)+.006,t)
                q=self.point(a,y);q+=[.0006*sin(a),0,-.0006*cos(a)]
                return q,self.drape(a,y),(u,t),linear((111,30,54),.88+.20*u)
            trim.grid([-1,0,1],steps(0,1,45),seam)
        p.save(fit=False);trim.save(fit=False)

    def sash(self,blouse):
        p=fabric(self.cut,'Rose charmeuse · obi, knot and two tails',.61,'atelier-silk.png',[.16,.073,.070])
        rose=linear((200,99,85));lining=linear((169,76,72));hip=[(self.cut.hip,1)]
        waist_angle=-.90
        def around(a,y,distance):
            q=self.point(a,y);return q+np.array([distance*sin(a),0,-distance*cos(a)])
        def band(a,t):
            dist=math.atan2(sin(a-waist_angle),cos(a-waist_angle));g=exp(-(dist/.58)**2)
            y=1.034+(.039-.012*g)*t+.0028*sin(a+.8)
            shell=blouse.shell(a,y)
            outer=np.array([sin(a),0,-cos(a)])
            q=mix(around(a,y,.005),shell+.004*outer,smooth(t))
            q+=outer*(.0023*sin(PI*t)+g*.0017*cos(3*PI*t))
            follow=smooth(t)
            skin=weights((self.cut.hip,1-follow),*[(j,w*follow) for j,w in self.cut.torso(*shell[:2])])
            return q,skin,(a/TAU*5,t*.35),rose*(.94+.09*sin(PI*t)+.037*g*cos(3*PI*t))
        p.grid(steps(-PI,PI,97),steps(0,1,9),band,reverse=True,loop=True)
        center=around(waist_angle,1.049,.012)
        outward=np.array([sin(waist_angle),0,-cos(waist_angle)])
        along=np.array([cos(waist_angle),0,sin(waist_angle)]);up=np.array([0,1,0])
        def knot(a,t):
            q=center+along*(.014*cos(a)*sin(t))+(up*.89+along*.42)*(.016*cos(t))+outward*(.010*sin(a)*sin(t))
            return q,hip,(a/TAU*.6,t*.4),rose*(.90+.15*cos(2.3*a+.7*t))
        p.grid(steps(0,TAU,23),steps(.008,PI-.008,13),knot,loop=True)
        # Wide folded ribbon, with the reverse side visible inside each loop.
        for side in (-1,1):
            def loop(u,t):
                bulge=sin(PI*t);wide=.010+.011*bulge
                q=center+along*side*(.005+(.035 if side<0 else .027)*bulge)
                q+=up*(-.010-.043*bulge+.018*sin(TAU*t))+outward*(.007+.017*bulge+.006*cos(TAU*t))
                q+=along*wide*u*(.51+.37*cos(TAU*t))+up*wide*u*.65
                q+=outward*.0048*(1-u*u)*bulge
                return q,hip,((u+1)*.2,t*.70),mix(rose,lining,.55*smooth((t-.48)/.4))*(.97+.08*(1-u*u))
            p.grid(steps(-1,1,9),steps(0,1,25),loop,reverse=side>0)
        for j,(length,lean) in enumerate([(.204,.41),(.165,-.28)]):
            chain=[self.cut.hip]
            for k in range(1,4):
                t=k/3;y=1.046-length*t;a=waist_angle+lean*t
                row=min(range(len(self.levels)),key=lambda r:abs(self.levels[r]-y));sector=round(a/TAU*self.sectors)%self.sectors
                name=f'DressTie_{j}_{k}'
                chain.append(self.cut.add_guide(name,f'DressGuide_{row}_{sector}'))
                self.cut.fit['ties'].append(dict(name=name,side=2*j-1,length=t))
            def tail(u,t):
                width=.005+.012*smooth(t/.36)
                a=waist_angle+lean*t+.040*sin(t*6+.7*j)*t+u*width/.15
                y=1.047-length*t+.012*u*t**7
                q=around(a,y,.016+.007*sin(PI*t)+.003*u*u+.003*sin(9*t+j))
                f=t*3;i=min(2,int(f));f-=i
                return q,weights((chain[i],1-f),(chain[i+1],f)),((u+1)*.28,t*1.2),rose*(.98+.11*sin(3*u+2*t)-.09*abs(u)**8)
            p.grid(steps(-1,1,12),steps(0,1,30),tail)
        p.save(fit=False)


class WrapBlouse:
    """Front and back panels share a closed armscye with each set-in sleeve."""
    waist=1.038
    underarm=1.238
    shoulder=1.342
    def __init__(self,cut):
        self.cut=cut
        self.hem_joints={}
        self.sections=Sections([(1.034,.111,-.121,.048),(1.069,.105,-.123,.040),
          (1.107,.100,-.126,.043),(1.145,.104,-.127,.046),(1.176,.116,-.135,.056),
          (1.201,.122,-.138,.062),(1.225,.127,-.126,.067),(1.243,.130,-.113,.069),
          (1.274,.129,-.092,.070),(1.306,.129,-.069,.067),(1.344,.135,-.047,.059)])
        self.silk=fabric(cut,'Tea rose crossover · silk crêpe',.69,'bordeaux-crepe.png',[.116,.043,.040])
        self.finished=fabric(cut,'Turned collar, sleeve facings and stitching',.70,'atelier-silk.png',[.091,.034,.032])
        self.offsets={self.silk:[],self.finished:[]}

    def top(self,a):
        u=abs(sin(a))
        knots=[0,.17,.33,.49,.64,.80,1]
        front=np.interp(u,knots,[1.238,1.264,1.299,1.338,1.348,1.347,self.shoulder])
        back=np.interp(u,knots,[1.323,1.327,1.333,1.338,1.348,1.347,self.shoulder])
        return float(front if cos(a)>=0 else back)

    def armhole(self,s,a):
        h=(1+cos(a))*.5;y=mix(self.underarm,self.shoulder,h)
        w=self.sections(y)[0]
        return np.array([s*w,y,mix(-.020,.008,smooth(h))+.050*sin(a)])

    def shell(self,a,y):
        sx,c=sin(a),cos(a);side=abs(sx)
        w,front,back=self.sections(y);x=w*sx
        mid=(front+back)/2
        z=mid-math.copysign(abs(c)**.84,c)*(back-front)/2
        h=clamp((y-self.underarm)/(self.shoulder-self.underarm))
        side_z=mix(-.020,.008,smooth(h))
        side_radius=.050*math.sqrt(max(0,1-(2*h-1)**2))
        top=self.top(a)
        # The two panels close across each shoulder. At the arm opening both
        # sides end on the sleeve cap itself, including its upper quadrant.
        shoulder_seam=smooth((side-.28)/.25)*smooth((y-top+.043)/.043)
        z=mix(z,mix(.013,.008,side),shoulder_seam)
        if y>self.underarm:
            z=mix(z,side_z-math.copysign(side_radius,c),smooth((side-.86)/.14))
        elif y>1.195:z=mix(z,-.020,smooth((y-1.195)/.043)*smooth((side-.86)/.14))
        # Radiating tension on the outer panel, with softer opposing folds across the back.
        run=x+.098
        guide=0.
        if run>-.018:
            for slope,base,amount,spread in [(.14,1.062,.0029,.006),(.42,1.067,.0048,.010),(.78,1.074,.0043,.013)]:
                d=(y-base-slope*run)/(spread+.014*max(0,run))
                guide+=amount*(exp(-d*d)-.55*exp(-((d-.98)/.9)**2))
        depth=guide*max(0,c)**.85 + .0026*sin(10*a+5*y)*max(0,-c)*exp(-((y-1.145)/.080)**2)
        return np.array([x+depth*sx,y,z-depth*c])

    def face(self,x,y):
        a=math.asin(np.clip(x/self.sections(y)[0],-.997,.997))
        y=min(y,self.top(a))
        return self.shell(a,y),a

    def sew(self,p,us,vs,fn,reverse=False,loop=False):
        def vertex(u,v):
            q,ws,uv,tint,offset=fn(u,v);self.offsets[p].append(offset)
            return q,ws,uv,tint
        p.grid(us,vs,vertex,reverse=reverse,loop=loop)

    def body(self):
        zero=np.zeros(3)
        def panel(a,t):
            y=mix(self.waist,self.top(a),t);q=self.shell(a,y)
            return q,self.cut.torso(*q[:2]),(.5+a/TAU,clamp((1.343-y)/.305)),1,zero
        seam_t=[((self.shoulder+self.underarm)/2+.052*cos(a)-self.waist)/(self.shoulder-self.waist)
                for a in steps(0,PI,27)]
        rows=sorted(set([*steps(0,(self.underarm-self.waist)/(self.shoulder-self.waist),34),*seam_t]))
        for a,b,count in [(-PI,-PI/2,32),(-PI/2,PI/2,65),(PI/2,PI,32)]:
            angles=steps(a,b,count)
            if abs(abs(a)-PI/2)<1e-6:angles[0]+=.000001
            if abs(abs(b)-PI/2)<1e-6:angles[-1]-=.000001
            self.sew(self.silk,angles,rows,panel,reverse=True)

    def collar(self):
        rose=linear((223,123,106))
        # The outer overlap continues in one cut from the neck to the side knot.
        # The other collar tucks underneath it at the bottom of the V.
        def lapel(side,w,t):
            outer=side==1
            join=.42 if outer else 1.
            if t<join:
                v=t/join;a=side*.55*(1-v);y=self.top(a);x=self.sections(y)[0]*sin(a)
                broad=.018*(.32+.68*smooth(v/.30))
                x+=side*broad*w
                y-=(.009+.004*v)*w
            else:
                v=(t-join)/(1-join) if outer else 0
                x=mix(.0,-.103,v)+side*.018*w*(1-.32*v)
                y=mix(1.238,1.048,v)-.012*w
            q,a=self.face(x,y)
            lift=(.0025 if outer else .0015)+.0014*sin(PI*w)+.0011*exp(-((w-.1)/.14)**2)
            off=np.array([sin(a),.15,-cos(a)])*lift
            tint=rose*(.96+.08*sin(PI*w)-.050*exp(-((w-.97)/.06)**2))
            return q,self.cut.torso(*q[:2]),(t*2,w*.28),tint,off
        for side in (-1,1):
            def panel(w,t):return lapel(side,w,t)
            self.sew(self.finished,steps(0,1,10),steps(0,1,73),panel,reverse=side<0)
            def stitch(u,t):
                q,ws,uv,_,off=lapel(side,.835+.025*u,t)
                return q,ws,uv,linear((188,95,87),.97+.07*cos(t*TAU*102)),off+[0,0,-.00028]
            self.sew(self.finished,[-1,1],steps(.035,.98,111),stitch,reverse=side<0)
        def back(a,t):
            y=self.top(a)-.011*t;q=self.shell(a,y)
            return q,self.cut.torso(*q[:2]),(a,t),rose*(.98+.06*sin(PI*t)),np.array([sin(a),.12,-cos(a)])*.0016
        self.sew(self.finished,steps(PI-.54,PI+.54,49),steps(0,1,6),back)

    def sleeves(self):
        coral=linear((213,111,96));inside=linear((164,76,76))
        for s in (-1,1):
            def sleeve(a,t):
                root=self.armhole(s,a)
                # End the rolled cuff on the upper arm, well before the elbow's blending zone.
                inside=max(0,-sin(a))
                end=.240+.003*cos(a)-.008*inside**2
                x=s*mix(abs(root[0]),end,t)
                belly=sin(PI*t)
                ry=mix(.052,.046,t)+.0044*belly
                rz=mix(.050,.042,t)+.005*belly-.005*t*inside**2
                drip=.0034*sin(3*a+.46*t)+.0021*sin(5*a-1.09*t)
                cy=mix((self.underarm+self.shoulder)*.5,1.289,t)
                cz=mix(.003,.003,t)
                z=cz+(rz+drip*t)*sin(a)
                y=cy+(ry+drip*t)*cos(a)-.0037*t
                q=np.array([x,y,z]);q+=np.array([0,0,root[2]-(.003+.05*sin(a))])*(1-smooth(t/.74))
                q[1]+= (root[1]-((self.underarm+self.shoulder)*.5+.052*cos(a)))*(1-t)
                half=PI/2-.000001 if sin(a)<=0 else PI/2+.000001
                seam=self.shell(s*half,root[1])
                return q+(seam-root)*(1-smooth(t/.36))
            side='R' if s>0 else 'L'
            parent='J_Bip_'+side+'_UpperArm'
            upper=self.cut.joint(side+'_UpperArm')
            inv=self.cut.matrices[upper].reshape(4,4).T
            controls=[];joints=[]
            for j in range(16):
                a=TAU*j/16
                name=f'SleeveRoll_{side}_{j}'
                joints.append(self.cut.add_guide(name,parent))
                def local(t):return (inv@np.r_[sleeve(a,t),1])[:3].round(6).tolist()
                controls.append(dict(name=name,middle=local(.63),lip=local(1.0)))
            self.hem_joints[s]=(upper,joints)
            self.cut.fit.setdefault('sleeveRolls',[]).append(dict(side='right' if s>0 else 'left',controls=controls))
            def main(a,t):
                q=sleeve(a,t);shade=(.97+.042*cos(3*a-.5*t)+.022*sin(5*a-t)-.12*exp(-((t-.84)/.023)**2))
                return q,self.cut.arm(*q[:2]),(a/TAU*2,t*1.0),coral*shade,np.zeros(3)
            self.sew(self.finished,steps(0,TAU,53),steps(0,1,32),main,reverse=s<0,loop=True)
            def cuff(a,t):
                q=sleeve(a,.83+.17*t)
                rad=np.array([0,cos(a),sin(a)])
                return q,self.cut.arm(*q[:2]),(a/TAU*2,t*.24),coral*(1.02+.075*sin(PI*t)),rad*(.0017+.0012*sin(PI*t))
            self.sew(self.finished,steps(0,TAU,53),steps(0,1,7),cuff,reverse=s<0,loop=True)
            def underside(a,i):
                q=sleeve(a,1)
                dx,dr=[(.0005,.0017),(.0011,.0004),(-.0008,-.0018),(-.009,-.0028)][i]
                return q,self.cut.arm(*q[:2]),(a/TAU*2,i*.05),mix(coral,inside,i/3),np.array([s*dx,dr*cos(a),dr*sin(a)])
            self.sew(self.finished,steps(0,TAU,53),range(4),underside,reverse=s<0,loop=True)
            def thread(a,u):
                q=sleeve(a,.871+.0028*u)
                return q,self.cut.arm(*q[:2]),(a,u),linear((178,88,79),.96+.14*sin(68*a)),np.array([0,.0033*cos(a),.0033*sin(a)])
            self.sew(self.finished,steps(0,TAU,151),[-1,1],thread,reverse=s<0,loop=True)

    def make(self):
        self.body();self.collar();self.sleeves()
        for p in [self.silk,self.finished]:
            # Transfer all layers from their shared underlying pattern, then add the
            # rolled thickness. Plackets and topstitching bend with those exact weights.
            points=np.array(p.pos)
            self.cut.surface.tailor(points,p.weights,p.info['name'],.0065)
            if p is self.finished:
                for i,(x,y,z) in enumerate(p.pos):
                    influence=smooth((abs(x)-.148)/.071)
                    if not influence:continue
                    upper,guides=self.hem_joints[1 if x>0 else -1]
                    sector=(math.atan2(z-.003,y-1.286)%TAU)*len(guides)/TAU
                    j=int(sector)%len(guides);u=sector-int(sector)
                    ws=dict(p.weights[i]);w=ws.get(upper,0.)*influence
                    ws[upper]=ws.get(upper,0.)-w
                    p.weights[i]=weights(*ws.items(),(guides[j],w*(1-u)),(guides[(j+1)%len(guides)],w*u))
            p.pos=points+np.array(self.offsets[p])
            p.save(fit=False)


def make_outfit(look,body,faces):
    skirt=BiasSkirt(look.cut,body,faces)
    blouse=WrapBlouse(look.cut)
    skirt.make();blouse.make();skirt.sash(blouse)
    boots=look.cloth('Oxblood burnished kid boots',(113,45,64),.49,'leather',ease=.004)
    look.boots(boots)
