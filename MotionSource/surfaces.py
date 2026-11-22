"""Fit the contact planes and shoe sole to Shino's actual skinned meshes."""
import json, math
import numpy as np
from mathutils import Vector
from rig import ROOT, read_glb, unpack, rest_matrices

class Surfaces:
    def __init__(self,rig):
        gl,bin=read_glb(ROOT/'Assets/Shino.vrm')
        parent,world=rest_matrices(gl['nodes'])
        hum={b['node']:b['bone'] for b in gl['extensions']['VRM']['humanoid']['humanBones']}
        body=next(n for n in gl['nodes'] if n.get('name')=='Body')
        skin=gl['skins'][body['skin']]['joints']
        prim=gl['meshes'][body['mesh']]['primitives']
        offsets=prim[0]['attributes']
        pos=unpack(gl,bin,offsets['POSITION'])
        joints=unpack(gl,bin,offsets['JOINTS_0'])
        weights=unpack(gl,bin,offsets['WEIGHTS_0'])
        def used(slots):
            return np.unique(np.concatenate([unpack(gl,bin,p['indices'])[:,0] for p in prim if p['material'] in slots]))
        shoe=used([13]);self.shoes=[]
        names=[]
        for node in skin:
            while node not in hum and node in parent:node=parent[node]
            names.append(hum.get(node,'hips'))
        for side in ('left','right'):
            indices=shoe[pos[shoe,0]*(1 if side=='right' else -1)>0]
            for name in [side+k for k in ('UpperLeg','LowerLeg','Foot','Toes')]:
                mask=(np.array(names)[joints[indices]]==name)*weights[indices]
                # Evaluate the fully skinned sole below, even when a vertex crosses the toe joint.
                if mask.max()==0:continue
                self.shoes.append((name,indices,mask.sum(axis=1)))
        self.sole={}
        for side in ('left','right'):
            entries=[e for e in self.shoes if e[0].startswith(side)]
            idx=entries[0][1]
            calibrated=np.asarray(pos[idx])*[-1,1,-1]
            self.sole[side]=[(name,w[:,None],calibrated-np.array(rig.rest[name])) for name,_,w in entries]
            if not np.allclose(sum(e[1] for e in self.sole[side]),1,atol=.001):raise ValueError('Unmapped shoe influence')
        chest=np.array(rig.rest['chest'])*[-1,1,-1]
        points=pos-chest
        limbs=np.array([any(part in n for part in ('Arm','Hand','Thumb','Index','Middle','Ring','Little')) for n in names])
        arm_weight=(limbs[joints]*weights).sum(axis=1)
        triangles=[]
        for p in prim:
            if p['material'] not in (9,10,11,12):continue
            idx=unpack(gl,bin,p['indices']).reshape(-1,3)
            if p['material']!=12:
                idx=idx[np.max(arm_weight[idx],axis=1)<.46]
            if p['material']==9:
                idx=idx[(points[idx,1].min(axis=1)>-.035) & (abs(points[idx,0]).max(axis=1)<.135)]
            triangles.extend(idx)
        faces=points[np.asarray(triangles)]
        edges=np.concatenate([faces[:,(0,1)],faces[:,(1,2)],faces[:,(2,0)]])
        profile=[]
        for y in np.arange(faces[:,:,1].min()+.0001,.251,.014):
            crossing=edges[(edges[:,0,1]>y)!=(edges[:,1,1]>y)]
            if len(crossing)<4:continue
            a,b=crossing[:,0],crossing[:,1]
            section=a+(b-a)*((y-a[:,1])/(b[:,1]-a[:,1]))[:,None]
            radii=[]
            for i in range(9):
                phi=i*math.pi/8
                radii.append(round(1000*np.max(abs(section[:,0])*math.sin(phi)-section[:,2]*math.cos(phi))))
            profile.append([round(1000*y),*radii])
        hip=rig.rest['hips']-rig.rest['chest']
        (ROOT/'Source/fit.js').write_text('const shinoSections='+json.dumps(profile)+';\nconst shinoHip='+json.dumps([-hip.x,hip.y,-hip.z])+';\n')
    def plant(self,pose,flight):
        pose.fk()
        low=10
        for side,entries in self.sole.items():
            surface=sum(w[:,0]*(local@np.array(pose.rot[name].to_matrix())[1]+pose.pos[name].y) for name,w,local in entries)
            low=min(low,surface.min())
        pose.hips.y+=float(flight+.0007-low)
