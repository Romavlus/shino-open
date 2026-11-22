// Poses use Shino's separate lip, eyelid and eyebrow shapes. A weight of one
// would move that part all the way to the sculpted extreme.
const shinoFacePoses = {
    rest: {},
    soft:       {closedSmile:.20, browWarm:.10},
    friendly:   {closedSmile:.57, smilingEyes:.055, browWarm:.25},
    beaming:    {closedSmile:.80, smilingEyes:.13, browWarm:.34},
    grin:       {closedSmile:.46, openSmile:.20, smilingEyes:.11, browWarm:.30},
    listening:  {browLift:.27, wideEyes:.12, closedSmile:.08},
    delighted:  {browLift:.38, wideEyes:.24, closedSmile:.52, openSmile:.12},
    startled:   {browLift:.49, wideEyes:.34, oh:.17},
    uncertain:  {browWorry:.30, browLift:.11, lipPress:.29},
    pensive:    {browWorry:.19, softEyes:.13, lipPress:.26},
    intent:     {browFocus:.19, lipPress:.26},
    determined: {browFocus:.20, closedSmile:.43},
    shivering:  {browWorry:.43, softEyes:.19, lipPress:.42},
    exhaling:   {browWorry:.28, softEyes:.14, oh:.10},
    drowsy:     {browWorry:.11, blink:.18, lipPress:.14},
    yawning:    {browLift:.21, blink:.63, aa:.59},
    chuckle:    {browWarm:.24, closedSmile:.51, smilingEyes:.14},
    laughing:   {browWarm:.32, closedSmile:.28, openSmile:.40, smilingEyes:.22},
};

// Each time is a fraction of the body take. Reaction and recovery are timed
// around the gesture: for instance the eyes open just as the hands uncover them.
const shinoFaceBeats = {
    stand: [[0,'rest'],[.55,'soft'],[1,'rest']],
    look:  [[0,'rest'],[.22,'listening'],[.44,'rest'],[.64,'listening'],[1,'rest']],
    think: [[0,'rest'],[.26,'pensive'],[.58,'pensive'],[.78,'listening'],[1,'rest']],
    wait:  [[0,'rest'],[.25,'intent'],[.49,'uncertain'],[.78,'soft'],[1,'rest']],
    hello: [[0,'rest'],[.14,'listening'],[.31,'friendly'],[.56,'beaming'],[.81,'friendly'],[1,'rest']],
    peek:  [[0,'rest'],[.20,'friendly'],[.34,'intent'],[.48,'intent'],[.60,'startled'],[.71,'delighted'],[.85,'beaming'],[1,'rest']],
    yawn:  [[0,'rest'],[.22,'drowsy'],[.45,'yawning'],[.56,'yawning'],[.77,'drowsy'],[.90,'soft'],[1,'rest']],
    idea:  [[0,'rest'],[.23,'pensive'],[.40,'listening'],[.53,'delighted'],[.73,'beaming'],[1,'rest']],
    plane: [[0,'rest'],[.16,'intent'],[.30,'friendly'],[.47,'beaming'],[.64,'determined'],[.81,'beaming'],[1,'rest']],
    hop:   [[0,'rest'],[.14,'intent'],[.33,'friendly'],[.54,'beaming'],[.75,'delighted'],[1,'rest']],
    sneak: [[0,'rest'],[.16,'intent'],[.40,'listening'],[.67,'intent'],[.83,'friendly'],[1,'rest']],
    dance: [[0,'rest'],[.18,'friendly'],[.34,'grin'],[.51,'determined'],[.72,'beaming'],[.89,'friendly'],[1,'rest']],
    start: [[0,'rest'],[.52,'listening'],[1,'rest']],
    stop:  [[0,'rest'],[.58,'soft'],[1,'rest']],
    turn:  [[0,'rest'],[.43,'listening'],[1,'rest']],
    curtsy:[[0,'rest'],[.20,'friendly'],[.48,'soft'],[.67,'soft'],[.85,'friendly'],[1,'rest']],
    highfive:[[0,'rest'],[.20,'listening'],[.40,'friendly'],[.58,'delighted'],[.68,'beaming'],[.83,'friendly'],[1,'rest']],
    shrug: [[0,'rest'],[.22,'pensive'],[.43,'uncertain'],[.62,'listening'],[.82,'soft'],[1,'rest']],
    giggle:[[0,'soft'],[.16,'friendly'],[.28,'laughing'],[.38,'chuckle'],[.52,'laughing'],[.63,'chuckle'],[.72,'laughing'],[.84,'friendly'],[1,'soft']],
    chilly:[[0,'rest'],[.18,'pensive'],[.32,'shivering'],[.48,'exhaling'],[.61,'shivering'],[.76,'exhaling'],[.88,'pensive'],[1,'rest']],
    hairdo:[[0,'rest'],[.20,'listening'],[.38,'intent'],[.57,'soft'],[.78,'friendly'],[1,'rest']],
    swat:  [[0,'rest'],[.13,'listening'],[.26,'startled'],[.40,'intent'],[.61,'intent'],[.79,'friendly'],[1,'rest']],
    twist: [[0,'rest'],[.17,'friendly'],[.33,'beaming'],[.53,'friendly'],[.72,'beaming'],[1,'rest']],
    duckdance:[[0,'rest'],[.14,'friendly'],[.31,'beaming'],[.48,'chuckle'],[.68,'grin'],[.83,'friendly'],[1,'rest']],
    teapot:[[0,'rest'],[.15,'listening'],[.34,'friendly'],[.57,'determined'],[.76,'beaming'],[1,'rest']],
    superhero:[[0,'rest'],[.16,'intent'],[.37,'listening'],[.57,'determined'],[.77,'determined'],[.91,'friendly'],[1,'rest']],
    hummingbird:[[0,'rest'],[.16,'listening'],[.31,'delighted'],[.50,'determined'],[.71,'beaming'],[.86,'friendly'],[1,'rest']],
};

function shinoFaceAnimation(manager) {
    const limits = {
        closedSmile:.94, openSmile:.47, lipPress:.64, aa:.70, oh:.24,
        smilingEyes:.26, wideEyes:.43, softEyes:.30, blink:1,
        browLift:.65, browWarm:.56, browWorry:.59, browFocus:.32,
    };
    const names = Object.keys(limits);
    const channels = names.map(name => {
        const expression=manager.getExpression(name);
        if(!expression)throw Error('Missing Shino face shape: '+name);
        return expression;
    });
    const weights=new Float64Array(names.length),saved=new Float64Array(names.length);
    const poses={};
    for(const [name,values] of Object.entries(shinoFacePoses)){
        poses[name]=names.map(key=>values[key]??0);
    }
    const smooth=x=>x*x*(3-2*x);
    const lips=['closedSmile','openSmile','lipPress','aa','oh'].map(key=>names.indexOf(key));
    const lids=['smilingEyes','wideEyes','softEyes'].map(key=>names.indexOf(key));
    const blink=names.indexOf('blink'),blinkTimes=[2.87,7.18,10.32,15.28];

    function add(key,phase,weight){
        const beats=shinoFaceBeats[key];
        if(!beats || weight<=0)return;
        let next=1;
        while(next<beats.length-1 && phase>beats[next][0])next++;
        const [a,from]=beats[next-1],[b,to]=beats[next];
        const mix=smooth(Math.min(1,Math.max(0,(phase-a)/(b-a))));
        for(let i=0;i<weights.length;i++){
            weights[i]+=weight*((1-mix)*poses[from][i]+mix*poses[to][i]);
        }
    }
    function naturalBlink(clock){
        const beat=clock%17.6;
        for(const onset of blinkTimes){
            const t=beat-onset;
            if(t>=0 && t<.172)return t<.064?smooth(t/.064):1-smooth((t-.064)/.108);
        }
        return 0;
    }
    function apply(level,clock){
        for(let i=0;i<weights.length;i++){
            saved[i]=channels[i].weight;
            weights[i]=Math.min(limits[names[i]],weights[i]*level);
        }
        // One lip surface shares a finite range, including during crossfades.
        const total=lips.reduce((sum,i)=>sum+weights[i],0);
        if(total>1)for(const i of lips)weights[i]/=total;
        const closure=1-(1-naturalBlink(clock))*(1-weights[blink]);
        weights[blink]=closure;
        for(const i of lids)weights[i]*=1-closure;
        for(let i=0;i<weights.length;i++)channels[i].weight=Math.min(1,saved[i]+weights[i]);
    }
    function restore(){
        for(let i=0;i<weights.length;i++)channels[i].weight=saved[i];
        weights.fill(0);
    }
    return {add,apply,restore};
}
