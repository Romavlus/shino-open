"""Humanoid authoring rig in VRMA coordinates (+Y up, +Z towards the audience).
Run inside Blender. All rest lengths come from the distributed CC0 Shino file.
"""
from pathlib import Path
import json
import struct
import math
import numpy as np
from mathutils import Vector, Quaternion, Euler, Matrix

ROOT = Path(__file__).resolve().parents[1]
FPS = 30
IDENTITY = Quaternion((1, 0, 0, 0))

def read_glb(path):
    raw = Path(path).read_bytes()
    magic, version, length, size, tag = struct.unpack_from('<4sIIII', raw)
    if magic != b'glTF' or version != 2 or length != len(raw) or tag != 0x4e4f534a:
        raise ValueError(f'Invalid GLB: {path}')
    return json.loads(raw[20:20+size]), raw[28+size:]

def unpack(gl, binary, index):
    a = gl['accessors'][index]
    view = gl['bufferViews'][a['bufferView']]
    dtype = np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']])
    width = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
    return np.ndarray((a['count'],width),dtype=dtype,buffer=binary,
                      offset=view.get('byteOffset',0)+a.get('byteOffset',0),
                      strides=(view.get('byteStride',width*dtype.itemsize),dtype.itemsize))

def rest_matrices(nodes):
    parents={child:i for i,n in enumerate(nodes) for child in n.get('children',[])}
    world={}
    def visit(i):
        if i not in world:
            n=nodes[i]
            if 'matrix' in n:
                local=Matrix(np.asarray(n['matrix']).reshape(4,4).T.tolist())
            else:
                x,y,z,w=n.get('rotation',(0,0,0,1))
                local=Matrix.LocRotScale(Vector(n.get('translation',(0,0,0))), Quaternion((w,x,y,z)), Vector(n.get('scale',(1,1,1))))
            world[i]=visit(parents[i])@local if i in parents else local
        return world[i]
    for i in range(len(nodes)):visit(i)
    return parents,world

def xyz(x=0,y=0,z=0):
    return Euler(tuple(math.radians(a) for a in (x,y,z)),'XYZ').to_quaternion()

def palm_frame(direction, thumb, side):
    x=direction.normalized()*side
    z=thumb-x*thumb.dot(x)
    if z.length<.01:
        z=Vector((0,1,0))-x*x.y
    z.normalize()
    y=z.cross(x).normalized()
    return Matrix((x,y,z)).transposed().to_quaternion()

class Rig:
    def __init__(self):
        gl,_=read_glb(ROOT/'Assets/Shino.vrm')
        ext=gl['extensions']['VRM']
        if ext['meta']['licenseName']!='CC0' or ext['meta']['title']!='Sendagaya Shino':
            raise ValueError('This rig is fitted to the original CC0 Sendagaya Shino.')
        parent,world=rest_matrices(gl['nodes'])
        mapping={}
        for entry in ext['humanoid']['humanBones']:
            key=entry['bone']
            if 'ThumbProximal' in key:key=key.replace('ThumbProximal','ThumbMetacarpal')
            elif 'ThumbIntermediate' in key:key=key.replace('ThumbIntermediate','ThumbProximal')
            mapping[entry['node']]=key
        self.rest={}
        self.parent={}
        for index,name in mapping.items():
            p=world[index].translation
            self.rest[name]=Vector((-p.x,p.y,-p.z))
            ancestor=parent.get(index)
            while ancestor is not None and ancestor not in mapping:ancestor=parent.get(ancestor)
            self.parent[name]=mapping.get(ancestor)
        def depth(k):
            return 0 if self.parent[k] is None else 1+depth(self.parent[k])
        self.names=sorted(self.rest,key=depth)
        self.offset={n:self.rest[n]-(self.rest[self.parent[n]] if self.parent[n] else Vector()) for n in self.names}
        self.arm_bind={}
        for side,sign in [('left',1),('right',-1)]:
            for name,child in [('UpperArm','LowerArm'),('LowerArm','Hand'),('Hand','MiddleProximal')]:
                v=self.rest[side+child]-self.rest[side+name]
                self.arm_bind[side+name]=palm_frame(v,Vector((0,0,1)),sign).inverted()
        self.nodes=[]
        indices={n:i for i,n in enumerate(self.names)}
        for n in self.names:
            children=[indices[c] for c in self.names if self.parent[c]==n]
            row={'name':n,'translation':list(self.offset[n])}
            if children:row['children']=children
            self.nodes.append(row)
        self.bones={n:{'node':i} for i,n in enumerate(self.names)}

class Pose:
    def __init__(self,rig):
        self.rig=rig
        self.hips=rig.rest['hips'].copy()
        self.q={n:IDENTITY.copy() for n in rig.names}
        self.pos={}; self.rot={}
    def update(self,n):
        parent=self.rig.parent[n]
        if parent:
            self.pos[n]=self.pos[parent]+self.rot[parent]@self.rig.offset[n]
            self.rot[n]=self.rot[parent]@self.q[n]
        else:self.pos[n]=self.hips.copy();self.rot[n]=self.q[n].copy()
    def fk(self):
        for name in self.rig.names:self.update(name)
    def absolute(self,n,q):
        self.q[n]=self.rot[self.rig.parent[n]].inverted()@q
        self.update(n)
    def limb(self,side,arm,target,pole,tip_q):
        n=[side+k for k in (('UpperArm','LowerArm','Hand') if arm else ('UpperLeg','LowerLeg','Foot'))]
        start=self.pos[n[0]]
        straight=target-start
        direction=straight.normalized()
        a=self.rig.offset[n[1]].length;b=self.rig.offset[n[2]].length
        distance=max(abs(a-b)+.0001,min(a+b-.00005,straight.length))
        projected=pole-direction*direction.dot(pole)
        if projected.length<1e-4:projected=Vector((0,0,1))-direction*direction.z
        along=(a*a-b*b+distance*distance)/(2*distance)
        middle=start+direction*along+projected.normalized()*math.sqrt(max(0,a*a-along*along))
        goal=start+direction*distance
        upper=(middle-start).normalized();lower=(goal-middle).normalized()
        if arm:
            sign=1 if side=='left' else -1
            normal=upper.cross(lower).normalized()
            flex=normal.cross(upper).normalized()
            self.absolute(n[0],palm_frame(upper,flex,sign)@self.rig.arm_bind[n[0]])
            self.absolute(n[1],palm_frame(lower,normal.cross(lower),sign)@self.rig.arm_bind[n[1]])
        else:
            for i,d in enumerate((upper,lower)):
                self.absolute(n[i],self.rig.offset[n[i+1]].normalized().rotation_difference(d))
        self.absolute(n[2],tip_q)

def write_motion(path,rig,key,frames):
    data=bytearray();views=[];access=[];channels=[];samplers=[]
    def add(arr,kind):
        arr=np.asarray(arr,dtype='<f4')
        view=len(views); views.append({'buffer':0,'byteOffset':len(data),'byteLength':arr.nbytes});data.extend(arr.tobytes())
        acc={'bufferView':view,'componentType':5126,'count':len(arr),'type':kind}
        if kind=='SCALAR':acc.update(min=[float(arr.min())],max=[float(arr.max())])
        access.append(acc);return len(access)-1
    clock=add(np.arange(len(frames))/FPS,'SCALAR')
    def track(n,prop,values):
        output=add(values,'VEC4' if prop=='rotation' else 'VEC3')
        channels.append({'sampler':len(samplers),'target':{'node':rig.bones[n]['node'],'path':prop}})
        samplers.append({'input':clock,'output':output,'interpolation':'LINEAR'})
    track('hips','translation',[list(f.hips) for f in frames])
    for n in rig.names:
        if n in ('leftEye','rightEye','jaw'):continue
        qs=np.array([tuple(f.q[n].normalized()) for f in frames])[:,[1,2,3,0]]
        for i in range(1,len(qs)):
            if qs[i-1]@qs[i]<0:qs[i]*=-1
        track(n,'rotation',qs)
    gl={'asset':{'version':'2.0','generator':'Shino Blender motion workshop','copyright':'CC0-1.0'},
        'extensionsUsed':['VRMC_vrm_animation'],'extensions':{'VRMC_vrm_animation':{'specVersion':'1.0','humanoid':{'humanBones':rig.bones}}},
        'scene':0,'scenes':[{'nodes':[rig.bones['hips']['node']]}],'nodes':rig.nodes,
        'accessors':access,'bufferViews':views,'buffers':[{'byteLength':len(data)}],
        'animations':[{'name':key,'channels':channels,'samplers':samplers}]}
    header=json.dumps(gl,separators=(',',':')).encode();header+=b' '*(-len(header)%4)
    path.write_bytes(struct.pack('<4sIIII',b'glTF',2,28+len(header)+len(data),len(header),0x4e4f534a)+header+struct.pack('<I4s',len(data),b'BIN\0')+data)
