"""Build Shino's motion library in Blender, from the acting sheets and CC0 KayKit takes."""
import json, math, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from rig import ROOT, Rig, Pose, write_motion, xyz, palm_frame, Vector, Quaternion, IDENTITY, FPS
from gestures import channels,sample_curve,SHEETS
from surfaces import Surfaces

CLIPS=[
 ('idle_loop','Дыхание',5.0,'base'),('walk','Обычный шаг',1.30,'gait'),('formal','Сдержанный шаг',1.57,'gait'),('soft-walk','Мягкая прогулка',1.60,'gait'),
 ('stand','Спокойная стойка',5.2,'idle'),('look','Осматривается',5.6,'idle'),('think','Задумалась',4.8,'idle'),('wait','Нетерпеливое ожидание',4.6,'idle'),
 ('hello','Привет!',3.2,'scene'),('peek','Ку-ку',3.2,'scene'),('yawn','Сонное потягивание',4.6,'scene'),('idea','Смотри, какая идея!',4.0,'scene'),('plane','Самолётик',4.0,'scene'),('hop','Классики',4.3,'scene'),('sneak','Крадётся',4.8,'scene'),('dance','Танцевальная пауза',5.6,'scene'),
 ('start','Первый шаг',1.1,'travel'),('stop','Остановка',1.2,'travel'),('turn','Разворот',1.53,'travel'),
 ('curtsy','Реверанс',3.4,'scene'),('highfive','Дай пять!',2.5,'scene'),('shrug','Пожимает плечами',2.8,'scene'),('giggle','Заливается смехом',4.7,'scene'),('chilly','Бр-р, холодно!',5.2,'scene'),('hairdo','Поправляет причёску',4.7,'scene'),('swat','Отгоняет муху',3.9,'scene'),('twist','Твист',4.7,'scene'),('duckdance','Танец утят',4.6,'scene'),('teapot','Я чайничек!',4.4,'scene'),('superhero','Супергероиня',4.0,'scene'),('hummingbird','Колибри',5.1,'scene')]
STRIDE={'walk':.85,'formal':.72,'soft-walk':.70}
TAU=math.tau
def smooth(x):
    x=max(0,min(1,x));return x*x*x*(10+x*(-15+6*x))
def bump(u):return math.sin(math.pi*max(0,min(1,u)))**2
def pulse(t,a,b):return bump((t-a)/(b-a)) if a<t<b else 0
def wave(u,n):return math.sin(TAU*u*n)
kay=json.loads((ROOT/'MotionSource/kaykit.json').read_text())
for row in kay.values():
    row['ix']={n:i for i,n in enumerate(row['bones'])}
def capture(key,bone,u):
    clip=kay[key];rows=clip['frames'];coord=(max(0,min(1,u)))*(len(rows)-1)
    a=int(coord);i=clip['ix'][bone]
    return Quaternion(rows[a][i]).slerp(Quaternion(rows[min(a+1,len(rows)-1)][i]),coord-a)

def step(p,stride,lift):
    swing=max(0,(p-.60)/.40)
    return stride*(.30-p+smooth(swing)),lift*math.sin(math.pi*swing)**1.55, 9*pulse(p,0,.27)-16*pulse(p,.40,.74)
def fingers(pose,side,sign,curl,point):
    for digit,fan,bend in [('Index',2,1-.86*point),('Middle',0,1),('Ring',-1.2,1.12),('Little',-2.9,1.28)]:
        for part,angle in [('Proximal',40),('Intermediate',43),('Distal',21)]:
            pose.q[side+digit+part]=xyz(0,sign*fan*(1-curl) if part=='Proximal' else 0, -sign*curl*bend*angle)
    for part,bend in [('Metacarpal',9),('Proximal',12),('Distal',15)]:
        pose.q[side+'Thumb'+part]=xyz(0,sign*(4+curl*bend),-sign*(3+curl*5))

def plane_heading(u):
    # Bank into the circle after takeoff, then roll out facing the starting direction.
    return TAU*smooth((u-.12)/.76)

def plane_travel(phases,rig):
    # Project forward steps onto the desktop as the character rounds the turn.
    screen_height=2*rig.rest['head'].y*2.31*math.tan(math.radians(16))
    path=[0.]
    for a,b in zip(phases,phases[1:]):
        u=(a+b)/2
        stride=.74*smooth(u/.16)*smooth((1-u)/.16)
        path.append(path[-1]+4*stride*(b-a)*math.cos(plane_heading(u))/screen_height)
    return [round(x,5) for x in path]

def make_pose(rig,surfaces,key,role,u,curve):
    values=sample_curve(*curve,u)
    left,right=values[:14].copy(),values[14:28].copy()
    pitch,yaw,roll,hx,hy,hz,shift,dip=values[28:]
    gait=role=='gait';idle=role in ('base','idle')
    envelope=1 if gait or idle else smooth(u/.16)*smooth((1-u)/.16)
    phase=u;stride=0;lift=0
    if gait:stride=STRIDE[key];lift=.060 if key=='walk' else .047
    elif key in ('start','stop','turn'):
        phase=u*(1 if key=='turn' else .78)+(.4 if key=='stop' else 0)
        stride=.63*(smooth(u) if key=='start' else smooth(1-u) if key=='stop' else bump(u));lift=.050
    elif key in ('plane','sneak','hummingbird'):
        phase=u*(3 if key=='sneak' else 4)
        stride={'plane':.74,'sneak':.46,'hummingbird':.37}[key]*envelope;lift=.075*envelope
    if key=='plane':
        lift=.095*envelope
        roll+=11*pulse(u,.15,.86)
        hy+=13*pulse(u,.10,.53)
    activeStep=min(1,stride/.37)
    if activeStep:
        sway=math.cos(TAU*(phase-.21));shift+=.025*sway*activeStep
        dip+=.018*math.cos(TAU*2*(phase-.15))*activeStep
        yaw+=3.3*wave(phase+.1,1)*activeStep;roll+=1.7*sway*activeStep
        if gait or role=='travel':
            swing=wave(phase-.05,1)
            left[2]+=.105*swing*activeStep;right[2]-=.105*swing*activeStep
            left[1]+=.016*abs(swing)*activeStep;right[1]+=.017*abs(swing)*activeStep
    breathing=wave(u,1 if idle else 2)
    bounce=0
    if key=='hop':
        for a,b,h in [(.16,.34,.102),(.38,.57,.135),(.61,.80,.117)]:
            bounce+=h*pulse(u,a,b)
    if key=='chilly':
        shake=wave(u,11)*envelope
        left[1]+=.014*shake;right[1]-=.010*shake;roll+=1.7*shake;hz-=2*shake
    if key=='giggle':
        laugh=wave(u,6)*envelope;pitch+=3.1*laugh;dip+=.012*laugh;right[1]+=.006*laugh
    if key=='hello':
        a=pulse(u,.19,.83)*wave(u,4)
        right[0]+=.033*a;right[3]+=.33*a
    if key=='hummingbird':
        flutter=envelope*wave(u,9)
        for hand in (left,right):hand[1]+=.044*flutter;hand[4]+=.22*flutter
    if key in ('dance','twist','duckdance'):
        dip+=.014*envelope*(1+math.cos(TAU*6*u));yaw+=4*envelope*wave(u,4)
    pose=Pose(rig);pose.hips+=Vector((shift,-.018-dip+.002*breathing+bounce,0))
    for n,w in [('hips',.18),('spine',.33),('chest',.31),('upperChest',.18)]:
        pose.q[n]=xyz((pitch+.65*breathing)*w,yaw*w,roll*w)
    if activeStep:pose.q['hips'] @= xyz(0,-7*wave(phase+.1,1)*activeStep,0)
    pose.q['neck']=xyz(.36*hx,.36*hy,.36*hz);pose.q['head']=xyz(.64*hx,.64*hy,.64*hz)
    for side,s,hand in [('left',1,left),('right',-1,right)]:
        # Lower each resting shoulder, letting it lift as that hand reaches for a gesture.
        raised=smooth((hand[1]+.31)/.14)
        drop=-.6 if gait else -2.8+2.2*raised
        pose.q[side+'Shoulder']=xyz(0,-s*.7,s*(drop+(2.5-drop)*pulse(u,.22,.83) if key=='shrug' else drop))
    pose.fk()
    for side,s,hand in [('left',1,left),('right',-1,right)]:
        p=(phase+(0 if s==1 else .5))%1
        z,y,footPitch=step(p,stride,lift) if activeStep else (0,0,0)
        width=.075 if gait else .083
        if key=='curtsy' and s==1:
            f=pulse(u,.10,.92);width-=.098*f;z-=.158*f;y+=.048*f;footPitch-=23*f
        if key=='hop':
            f=(pulse(u,.13,.49) if s==1 else pulse(u,.40,.78));y+=.115*f;z-=.115*f;width+=.026*f
        if key in ('dance','twist','duckdance','superhero'):
            width+=(.050 if key=='superhero' else .029)*envelope
            if key!='superhero':y+=.023*max(0,s*wave(u,3))*envelope
        if key=='highfive' and s==-1:z+=.095*pulse(u,.2,.95)
        pose.limb(side,False,Vector((s*width,rig.rest[side+'Foot'].y+y+bounce,z+.008*s)),
                  Vector((.12*s,.12,1)),xyz(footPitch,4*s+(11*wave(u,3)*envelope if key=='twist' else 0),0))
        chest=pose.rot['upperChest'];origin=pose.pos['upperChest']
        def body(v):return chest@Vector((s*v[0],v[1],v[2]))
        goal=origin+body(hand[:3]);direction=body(hand[3:6]);thumb=body(hand[6:9])
        pose.limb(side,True,goal,body(hand[9:12]),palm_frame(direction,thumb,s)@rig.arm_bind[side+'Hand'])
        if key=='hairdo' and side=='right':
            # Roll from the elbow as the hand lifts. Keep the wrist nearly in line
            # with the forearm while the fingertips follow the lock of hair.
            reach=smooth(u/.17)*smooth((1-u)/.17)
            axis=rig.offset['rightHand'].normalized()
            pose.q['rightLowerArm'] @= Quaternion(axis,math.radians(44)*reach)
            pose.update('rightLowerArm')
            fingers_rest=rig.offset['rightMiddleProximal'].normalized()
            aim=pose.rot['rightLowerArm'].inverted()@direction.normalized()
            bend=fingers_rest.rotation_difference(aim)
            wrist=IDENTITY.slerp(bend,min(1,math.radians(22)/max(bend.angle,.0001)))
            pose.q['rightHand']=wrist
        fingers(pose,side,s,hand[12],hand[13])
        if key in ('walk','sneak','hello'):
            source={'hello':'wave','walk':'walk','sneak':'sneak'}[key]
            names={'hello':['UpperArm','LowerArm','Hand'] if s==-1 else [],
                   'sneak':['UpperLeg','LowerLeg','UpperArm','LowerArm'],'walk':['UpperArm','LowerArm','UpperLeg','LowerLeg']}[key]
            weight={'hello':.24*envelope,'sneak':.19*envelope,'walk':.19}[key]
            for n in names:
                bone=side+n
                pose.q[bone]=pose.q[bone].slerp(capture(source,bone,u if key=='hello' else phase%1),weight)
        if gait or role=='travel':
            # Use the final forearm, including the captured upper/lower arm swing.
            for part in ('UpperArm','LowerArm','Hand'):
                pose.update(side+part)
            forearm=(pose.pos[side+'Hand']-pose.pos[side+'LowerArm']).normalized()
            swing=s*wave(phase-.12,1)
            # A loose wrist follows the forearm with a small delayed flexion.
            aim=forearm.lerp(chest@Vector((0,-1,0)),.20).normalized()
            aim=Quaternion(chest@Vector((1,0,0)),math.radians(-11*swing))@aim
            palm=palm_frame(aim,body((-.22,.04,1)),s)@rig.arm_bind[side+'Hand']
            wrist=pose.rot[side+'LowerArm'].inverted()@palm
            pose.q[side+'Hand']=pose.q[side+'Hand'].slerp(wrist,activeStep)
    if key=='plane':
        heading=xyz(0,math.degrees(plane_heading(u)),0)
        pose.q['hips']=heading@pose.q['hips']
        pose.hips=rig.rest['hips']+heading@(pose.hips-rig.rest['hips'])
    surfaces.plant(pose,bounce)
    return pose

if __name__=='__main__':
    rig=Rig();surface=Surfaces(rig);output=ROOT/'Motions'
    output.mkdir(exist_ok=True);rows=[];base={};actions={}
    for key,label,duration,role in CLIPS:
        steps=round(duration*FPS);duration=steps/FPS
        curve=channels(key,role)
        frames=[make_pose(rig,surface,key,role,k/steps,curve) for k in range(steps+1)]
        if key=='hairdo':
            rest=actions['idle_loop'][0].q['rightHand']
            for i,pose in enumerate(frames):
                u=i/steps
                pose.q['rightHand']=rest.slerp(pose.q['rightHand'],smooth(u/.17)*smooth((1-u)/.17))
        if role in ('gait','idle','base'):frames[-1]=frames[0]
        write_motion(output/(key+'.vrma'),rig,key,frames);actions[key]=frames
        row=dict(key=key,label=label,duration=duration,role=role,file=key+'.vrma')
        if role in ('base','gait'):base[key+'.vrma']={'duration':duration,'cycleTravel':STRIDE.get(key,0)/(2*rig.rest['head'].y*2.31*math.tan(math.radians(16)))}
        else:
            if key in ('plane','hummingbird','sneak','start','stop','turn'):
                dist={'plane':1.06,'sneak':.72,'hummingbird':.68,'start':.23,'stop':.21,'turn':.19}[key]
                phase=[i/60 for i in range(61)]
                row['travel']=[round(dist*(math.sin(math.pi*smooth(t)) if key=='turn' else t*t if key=='start' else t*(2-t) if key=='stop' else (t-math.sin(TAU*t)/TAU)),5) for t in phase]
                if key=='plane':row['travel']=plane_travel(phase,rig)
                if key=='turn':row['heading']=[round(math.pi*smooth(t),5) for t in phase]
            rows.append(row)
        print('Baked',key,len(frames),flush=True)
    (output/'catalog.json').write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':')))
    (output/'base.json').write_text(json.dumps(base))
    if '--blend' in sys.argv:
        from workshop import save_workshop
        save_workshop(rig,actions)
