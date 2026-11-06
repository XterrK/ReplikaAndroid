// Interaction prototype only. Amplitude is explicitly simulated; no microphone is opened.
let dispose=()=>{};
const TAU=Math.PI*2,clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
export function mountOrb(){
 dispose();const canvas=document.querySelector('#liquid-orb');if(!canvas)return;
 const ctx=canvas.getContext('2d'),meter=document.querySelector('#orb-vu'),vu=meter.getContext('2d');
 const dark=document.body.dataset.theme==='dark',reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const status=document.querySelector('#orb-status'),start=document.querySelector('#orb-start'),pause=document.querySelector('#orb-pause'),orb=document.querySelector('#orb-button'),slider=document.querySelector('#amplitude'),hint=document.querySelector('#orb-hint');
 let phase='idle',last=0,time=0,expansion=0,velocity=0,level=0,previousLevel=0,seconds=0,frameHandle,timeout,phaseTimer,stopped=false,settling=2.6,frames=0,drawSeconds=0;
 let stretch=0,stretchSpeed=0,touchAngle=0,targetAngle=0,touchX=0,touchY=0,touching=false,contact=0,contactSpeed=0,cx=0,cy=0,cvx=0,cvy=0;
 const modes=Array.from({length:5},()=>({x:0,v:0})),points=Array.from({length:96},()=>[0,0]);
 const live=()=>phase==='recording'||phase==='starting',playable=()=>phase==='recording'||phase==='paused';
 function wake(){settling=2.6;if(!frameHandle&&!timeout&&!stopped){last=0;frameHandle=requestAnimationFrame(frame)}}
 function state(next){
  phase=next;canvas.dataset.phase=phase;document.body.dataset.orbPhase=phase;
  status.textContent=({idle:'Готово к записи',starting:'Включаем запись…',recording:'Записываем',paused:'Запись на паузе',stopping:'Сохраняем…',saved:'Демонстрация сохранена'})[phase];
  start.textContent=playable()?'Остановить':phase==='saved'?'Новая запись':'Начать запись';
  start.disabled=['starting','stopping'].includes(phase);pause.hidden=!playable();pause.textContent=phase==='paused'?'Продолжить':'Пауза';
  hint.textContent=playable()?'Нажмите или потяните шар. Запись продолжится.':phase==='starting'?'Готовимся слушать':phase==='stopping'?'Завершаем запись':phase==='saved'?'В приложении запись появится в библиотеке.':'Нажмите на шар, чтобы начать';
  orb.setAttribute('aria-label',playable()?'Размять шар. '+(phase==='recording'?'Запись идёт.':'Запись на паузе.'):'Начать симуляцию записи');
  orb.disabled=['starting','stopping'].includes(phase);wake();
 }
 function action(){
  if(['idle','saved'].includes(phase)){seconds=0;state('starting');phaseTimer=setTimeout(()=>state('recording'),420)}
  else if(playable()){release();state('stopping');phaseTimer=setTimeout(()=>state('saved'),650)}
 }
 function press(x=0,y=0){if(reduced)return;touching=true;move(x,y);stretchSpeed=Math.min(3.5,stretchSpeed+1.9);contactSpeed=Math.min(5,contactSpeed+3.2);modes[0].v+=.32;modes[1].v-=.19;wake()}
 function move(x,y){touchX=clamp(x,-1,1);touchY=clamp(y,-1,1);const d=Math.min(1,Math.hypot(x,y));targetAngle=d>.12?Math.atan2(y,x):0;wake()}
 function release(){touching=false;touchX=touchY=0;wake()}
 function point(event){const r=orb.getBoundingClientRect(),radius=r.width*.34;return[(event.clientX-r.left-r.width/2)/radius,(event.clientY-r.top-r.height/2)/radius]}
 start.onclick=action;pause.onclick=()=>state(phase==='paused'?'recording':'paused');
 orb.onclick=event=>{if(!playable())action();else if(event.detail===0){press(.65,-.15);release()}};
 orb.onpointerdown=event=>{if(!playable())return;event.preventDefault();orb.setPointerCapture(event.pointerId);press(...point(event))};
 orb.onpointermove=event=>{if(touching&&orb.hasPointerCapture(event.pointerId))move(...point(event))};
 orb.onpointerup=orb.onpointercancel=event=>{if(!playable())return;release();if(orb.hasPointerCapture(event.pointerId))orb.releasePointerCapture(event.pointerId)};
 document.querySelector('#orb-reset').onclick=()=>{clearTimeout(phaseTimer);release();seconds=0;slider.value=.25;state('idle')};
 slider.oninput=wake;document.querySelectorAll('[data-sim]').forEach(button=>button.onclick=()=>{slider.value=button.dataset.sim;wake()});
 function physics(dt){
  const raw=phase==='recording'?+slider.value:0;
  // This display envelope receives ONLY the test slider, never touch impulses.
  level+=(raw-level)*(1-Math.exp(-dt/(raw>level?.038:.32)));
  if(reduced){expansion=(live()?.09:0)+level*.125;stretch=cx=cy=contact=0;for(const m of modes)m.x=0;return}
  const onset=Math.max(0,level-previousLevel);previousLevel=level;
  if(onset>.015)modes.forEach((m,j)=>m.v+=(j%2?-1:1)*onset*.18/(j+1));
  const count=Math.max(1,Math.ceil(dt*120)),h=dt/count;
  for(let n=0;n<count;n++){
   time+=h;const target=(live()?.09:0)+level*.125;velocity+=(88*(target-expansion)-11.8*velocity)*h;expansion=clamp(expansion+velocity*h,-.025,.235);
   modes.forEach((m,j)=>{const target=(.0015+level*.025)/Math.sqrt(j+1)*Math.sin(time*(1.65+j*.43)+j*1.3);m.v+=((36+j*10)*(target-m.x)-5.7*m.v)*h;m.x=clamp(m.x+m.v*h,-.026,.026)});
   touchAngle+=Math.atan2(Math.sin(targetAngle-touchAngle),Math.cos(targetAngle-touchAngle))*(1-Math.exp(-h*13));
   const stretchTarget=touching?.19+Math.min(1,Math.hypot(touchX,touchY))*.17:0;
   stretchSpeed+=(62*(stretchTarget-stretch)-7.8*stretchSpeed)*h;stretch=clamp(stretch+stretchSpeed*h,-.16,.43);
   cvx+=(72*((touching?touchX*.16:0)-cx)-10*cvx)*h;cvy+=(72*((touching?touchY*.16:0)-cy)-10*cvy)*h;cx=clamp(cx+cvx*h,-.19,.19);cy=clamp(cy+cvy*h,-.19,.19);
   contactSpeed+=(-55*contact-8.5*contactSpeed)*h;contact=clamp(contact+contactSpeed*h,-.18,.55);
  }
 }
 function draw(){
  const w=canvas.width,base=w/2,sx=Math.exp(stretch),sy=1/sx;let squares=0,maxRadius=0,minRadius=Infinity;
  for(let i=0;i<points.length;i++){
   const a=i*TAU/points.length,relative=a-touchAngle,ca=Math.cos(relative),sa=Math.sin(relative);
   let wave=0;modes.forEach((m,j)=>wave+=m.x*Math.sin(a*(j+2)+time*.24+j*1.7));
   const boundary=(1/Math.sqrt(ca*ca/(sx*sx)+sa*sa/(sy*sy)))*(1+clamp(wave*2.5+contact*.085*Math.cos(relative*3-time*1.1),-.2,.2)+.006*Math.sin(a*3+time*.48));
   points[i][0]=Math.cos(a)*boundary;points[i][1]=Math.sin(a)*boundary;squares+=boundary*boundary;
  }
  const areaScale=1/Math.sqrt(squares/points.length);
  for(const p of points){p[0]*=areaScale;p[1]*=areaScale;const r=Math.hypot(...p);maxRadius=Math.max(maxRadius,r);minRadius=Math.min(minRadius,r)}
  const desired=w*.34*(1+expansion),r=Math.min(desired,w*.43/maxRadius),c=base+cx*r,y=base+cy*r;
  const path=new Path2D();
  for(let i=0;i<points.length;i++){const p=points[(i+points.length-1)%points.length],q=points[i],n=points[(i+1)%points.length],m=points[(i+2)%points.length];if(!i)path.moveTo(c+q[0]*r,y+q[1]*r);path.bezierCurveTo(c+(q[0]+(n[0]-p[0])/6)*r,y+(q[1]+(n[1]-p[1])/6)*r,c+(n[0]-(m[0]-q[0])/6)*r,y+(n[1]-(m[1]-q[1])/6)*r,c+n[0]*r,y+n[1]*r)}path.closePath();
  ctx.clearRect(0,0,w,w);
  let g=ctx.createRadialGradient(base,base+desired*.97,0,base,base+desired*.97,desired);g.addColorStop(0,dark?'#9e84d329':'#727eae25');g.addColorStop(1,'#0000');ctx.fillStyle=g;ctx.beginPath();ctx.ellipse(base+cx*r*.4,base+desired*.97,desired,desired*.15,0,0,TAU);ctx.fill();
  ctx.save();ctx.clip(path);ctx.translate(c,y);ctx.rotate(touchAngle);ctx.scale(sx,sy);ctx.translate(-c,-y);
  g=ctx.createLinearGradient(c-r,y-r,c+r,y+r);g.addColorStop(0,dark?'#dceaff':'#f4fbff');g.addColorStop(.25,dark?'#7fa6e8':'#b9d8ed');g.addColorStop(.56,dark?'#8580d5':'#c7b8e6');g.addColorStop(.82,dark?'#4d497e':'#d9d9ed');g.addColorStop(1,dark?'#c6aeed':'#f4f8ff');ctx.fillStyle=g;ctx.globalAlpha=dark ? .80 : .64;ctx.fillRect(c-r*2,y-r*2,r*4,r*4);ctx.globalAlpha=1;
  g=ctx.createRadialGradient(c-r*.18,y-r*.27,r*.05,c,y,r*1.06);g.addColorStop(0,'#ffffff20');g.addColorStop(.55,'#9daff500');g.addColorStop(.83,dark?'#27305632':'#737da325');g.addColorStop(.94,dark?'#c9c0ef7c':'#ece5f490');g.addColorStop(1,dark?'#e8e9ffbf':'#ffffffdf');ctx.fillStyle=g;ctx.fillRect(c-r*2,y-r*2,r*4,r*4);
  g=ctx.createRadialGradient(c-r*.1,y+r*.42,0,c-r*.1,y+r*.42,r*.9);g.addColorStop(0,dark?'#c4dbff65':'#ffffff9c');g.addColorStop(.5,dark?'#a9b8ff24':'#e8f9ff44');g.addColorStop(1,'#ffffff00');ctx.fillStyle=g;ctx.fillRect(c-r*2,y-r*2,r*4,r*4);
  ctx.save();ctx.translate(c,y);ctx.rotate(-.48+Math.sin(time*.32)*.05);g=ctx.createLinearGradient(0,-r*.4,0,r*.33);g.addColorStop(0,'#fff0');g.addColorStop(.38,dark?'#e4e8ff19':'#ffffff28');g.addColorStop(.54,dark?'#ecebff68':'#ffffff80');g.addColorStop(.71,'#fff0');ctx.fillStyle=g;ctx.beginPath();ctx.ellipse(0,-r*.08,r*1.3,r*.55,0,0,TAU);ctx.fill();ctx.restore();
  const lx=c-r*.43+Math.sin(time*.38)*r*.04,ly=y-r*.54;
  g=ctx.createRadialGradient(lx,ly,0,lx,ly,r*.31);g.addColorStop(0,'#fffffff5');g.addColorStop(.20,'#ffffffa0');g.addColorStop(.53,'#ffffff22');g.addColorStop(1,'#fff0');ctx.fillStyle=g;ctx.fillRect(c-r*2,y-r*2,r*4,r*4);
  ctx.save();ctx.translate(c-r*.27,y-r*.55);ctx.rotate(-.56);ctx.scale(1,.16);g=ctx.createRadialGradient(0,0,0,0,0,r*.52);g.addColorStop(0,'#fffffff0');g.addColorStop(.4,'#ffffff80');g.addColorStop(1,'#fff0');ctx.fillStyle=g;ctx.beginPath();ctx.arc(0,0,r*.52,0,TAU);ctx.fill();ctx.restore();
  ctx.strokeStyle='#ffffff9c';ctx.lineWidth=1.6;ctx.beginPath();ctx.ellipse(c-r*.12,y-r*.13,r*.7,r*.73,-.2,Math.PI*1.04,Math.PI*1.48);ctx.stroke();
  ctx.restore();g=ctx.createLinearGradient(c-r,y-r,c+r,y+r);g.addColorStop(0,'#ffffffed');g.addColorStop(.4,'#adc9ff55');g.addColorStop(.8,'#f6d3edb8');g.addColorStop(1,'#ffffff77');ctx.strokeStyle=g;ctx.lineWidth=1.7;ctx.stroke(path);
  canvas.dataset.expansion=expansion.toFixed(4);canvas.dataset.level=level.toFixed(4);canvas.dataset.stretch=stretch.toFixed(4);canvas.dataset.shapeRatio=(maxRadius/minRadius).toFixed(4);canvas.dataset.touch=touching?'active':'released';drawVu();
 }
 function drawVu(){
  const w=meter.width,h=meter.height,input=phase==='recording'?level:0;vu.clearRect(0,0,w,h);
  const g=vu.createLinearGradient(0,h,0,0);g.addColorStop(0,dark?'#a4baff':'#729be3');g.addColorStop(.5,dark?'#b8a6f0':'#a494df');g.addColorStop(1,dark?'#ecc5e1':'#d998c1');vu.fillStyle=g;
  [.38,.72,1,.78,.48].forEach((factor,i)=>{const height=input>0.002?5+input*factor*(h-14):3;vu.globalAlpha=input>.002?.86:.2;vu.beginPath();vu.roundRect(4+i*11,(h-height)/2,6,height,3);vu.fill()});vu.globalAlpha=1;meter.dataset.level=input.toFixed(4);meter.setAttribute('aria-valuenow',Math.round(input*100));
 }
 function frame(now){
  frameHandle=0;timeout=0;if(stopped||!canvas.isConnected||document.hidden)return;
  const wall=Math.min(.3,(now-last)/1000||1/60),dt=Math.min(.05,wall);last=now;drawSeconds+=wall;if(phase==='recording')seconds+=wall;settling-=wall;
  document.querySelector('#orb-time').textContent=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
  physics(dt);draw();canvas.dataset.frames=++frames;canvas.dataset.fps=(frames/drawSeconds).toFixed(1);
  if(live()||touching||settling>0){if(reduced||!live())timeout=setTimeout(()=>{timeout=0;frameHandle=requestAnimationFrame(frame)},reduced?120:50);else frameHandle=requestAnimationFrame(frame)}
 }
 const visibility=()=>{if(!document.hidden)wake()};document.addEventListener('visibilitychange',visibility);
 state('idle');dispose=()=>{stopped=true;cancelAnimationFrame(frameHandle);clearTimeout(timeout);clearTimeout(phaseTimer);document.removeEventListener('visibilitychange',visibility)};
}
