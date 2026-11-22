"""Combine adjacent draw calls with identical materials and vertex/morph streams.
Texture data, triangle order, expressions, skinning weights and the rig are retained intact.
"""
import itertools, json, struct


def register_face_controls(gl):
    """Expose Shino's existing local facial shapes to the VRM expression mixer."""
    names = {
        'closedSmile': 'MTH_Fun', 'openSmile': 'MTH_Joy', 'lipPress': 'MTH_Neutral',
        'smilingEyes': 'EYE_Joy', 'wideEyes': 'EYE_Surprised', 'softEyes': 'EYE_Sorrow',
        'browLift': 'BRW_Surprised', 'browWarm': 'BRW_Joy',
        'browWorry': 'BRW_Sorrow', 'browFocus': 'BRW_Angry',
    }
    mesh_id = next(i for i, mesh in enumerate(gl['meshes']) if mesh['name'] == 'Face.baked')
    primitives = gl['meshes'][mesh_id]['primitives']
    targets = primitives[0]['extras']['targetNames']
    if any(p['extras']['targetNames'] != targets for p in primitives):
        raise ValueError('The face primitives have different shape orders')
    indices = {name.rsplit('_Fcl_', 1)[-1]: i for i, name in enumerate(targets)}
    groups = gl['extensions']['VRM']['blendShapeMaster']['blendShapeGroups']
    for name, target in names.items():
        groups.append({'name': name, 'presetName': 'unknown', 'isBinary': False,
                       'binds': [{'mesh': mesh_id, 'index': indices[target], 'weight': 100}],
                       'materialValues': []})

def optimize_model(source, destination):
    raw=source.read_bytes()
    size=struct.unpack_from('<I',raw,12)[0]
    gl=json.loads(raw[20:20+size])
    register_face_controls(gl)
    binary=bytearray(raw[28+size:28+size+gl['buffers'][0]['byteLength']])
    for mesh in gl['meshes']:
        def signature(p):return {k:v for k,v in p.items() if k!='indices'}
        out=[]
        for _,group in itertools.groupby(mesh['primitives'],key=signature):
            parts=list(group)
            if len(parts)==1:
                out.append(parts[0]);continue
            arrays=[gl['accessors'][p['indices']] for p in parts]
            component=arrays[0]['componentType']
            if any(a['type']!='SCALAR' or a['componentType']!=component or 'sparse' in a for a in arrays):
                out.extend(parts);continue
            width={5121:1,5123:2,5125:4}[component]
            buf=bytearray()
            for a in arrays:
                view=gl['bufferViews'][a['bufferView']]
                if view.get('byteStride',width)!=width:raise ValueError('Interleaved index data')
                start=view.get('byteOffset',0)+a.get('byteOffset',0)
                buf.extend(binary[start:start+a['count']*width])
            binary.extend(bytes(-len(binary)%4))
            gl['bufferViews'].append({'buffer':0,'byteOffset':len(binary),'byteLength':len(buf),'target':34963})
            access={'bufferView':len(gl['bufferViews'])-1,'componentType':component,'count':sum(a['count'] for a in arrays),'type':'SCALAR'}
            gl['accessors'].append(access);binary.extend(buf)
            out.append({**parts[0],'indices':len(gl['accessors'])-1})
        mesh['primitives']=out
    binary.extend(bytes(-len(binary)%4));gl['buffers'][0]['byteLength']=len(binary)
    head=json.dumps(gl,separators=(',',':')).encode();head+=b' '*(-len(head)%4)
    destination.write_bytes(struct.pack('<4sIIII',b'glTF',2,28+len(head)+len(binary),len(head),0x4e4f534a)+head+struct.pack('<I4s',len(binary),b'BIN\0')+binary)
