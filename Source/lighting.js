/* Single shadow map for the animated figure, with a camera-relative studio key.
   Both skinned normals and view direction feed the rim and hair reflection. */
function shinoLighting(renderer,scene,camera,Sun,Sky,Vector){
    const key=new Sun(0xfff2e4,2.35);
    const fill=new Sky(0xf2f5ff,0xd4cee8,.84);
    const pivot=new Vector(0,.88,0),offset=new Vector(),towards=new Vector(),right=new Vector();
    const up=new Vector(0,1,0);
    scene.add(key,key.target,fill);
    key.target.position.copy(pivot);
    key.castShadow=true;
    renderer.shadowMap.enabled=true;
    renderer.shadowMap.type=1; // PCFShadowMap; skin and cutout hair share one depth pass.
    key.shadow.mapSize.set(1024,1024);
    Object.assign(key.shadow.camera,{left:-.94,right:.94,top:1.02,bottom:-1.02,near:1,far:6});
    key.shadow.camera.updateProjectionMatrix();
    key.shadow.normalBias=.0024;
    key.shadow.bias=-.00016;
    key.shadow.radius=1.6;
    function aim(){
        // Follow the azimuth gradually with the camera. Keep a world-space component
        // so an orbit also changes which folds and strands receive the key light.
        towards.copy(camera.position).sub(pivot);
        const yaw=Math.atan2(towards.x,towards.z);
        towards.set(Math.sin(yaw),0,Math.cos(yaw));
        right.crossVectors(up,towards);
        offset.set(-.38,.94,.32).addScaledVector(towards,.58).addScaledVector(right,-.72).normalize();
        key.position.copy(pivot).addScaledVector(offset,3.2);
    }
    function fit(vrm){
        const materials=new Set();
        vrm.scene.traverse(mesh=>{
            if(!mesh.isSkinnedMesh)return;
            mesh.frustumCulled=false;
            const list=Array.isArray(mesh.material)?mesh.material:[mesh.material];
            const base=list[0],n=base.name;
            // Delicate transparent eye and brow decals share the face underneath.
            mesh.castShadow=!/Eye|FaceBrow|Mouth|HairBack/.test(n);
            mesh.receiveShadow=true;
            if(materials.has(base) || !base.isMToonMaterial)return;
            materials.add(base);
            const hair=/HAIR/.test(n),clothes=/CLOTH/.test(n),skin=/SKIN/.test(n);
            if(!hair && !clothes && !skin)return;
            const isBow=/AccessoryNeck/.test(n);
            const strength=hair ? .045 : isBow ? .025 : .010;
            const gloss=hair?.115:isBow?.070:clothes?.009:.008;
            base.shadingToonyFactor=hair?.48:.54;
            if(skin || clothes){
                const shade=base.shadeColorFactor;
                shade.setRGB(shade.r*(skin?.85:.79),shade.g*(skin?.87:.85),shade.b*(skin?.97:1));
            }
            const compileMToon=base.onBeforeCompile.bind(base);
            const mtoonKey=base.customProgramCacheKey.bind(base);
            base.customProgramCacheKey=()=>mtoonKey()+'-shino-rim-v5-'+n;
            base.onBeforeCompile=(shader,context)=>{
                compileMToon(shader,context);
                const marker='col += rimMix * rim;';
                if(!shader.fragmentShader.includes(marker))throw Error('MToon shader lacks rim hook');
                shader.fragmentShader=shader.fragmentShader.replace(marker,`
                // Keep reflections across the surface and feather the bright edge of the original matcap.
                float facing = saturate(dot(normal,viewDir));
                col += rimMix * rim * mix(.055, .78, smoothstep(.03,.59,facing));
                #if !defined( OUTLINE ) && NUM_DIR_LIGHTS > 0
                    vec3 L = directionalLights[0].direction;
                    float NdotV = saturate(dot(normal, viewDir));
                    vec3 silhouetteL = normalize(vec3(-L.x, L.y*.40, -.85));
                    float side = smoothstep(-.24,.90,dot(normal,silhouetteL));
                    float edge = pow(1.0-NdotV,3.3)*side;
                    col += vec3(.72,.66,.59)*edge*${strength.toFixed(3)};
                    vec3 halfKey = normalize(L + viewDir);
                    float lobe = pow(saturate(dot(normal,halfKey)),${hair?'34.0':'45.0'});
                    col += vec3(.64,.76,1.)*lobe*${gloss.toFixed(3)};
                #endif`);
            };
            base.needsUpdate=true;
        });
    }
    return {aim,fit};
}
