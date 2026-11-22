function fitArmContacts(vrm, Vector, limbs, steer, padding=0) {
    const bone = name => vrm.humanoid.getNormalizedBoneNode(name);
    const upperChest=bone('upperChest');
    const chest = bone('chest'), hips = bone('hips'), head = bone('head');
    const profile = shinoSections.map(row => row.map(n => n / 1000));
    // The lower pleats are spring-driven. Leave room for their outward swing at
    // the hip and hem; the front of the fitted vest keeps its measured outline.
    const restProfile=profile.map(row=>row.slice());
    const swing=profile.map(row=>row.map((_,j)=>Math.min(1,Math.max(0,(-row[0]-.10)/.11))*(.015+.044*Math.sin((j-1)*Math.PI/8)**2)));
    let lastRoom=-1;
    function setRoom(room){
        if(room===lastRoom)return;
        lastRoom=room;
        for(let i=0;i<profile.length;i++)for(let j=1;j<profile[i].length;j++)
            profile[i][j]=restProfile[i][j]+room*swing[i][j];
    }
    setRoom(1);
    const slopePads=profile.slice(1).map((row,i)=>row.map((d,j)=>
        Math.min(1.55,Math.hypot(1,(d-profile[i][j])/(row[0]-profile[i][0])))));
    const hipBind = new Vector(...shinoHip);
    const dirs = Array.from({length:16}, (_, i) => [Math.sin(i*Math.PI/8), -Math.cos(i*Math.PI/8), Math.min(i,16-i)+1]);
    const invChest = chest.matrixWorld.clone(), toHip = invChest.clone(), toChest = invChest.clone();
    const toHead = invChest.clone(), fromHead = invChest.clone();
    const inHip = new Vector(), point = new Vector(), local = new Vector(), shift = new Vector(), moved = new Vector();
    const axis = new Vector(), otherAxis = new Vector(), gap = new Vector(), goal = new Vector();
    const parentOrientation=chest.quaternion.clone();
    const clamp = x => Math.max(0, Math.min(1, x));
    const intoChest = (node, out) => out.setFromMatrixPosition(node.matrixWorld).applyMatrix4(invChest);
    const wristSwing=parentOrientation.clone(), identity=parentOrientation.clone().identity();
    const sleeve=.028+padding;
    const sections=[[0,.032+padding],[.30,.034+padding],[.60,.030+padding],[.83,.023+padding*.8],[1,.019+padding*.3]];
    const pairs = [[1,1],[2,1],[1,2],[2,2],[0,2],[2,0]];
    const arms = limbs.map((limb,i) => {
        const side=i===0?'left':'right';
        const samples=['Index','Middle','Ring','Little','Thumb'].flatMap(digit =>
            ['Proximal','Distal'].map(part=>({node:bone(side+digit+part),
                previous:part==='Distal'?bone(side+digit+(digit==='Thumb'?'Proximal':'Intermediate')):null,
                extension:digit==='Thumb'?.015:.020,offset:new Vector(),pad:part==='Distal'?.013:.022})));
        return {limb, sign:i===0?-1:1, samples, s:new Vector(), e:new Vector(), w:new Vector(),
            e0:new Vector(), w0:new Vector(), tip:new Vector(), tipOffset:new Vector(),
            lastElbow:new Vector(),lastWrist:new Vector(),
            orientation:chest.quaternion.clone(), forward:0, upper:0, lower:0};
    });
    let fitted=false;
    // Signed support planes also fit the flatter lapels and the flared hem. If
    // a segment crosses the midline, escape towards the front of the vest.
    function garmentPush(p, pad, arm) {
        local.copy(p);
        inHip.copy(p).applyMatrix4(toHip).add(hipBind);
        // A bent or turned waist can bring the hem up alongside the ribs.
        // Its hip-space height identifies the right cloth section on both sides.
        const follow=clamp((.003-Math.min(p.y,inHip.y))/.098)*(1-clamp((p.y-.018)/.046));
        if(follow) local.lerp(inHip,follow);
        const y=local.y;
        if(y<profile[0][0]-.015 || y>profile.at(-1)[0]+.012) return false;
        let lo=0,hi=profile.length-1;
        while(hi-lo>1){const mid=(lo+hi)>>1;if(profile[mid][0]<=y)lo=mid;else hi=mid}
        const low=profile[lo], high=profile[hi], t=clamp((y-low[0])/(high[0]-low[0]));
        const front=low[1]+(high[1]-low[1])*t, back=low[9]+(high[9]-low[9])*t;
        const side=low[5]+(high[5]-low[5])*t;
        const slope=slopePads[lo];
        if(Math.abs(local.x)>side+pad*slope[5] || local.z>back+pad*slope[9] || -local.z>front+pad*slope[1])return false;
        const midZ=(back-front)*.5;
        let dx=local.x/(side+.002),dz=(local.z-midZ)/((front+back)*.5+.002);
        const route=arm.forward*clamp((.15-local.z)/.10);
        dx+=(arm.sign*.18)*clamp(1-Math.abs(dx)*2)*(1-route);
        dz=dz*(1-route)-route;
        const mag=Math.hypot(dx,dz);
        if(mag<.00001){dx=arm.sign;dz=0}else{dx/=mag;dz/=mag}
        let distance=Infinity;
        for(const [nx,nz,col] of dirs){
            const depth=low[col]+(high[col]-low[col])*t+pad*slope[col]-local.x*nx-local.z*nz;
            if(depth<=.00015)return false;
            const along=dx*nx+dz*nz;
            if(along>.00001)distance=Math.min(distance,depth/along);
        }
        shift.set(dx*distance,0,dz*distance);
        if(follow){
            // Rotate the correction back from the pelvic frame, without translation.
            const m=toChest.elements, x=shift.x,z=shift.z;
            moved.set(m[0]*x+m[8]*z,m[1]*x+m[9]*z,m[2]*x+m[10]*z);
            shift.lerp(moved,follow);
        }
        return true;
    }
    function headPush(p,pad) {
        local.copy(p).applyMatrix4(toHead);
        local.y-=.051;local.z-=.001;
        const rx=.095+pad,ry=.115+pad,rz=.098+pad;
        const r=Math.hypot(local.x/rx,local.y/ry,local.z/rz);
        if(r>=1)return false;
        if(r<.001)local.set(0,0,-rz);
        else local.multiplyScalar(1/r-1);
        const m=fromHead.elements,{x,y,z}=local;
        shift.set(m[0]*x+m[4]*y+m[8]*z,m[1]*x+m[5]*y+m[9]*z,m[2]*x+m[6]*y+m[10]*z);
        return true;
    }
    function push(p,pad,arm) {
        return (p.y>.145 && headPush(p,pad)) || garmentPush(p,pad,arm);
    }
    function fitSegment(arm, t, pad) {
        point.lerpVectors(arm.e,arm.w,t);
        if(!push(point,pad,arm))return false;
        const norm=(1-t)*(1-t)+t*t;
        arm.e.addScaledVector(shift,(1-t)/norm);
        arm.w.addScaledVector(shift,t/norm);
        return true;
    }
    function bodyContact(arm) {
        let hit=false;
        // The shoulder is a sewn joint. Start measuring the sleeve below the cap.
        point.lerpVectors(arm.s,arm.e,.67);
        if(push(point,sleeve*.72,arm)){arm.e.addScaledVector(shift,1/.67);hit=true}
        for(const [t,pad] of sections)if(fitSegment(arm,t,pad))hit=true;
        for(const sample of arm.samples){
            point.copy(arm.w).add(sample.offset);
            if(push(point,sample.pad,arm)){arm.w.add(shift);hit=true}
        }
        return hit;
    }
    function lengths(arm) {
        // Position constraints keep both bone lengths and the authored elbow bend.
        axis.subVectors(arm.w,arm.e);
        const len=axis.length();
        if(len>1e-7){
            axis.multiplyScalar((len-arm.lower)/len);
            arm.e.addScaledVector(axis,.45);arm.w.addScaledVector(axis,-.55);
        }
        arm.e.sub(arm.s).setLength(arm.upper).add(arm.s);
    }
    function separate(first,second,kindA,kindB,cold) {
        const end = (arm,kind) => kind===0 ? arm.e : kind===1 ? arm.w : arm.tip.copy(arm.w).add(arm.tipOffset);
        const start = (arm,kind) => kind===0 ? arm.s : kind===1 ? arm.e : arm.w;
        const a=start(first,kindA), b=start(second,kindB);
        axis.subVectors(end(first,kindA),a);otherAxis.subVectors(end(second,kindB),b);gap.subVectors(a,b);
        const aa=axis.lengthSq(),bb=otherAxis.lengthSq(),ab=axis.dot(otherAxis);
        const ag=axis.dot(gap),bg=otherAxis.dot(gap),det=aa*bb-ab*ab;
        let u=det>1e-9?clamp((ab*bg-bb*ag)/det):.5;
        let v=clamp((ab*u+bg)/bb);u=clamp((ab*v-ag)/aa);
        gap.addScaledVector(axis,u).addScaledVector(otherAxis,-v);
        const d=gap.length();
        const radius=k=>k===2?.020:k===0?.036:sleeve;
        const need=radius(kindA)+radius(kindB)-d;
        if(need<=.0003)return false;
        if(d>.00001)gap.multiplyScalar(1/d);else gap.set(0,1,0);
        // For the shivering embrace keep a consistent over/under order while
        // the two forearms cross. Elsewhere retain the performer's contact side.
        if(cold>.001 && kindA>0 && kindB>0){
            gap.lerp(moved.set(0,.83,-.56),cold).normalize();
        }
        const move=(arm,kind,t,amount)=>{
            if(kind===0){arm.e.addScaledVector(gap,amount*Math.min(1.4,t*1.6));return}
            if(kind===2){arm.w.addScaledVector(gap,amount);return}
            const n=(1-t)*(1-t)+t*t;
            arm.e.addScaledVector(gap,amount*(1-t)/n);arm.w.addScaledVector(gap,amount*t/n);
        };
        const share=kindA===0?.10:kindB===0?.90:.50;
        move(first,kindA,u,need*share);move(second,kindB,v,-need*(1-share));
        return true;
    }
    return function apply(cold,dt,quiet,acting,gait) {
        chest.updateWorldMatrix(true,true);
        invChest.copy(chest.matrixWorld).invert();
        toHip.copy(hips.matrixWorld).invert().multiply(chest.matrixWorld);
        toChest.copy(toHip).invert();
        toHead.copy(head.matrixWorld).invert().multiply(chest.matrixWorld);
        fromHead.copy(toHead).invert();
        const carry=fitted && dt>0 ? Math.exp(-dt*16) : 0;
        fitted=false;
        let restingHand=0;
        for(const arm of arms){
            const {limb}=arm;
            if(acting){
                const wrist=upperChest.worldToLocal(limb.hand.bone.getWorldPosition(point));
                const distance=Math.hypot(Math.abs(wrist.x)-.19,wrist.y+.346,wrist.z);
                restingHand=Math.max(restingHand,1-clamp((distance-.014)/.065));
            }
            intoChest(limb.arm.bone,arm.s);intoChest(limb.elbow.bone,arm.e);intoChest(limb.hand.bone,arm.w);
            arm.e0.copy(arm.e);arm.w0.copy(arm.w);
            arm.upper=arm.s.distanceTo(arm.e);arm.lower=arm.e.distanceTo(arm.w);
            arm.forward=clamp((.105-arm.sign*arm.w.x)/.12)*clamp((.105-arm.w.z)/.085);
            for(const sample of arm.samples){
                intoChest(sample.node,sample.offset);
                if(sample.previous){
                    axis.subVectors(sample.offset,intoChest(sample.previous,point)).setLength(sample.extension);
                    sample.offset.add(axis);
                }
                sample.offset.sub(arm.w);
            }
            arm.tipOffset.copy(arm.samples[3].offset);
            if(carry){
                arm.e.addScaledVector(arm.lastElbow,carry);
                arm.w.addScaledVector(arm.lastWrist,carry);
            }
        }
        setRoom(1-clamp(quiet+acting*restingHand));
        for(let i=0;i<12;i++){
            let hit=bodyContact(arms[0]);
            if(bodyContact(arms[1]))hit=true;
            for(const [a,b] of pairs){
                if(separate(arms[0],arms[1],a,b,cold))hit=true;
            }
            if(!hit && i===0 && !carry)return;
            for(const arm of arms)lengths(arm);
            if(!hit && arms.every(arm=>Math.abs(arm.e.distanceTo(arm.w)-arm.lower)<.0002))break;
        }
        for(const arm of arms){
            arm.lastElbow.subVectors(arm.e,arm.e0);
            arm.lastWrist.subVectors(arm.w,arm.w0);
            if(arm.e.distanceToSquared(arm.e0)+arm.w.distanceToSquared(arm.w0)<1e-9)continue;
            fitted=true;
            const {limb}=arm,hand=limb.hand.bone;
            hand.getWorldQuaternion(arm.orientation);
            steer(limb.arm.bone,limb.elbow.bone,goal.copy(arm.e).applyMatrix4(chest.matrixWorld),1);
            steer(limb.elbow.bone,hand,goal.copy(arm.w).applyMatrix4(chest.matrixWorld),1);
            if(gait>0){
                // Carry the palm with the corrected forearm while keeping its authored wrist flex.
                axis.subVectors(arm.w0,arm.e0).transformDirection(chest.matrixWorld);
                otherAxis.subVectors(arm.w,arm.e).transformDirection(chest.matrixWorld);
                wristSwing.setFromUnitVectors(axis,otherAxis).slerp(identity,1-clamp(gait));
                arm.orientation.premultiply(wristSwing);
            }
            hand.parent.getWorldQuaternion(parentOrientation);
            hand.quaternion.copy(parentOrientation.invert()).multiply(arm.orientation);
            hand.updateWorldMatrix(false,true);
        }
    };
}
