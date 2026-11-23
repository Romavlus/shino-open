"""Build the cloth collision surface and transfer weights from Shino's body."""
import numpy as np


def body_collider(cut,positions,triangles):
    # Horizontal intersections of these original skinned edges describe the
    # complete calf, knee, thigh and hip silhouettes, including bent poses.
    height=positions[triangles,1]
    faces=triangles[(height.max(1)>.12)&(height.min(1)<1.105)]
    original=np.unique(faces);joints={};vertices=[];welded={};mapping={}
    for v in original:
        weights={}
        for bone,weight in zip(cut.source_joints[v],cut.source_weights[v]):
            if weight:weights[int(bone)]=weights.get(int(bone),0)+float(weight)
        row=[round(float(x),6) for x in positions[v]]
        for bone,weight in sorted(weights.items()):
            if bone not in joints:joints[bone]=len(joints)
            row.extend([joints[bone],round(weight,6)])
        key=tuple(row)
        if key not in welded:
            welded[key]=len(vertices);vertices.append(row)
        mapping[v]=welded[key]
    edges=set()
    for a,b,c in faces:
        for j,k in ((a,b),(b,c),(c,a)):
            x,y=mapping[j],mapping[k]
            if x!=y:edges.add((min(x,y),max(x,y)))
    return dict(vertices=vertices,edges=np.array(sorted(edges)).ravel().tolist(),
                bones=[[cut.bones[j],cut.matrices[j].tolist()] for j in joints])


class GarmentFit:
    """Transfer the deformation of the closest body triangle to close-fitting cloth."""
    def __init__(self,cut,positions,normals,faces):
        self.cut=cut
        self.faces=faces
        self.positions=positions
        self.normals=normals
        self.grid={}
        self.width=.068
        triangles=positions[faces]
        for i,(lo,hi) in enumerate(zip(triangles.min(1),triangles.max(1))):
            start=np.floor((lo-.062)/self.width).astype(int);end=np.floor((hi+.062)/self.width).astype(int)
            for x in range(start[0],end[0]+1):
                for y in range(start[1],end[1]+1):
                    for z in range(start[2],end[2]+1):
                        self.grid.setdefault((x,y,z),[]).append(i)

    def closest(self,points,indices):
        f=self.faces[indices];a,b,c=self.positions[f].transpose(1,0,2)
        ab=b-a;ac=c-a;ap=points[:,None,:]-a
        ab2=(ab*ab).sum(1);ac2=(ac*ac).sum(1);dot=(ab*ac).sum(1)
        d=(ab2*ac2-dot*dot).clip(1e-14)
        x=np.einsum('nki,ki->nk',ap,ab);y=np.einsum('nki,ki->nk',ap,ac)
        v=(ac2*x-dot*y)/d;w=(ab2*y-dot*x)/d
        dist=np.sum((ap-v[:,:,None]*ab-w[:,:,None]*ac)**2,axis=2)
        dist[(v<0)|(w<0)|(v+w>1)]=np.inf
        for j,(s,e) in enumerate(((a,b),(b,c),(c,a))):
            edge=e-s;relative=points[:,None,:]-s
            t=np.clip(np.einsum('nki,ki->nk',relative,edge)/np.maximum(1e-14,np.sum(edge*edge,axis=1)),0,1)
            dt=np.sum((relative-t[:,:,None]*edge)**2,axis=2);use=dt<dist
            dist[use]=dt[use]
            uv=((t,0),(1-t,t),(0,1-t))[j]
            for arr,val in zip((v,w),uv):arr[use]=val[use] if isinstance(val,np.ndarray) else val
        k=dist.argmin(1);n=np.arange(len(k));v=v[n,k];w=w[n,k]
        return f[k],np.column_stack([1-v-w,v,w])

    def tailor(self,points,influences,material,allowance=None):
        # The skirt and ribbon have their own cloth rig. The boot shaft, sleeves
        # and bodice need the same bend, twist and bust weights as the body below.
        selected=np.flatnonzero((points[:,1]>1.044) | (points[:,1]<.225))
        cells={}
        for i in selected:
            cell=tuple(np.floor(points[i]/self.width).astype(int))
            cells.setdefault(cell,[]).append(int(i))
        is_knit='Knit' in material or 'Button' in material
        for cell,ids in cells.items():
            indices=self.grid.get(cell)
            if not indices:continue
            for start in range(0,len(ids),96):
                part=ids[start:start+96];p=points[part]
                f,bary=self.closest(p,indices)
                surface=np.einsum('nij,ni->nj',self.positions[f],bary)
                normals=np.einsum('nij,ni->nj',self.normals[f],bary)
                normals/=np.maximum(1e-9,np.linalg.norm(normals,axis=1))[:,None]
                gap=((p-surface)*normals).sum(1)
                for j,i in enumerate(part):
                    x,y,z=p[j];shoe=y<.225
                    fade=1. if shoe else min(1.,max(0.,(y-1.044)/.059))
                    # Add only ease. The drafted flare and gathers keep their cut.
                    if allowance is not None:ease=allowance
                    elif shoe:ease=.0035
                    elif is_knit and abs(x)>.508:ease=.0018+.0102*max(0.,(.532-abs(x))/.024)
                    else:ease=.021 if is_knit and abs(x)<.158 else .012
                    points[i]+=normals[j]*max(0.,ease-gap[j])*fade
                    if shoe:points[i,1]=max(.0004,points[i,1])
                    merged={}
                    for k,t in influences[i]:merged[k]=(1-fade)*t
                    for vertex,fraction in zip(f[j],bary[j]):
                        for k,t in zip(self.cut.source_joints[vertex],self.cut.source_weights[vertex]):
                            if t>0:merged[int(k)]=merged.get(int(k),0)+fade*fraction*float(t)
                    values=sorted(merged.items(),key=lambda pair:-pair[1])[:4];total=sum(q for _,q in values)
                    influences[i]=[(k,q/total) for k,q in values if q>1e-7]
