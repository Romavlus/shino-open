async function startPet() {
    const {Renderer,Scene,Camera,Sun,Sky,Loader,AvatarLoader,MotionLoader,clip,Mixer,Vector} = window.ShinoRuntime;
    let studio=location.pathname.endsWith('studio.html') && !new URLSearchParams(location.search).has('desktop');
    const send=(type,value)=>window.webkit.messageHandlers.pet.postMessage({type,value});
    const renderer=new Renderer({alpha:true,antialias:true});
    renderer.setClearColor(0,0);
    renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
    (document.querySelector('#stage')||document.body).append(renderer.domElement);
    const scene=new Scene(),camera=new Camera(32,1,.05,30);
    const lighting=shinoLighting(renderer,scene,camera,Sun,Sky,Vector);
    function render(){lighting.aim();renderer.render(scene,camera)}
    const loader=new Loader().register(p=>new AvatarLoader(p));
    const motions=new Loader().register(p=>new MotionLoader(p));
    const files=['idle_loop.vrma','walk.vrma','formal.vrma','soft-walk.vrma',...catalog.map(c=>c.file)];
    const params=new URLSearchParams(location.search);
    const previewFile=(petModel.preview?.key??'hello')+'.vrma';
    const initial=[...new Set([0,...(studio?[files.indexOf(previewFile)]:params.getAll('clip').map(Number))])].filter(i=>files[i]);
    const [avatar,...startup]=await Promise.all([loader.loadAsync(petModel.file),...initial.map(i=>motions.loadAsync(files[i]))]);
    const vrm=avatar.userData.vrm;
    vrm.scene.rotation.y=Math.PI;
    scene.add(vrm.scene);
    lighting.fit(vrm);
    const head=vrm.humanoid.getRawBoneNode('head');
    const height=head.getWorldPosition(new Vector()).y;
    const hips=vrm.humanoid.getRawBoneNode('hips'),pattern=hips.userData.wrapDress;
    const wrapDress=pattern?.body?fitHangingDress(vrm,hips,pattern,Vector):null;
    const frameHeight=height;
    const cameraHeight=height*.58;
    const coreFraction=Number(params.get('core')) || 1;
    const travelScale=(wrapDress?.gaitScale??1)*coreFraction;
    camera.position.set(0,cameraHeight, frameHeight*2.31);
    camera.lookAt(0,cameraHeight,0);
    let portrait=false;
    let controls;
    const center=new Vector(0,cameraHeight,0);
    const offset=new Vector();
    let trackMask=false,maskDirty=true,desktopYaw=0;
    function desktopView(yaw,pitch){
        maskDirty=true;
        if(studio)return;
        desktopYaw=yaw;
        const distance=frameHeight*2.31,radius=distance*Math.cos(pitch);
        camera.position.set(radius*Math.sin(yaw),cameraHeight+distance*Math.sin(pitch),radius*Math.cos(yaw));
        camera.lookAt(center);render();
    }
    function frameSubject(){
        if(!controls)return;
        if(portrait){head.getWorldPosition(center);center.y+=.01}
        else center.set(0,cameraHeight,0);
        offset.subVectors(camera.position,controls.target).setLength(portrait?.91:frameHeight*2.65);
        controls.target.copy(center);
        camera.position.copy(center).add(offset);
        controls.update();
    }
    function enableOrbit(){
        controls=new window.ShinoRuntime.OrbitControls(camera,renderer.domElement);
        controls.enablePan=false;
        controls.minDistance=.32;controls.maxDistance=height*4;
        controls.minPolarAngle=.15;controls.maxPolarAngle=Math.PI-.15;
        controls.target.copy(center);
        frameSubject();
        controls.addEventListener('change',()=>render());
    }
    if(studio)enableOrbit();
    const stage=document.querySelector('#stage')||document.documentElement;
    const floorFraction=Number(params.get('floor')??.045);
    const solePoint=new Vector(), soleSamples=[];
    // Keep the lowest rest vertex in each patch of the two soles. Evaluate just
    // these vertices with their actual skin weights throughout the step.
    if(!studio){
        vrm.scene.updateMatrixWorld(true);
        vrm.scene.traverse(mesh=>{
            if(!mesh.isSkinnedMesh || !mesh.visible)return;
            const g=mesh.geometry, cells=new Map();
            const count=g.index?.count??g.attributes.position.count;
            const visited=new Set();
            for(let i=0;i<count;i++){
                const index=g.index?g.index.getX(i):i;
                if(visited.has(index))continue;
                visited.add(index);
                solePoint.fromBufferAttribute(g.attributes.position,index).applyMatrix4(mesh.matrixWorld);
                if(solePoint.y>.085 || solePoint.y<-.10)continue;
                mesh.getVertexPosition(index,solePoint).applyMatrix4(mesh.matrixWorld);
                if(solePoint.y>.075 || solePoint.y<-.10)continue;
                const key=Math.floor(solePoint.x/.025)+','+Math.floor(solePoint.z/.025);
                if(!cells.has(key)||cells.get(key).y>solePoint.y)cells.set(key,{mesh,index,y:solePoint.y});
            }
            soleSamples.push(...cells.values());
        });
    }
    let baseProjectionY=0,floorShift=0;
    function groundFeet(dt){
        if(studio || !soleSamples.length)return;
        camera.updateMatrixWorld();
        const projection=camera.projectionMatrix;
        projection.elements[9]=baseProjectionY;
        const motion=record();
        // Shino's planted takes keep a supporting foot even in a curtsy or a turn.
        // Her hop lifts both feet off the floor.
        const airborne=motion?.key==='hop';
        if(!airborne){
            let bottom=Infinity;
            for(const {mesh,index} of soleSamples){
                mesh.getVertexPosition(index,solePoint).applyMatrix4(mesh.matrixWorld).project(camera);
                bottom=Math.min(bottom,solePoint.y);
            }
            const shift=bottom+1-2*floorFraction;
            // Ease back from an airborne scene without damping ordinary footfalls.
            const delta=shift-floorShift;
            floorShift+=dt>0 && Math.abs(delta)>.045 ? delta*(1-Math.exp(-dt*22)):delta;
        }
        projection.elements[9]+=floorShift;
        camera.projectionMatrixInverse.copy(projection).invert();
    }
    function resize(){
        maskDirty=true;
        renderer.setSize(stage.clientWidth,stage.clientHeight,false);
        const w=stage.clientWidth,h=stage.clientHeight;
        if(!w || !h)return;
        camera.clearViewOffset();
        camera.aspect=w/h;
        if(!studio && coreFraction<1){
            const core=h*coreFraction;
            camera.setViewOffset(w,core,0,core-h,w,h);
        }
        camera.updateProjectionMatrix();
        baseProjectionY=camera.projectionMatrix.elements[9];
        if(controls)render();
    }
    resize();new ResizeObserver(resize).observe(stage);
    const mixer=new Mixer(vrm.scene);
    const actions=new Array(files.length),pending=new Map(),recent=new Set();
    function attach(i,asset){
        actions[i]=mixer.clipAction(clip(asset.userData.vrmAnimations[0],vrm));recent.add(i);
        return actions[i];
    }
    initial.forEach((id,i)=>attach(id,startup[i]));
    function prepare(i){
        if(actions[i])return Promise.resolve(actions[i]);
        if(!pending.has(i))pending.set(i,motions.loadAsync(files[i]).then(asset=>attach(i,asset)).finally(()=>pending.delete(i)));
        return pending.get(i);
    }
    function trim(requested){
        for(const i of recent){
            if(recent.size<=7)break;
            if(i===requested || i===0 || i===active || actions[i].isRunning() || transition?.layers.some(l=>l.action===actions[i]))continue;
            mixer.uncacheClip(actions[i].getClip());delete actions[i];recent.delete(i);
        }
    }
    let active=0,angle=0,desiredAngle=0,forceX=0,forceY=0,lagX=0,lagY=0;
    // Bind tracks during loading, so their first button press can blend immediately.
    for(const action of actions.filter(Boolean)){action.play();mixer.update(0);action.stop()}
    actions[0].play();
    const isWalk=i=>Object.hasOwn(cycleTravel,files[i]);
    let transition=null,paused=false,expressionLevel=1,focusX=0,focusY=0,eyesX=0,eyesY=0,headX=0,headY=0;
    let sceneDirection=0;
    function record(){return catalog[active-4]}
    function travelSample(values,t,duration){
        const position=Math.min(1,Math.max(0,t/duration))*(values.length-1),i=Math.floor(position);
        return values[i]+((values[i+1]??values[i])-values[i])*(position-i);
    }
    function blend(dt){
        if(!transition)return;
        transition.time+=dt;
        const u=Math.min(1,transition.time/transition.duration);
        const amount=u*u*(3-2*u);
        for(const entry of transition.layers){
            const weight=entry.from+(entry.to-entry.from)*amount;
            entry.action.setEffectiveWeight(weight);
            if(u===1 && !entry.to)entry.action.stop();
        }
        if(u===1){transition=null;trim(active)}
    }
    const chillyIndex=files.indexOf('chilly.vrma');
    const restingClips=[0,...catalog.filter(row=>row.role==='idle').map(row=>files.indexOf(row.file))];
    const hairs=Array.from(vrm.springBoneManager.joints)
        .filter(j=>j.bone.name.toLowerCase().includes('hairjoint'))
        .map(joint=>{
            return {joint,gravity:joint.settings.gravityDir.clone(),power:joint.settings.gravityPower};
        });
    let selection=0, pivot=null;
    function travelHeading(index,dir,seconds=0){
        if(!dir)return 0;
        const meta=catalog[index-4];
        const swing=meta?.heading ? travelSample(meta.heading,seconds,meta.duration) : 0;
        return (studio?0:desktopYaw)+dir*Math.PI/2-(meta?.directionOffset||0)+swing;
    }
    function cancelPivot(){
        if(pivot){pivot.finish(false);pivot=null}
    }
    async function faceTravel(index,dir,phase){
        cancelPivot();
        const token=++selection;
        const continuing=phase==='current' && active===index;
        if(continuing)phase=actions[index].time/actions[index].getClip().duration;
        else if(!Number.isFinite(phase))phase=null;
        const seconds=Number.isFinite(phase)?phase*clipSeconds[files[index]]:0;
        const target=travelHeading(index,dir,seconds);
        const arc=Math.atan2(Math.sin(target-angle),Math.cos(target-angle));
        const facing=new Promise(finish=>{
            pivot={from:angle,arc,target,time:0,duration:Math.abs(arc)<.025?0:.14+.43*Math.abs(arc)/Math.PI,finish};
            if(!pivot.duration){angle=desiredAngle=target;finish(true)}
        });
        const request=pivot;
        try{
            const [done]=await Promise.all([facing,prepare(index)]);
            if(!done || token!==selection || pivot!==request)return false;
            pivot=null;angle=desiredAngle=target;
            if(continuing)sceneDirection=dir;
            else play(index,dir,true,phase);
            return true;
        }finally{if(token===selection)cancelPivot()}
    }
    function play(index,dir=0,restart=false,resumePhase=null){
        cancelPivot();
        const token=++selection;
        if(!files[index])return;
        if(!actions[index])return prepare(index).then(()=>{if(token===selection)play(index,dir,restart,resumePhase)}).catch(err=>{
            if(token===selection)send('motionError',String(err));
        });
        recent.delete(index);recent.add(index);trim(index);
        sceneDirection=dir;desiredAngle=travelHeading(index,dir);
        if(!restart && index===active && (index===0 || isWalk(index)))return;
        const next=actions[index],meta=catalog[index-4];
        const once=meta && (meta.role==='travel' || (meta.role==='scene' && !studio));
        next.setLoop(once?2200:2201,once?1:Infinity);next.clampWhenFinished=!!once;
        // On a model change continue the same beat of this character's own take.
        // Skip the blend from the new model's idle pose, including when paused.
        if(Number.isFinite(resumePhase)){
            mixer.stopAllAction();transition=null;active=index;
            next.reset().setEffectiveTimeScale(1).setEffectiveWeight(1);
            next.time=Math.min(.999999,Math.max(0,resumePhase))*next.getClip().duration;
            next.play();mixer.update(0);
            desiredAngle=travelHeading(index,dir,next.time);
            angle=desiredAngle;vrm.scene.rotation.y=Math.PI+angle;faceClock=next.time;
            wrapDress?.reset();paint(0);vrm.scene.updateMatrixWorld(true);vrm.springBoneManager.reset();paint(0);
            return;
        }
        const layers=actions.filter(a=>a===next || (a.isRunning()||a===actions[active])).map(action=>({
            action, from:(action.isRunning()||action===actions[active])?action.getEffectiveWeight():0, to:action===next?1:0
        }));
        const initial=layers.find(layer=>layer.action===next).from;
        next.reset().setEffectiveTimeScale(1);
        if(isWalk(index) && ['start','turn'].includes(record()?.key)){
            // Enter the cycle on the leg which was bearing weight at the end of the transition.
            const knee=vrm.humanoid.getNormalizedBoneNode('leftLowerLeg');
            const track=next.getClip().tracks.find(t=>t.name.startsWith(knee.name+'.quaternion'));
            if(track){
                let best=-1;
                for(let k=0;k<track.times.length;k++){
                    const score=Math.abs(delta.fromArray(track.values,k*4).dot(knee.quaternion));
                    if(score>best){best=score;next.time=track.times[k]}
                }
            }
        }
        if(!studio && catalog[index-4]?.role==='idle'){
            const joints=['head','chest','leftUpperArm','rightUpperArm','hips'].map(k=>vrm.humanoid.getNormalizedBoneNode(k));
            const tracks=joints.map(b=>next.getClip().tracks.find(t=>t.name===b.name+'.quaternion'));
            let best=-1;
            for(let i=0;i<16;i++){
                const fraction=i/16;
                let score=0;
                tracks.forEach((t,j)=>{if(t){const k=Math.round(fraction*(t.times.length-1));score+=Math.abs(delta.fromArray(t.values,4*k).dot(joints[j].quaternion))}});
                if(score>best){best=score;next.time=fraction*next.getClip().duration}
            }
        }
        next.setEffectiveWeight(initial).play();
        transition={layers,time:0,duration:isWalk(index) || isWalk(active) ? .40 : .26};
        active=index;
    }
    let lastDrag=-Infinity;
    function drag(vx,vy){
        // Points per second on the desktop: quiet at low speeds, bounded on a flick.
        const speed=Math.hypot(vx,vy);
        const gain=2.6*speed/(speed*speed+620*620);
        forceX=-vx*gain;
        forceY=-vy*gain;
        lastDrag=performance.now();
    }
    // Apply drag on top of the current pose for one humanoid update. The saved
    // normalized rotations go back to the mixer; the rendered bones keep the result.
    function joint(name){
        const bone=vrm.humanoid.getNormalizedBoneNode(name);
        return {bone,pose:bone.quaternion.clone()};
    }
    const neck=joint('neck'),headJoint=joint('head');
    const legs=['left','right'].map(side=>({
        thigh:joint(side+'UpperLeg'),knee:joint(side+'LowerLeg'),ankle:joint(side+'Foot')
    }));
    const overlay=[neck,headJoint,...legs.flatMap(leg=>[leg.thigh,leg.knee,leg.ankle])];
    const arms=['left','right'].map(side=>joint(side+'UpperArm'));
    const delta=neck.pose.clone(),identity=neck.pose.clone().identity();
    const eyes=['leftEye','rightEye'].map(joint);
    overlay.push(...eyes);
    const limbs=['left','right'].map((side,i)=>({
        arm:arms[i],elbow:joint(side+'LowerArm'),hand:joint(side+'Hand')
    }));
    const from=new Vector(),to=new Vector();
    function steer(parent,child,goal,strength){
        parent.parent.worldToLocal(from.copy(child.getWorldPosition(from))).sub(parent.position).normalize();
        parent.parent.worldToLocal(to.copy(goal)).sub(parent.position).normalize();
        delta.setFromUnitVectors(from,to).slerp(identity,1-strength);
        parent.quaternion.premultiply(delta);parent.updateWorldMatrix(true,true);
    }
    const clearArms=fitArmContacts(vrm,Vector,limbs,steer,wrapDress?.sleevePadding);
    const pendulum=new Vector(),velocity=new Vector();
    function updateAvatar(dt,acting){
        // Less damping than the head lets the feet settle a little later.
        const steps=Math.max(1,Math.ceil(dt/.014)),h=dt/steps;
        for(let i=0;i<steps;i++){
            velocity.x+=(55*(lagX-pendulum.x)-10*velocity.x)*h;
            velocity.y+=(55*(lagY-pendulum.y)-10*velocity.y)*h;
            pendulum.addScaledVector(velocity,h);
        }
        for(const arm of arms)arm.pose.copy(arm.bone.quaternion);
        for(const limb of limbs){
            limb.elbow.pose.copy(limb.elbow.bone.quaternion);
            limb.hand.pose.copy(limb.hand.bone.quaternion);
        }
        for(const j of overlay)j.pose.copy(j.bone.quaternion);
        const meta=record(),time=actions[active].time;
        const glance=meta?.key==='look'? Math.sin(time*1.25)*.13:0;
        for(const eye of eyes){eye.bone.rotateY(eyesX*.20+glance);eye.bone.rotateX(eyesY*.12)}
        headJoint.bone.rotateY(headX*.14);headJoint.bone.rotateX(headY*.09);
        neck.bone.rotateZ(lagX*.016);headJoint.bone.rotateZ(lagX*.030);
        headJoint.bone.rotateY(-lagX*.022);headJoint.bone.rotateX(lagY*.045);
        for(const [index,leg] of legs.entries()){
            const sway=pendulum.x*(index===0?.060:.052);
            const tuck=Math.max(0,-pendulum.y)*.090+Math.abs(sway)*.24;
            leg.thigh.bone.rotateZ(-sway);leg.thigh.bone.rotateX(tuck*.6+pendulum.y*.034);
            leg.knee.bone.rotateX(-tuck);leg.ankle.bone.rotateX(tuck*.28);
        }
        {
            const weight=i=>actions[i]?.isRunning()?actions[i].getEffectiveWeight():0;
            const restingWeight=restingClips.reduce((sum,i)=>sum+weight(i),0);
            clearArms(weight(chillyIndex),dt,restingWeight,acting,weight(1)+weight(2)+weight(3));
        }
        vrm.update(dt);
        if(wrapDress)wrapDress.update(dt,lagX,lagY,Math.atan2(camera.position.x,camera.position.z));
        for(const j of overlay)j.bone.quaternion.copy(j.pose);
        for(const arm of arms)arm.bone.quaternion.copy(arm.pose);
        for(const limb of limbs){limb.elbow.bone.quaternion.copy(limb.elbow.pose);limb.hand.bone.quaternion.copy(limb.hand.pose)}
    }
    const mask=document.createElement('canvas');
    mask.width=32;mask.height=52;
    const pixels=mask.getContext('2d',{willReadFrequently:true});
    let previousMask='',lastMask=-1000,lastFrame=0;
    const gravity=new Vector();
    function frame(now){
        const dt=Math.min(.07,(now-lastFrame)/1000);
        lastFrame=now;
        if(paused)return;
        const meta=record();
        if(pivot){
            pivot.time+=dt;
            const t=pivot.duration?Math.min(1,pivot.time/pivot.duration):1;
            angle=pivot.from+pivot.arc*t*t*(3-2*t);
            if(t===1)pivot.finish(true);
        }else{
            if(sceneDirection)desiredAngle=travelHeading(active,sceneDirection,actions[active].time);
            const error=Math.atan2(Math.sin(desiredAngle-angle),Math.cos(desiredAngle-angle));
            angle+=error*(1-Math.exp(-dt*(meta?.heading?18:4)));
        }
        eyesX+=(focusX-eyesX)*(1-Math.exp(-dt*12));eyesY+=(focusY-eyesY)*(1-Math.exp(-dt*12));
        headX+=(eyesX-headX)*(1-Math.exp(-dt*3));headY+=(eyesY-headY)*(1-Math.exp(-dt*3));
        vrm.scene.rotation.y=Math.PI+angle;
        const follow=1-Math.exp(-dt*11);
        lagX+=(forceX-lagX)*follow;lagY+=(forceY-lagY)*follow;
        if(now-lastDrag>45){forceX*=Math.exp(-dt*10);forceY*=Math.exp(-dt*10)}
        for(const {joint,gravity:rest,power} of hairs){
            gravity.copy(rest).multiplyScalar(power);
            gravity.x+=lagX*.26;
            gravity.y+=lagY*.20;
            gravity.z+=lagY*.14;
            const magnitude=gravity.length();
            joint.settings.gravityPower=magnitude;
            joint.settings.gravityDir.copy(magnitude>1e-5?gravity.multiplyScalar(1/magnitude):rest);
        }
        const motionDt=pivot && sceneDirection ? 0:dt;
        blend(motionDt);mixer.update(motionDt);faceClock+=dt;paint(dt);
        if(!studio && (maskDirty || (trackMask && now-lastMask>205))){
            maskDirty=false;
            lastMask=now;pixels.clearRect(0,0,32,52);pixels.drawImage(renderer.domElement,0,0,32,52);
            const data=pixels.getImageData(0,0,32,52).data;
            let bits='';
            for(let i=3;i<data.length;i+=4)bits+=data[i]>35?'1':'0';
            if(bits!==previousMask){send('mask',bits);previousMask=bits}
        }
    }
    const face=shinoFaceAnimation(vrm.expressionManager);
    let faceClock=0;
    function paint(dt){
        let acting=0;
        for(const [i,motion] of catalog.entries()){
            const action=actions[i+4];
            if(action && (action.isRunning() || active===i+4 || transition?.layers.some(layer=>layer.action===action))){
                const weight=action.getEffectiveWeight();
                if(motion.role==='scene' || motion.role==='travel')acting+=weight;
                face.add(motion.key,action.time/motion.duration,weight,motion.role);
            }
        }
        face.apply(expressionLevel,faceClock);
        updateAvatar(dt,acting);
        groundFeet(dt);
        if(controls && portrait){
            head.getWorldPosition(center);center.y+=.01;
            camera.position.add(offset.subVectors(center,controls.target));
            controls.target.copy(center);
        }
        render();
        face.restore();
    }
    function sample(index,seconds){
        if(!actions[index])return prepare(index).then(()=>sample(index,seconds));
        const jumped=index!==active || !paused || Math.abs(seconds-actions[index].time)>.10;
        if(jumped)mixer.stopAllAction();
        transition=null;active=index;
        actions[index].reset().setEffectiveWeight(1).play();actions[index].time=Math.min(seconds,actions[index].getClip().duration-.0001);
        mixer.update(0);faceClock=seconds;angle=desiredAngle=0;vrm.scene.rotation.y=Math.PI;
        if(jumped){wrapDress?.reset();paint(0);vrm.scene.updateMatrixWorld(true);vrm.springBoneManager.reset()}
        paint(1/30);
    }
    // The native verification samples the rendered skeleton after retargeting.
    // The normalized arm rotations have already been restored for the mixer.
    function inspectFit(){
        const raw=name=>vrm.humanoid.getRawBoneNode(name);
        const ribs=raw('chest');
        const upperChest=raw('upperChest')??ribs;
        const wrists=['left','right'].map(side=>
            upperChest.worldToLocal(raw(side+'Hand').getWorldPosition(new Vector())).toArray());
        const crossings=['left','right'].map(side=>{
            const e=ribs.worldToLocal(raw(side+'LowerArm').getWorldPosition(new Vector()));
            const w=ribs.worldToLocal(raw(side+'Hand').getWorldPosition(new Vector()));
            const u=-e.x/(w.x-e.x);
            return u>=0 && u<=1 ? e.lerp(w,u).z : null;
        });
        const pitch=name=>{
            const q=vrm.humanoid.getNormalizedBoneNode(name).quaternion;
            return 2*Math.atan2(Math.abs(q.x),Math.abs(q.w));
        };
        const m=vrm.scene.matrixWorld.elements,c=camera.matrixWorld.elements;
        const screenRight=-m[8]*c[0]-m[10]*c[2];
        let bodyIndices=0;
        vrm.scene.traverse(mesh=>{
            if(!mesh.isSkinnedMesh)return;
            const base=Array.isArray(mesh.material)?mesh.material[0]:mesh.material;
            if(base?.name.endsWith('Body_00_SKIN'))bodyIndices+=mesh.geometry.index.count;
        });
        return {wrists,crossings,screenRight,chestPitch:pitch('chest'),neckPitch:pitch('neck'),headPitch:pitch('head'),
                bodyIndices,cloth:wrapDress?.measure()};
    }
    let visible=true,animating=false;
    function syncFrames(){
        const next=visible && !document.hidden && !paused;
        if(next===animating)return;
        animating=next;
        if(next)lastFrame=performance.now();
        renderer.setAnimationLoop(next?frame:null);
    }
    document.addEventListener('visibilitychange',syncFrames);
    function previewState(){
        const action=actions[active];
        return {phase:action.time/action.getClip().duration,
            key:files[active].replace(/\.vrma$/,''),
            camera:controls?offset.subVectors(camera.position,controls.target).multiplyScalar(1/height).toArray():null};
    }
    function restoreCamera(closeUp,relative){
        portrait=closeUp;frameSubject();
        if(controls && Array.isArray(relative) && relative.length===3 && relative.every(Number.isFinite)){
            offset.fromArray(relative);
            if(offset.lengthSq()>0){
                offset.setLength(Math.max(controls.minDistance,Math.min(controls.maxDistance,offset.length()*height)));
                camera.position.copy(controls.target).add(offset);controls.update();render();
            }
        }
    }
    window.pet={play,drag,sample,previewState,restoreCamera,
        desktopView,prepare,faceTravel,cancelPivot,
        watchMask(value){if(value && !trackMask)maskDirty=true;trackMask=value},
        prefetch(i){prepare(i).then(()=>trim(i)).catch(()=>{});},

        enterStudio(){
            if(studio)return;
            studio=true;document.documentElement.classList.remove('desktop');
            camera.position.set(0,cameraHeight,frameHeight*2.65);enableOrbit();resize();
            focusX=focusY=0;window.studioReady();
        },
        paused:v=>{paused=v;syncFrames()},visibility:v=>{visible=v;syncFrames()},portrait:v=>{portrait=v;frameSubject();paint(0)},
        intensity(v){
            const next=Math.min(1.5,Math.max(0,v));
            if(!Number.isFinite(next) || next===expressionLevel)return;
            expressionLevel=next;
            if(paused && visible && !document.hidden)paint(0);
        },
        gaze:(x,y)=>{focusX=x;focusY=y},
        durations:files.map((file,i)=>clipSeconds[file]),
        check:(fit=false)=>({model:petModel.id,file:petModel.file,dress:!!wrapDress,motions:actions.length,hairs:hairs.length,rendered:renderer.info.render.frame,active,...(fit?inspectFit():{}),
        power:Math.max(...hairs.map(h=>h.joint.settings.gravityPower)),triangles:renderer.info.render.triangles,
        knee:vrm.humanoid.getNormalizedBoneNode('leftLowerLeg').rotation.x,
        strand:hairs[0]?.joint.bone.quaternion.toArray(),transparent:renderer.getClearAlpha()===0})};
    const walkRates=files.map((file,i)=>isWalk(i) ? cycleTravel[file]*travelScale/clipSeconds[file] : 0);
    syncFrames();send('ready',{rates:walkRates,durations:window.pet.durations,travelScale:[travelScale]});if(studio)window.studioReady();
}
startPet().catch(error=>window.webkit.messageHandlers.pet.postMessage({type:'error',value:String(error.stack||error)}));
