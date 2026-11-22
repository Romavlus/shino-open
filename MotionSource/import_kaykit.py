"""Extract the used CC0 keyframes from KayKit Character Animations 1.1.
blender -b -P import_kaykit.py -- /path/to/gltf/Rig_Medium
"""
from pathlib import Path
import sys, json, bisect, math
sys.path.insert(0,str(Path(__file__).parent))
from rig import ROOT, FPS, read_glb, rest_matrices, unpack
from mathutils import Quaternion, Vector, Matrix

def quat(v):
    return Quaternion((v[3],v[0],v[1],v[2])).normalized()

def extract(p, take):
    gl,binary=read_glb(p);nodes=gl['nodes'];parents,bind=rest_matrices(nodes)
    anim=next(a for a in gl['animations'] if a['name']==take)
    channels={}
    for c in anim['channels']:
        s=anim['samplers'][c['sampler']]
        if s.get('interpolation','LINEAR')!='LINEAR':raise ValueError(take)
        channels[c['target']['node'],c['target']['path']]=(unpack(gl,binary,s['input'])[:,0].tolist(),unpack(gl,binary,s['output']))
    length=max(times[-1] for times,values in channels.values())
    source={n['name']:i for i,n in enumerate(nodes)}
    mapping={'hips':'hips','chest':'chest','spine':'spine','head':'head'}
    for side,suffix in [('left','.l'),('right','.r')]:
        for k in ['UpperArm','LowerArm','Hand','UpperLeg','LowerLeg','Foot','Toes']:mapping[side+k]=k.lower()+suffix
    keys=list(mapping);inverse={source[n]:k for k,n in mapping.items()}
    parent_h={}
    for k,name in mapping.items():
        a=parents.get(source[name])
        while a is not None and a not in inverse:a=parents.get(a)
        parent_h[k]=inverse.get(a)
    def local(i,prop,t):
        default={'rotation':(0,0,0,1),'translation':(0,0,0),'scale':(1,1,1)}
        convert=quat if prop=='rotation' else Vector
        if (i,prop) not in channels:return convert(nodes[i].get(prop,default[prop]))
        times,values=channels[i,prop];j=max(0,bisect.bisect_right(times,t)-1)
        a=convert(values[j])
        if j+1==len(times):return a
        b=convert(values[j+1]);u=(t-times[j])/(times[j+1]-times[j])
        return a.slerp(b,u) if prop=='rotation' else a.lerp(b,u)
    frames=[]
    for f in range(round(length*FPS)+1):
        t=min(f/FPS,length);world={}
        def matrix(i):
            if i not in world:
                m=Matrix.LocRotScale(local(i,'translation',t),local(i,'rotation',t),local(i,'scale',t))
                world[i]=matrix(parents[i])@m if i in parents else m
            return world[i]
        rotations={k:matrix(source[n]).to_quaternion()@bind[source[n]].to_quaternion().inverted() for k,n in mapping.items()}
        relative=[rotations[parent_h[k]].inverted()@rotations[k] if parent_h[k] else rotations[k] for k in keys]
        frames.append([[round(x,6) for x in q.normalized()] for q in relative])
    return {'bones':keys,'frames':frames}
if __name__=='__main__':
    source=Path(sys.argv[sys.argv.index('--')+1]);spec={'wave':('Simulation','Waving'),'sneak':('MovementAdvanced','Sneaking'),'walk':('MovementBasic','Walking_A')}
    data={k:extract(source/('Rig_Medium_'+pack+'.glb'),take) for k,(pack,take) in spec.items()}
    (ROOT/'MotionSource/kaykit.json').write_text(json.dumps(data,separators=(',',':')))
