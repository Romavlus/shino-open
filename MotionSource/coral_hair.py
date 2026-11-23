"""A side-part groom for 33C. A solid inner shape supports layered, alpha-cut hair cards."""
import math

import numpy as np

from atelier_hair import chain_weights, curve, spring_chain, unit
from tailor_shino import Piece, TAU, clamp, cos, exp, linear, mix, sin, smooth, steps, weights

PI=math.pi
PLUM=linear((113,63,90))
SHADE=linear((71,37,59))
GLOW=linear((152,90,112))
CORAL=linear((238,124,117))


def blend_direction(a,b,t):
    theta=math.acos(np.clip(float(a@b),-.99999,.99999))
    return (sin((1-t)*theta)*a+sin(t*theta)*b)/sin(theta)


def cap_direction(side,f,t):
    angle=mix(-1.08,.96,f)
    part=unit(np.array([.27-.12*f,cos(angle),sin(angle)]))
    end=side*mix(1.02,PI,f)
    fall=1.89+.75*f+.12*sin(PI*f)
    target=np.array([sin(fall)*sin(end),cos(fall),-sin(fall)*cos(end)])
    v=blend_direction(part,target,t)
    v[2]-=.12*sin(PI*t)*(1-f)**2
    # In front view a side part lifts off the forehead before the swept lock
    # drops beside the eye. A great-circle arc alone produces a ruler-straight V.
    if f<.46:
        brow=FRONT[side]
        route=curve(brow,t)
        fx=(route[0]-.001)/.103;fy=(route[1]-1.511)/.131
        face=unit(np.array([fx,fy,-math.sqrt(max(.006,1-fx*fx-fy*fy))]))
        origin=unit(np.array([.27,cos(-1.08),sin(-1.08)]))
        end=1.02*side
        previous=blend_direction(origin,np.array([sin(1.89)*sin(end),cos(1.89),-sin(1.89)*cos(end)]),t)
        previous[2]-=.12*sin(PI*t)
        v+=(face-unit(previous))*(1-smooth(f/.46))
    return unit(v)


FRONT={
  1:np.array([[.028,1.572,0],[.053,1.574,0],[.071,1.551,0],[.075,1.520,0],[.085,1.493,0],[.094,1.464,0]]),
 -1:np.array([[.028,1.572,0],[.016,1.574,0],[-.006,1.546,0],[-.039,1.523,0],[-.072,1.510,0],[-.092,1.474,0]])}


def scalp(side,f,t,offset):
    n=cap_direction(side,f,t)
    return np.array([.001,1.511,.008])+n*(np.array([.103,.131,.117])+offset)


def pinned_then_free(chain,head,t,start):
    extent=smooth((t-start)/.25)*.94
    local=clamp((t-start)/(1-start))
    return weights((head,1-extent),*[(j,w*extent) for j,w in chain_weights(chain,local)])


def atlas(tile,u,t):
    return ((tile+.018+.964*u)/4,.012+.976*t)


def ribbon(piece,path,halfwidth,depth,color,binding,tile,across,phase=0,*,fine=False,paint=None):
    path=np.asarray(path,dtype=float);axis=unit(np.asarray(across,dtype=float))
    rows=steps(0,1,41 if not fine else 32);frames=[]
    for t in rows:
        tangent=unit(curve(path,min(1,t+.002))-curve(path,max(0,t-.002)))
        # A gently rotating cross-section gives different reflections to adjacent locks.
        side=axis-tangent*(axis@tangent)
        if np.linalg.norm(side)<.01:side=frames[-1][1] if frames else np.cross(tangent,[0,1,0])
        side=unit(side)
        if frames and frames[-1][1]@side<0:side=-side
        normal=unit(np.cross(side,tangent))
        roll=.22*sin(7*t+phase)*smooth(t/.25)
        rotated=side*cos(roll)+normal*sin(roll)
        frames.append((curve(path,t),rotated,unit(np.cross(rotated,tangent)),t))
    def point(u,i):
        center,side,normal,t=frames[i]
        grow=.33+.67*smooth(t/.18)
        taper=1-.986*smooth((t-(.55 if fine else .65))/(.45 if fine else .35))
        envelope=grow*taper
        bump=(1-u*u)*(.92+.08*cos(3*u+4*t))
        q=center+side*(u*halfwidth*envelope)+normal*(bump*depth*envelope)
        uv=atlas(tile,(u+1)*.5,t) if paint is None else ((paint+.025+.95*(u+1)*.5)/2,.01+.98*t)
        return q,binding(t),uv,color(t)*(.95+.065*(1-u*u))
    piece.grid(steps(-1,1,5 if fine else 9),range(len(rows)),point)


def make_waves(cut):
    head=cut.joint('C_Head')
    fixed=lambda t:[(head,1)]
    core=Piece(cut,'Aubergine roots and underhair',.61)
    cap=Piece(cut,'Combed side part HAIR',.48,'bordeaux-crown.png')
    cap.info.update(anisotropy=.39,sheen=[.15,.072,.12],sheenRoughness=.51)
    mass=Piece(cut,'Painted shoulder-wave HAIR',.48,'bordeaux-wave.png')
    mass.info.update(anisotropy=.36,sheen=[.15,.065,.10],sheenRoughness=.56)
    cards=Piece(cut,'Hand-combed plum and coral strands HAIR',.51,'bordeaux-strands.png')
    cards.info.update(normal='bordeaux-strands-n.png',normalScale=.23,alphaCutoff=.33,
                      sheen=[.18,.08,.14],sheenRoughness=.48,anisotropy=.42)
    # Two growth fields meet at a narrow curved side part. The shell and all
    # overlying strokes follow the same field, including around the back of the head.
    for side in (-1,1):
        lane=0 if side<0 else 1
        def base(f,t):
            ridges=.0017*sin(TAU*(7.4*f+.14*sin(5*t)))+.0008*sin(TAU*(12.2*f-.21*t))
            lift=.0012+.007*sin(PI*clamp(t/.43))*exp(-((f-.25)/.85)**4)
            q=scalp(side,f,t,lift+ridges*smooth(t/.20))
            uv=((lane+.004+.992*f)/2,t)
            return q,fixed(t),uv,.95+.06*smooth(t/.24)
        cap.grid(steps(0,1,72),steps(0,1,42),base,reverse=side<0)
        # Feather the fringe and temples where the opaque fitted shell ends.
        # The body of the crown is one uninterrupted painted surface.
        for j in range(7):
            f=(j+.42)/8
            path=np.stack([scalp(side,f,t,.0039) for t in steps(.48,1,9)])
            for i,p in enumerate(path):
                p[1]-=(.008+.009*cos(j*2.1))*smooth(i/8)
            ribbon(cards,path,.0039+.0015*(j%2),.0011,lambda t:mix(PLUM,GLOW,.24),fixed,
                   j%4,(.46*side,.14,.88),j,fine=True)

    # The back curtain has a continuous, tapered underlayer and individually
    # shaped surface locks. Neighbouring tips share guides at their roots.
    back=[]
    for j in range(7):
        a=1.01+(TAU-2.02)*j/6
        s,c=sin(a),cos(a)
        coords=np.array([[.022,1.628,.003],[.068*s,1.612,.016-.072*c],[.102*s,1.538,.014-.111*c],
              [.103*s,1.451,.017-.112*c],[.106*s-.008,1.380,.040-.096*c],
              [.109*s-.020,1.302,.056-.092*c],[.098*s-.019,1.239+.043*sin(a),.071-.076*c]])
        chain=spring_chain(cut,'HairJoint_CoralNape_'+str(j),'J_Bip_C_Head',coords[2:].tolist(),1.32,.065,.62,[1,2])
        back.append((a,coords,chain))
    def section(f,t):
        k=clamp(f)*6;i=min(5,int(k));u=k-i
        a,p,chain=back[i];b,q,other=back[i+1]
        xyz=mix(curve(p,t),curve(q,t),u)
        across=unit(np.array([cos(mix(a,b,u)),0,sin(mix(a,b,u))]))
        influence=weights(*[(n,w*(1-u)) for n,w in pinned_then_free(chain,head,t,2/6)],
                          *[(n,w*u) for n,w in pinned_then_free(other,head,t,2/6)])
        return xyz,across,influence
    def under(f,v):
        t=.25+(.636+.025*sin(18*f))*v;q,side,ws=section(f,t)
        q[1]+=.016*sin(19*f)*v**6
        return q,ws,(f*6,t),mix(SHADE,PLUM,.36+.14*sin(16*f))
    core.grid(steps(0,1,54),steps(0,1,34),under)
    for j in range(24):
        f=(j+.5)/24;phase=2.41*j
        a=mix(back[0][0],back[-1][0],f);radial=np.array([sin(a),0,-cos(a)])
        path=[]
        for t in steps(.23,1,8):
            p,side,_=section(f,t)
            p+=radial*(.004+.004*sin(PI*t)) + side*(.008*sin(7*t+phase)*smooth((t-.4)/.45))
            p[1]+=(.032*sin(phase)-.007)*smooth((t-.69)/.31)
            path.append(p)
        tone=mix(PLUM,GLOW,.13+.17*(.5+.5*cos(phase)))
        ribbon(cards,path,.019+.004*cos(phase),.004,lambda t:tone,lambda t:section(f,.23+.77*t)[2],
               j%4,(cos(a),0,sin(a)),phase)

    # Three overlapping S-waves travel from the right temple around the shoulder.
    # Their surface ribbons and the fine separated tips ride the same physical chain.
    master=np.array([[-.071,1.584,-.067],[-.100,1.519,-.064],[-.102,1.450,-.054],
                     [-.086,1.385,-.063],[-.110,1.335,-.102],[-.147,1.289,-.123],
                     [-.143,1.246,-.138],[-.109,1.196,-.147],[-.098,1.155,-.146],
                     [-.122,1.103,-.136]])
    for j in [0,2,3,1]:
        k=j-1.5;phase=j*1.36
        route=master.copy()
        for i,p in enumerate(route):
            t=i/(len(route)-1);f=smooth(t/.31)
            p[0]+=f*(k*.012+.016*sin(t*9+phase));p[2]+=f*(.006*k+.004*cos(8*t+phase))
            if j==1:
                p[2]-=.022*smooth((t-.19)/.31)
                p[0]+=.008*sin(PI*2*t)-.006*t
            p[1]+=.010*sin(phase)*sin(PI*t)
        route[-1,1]+=.016*j-.011;route[-1,0]+=.012*cos(phase)
        chain=spring_chain(cut,'HairJoint_SilkWave_'+str(j),'J_Bip_C_Head',route[2:].tolist(),1.44,.064,.66,[0,1,2,7])
        binding=lambda t:pinned_then_free(chain,head,t,2/9)
        base=mix(PLUM,SHADE,.17+.14*(j%2))
        def tint(t):
            warmth=(.96 if j==1 else .18 if j==0 else .05)*smooth((t-.22)/.23)
            return mix(base,CORAL,warmth)
        # A softly domed central ribbon has enough body in profile, with overlapping
        # narrower cards providing the contour and the visible comb marks.
        route[0]+=[.013,-.006,.017];route[1]+=[.005,0,.007]
        if j==1:
            # The copper emerges below the ear, so the temple stays plum.
            ribbon(mass,route,.021,.0055,lambda t:mix(linear((136,96,108)),np.ones(3),smooth((t-.18)/.32)),
                   binding,j%4,(.93,.01,.35),phase,paint=1)
        else:
            ribbon(mass,route,.022,.006,lambda t:np.ones(3),binding,j%4,(.93,.01,.35),phase,paint=0)
        for m in range(2):
            offset=(m-.5)*.030
            path=route.copy()
            for i,p in enumerate(path):
                t=i/(len(path)-1);fan=smooth(t/.22)
                p[0]+=fan*(offset+.007*sin(8*t+phase+m*.85))
                p[2]-=.004+.0035*fan+.002*cos(7*t+m+phase)
            path[-1,1]+=.021*sin(phase+2.4*m)
            path[-1,0]+=.015*cos(phase+1.4*m)
            def pigment(t):
                amount=.10+.10*cos(m*2.1+phase)
                return mix(tint(t),GLOW,amount)*(1.05+.11*cos(m*1.4))
            ribbon(cards,path,.0056+.0018*cos(phase+m),.0022,pigment,binding,(j+m)%4,(.96,.02,.22),phase+m)
        for m in range(2):
            path=route.copy()
            for i,p in enumerate(path):
                t=i/9;f=smooth((t-.19)/.60)
                p[0]+=(1 if m else -1)*f*(.017+.009*sin(10*t+j))
                p[2]-=.009+.006*f
            path[-1,1]-=.012*(m+1);path[-1,0]+=.009*(-1)**j
            ribbon(cards,path,.0025+.0009*m,.0009,lambda t:mix(tint(t),GLOW,.23),binding,
                   (j+m+2)%4,(1,0,.15),phase+2*m,fine=True)

    # Fine hairs along the hairline step away from the main sweep. They taper
    # before the eye, and do not form a second opaque fringe.
    for side in (-1,1):
        for j in range(4):
            path=np.stack([scalp(side,.008+j*.008,t,.002+j*.0006) for t in steps(.13,.96,8)])
            for i,p in enumerate(path):
                t=i/7
                p[0]-=side*(.002+.002*j)*sin(PI*t)
                p[1]-=(.006+.002*j)*sin(PI*t)
                p[2]-=.0028*sin(PI*t)
            path[-1,1]-=.012+.004*j;path[-1,0]+=.009*side
            ribbon(cards,path,.0016+.00055*j,.0009,lambda t:mix(PLUM,GLOW,.45),fixed,
                   j%4,(1,.09,.15),j,fine=True)
    for side in (-1,1):
        p=np.array([[side*.049,1.606,-.073],[side*.072,1.565,-.085],[side*.091,1.512,-.073],
                    [side*.101,1.452,-.058],[side*.111,1.405,-.061],[side*.092,1.368,-.078],[side*.082,1.355,-.074]])
        if side<0:p[3:,2]-=.008
        chain=spring_chain(cut,'HairJoint_FaceCurl_'+str(side),'J_Bip_C_Head',p[2:].tolist(),1.27,.081,.61,[2,3])
        for m in range(3):
            route=p.copy();route[2:,0]+=side*m*.003;route[3:,2]-=m*.003;route[-1,1]+=.015*m
            ribbon(cards,route,.0065 if m==0 else .0024,.0018,lambda t:mix(PLUM,GLOW,.20+.13*m),
                   lambda t:pinned_then_free(chain,head,t,2/6),(m+2)%4,(1,0,.26*side),m,fine=m>0)
    core.save(fit=False);cap.save(fit=False);mass.save(fit=False);cards.save(fit=False)
