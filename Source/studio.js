const el=id=>document.getElementById(id);
const petModel=window.petModelConfig??{id:'shino',name:'Сино',file:'Shino.vrm',choices:[]};
const slotPickers=[];
window.setSlots=values=>{
    const group=el('modelPicker');
    while(slotPickers.length>values.length){
        const picker=slotPickers.pop();
        picker.labels[0].remove();picker.remove();
    }
    values.forEach((value,i)=>{
        if(!slotPickers[i]){
            const number=i+1,picker=document.createElement('select'),label=document.createElement('label');
            picker.id=i?'character'+number:'character';label.htmlFor=picker.id;label.textContent='Персонаж '+number;
            if(i)picker.add(new Option('Нет',''));
            for(const choice of petModel.choices)picker.add(new Option(choice.title,choice.id));
            picker.onchange=()=>window.webkit.messageHandlers.pet.postMessage({
                type:'slot',slot:number,value:picker.value,preview:window.studioSnapshot()
            });
            group.append(label,picker);slotPickers.push(picker);
        }
        slotPickers[i].value=value;
    });
    el('slotCount').value=values.length;
    el('fewer').disabled=values.length<=1;el('more').disabled=values.length>=10;
};
for(const [id,step] of [['fewer',-1],['more',1]]){
    el(id).onclick=()=>{
        const input=el('slotCount');
        input.value=Math.min(10,Math.max(1,(input.valueAsNumber||slotPickers.length)+step));
        input.dispatchEvent(new Event('change'));
    };
}
el('slotCount').onchange=e=>{
    const n=e.target.valueAsNumber;
    if(Number.isFinite(n))profileCommand('slotCount',Math.min(10,Math.max(1,Math.round(n))));
    e.target.value=Number.isFinite(n)?Math.min(10,Math.max(1,Math.round(n))):slotPickers.length;
};
el('slotCount').onkeydown=e=>{if(e.key==='Enter')e.target.blur()};
window.setSlots(petModel.slots??[petModel.id,'','']);
const previews=[
    {clip:3,key:'soft-walk',label:'Мягкая прогулка',role:'gait'},
    {clip:1,key:'walk',label:'Обычный шаг',role:'gait'},
    {clip:2,key:'formal',label:'Сдержанный шаг',role:'gait'},
    ...catalog.map((row,i)=>({...row,clip:4+i}))
];
let selected=previews.find(entry=>entry.key===(petModel.preview?.key??'hello'))??previews.find(entry=>entry.key==='hello');
let stopped=false,closeUp=false;
const defaultVisits={enabled:false,period:600,duration:20};
let prefs={frequency:'normal',low:60,high:120,amount:100,gaze:true,disabled:[],visits:defaultVisits};
function choose(motion,previous=null){
    selected=motion;
    const walking=motion.role==='gait' || motion.role==='travel';
    el('caption').textContent=motion.label;
    el('autoOption').hidden=walking;
    el('auto').checked=!prefs.disabled.includes(motion.key);
    document.querySelectorAll('#list button').forEach(b=>b.setAttribute('aria-pressed',Number(b.dataset.clip)===motion.clip));
    if(window.pet){
        stopped=Boolean(previous?.paused);pet.play(motion.clip,walking?1:0,true,previous?.phase??null);
        if(previous){closeUp=Boolean(previous.portrait);pet.restoreCamera(closeUp,previous.camera)}
        pet.paused(stopped);el('pause').textContent=stopped?'Продолжить':'Пауза';
        el('portrait').textContent=closeUp?'В полный рост':'Портрет';
    }
}
for(const motion of previews){
    const button=document.createElement('button');
    button.textContent=motion.label;
    button.dataset.clip=motion.clip;
    button.onclick=()=>choose(motion);
    el(motion.role).append(button);
}
function tab(settings){
    el('options').hidden=!settings;el('library').hidden=settings;
    el('showOptions').setAttribute('aria-pressed',settings);el('showLibrary').setAttribute('aria-pressed',!settings);
}
function update(p){
    const visits=p.visits??defaultVisits;
    prefs={...p,visits};
    el('presence').value=visits.enabled?'visits':'always';el('visits').hidden=!visits.enabled;
    const unit=Number(el('periodUnit').value);
    el('period').value=Number((visits.period/unit).toFixed(4));
    el('period').min=2/unit;el('period').max=86400/unit;
    el('duration').value=visits.duration;el('duration').max=visits.period-1;
    const arrival=p.frequency==='manual'?'принимает случайную стойку.':'разыгрывает одну из включённых сценок, затем принимает случайную стойку.';
    el('arrivalHint').textContent='При появлении персонаж '+arrival;
    for(const k of ['frequency','low','high','amount'])el(k).value=p[k];
    el('gaze').checked=p.gaze;el('level').value=p.amount;
    el('interval').hidden=!['custom','fixed'].includes(p.frequency);
    el('highRow').hidden=p.frequency==='fixed';el('lowLabel').textContent=p.frequency==='fixed'?'Каждые':'От';
    el('auto').checked=!p.disabled.includes(selected.key);window.pet?.intensity(p.amount/100);
}
function save(event){
    const low=Math.min(86400,Math.max(5,Math.round(Number(el('low').value)||5)));
    const high=Math.min(86400,Math.max(low,Math.round(Number(el('high').value)||low)));
    const period=Math.min(86400,Math.max(2,Math.round(el('period').value*el('periodUnit').value)||prefs.visits.period));
    const duration=Math.min(period-1,Math.max(1,Math.round(Number(el('duration').value))||prefs.visits.duration));
    const disabled=new Set(prefs.disabled);
    if(event?.target===el('auto') && !el('autoOption').hidden){
        if(el('auto').checked)disabled.delete(selected.key);else disabled.add(selected.key);
    }
    update({frequency:el('frequency').value,amount:Number(el('amount').value),gaze:el('gaze').checked,low,high,disabled:[...disabled],
        visits:{enabled:el('presence').value==='visits',period,duration}});
    window.webkit.messageHandlers.pet.postMessage({type:'prefs',value:prefs});
}
el('showOptions').onclick=()=>tab(true);el('showLibrary').onclick=()=>tab(false);
window.setBackdrop=(value,choices)=>{
    const picker=el('backdrop');
    if(!picker.options.length)for(const choice of choices)picker.add(new Option(choice.title,choice.id));
    picker.value=value;
};
el('backdrop').onchange=e=>profileCommand('backdrop',e.target.value);
el('openScene').onclick=()=>profileCommand('openScene');
for(const k of ['auto','frequency','low','high','amount','gaze','presence','period','duration'])el(k).onchange=save;
el('periodUnit').onchange=()=>update(prefs);
el('visitNow').onclick=()=>window.webkit.messageHandlers.pet.postMessage({type:'visitNow'});
el('amount').oninput=()=>{el('level').value=el('amount').value;window.pet?.intensity(+el('amount').value/100)};
el('pause').onclick=()=>{if(!window.pet)return;stopped=!stopped;pet.paused(stopped);el('pause').textContent=stopped?'Продолжить':'Пауза'};
el('again').onclick=()=>choose(selected);
el('portrait').onclick=()=>{if(!window.pet)return;closeUp=!closeUp;pet.portrait(closeUp);el('portrait').textContent=closeUp?'В полный рост':'Портрет'};
let awaitingPreview=true;
window.studioSnapshot=()=>{
    if(awaitingPreview && petModel.preview)return petModel.preview;
    const pose=window.pet?.previewState();
    return {key:selected.key,phase:pose?.key===selected.key?pose.phase:0,camera:pose?.camera,
        paused:stopped,portrait:closeUp,settings:!el('options').hidden,scroll:document.querySelector('aside').scrollTop};
};
window.studioReady=()=>{
    update(prefs);choose(selected,awaitingPreview?petModel.preview:null);
    if(awaitingPreview && petModel.preview){
        tab(Boolean(petModel.preview.settings));
        document.querySelector('aside').scrollTop=petModel.preview.scroll??0;
    }
    awaitingPreview=false;
};
let receivedSettings=false;
window.setDesktopSize=(size,max)=>{
    for(const id of ['scaleRange','scaleExact']){
        el(id).max=max;el(id).value=size;
    }
};
function previewSize(size){
    const range=el('scaleRange');
    const percent=Math.max(+range.min,Math.min(+range.max,Math.round(size)));
    window.setDesktopSize(percent,+range.max);
    window.webkit.messageHandlers.pet.postMessage({type:'size',value:percent});
}
el('scaleRange').oninput=e=>previewSize(e.target.valueAsNumber);
el('scaleExact').oninput=e=>{if(e.target.value && e.target.validity.valid)previewSize(e.target.valueAsNumber)};
el('scaleExact').onchange=e=>previewSize(Number.isFinite(e.target.valueAsNumber)?e.target.valueAsNumber:el('scaleRange').valueAsNumber);
window.setupStudio=(p,settings,size=100,max=400)=>{
    window.setDesktopSize(size,max);
    if(!receivedSettings && p.visits && p.visits.period%60!==0)el('periodUnit').value='1';
    receivedSettings=true;update(p);tab(settings);
};
tab(false);update(prefs);

function profileCommand(type,value){window.webkit.messageHandlers.pet.postMessage({type,value})}
el('mode').onchange=()=>profileCommand('mode',el('mode').value==='personal');
el('target').onchange=()=>profileCommand('target',+el('target').value);
el('walk').onchange=()=>profileCommand('walk',el('walk').checked);
el('gaitChoice').onchange=()=>profileCommand('gait',+el('gaitChoice').value);
window.updateProfile=p=>{
    el('mode').value=p.individual?'personal':'shared';
    el('targetRow').hidden=!p.individual;
    el('target').replaceChildren(...p.slots.flatMap((id,i)=>id?[new Option('Персонаж '+(i+1)+' · '+petModel.choices.find(c=>c.id===id).title,String(i+1))]:[]));
    el('target').value=p.target;el('walk').checked=p.walk;el('gaitChoice').value=p.gait;
    window.setDesktopSize(p.size,p.max);update(p.prefs);
};

el('resetAngle').onclick=()=>profileCommand('resetAngle',true);
el('login').onchange=()=>profileCommand('login',true);
window.setLogin=(enabled,pending)=>{el('login').checked=enabled;el('login').indeterminate=pending};
