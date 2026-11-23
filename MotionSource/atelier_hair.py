"""Hairstyles and short, rest-shaped VRM spring chains for the three costume sketches."""
import math
import numpy as np
from tailor_shino import Piece, TAU, clamp, cos, sin, linear, mix, smooth, steps, weights


def spring_chain(cut,label,parent,coords,stiffness,gravity,drag,colliders):
    joints=[]
    for i,pivot in enumerate(coords):
        name=f'{label}_{i}'
        joints.append(cut.add_guide(name,parent,position=pivot))
        parent=name
    cut.spring_groups.append(dict(comment=label,bones=[cut.bones[joints[0]]],stiffiness=stiffness,
        gravityPower=gravity,gravityDir=dict(x=0,y=-1,z=0),dragForce=drag,center=-1,
        hitRadius=.009,colliderGroups=colliders))
    return joints


def chain_weights(chain,t):
    f=clamp(t)*(len(chain)-1);i=min(int(f),len(chain)-2);u=f-i
    return weights((chain[i],1-u),(chain[i+1],u))


def curve(points,t):
    f=clamp(t)*(len(points)-1);i=min(len(points)-2,int(f));u=f-i
    a,b,c,d=points[max(0,i-1)],points[i],points[i+1],points[min(len(points)-1,i+2)]
    return .5*((2*b)+(-a+c)*u+(2*a-5*b+4*c-d)*u*u+(-a+3*b-3*c+d)*u*u*u)


def unit(v):return v/max(1e-9,np.linalg.norm(v))


def lock(piece,coords,width,depth,tint,weight,side=(1,0,0),phase=0,tip=.79,root=.63):
    points=np.asarray(coords,dtype=float)
    axis=unit(np.asarray(side,dtype=float))
    cross=[]
    for t in steps(0,1,34):
        v=unit(curve(points,min(1,t+.002))-curve(points,max(0,t-.002)))
        vside=axis-v*np.dot(axis,v)
        if np.linalg.norm(vside)<.05:vside=cross[-1][1] if cross else np.cross(v,[0,0,1])
        vside=unit(vside)
        if cross and np.dot(cross[-1][1],vside)<0:vside=-vside
        cross.append((curve(points,t),vside,unit(np.cross(vside,v)),t))
    def vertex(a,i):
        p,across,normal,t=cross[i]
        envelope=(root+(1-root)*smooth(t/.21))*(1-.982*smooth((t-tip)/(1-tip)))
        axis_a=cos(a);axis_b=sin(a)
        q=p+across*(width*axis_a*envelope)+normal*(depth*axis_b*envelope)
        gain=(.86+.13*(1-axis_a*axis_a)+.08*cos(3*a+phase+1.8*t)+.052*sin(6*a+.7*t))
        color=tint(t) if callable(tint) else tint
        luster=.10*math.exp(-((t-.24-.13*axis_a)/.095)**2)+.065*math.exp(-((t-.64+.09*axis_a)/.12)**2)
        return q,weight(t),((1+axis_a)*.5,.04+t*.92),color*(gain+luster)
    piece.grid(steps(0,TAU,15),range(len(cross)),vertex,loop=True)


def hair_material(cut,label):
    p=Piece(cut,label,.38,'atelier-locks.png')
    p.info.update(normal='atelier-locks-n.png',normalScale=.12,sheen=[.24,.15,.21])
    return p


def stock_groups(cut,groups):
    hair=next(m for m in cut.doc['meshes'] if m['name'].startswith('Hair001'))
    idx=np.concatenate([cut.read(hair['primitives'][i]['indices']).ravel() for i in groups])
    return cut.store(idx,'SCALAR','<u2' if idx.max()<65536 else '<u4',34963)


def crown(cut,piece,rgb):
    head=cut.joint('C_Head')
    def point(a,t):
        c,s=cos(a),sin(a)
        end=1.63-.45*max(c,0)**2+.81*max(-c,0)+.13*abs(s)
        end+=.19*abs(s)
        theta=.013+(end-.013)*t
        radius=.0014*cos(25*a+.9*sin(theta)*s)*sin(theta)
        x=(.100+radius)*sin(theta)*s+.0017
        y=1.511+(.129+radius)*cos(theta)
        z=.008-(.114+radius)*sin(theta)*c
        return (x,y,z),[(head,1)],(a/TAU*9,t),rgb*(.96+.071*cos(14*a+s*t))
    # The shell has a separate growth direction on each side of the crown.
    piece.grid(steps(0,TAU,113),steps(0,1,25),point,loop=True)


def ponytail(cut):
    head=cut.joint('C_Head')
    main=hair_material(cut,'Azalea ponytail and crown HAIR')
    core=linear((230,60,125))
    blush=linear((250,98,159))
    low=linear((166,42,90))
    crown(cut,main,core)
    fixed=lambda t:[(head,1)]
    def dynamic(chain,amount=.90,delay=0):
        return lambda t:weights((head,1-amount*smooth((t-delay)/.30)),
            *[(j,v*amount*smooth((t-delay)/.30)) for j,v in chain_weights(chain,clamp((t-delay)/(1-delay)))])
    pivot=np.array([-.034,1.615,.065])
    path=np.array([pivot,[-.057,1.637,.078],[-.077,1.645,.098],[-.104,1.626,.121],[-.123,1.563,.141],[-.124,1.440,.141],
                   [-.176,1.305,.130],[-.204,1.193,.121],[-.162,1.085,.115]])
    for layer in range(3):
        route=path.copy();route[:,2]+=(layer-1)*.009*np.sin(np.linspace(0,math.pi*.72,len(route)))
        chain=spring_chain(cut,'HairJoint_Pony_'+str(layer),'J_Bip_C_Head',route[2:].tolist(),
                           1.20-.085*layer,.095,.54+layer*.025,[0,1,2,4,7])
        influence=lambda t,chain=chain:dynamic(chain,.93)(clamp((t-.25)/.75))
        for j in range(5):
            coords=route.copy();phase=(j/5+layer*.12)*TAU
            for i,q in enumerate(coords):
                t=i/(len(coords)-1);amp=smooth(t/.35)
                q[0]+=amp*((j-2)*.013+.022*sin(t*8+phase))
                q[2]+=.010*amp*cos(phase+.9*t)
            coords[-1,1]+=.046*sin(phase+1.7)+.020*layer
            coords[-1,0]+=.041*sin(phase+.6)
            color=mix(low,blush,.36+.23*sin(phase+.5)+layer*.10)
            lock(main,coords,.019+.003*cos(phase),.009,color,influence,(.93,.02,.34),phase,tip=.61,root=.44)
    # Two separated wisps describe the arc when the ponytail turns.
    for j in range(2):
        q=path.copy();q[2:5,0]-=.035+.014*j;q[4:,2]+=(j-.5)*.075;q[-1,0]+=(j-.5)*.085;q[-1,1]+=.015+.055*j
        lock(main,q,.006,.003,mix(core,blush,.50),influence,(1,0,.2),j,tip=.62,root=.20)
    # Twined scalp braids follow the temple into the elastic.
    for row in range(2):
        route=np.array([[-.083,1.515+.020*row,-.065],[-.102,1.535+.016*row,-.022],
              [-.098,1.570+.012*row,.034],[-.079,1.599+.006*row,.071],pivot])
        for j in range(2):
            def braid(a,t):
                q=curve(route,t);T=unit(curve(route,min(1,t+.002))-curve(route,max(0,t-.002)))
                U=unit(np.cross(T,[-1,0,0]));V=unit(np.cross(T,U));phi=TAU*5.5*t+j*math.pi
                q+=U*(.0045*cos(phi)+.0044*cos(a))+V*(.0045*sin(phi)+.0044*sin(a))
                return q,fixed(t),(a/TAU,t*2),mix(core,blush,.23+.25*j)
            main.grid(steps(0,TAU,9),steps(0,1,92),braid,loop=True)
    tie=Piece(cut,'Graphite ponytail elastic',.79)
    axis=unit(path[1]-pivot);u=unit(np.cross(axis,[0,0,1]));v=np.cross(axis,u)
    def elastic(a,t):
        outside=u*cos(a)+v*sin(a)
        q=pivot+axis*(.009+.004*sin(t))+outside*(.025+.004*cos(t))
        return q,fixed(0),(a/TAU,t/TAU),linear((41,32,47),1+.15*cos(t))
    tie.grid(steps(0,TAU,37),steps(0,TAU,11),elastic,loop=True);tie.save(fit=False)
    for s in (-1,1):
        p=np.array([[s*.054,1.596,-.055],[s*.080,1.548,-.078],[s*.087,1.489,-.074],[s*.081,1.421,-.087],[s*.064,1.374,-.082]])
        chain=spring_chain(cut,'HairJoint_Tendril_'+str(s),'J_Bip_C_Head',p[1:].tolist(),1.12,.08,.58,[2,3])
        lock(main,p,.013,.0045,blush,lambda t:dynamic(chain,.66)(clamp((t-.25)/.75)),phase=s)
    main.save(fit=False)


def hair_style(cut,kind):
    if kind=='marine':
        inside=[12,14,16,17,19,20,28,29,*range(30,43)]
        return dict(groups=[dict(role='navy',indices=stock_groups(cut,[i for i in range(46) if i not in inside])),
                            dict(role='teal',indices=stock_groups(cut,inside))],clip=True)
    ponytail(cut)
    # Fan the lower edge of the native fringe into tapered, uneven pink points.
    parts=next(m for m in cut.doc['meshes'] if m['name'].startswith('Hair001'))['primitives']
    pos=cut.read(parts[0]['attributes']['POSITION']).copy()
    uv=cut.read(parts[0]['attributes']['TEXCOORD_0'])
    for i,p in enumerate(parts[:12]):
        idx=np.unique(cut.read(p['indices']));u=uv[idx,0];v=uv[idx,1]
        u=(u-u.min())/max(1.e-6,np.ptp(u));tip=np.clip((v-.70)/.30,0,1)**1.5
        point=np.abs(u-(.42+.17*sin(1.8*i)))
        pos[idx,1]+=tip*(.018*point*2-.010-.005*sin(i))
        pos[idx,0]+=tip*.006*sin(1.7*i)
    return dict(groups=[dict(role='pink',indices=stock_groups(cut,list(range(12))),
                                  position=cut.store(pos,'VEC3',target=34962))],clip=True)
