/* Outer surface of the actual skinned thighs, knees, calves and pelvis, sampled
   along horizontal rays. The table is rebuilt once per pose, not per substep. */
function dressBodySurface(vrm,source,sectors,Vector,prototype){
    const transforms=source.bones.map(([name,bind])=>({
        node:vrm.scene.getObjectByName(name),bind:prototype.clone().fromArray(bind),matrix:prototype.clone()
    }));
    const points=source.vertices.map(row=>({rest:new Vector(...row.slice(0,3)), skin:row.slice(3),pos:new Vector()}));
    const temp=new Vector(),edges=source.edges;
    const angles=sectors*4,planes=32,rows=114,base=-.90,step=.0095,tau=2*Math.PI;
    const depths=new Float32Array(angles*rows),support=new Float32Array(rows*planes);
    const nx=Float64Array.from({length:planes},(_,i)=>Math.sin(i*tau/planes));
    const nz=Float64Array.from({length:planes},(_,i)=>-Math.cos(i*tau/planes));
    const projections=Array.from({length:angles},(_,i)=>{
        const x=Math.sin(i*tau/angles),z=-Math.cos(i*tau/angles),cuts=[];
        for(let j=0;j<planes;j++){const dot=x*nx[j]+z*nz[j];if(dot>.05)cuts.push([j,1/dot])}
        return cuts;
    });
    function update(inverseFrame){
        for(const bone of transforms)bone.matrix.multiplyMatrices(inverseFrame,bone.node.matrixWorld).multiply(bone.bind);
        for(const {rest,skin,pos} of points){
            pos.set(0,0,0);
            for(let i=0;i<skin.length;i+=2)pos.addScaledVector(temp.copy(rest).applyMatrix4(transforms[skin[i]].matrix),skin[i+1]);
        }
        // Cloth spans between the two legs. A radial ray that just misses a
        // kneecap must not interpolate from the kneecap to empty space.
        support.fill(.018);
        for(let k=0;k<edges.length;k+=2){
            let a=points[edges[k]].pos,b=points[edges[k+1]].pos;
            if(a.y>b.y){const swap=a;a=b;b=swap}
            const lo=Math.max(0,Math.floor((a.y-base)/step)),hi=Math.min(rows-1,Math.ceil((b.y-base)/step));
            const height=Math.max(1e-7,b.y-a.y);
            for(let j=lo;j<=hi;j++){
                const t=Math.min(1,Math.max(0,(base+j*step-a.y)/height)),off=j*planes;
                const x=a.x+(b.x-a.x)*t,z=a.z+(b.z-a.z)*t;
                for(let n=0;n<planes;n++){const h=x*nx[n]+z*nz[n];if(h>support[off+n])support[off+n]=h}
            }
        }
        for(let i=0;i<angles;i++)for(let j=0;j<rows;j++){
            let limit=Infinity;const off=j*planes;
            for(const [n,invDot] of projections[i])limit=Math.min(limit,support[off+n]*invDot);
            depths[i*rows+j]=limit;
        }
    }
    function radius(x,y,z){
        const level=(y-base)/step;
        if(level<0 || level>=rows-1)return 0;
        let a=Math.atan2(x,-z)*angles/tau;if(a<0)a+=angles;
        const i=Math.floor(a)%angles,j=Math.floor(level),f=a-Math.floor(a),t=level-j;
        const l=i*rows+j,r=((i+1)%angles)*rows+j;
        return (1-f)*(depths[l]+(depths[l+1]-depths[l])*t)+f*(depths[r]+(depths[r+1]-depths[r])*t);
    }
    return {update,radius};
}

/* Lightweight particle cloth in a gravity-aligned frame. Only the waistband is
   pinned. Warp, weft and bias lengths couple adjacent panels across the wrap. */
function fitHangingDress(vrm,hips,pattern,Vector){
    const {levels,sectors,shell}=pattern,origin=new Vector(...pattern.origin);
    const mat=hips.matrixWorld;
    const frame=mat.clone(),inverse=mat.clone(),oldFrame=mat.clone(),carry=mat.clone(),hipToFrame=mat.clone(),frameToHip=mat.clone();
    const body=dressBodySurface(vrm,pattern.body,sectors,Vector,mat);
    const rings=levels.map((y,r)=>shell[r].map(([x,z],i)=>{
        const length=(levels[0]-y)/(levels[0]-levels.at(-1));
        return {node:vrm.scene.getObjectByName('DressGuide_'+r+'_'+i),rest:new Vector(x,y,z).sub(origin),
                target:new Vector(),p:new Vector(),v:new Vector(),old:new Vector(),offset:new Vector(),
                length,mass:r===0?0:.38+.62*length};
    }));
    const list=rings.flat(),links=[],cells=[],ties=pattern.ties.map(t=>({...t,
        node:vrm.scene.getObjectByName(t.name),p:new Vector(),v:new Vector()}));
    function link(a,b,min,max,strength){
        const distance=a.rest.distanceTo(b.rest);
        links.push({a,b,min:min*distance,max:max*distance,strength});
    }
    for(let r=1;r<rings.length;r++)for(let i=0;i<sectors;i++){
        const j=(i+1)%sectors,a=rings[r-1][i],b=rings[r-1][j],c=rings[r][i],d=rings[r][j];
        link(a,c,.87,1.009,.94);link(c,d,.88,1.05,.66);
        link(a,d,.86,1.06,.37);link(b,c,.86,1.06,.37);
        if(r>1)link(rings[r-2][i],c,.85,1.014,.45);
        cells.push([a,b,c,d]);
    }
    const delta=new Vector(),temp=new Vector(),lift=new Vector(),gravity=new Vector(),oldSlope=new Vector(),newSlope=new Vector();
    const rotation=hips.quaternion.clone(),identity=hips.quaternion.clone().identity();
    let reset=true,previousYaw=0,yawRate=0;
    function constrain(){
        for(const {a,b,min,max,strength} of links){
            delta.subVectors(b.p,a.p);const d=delta.length();
            const limit=Math.max(min,Math.min(max,d));
            if(Math.abs(d-limit)<.00002)continue;
            delta.multiplyScalar(strength*(d-limit)/(Math.max(d,.00001)*(a.mass+b.mass)));
            a.p.addScaledVector(delta,a.mass);b.p.addScaledVector(delta,-b.mass);
        }
    }
    // A knee lifts the panel only when it reaches it. Above the knee the
    // surface normal can point upwards; below it the free hem hangs through.
    function penetration(p){
        const distance=Math.hypot(p.x,p.z),radius=body.radius(p.x,p.y,p.z);
        const depth=radius+.013-distance;
        if(radius===0 || depth<=0 || distance<.001)return false;
        const above=body.radius(p.x,p.y+.012,p.z);
        const slope=above>0?Math.min(1.25,Math.max(0,(radius-above)/.012)):0;
        const radial=depth/(1+slope*slope);
        lift.set(p.x/distance*radial,slope*radial,p.z/distance*radial);
        return true;
    }
    function contact(){
        for(const g of list)if(g.mass && penetration(g.p))g.p.add(lift);
        // The printable surface interpolates four skin guides. Check between
        // them too, where a raised knee may pass through a coarse grid cell.
        function edgeContact(a,b){
            temp.lerpVectors(a.p,b.p,.5);
            if(penetration(temp)){
                const scale=2/(a.mass+b.mass);a.p.addScaledVector(lift,a.mass*scale);b.p.addScaledVector(lift,b.mass*scale);
            }
        }
        for(const [a,b,c,d] of cells){
            edgeContact(a,c);edgeContact(c,d);
            temp.copy(a.p).add(b.p).add(c.p).add(d.p).multiplyScalar(.25);
            if(!penetration(temp))continue;
            const scale=4/(a.mass+b.mass+c.mass+d.mass);
            a.p.addScaledVector(lift,a.mass*scale);b.p.addScaledVector(lift,b.mass*scale);
            c.p.addScaledVector(lift,c.mass*scale);d.p.addScaledVector(lift,d.mass*scale);
        }
    }
    function update(dt,dragX,dragY,cameraYaw){
        hips.updateWorldMatrix(true,true);
        const m=mat.elements,yaw=Math.atan2(m[8],m[10]);
        frame.makeRotationY(yaw).setPosition(m[12],m[13],m[14]);inverse.copy(frame).invert();
        hipToFrame.multiplyMatrices(inverse,mat);frameToHip.copy(hipToFrame).invert();
        carry.multiplyMatrices(inverse,oldFrame);
        const turn=Math.atan2(Math.sin(yaw-previousYaw),Math.cos(yaw-previousYaw));
        if(!reset && !dt)return;
        if(reset)yawRate=0;
        else yawRate+=(Math.max(-6,Math.min(6,turn/dt))-yawRate)*-Math.expm1(-dt*10);
        oldFrame.copy(frame);previousYaw=yaw;body.update(inverse);
        for(let r=0;r<rings.length;r++)for(let i=0;i<sectors;i++){
            const g=rings[r][i],top=rings[0][i];
            g.target.copy(g.rest).applyMatrix4(hipToFrame);
            temp.copy(top.target).add(g.rest).sub(top.rest);
            const free=Math.min(1,g.length*3.2);g.target.lerp(temp,free*free*(3-2*free));
            if(reset || !g.mass){g.p.copy(g.target);g.v.set(0,0,0)}
            else{
                // Moving the support carries the yoke. The free end retains
                // more of its world-space position while the wearer turns.
                temp.copy(g.p).applyMatrix4(carry);
                g.p.lerp(temp,.12+.73*g.length);
                const e=carry.elements,vx=g.v.x,vz=g.v.z;g.v.x=e[0]*vx+e[8]*vz;g.v.z=e[2]*vx+e[10]*vz;
            }
        }
        const steps=Math.max(1,Math.ceil(dt*90)),h=dt/steps;
        const pull=yaw-cameraYaw;
        gravity.set(Math.cos(pull)*dragX,0,Math.sin(pull)*dragX);
        for(let n=0;n<steps;n++){
            for(const g of list){
                if(!g.mass)continue;
                g.old.copy(g.p);const l=g.length;
                const k=42+135*(1-l)*(1-l);
                delta.subVectors(g.target,g.p).multiplyScalar(k);
                delta.y-=5*l;delta.y+=.82*dragY*l;delta.addScaledVector(gravity,1.8*l);
                g.v.multiplyScalar(Math.exp(-h*(7+6*(1-l)))).addScaledVector(delta,h);
                g.p.addScaledVector(g.v,h);
            }
            for(let j=0;j<(reset?9:3);j++){constrain();contact()}
            if(h>0 && !reset)for(const g of list)if(g.mass)g.v.subVectors(g.p,g.old).multiplyScalar(1/h).clampLength(0,2.5);
        }
        for(const g of list)g.offset.copy(g.p).applyMatrix4(frameToHip).sub(g.rest);
        for(let r=0;r<rings.length;r++)for(let i=0;i<sectors;i++){
            const g=rings[r][i],a=rings[Math.max(0,r-1)][i],b=rings[Math.min(rings.length-1,r+1)][i];
            oldSlope.subVectors(b.rest,a.rest);newSlope.copy(oldSlope).add(b.offset).sub(a.offset).normalize();
            rotation.setFromUnitVectors(oldSlope.normalize(),newSlope);
            g.node.quaternion.slerpQuaternions(identity,rotation,.50*g.length);
            g.node.position.copy(g.rest).sub(temp.copy(g.rest).applyQuaternion(g.node.quaternion)).add(g.offset);
        }
        for(const tie of ties){
            const l=tie.length;
            temp.set(.0035*yawRate+.014*gravity.x,.0015*Math.abs(yawRate)+.003*dragY,.008*gravity.z+tie.side*.002*yawRate)
                .addScaledVector(rings[3][0].v,.012).multiplyScalar(l*l);
            if(reset){tie.p.set(0,0,0);tie.v.set(0,0,0)}
            for(let j=0;j<steps;j++){delta.subVectors(temp,tie.p).multiplyScalar(115).addScaledVector(tie.v,-13);
                tie.v.addScaledVector(delta,h);tie.p.addScaledVector(tie.v,h)}
            tie.node.position.copy(tie.p);
        }
        reset=false;
    }
    function measure(){
        const displacement=row=>Math.max(...row.map(g=>g.offset.length()));
        const knees=rings.filter((_,i)=>levels[i]>=.45 && levels[i]<=.65);
        return {waist:displacement(rings[0]),hem:displacement(rings.at(-1)),ties:ties.map(t=>t.p.length()),
                kneeFront:Math.max(...knees.flatMap(row=>row.map(g=>-g.p.z)))};
    }
    return {update,measure,gaitScale:1,liftScale:1,sleevePadding:pattern.sleevePadding,reset(){reset=true}};
}
