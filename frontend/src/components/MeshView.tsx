import {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js';
import type {SimulationState} from '../types';
const R=6371;
function earthTexture(){
 const c=document.createElement('canvas');c.width=2048;c.height=1024;const x=c.getContext('2d')!;
 x.fillStyle='#092943';x.fillRect(0,0,c.width,c.height);
 const shapes=[[[ -168,70],[-140,71],[-124,58],[-128,48],[-116,30],[-98,15],[-82,8],[-78,22],[-64,47],[-53,53],[-65,63],[-90,74]],[[ -80,10],[-62,9],[-50,-2],[-35,-7],[-47,-24],[-59,-54],[-73,-53],[-78,-20]],[[ -18,35],[6,38],[33,31],[45,12],[50,-12],[32,-35],[17,-35],[7,-16],[-10,4]],[[ -10,36],[-9,58],[9,72],[44,69],[65,78],[100,73],[140,59],[178,66],[165,48],[138,35],[127,20],[108,5],[101,7],[88,22],[77,8],[67,25],[47,30],[35,42],[25,36]],[[112,-11],[138,-11],[154,-25],[145,-40],[116,-35]],[[ -54,59],[-20,70],[-34,83],[-60,82]],[[48,-13],[51,-24],[45,-26],[44,-17]],[[130,32],[145,45],[143,32]],[[ -180,-72],[-100,-67],[0,-72],[100,-67],[180,-74],[180,-90],[-180,-90]]];
 for(const shape of shapes){x.beginPath();shape.forEach(([lon,lat],i)=>{const px=(lon+180)/360*c.width,py=(90-lat)/180*c.height;i?x.lineTo(px,py):x.moveTo(px,py);});x.closePath();x.fillStyle='#286978';x.fill();x.strokeStyle='#69b5b6';x.lineWidth=1.2;x.stroke();}
 x.strokeStyle='rgba(96,170,190,.14)';x.lineWidth=1;for(let i=0;i<=24;i++){x.beginPath();x.moveTo(i*c.width/24,0);x.lineTo(i*c.width/24,c.height);x.stroke();}for(let i=0;i<=12;i++){x.beginPath();x.moveTo(0,i*c.height/12);x.lineTo(c.width,i*c.height/12);x.stroke();}
 const texture=new THREE.CanvasTexture(c);texture.colorSpace=THREE.SRGBColorSpace;return texture;
}
function label(text:string,color='#b7d7e8'){
 const c=document.createElement('canvas');c.width=256;c.height=64;const x=c.getContext('2d')!;x.font='500 28px monospace';x.textAlign='center';x.fillStyle=color;x.fillText(text,128,39);
 const m=new THREE.SpriteMaterial({map:new THREE.CanvasTexture(c),transparent:true,depthTest:true});const s=new THREE.Sprite(m);s.scale.set(.29,.0725,1);return s;
}
function dispose(root:THREE.Object3D){root.traverse(o=>{const m=o as THREE.Mesh;m.geometry?.dispose();if(m.material){const materials=Array.isArray(m.material)?m.material:[m.material];materials.forEach(a=>{if(a instanceof THREE.SpriteMaterial)a.map?.dispose();if(a instanceof THREE.MeshPhongMaterial)a.map?.dispose();a.dispose();});}});}
function attitude(axes:number[][]){if(axes.length!==3)return new THREE.Quaternion();const m=new THREE.Matrix4().set(axes[0][0],axes[0][1],axes[0][2],0,axes[1][0],axes[1][1],axes[1][2],0,axes[2][0],axes[2][1],axes[2][2],0,0,0,0,1);return new THREE.Quaternion().setFromRotationMatrix(m);}
function hermite(a:number[],v:number[],b:number[],w:number[],u:number,dt:number){const u2=u*u,u3=u2*u;return new THREE.Vector3(...a.map((x,i)=>(2*u3-3*u2+1)*x+(u3-2*u2+u)*dt*v[i]+(-2*u3+3*u2)*b[i]+(u3-u2)*dt*w[i]) as [number,number,number]);}
export default function MeshView({state,selected,onSelect}:{state:SimulationState;selected:string|null;onSelect:(id:string)=>void;activeRoute?:string[]}){
 const host=useRef<HTMLDivElement>(null),latest=useRef(state),selection=useRef(selected),select=useRef(onSelect);latest.current=state;selection.current=selected;select.current=onSelect;
 const timeline=useRef({frames:[{time_s:state.time_s,run_epoch:state.run_epoch,satellites:state.satellites}],display:state.time_s,received:performance.now(),lastFrame:performance.now(),rate:1,paused:state.paused});
 useEffect(()=>{const x=timeline.current,now=performance.now();const last=x.frames[x.frames.length-1];
  if(state.run_epoch!==last.run_epoch){timeline.current={frames:[{time_s:state.time_s,run_epoch:state.run_epoch,satellites:state.satellites}],display:state.time_s,received:now,lastFrame:now,rate:1,paused:state.paused};return;}
  if(state.paused!==x.paused){x.received=now;x.paused=state.paused;}
  if(state.time_s>last.time_s){x.rate=Math.max(.1,Math.min(200,(state.time_s-last.time_s)/Math.max(.05,(now-x.received)/1000)));x.received=now;x.frames.push({time_s:state.time_s,run_epoch:state.run_epoch,satellites:state.satellites});x.frames=x.frames.slice(-20);}
 },[state]);
 const [error,setError]=useState(''),[hover,setHover]=useState(''),[epoch,setEpoch]=useState('live'),[cones,setCones]=useState(true);const epochRef=useRef(epoch),conesRef=useRef(cones),reset=useRef<()=>void>(()=>{});epochRef.current=epoch;conesRef.current=cones;
 useEffect(()=>{
  const el=host.current!;let renderer:THREE.WebGLRenderer;try{renderer=new THREE.WebGLRenderer({antialias:true});}catch{setError('WebGL is unavailable. Enable browser hardware acceleration.');return;}
  renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.autoClear=false;el.appendChild(renderer.domElement);
  const scene=new THREE.Scene(),formation=new THREE.Scene();scene.background=new THREE.Color('#06111d');formation.background=new THREE.Color('#d7e4ed');
  const camera=new THREE.PerspectiveCamera(38,1,.01,80);camera.position.set(2.65,1.45,2.8);const fc=new THREE.PerspectiveCamera(40,1,.01,1000);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.enablePan=false;controls.minDistance=1.65;controls.maxDistance=8;
  reset.current=()=>{camera.position.set(2.65,1.45,2.8);controls.target.set(0,0,0);};
  scene.add(new THREE.AmbientLight(0xa6c8e9,.42));formation.add(new THREE.AmbientLight(0xffffff,2.2));
  const sun=new THREE.DirectionalLight(0xfff0d9,3.0);scene.add(sun);const fsun=new THREE.DirectionalLight(0xffffff,2);fsun.position.set(8,5,3);formation.add(fsun);
  const earth=new THREE.Mesh(new THREE.SphereGeometry(1,72,48),new THREE.MeshPhongMaterial({map:earthTexture(),shininess:7}));scene.add(earth);
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.015,48,32),new THREE.MeshBasicMaterial({color:0x4aa5e0,transparent:true,opacity:.1,side:THREE.BackSide})));
  const ground=new THREE.Mesh(new THREE.OctahedronGeometry(.014),new THREE.MeshBasicMaterial({color:0x72edc7}));scene.add(ground);
  const groundTag=label('PUNE / GND','#8fe8ce');groundTag.scale.multiplyScalar(.7);scene.add(groundTag);
  const orbitLine=new THREE.Line(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0x669bb8,transparent:true,opacity:.35}));scene.add(orbitLine);
  const trackMarker=new THREE.Mesh(new THREE.SphereGeometry(.024,12,8),new THREE.MeshBasicMaterial({color:0xffbf71}));scene.add(trackMarker);
  const clusterTag=label('50 km FORMATION','#f1ca91');clusterTag.scale.multiplyScalar(1.05);scene.add(clusterTag);
  const antennaGroup=new THREE.Group();formation.add(antennaGroup);
  const bodies=new Map<string,THREE.Group>(),dots=new Map<string,THREE.Mesh>();const graph=new THREE.Group(),allocation=new THREE.Group(),targetGroup=new THREE.Group();formation.add(graph,allocation);scene.add(targetGroup);
  let signature='',linkSignature='',frame=0,w=1,h=1,split=.6,lastTargetStamp='',coneSignature='';let moved=false,downX=0,downY=0;
  const ray=new THREE.Raycaster(),mouse=new THREE.Vector2();ray.params.Line={threshold:.12};
  const vector=(p:number[],scale=1)=>new THREE.Vector3(p[0]*scale,p[1]*scale,p[2]*scale);
  const makeBody=(id:string,group:string)=>{
   const g=new THREE.Group();g.userData.id=id;
   const body=new THREE.Mesh(new THREE.BoxGeometry(.10,.10,.3),new THREE.MeshPhongMaterial({color:0xced3db,shininess:50}));g.add(body);
   for(const sign of [-1,1]){const panel=new THREE.Mesh(new THREE.BoxGeometry(.45,.02,.24),new THREE.MeshPhongMaterial({color:group==='SWARM-01'?0x166497:0x725b9f,shininess:25}));panel.position.x=sign*.3;g.add(panel);const ant=new THREE.Mesh(new THREE.SphereGeometry(.045,8,6),new THREE.MeshBasicMaterial({color:0xb17c29}));ant.position.x=sign*.08;g.add(ant);}
   const tag=label(id,group==='SWARM-01'?'#123e65':'#593d7b');tag.scale.set(1.4,.35,1);tag.position.y=.45;g.add(tag);
   const lock=label('▣ LOCK','#99651a');lock.name='lock';lock.position.y=.85;lock.scale.set(1,.25,1);g.add(lock);
   const leader=label('COORDINATOR','#665013');leader.name='leader';leader.position.y=1.13;leader.scale.set(1.6,.4,1);g.add(leader);
   return g;
  };
  function drawLine(a:string,b:string,color:number,dashed=false,opacity=1){
   const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute([0,0,0,0,0,0],3));
   const material=dashed?new THREE.LineDashedMaterial({color,dashSize:.15,gapSize:.12,transparent:true,opacity}):new THREE.LineBasicMaterial({color,transparent:true,opacity});
   const line=new THREE.Line(geometry,material);line.userData.source=a;line.userData.target=b;line.frustumCulled=false;return line;
  }
  function updateLine(line:THREE.Line){const a=bodies.get(line.userData.source)?.position,b=bodies.get(line.userData.target)?.position;if(!a||!b){line.visible=false;return;}line.visible=true;const attribute=line.geometry.getAttribute('position') as THREE.BufferAttribute;attribute.setXYZ(0,a.x,a.y,a.z);attribute.setXYZ(1,b.x,b.y,b.z);attribute.needsUpdate=true;line.geometry.computeBoundingSphere();if(line.material instanceof THREE.LineDashedMaterial)line.computeLineDistances();}
  function rebuild(s:SimulationState,history:typeof s.graph_history[number]|undefined){
   dispose(graph);graph.clear();dispose(allocation);allocation.clear();
   const edges=history?.edges??s.links.filter(l=>l.target!=='GND');const backbone=new Set(history?.backbone??s.graph_history[s.graph_history.length-1]?.backbone??[]);
   for(const edge of edges){const strong=backbone.has(edge.key),chosen=edge.source===selection.current||edge.target===selection.current;
    const line=drawLine(edge.source,edge.target,!edge.available?0xab5668:strong?0x193d54:0x527991,!strong,!edge.available?.27:strong?.95:chosen?.3:.075);line.userData.link=edge;graph.add(line);
    if(strong&&s.satellites.length<=20){const tag=label(edge.weight.toFixed(2),'#183e55');tag.scale.set(.85,.2125,1);tag.userData.edge=edge.key;tag.userData.source=edge.source;tag.userData.target=edge.target;graph.add(tag);}
   }
   if(!history){
    for(const t of s.tasks.filter(t=>t.owner&&!['delivered','expired','failed'].includes(t.status))){if(t.coordinator_id&&t.coordinator_id!==t.owner){const line=drawLine(t.coordinator_id,t.owner!,0xbd7c16,true,.95);line.userData.kind='allocation';line.userData.task=t.task_id;allocation.add(line);}}
    for(const m of s.control_messages.filter(m=>m.status==='in_flight'&&m.target&&m.holder!==m.target).slice(0,10)){const line=drawLine(m.holder,m.target!,0x147ea7,true,.85);line.userData.kind='request';allocation.add(line);}
    for(const t of s.tasks.filter(t=>t.status==='processed'))for(let i=0;i<t.route.length-1;i++)if(t.route[i+1]!=='GND'){const line=drawLine(t.route[i],t.route[i+1],0x148a64,false,.95);line.userData.kind='product';allocation.add(line);}
   }
  }
  function animate(){
   const s=latest.current,clock=timeline.current,now=performance.now(),wallDt=Math.min(.08,Math.max(0,(now-clock.lastFrame)/1000));clock.lastFrame=now;
   const newest=clock.frames[clock.frames.length-1];
   if(s.paused){clock.display+=(newest.time_s-clock.display)*(1-Math.exp(-wallDt/.3));}
   else{const lag=Math.max(.8,clock.rate*.75),target=Math.min(newest.time_s,newest.time_s-lag+(now-clock.received)/1000*clock.rate),velocity=Math.max(0,Math.min(2*clock.rate,clock.rate+1.8*(target-clock.display)));clock.display=Math.min(newest.time_s+Math.min(5,clock.rate*.3),clock.display+velocity*wallDt);}
   let before=clock.frames[0],after=newest;for(let i=1;i<clock.frames.length;i++)if(clock.frames[i].time_s>=clock.display){before=clock.frames[i-1];after=clock.frames[i];break;}
   const hs={a:before,b:after},alpha=after.time_s>before.time_s?Math.min(1,Math.max(0,(clock.display-before.time_s)/(after.time_s-before.time_s))):1,simTime=clock.display;
   const history=epochRef.current==='live'?undefined:s.graph_history.find(g=>String(g.epoch)===epochRef.current);
   const sig=`${s.run_epoch}:${s.satellites.length}`;
   if(sig!==signature){signature=sig;for(const x of bodies.values()){dispose(x);formation.remove(x);}for(const x of dots.values()){dispose(x);scene.remove(x);}bodies.clear();dots.clear();
    for(const sat of s.satellites){const body=makeBody(sat.id,sat.swarm);formation.add(body);bodies.set(sat.id,body);const dot=new THREE.Mesh(new THREE.SphereGeometry(.006,8,6),new THREE.MeshBasicMaterial({color:sat.swarm==='SWARM-01'?0x73d8f7:0xc0a2f0}));scene.add(dot);dots.set(sat.id,dot);}linkSignature='';
   }
   const positions=new Map<string,THREE.Vector3>();const center=new THREE.Vector3();
   for(const sat of s.satellites){const a=hs.a.satellites.find(x=>x.id===sat.id)??sat,b=hs.b.satellites.find(x=>x.id===sat.id)??sat;
    const p=hs.b.time_s>hs.a.time_s?hermite(a.position,a.velocity,b.position,b.velocity,alpha,hs.b.time_s-hs.a.time_s):vector(sat.position);
    const extra=Math.max(0,simTime-b.time_s);if(extra>0){p.addScaledVector(vector(b.velocity),extra);const radius=vector(b.position).length();p.addScaledVector(vector(b.position),-.5*398600.4418*extra*extra/(radius*radius*radius));}positions.set(sat.id,p);center.add(p);dots.get(sat.id)!.position.copy(p.clone().divideScalar(R));
    const body=bodies.get(sat.id)!;body.quaternion.slerpQuaternions(attitude(a.body_axes_eci),attitude(b.body_axes_eci),alpha);
    (body.children[0] as THREE.Mesh).material instanceof THREE.MeshPhongMaterial&&((body.children[0] as THREE.Mesh).material as THREE.MeshPhongMaterial).color.set(sat.health==='isolated'?0xd87183:sat.health==='degraded'?0xdca65b:0xcbd4dd);
    body.getObjectByName('lock')!.visible=!history&&sat.owner_task_ids.length>0;body.getObjectByName('leader')!.visible=sat.id===(history?.coordinator?.node_id??s.coordinator?.node_id);
   }
   center.divideScalar(s.satellites.length);let displayCenter=center;
   if(history){displayCenter=new THREE.Vector3();history.nodes.forEach(n=>displayCenter.add(vector(n.position)));displayCenter.divideScalar(history.nodes.length);}
   for(const sat of s.satellites){const p=history?.nodes.find(n=>n.id===sat.id)?.position;const display=p?vector(p):positions.get(sat.id)!;bodies.get(sat.id)!.position.copy(display.clone().sub(displayCenter).divideScalar(50));}
   const span=Math.max(3,...[...bodies.values()].map(b=>b.position.length()));fc.position.copy(camera.position.clone().normalize().multiplyScalar(((span+1)/Math.sin(20*Math.PI/180*Math.min(1,fc.aspect))+2)*camera.position.length()/4.1));fc.lookAt(0,0,0);
   const stamp=`${s.run_epoch}:${s.time_s}:${s.version}:${selection.current}:${epochRef.current}`;
   if(linkSignature!==stamp){linkSignature=stamp;rebuild(s,history);}
   graph.children.forEach(o=>{if(o instanceof THREE.Line)updateLine(o);else if(o instanceof THREE.Sprite){const a=bodies.get(o.userData.source)?.position,b=bodies.get(o.userData.target)?.position;if(a&&b)o.position.copy(a.clone().lerp(b,.5).add(new THREE.Vector3(0,.16,0)));}});
   allocation.children.forEach(o=>updateLine(o as THREE.Line));
   // Only the selected spacecraft's cone geometry is shown; it matches backend half angle.
   const selectedBody=bodies.get(selection.current??''),sat=s.satellites.find(n=>n.id===selection.current);
   const coneStamp=`${selection.current}:${conesRef.current}:${sat?.antenna_error_deg}:${sat?.antenna_mount_deg}`;
   if(coneStamp!==coneSignature){coneSignature=coneStamp;dispose(antennaGroup);antennaGroup.clear();
    if(conesRef.current&&sat){for(const sign of [-1,1]){const length=1.1,radius=Math.tan(sat.antenna_beam_half_deg*Math.PI/180)*length;
     const cone=new THREE.Mesh(new THREE.ConeGeometry(radius,length,16,1,true),new THREE.MeshBasicMaterial({color:sat.antenna_error_deg?0xc46771:0x3d95bc,transparent:true,opacity:.06,side:THREE.DoubleSide,depthWrite:false}));
     const axis=new THREE.Vector3(sign*Math.cos((sat.antenna_mount_deg+sat.antenna_error_deg)*Math.PI/180),0,-sign*Math.sin((sat.antenna_mount_deg+sat.antenna_error_deg)*Math.PI/180));
     cone.quaternion.setFromUnitVectors(new THREE.Vector3(0,-1,0),axis);cone.position.copy(axis.clone().multiplyScalar(length/2).add(new THREE.Vector3(sign*.055,0,0)));antennaGroup.add(cone);
     antennaGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(sign*.055,0,0),axis.clone().multiplyScalar(length*1.3).add(new THREE.Vector3(sign*.055,0,0))]),new THREE.LineBasicMaterial({color:0x4c93ad,transparent:true,opacity:.5})));}}
   }
   if(selectedBody){antennaGroup.position.copy(selectedBody.position);antennaGroup.quaternion.copy(selectedBody.quaternion);}
   const angle=simTime*2*Math.PI/(365.256363004*86400),sunDirection=new THREE.Vector3(Math.cos(angle),Math.sin(angle)*Math.sin(.4090928),Math.sin(angle)*Math.cos(.4090928));sun.position.copy(sunDirection.multiplyScalar(5));earth.rotation.y=-simTime*2*Math.PI/86164.0905;
   const lat=s.ground.lat*Math.PI/180,lon=s.ground.lon*Math.PI/180+simTime*2*Math.PI/86164.0905;ground.position.set(Math.cos(lat)*Math.cos(lon),Math.sin(lat),Math.cos(lat)*Math.sin(lon)).multiplyScalar(1.004);groundTag.position.copy(ground.position.clone().multiplyScalar(1.055));
   trackMarker.position.copy(center.clone().divideScalar(R));clusterTag.position.copy(trackMarker.position.clone().multiplyScalar(1.11));
   if(frame%15===0){const p=positions.get(s.satellites[0].id)!.clone().normalize(),normal=vector(s.satellites[0].velocity).cross(positions.get(s.satellites[0].id)!).normalize(),q=normal.clone().cross(p).normalize(),ring=[];for(let i=0;i<=160;i++){const a=i/160*Math.PI*2;ring.push(p.clone().multiplyScalar(Math.cos(a)).addScaledVector(q,Math.sin(a)).multiplyScalar((R+550)/R));}orbitLine.geometry.dispose();orbitLine.geometry=new THREE.BufferGeometry().setFromPoints(ring);}
   const targetStamp=`${s.run_epoch}:${Math.floor(simTime/2)}:${s.tasks.length}`;if(targetStamp!==lastTargetStamp){lastTargetStamp=targetStamp;dispose(targetGroup);targetGroup.clear();const events=new Map(s.tasks.filter(t=>!['delivered','failed','expired'].includes(t.status)).map(t=>[t.event_id,t]));for(const [,t] of [...events].slice(0,10)){const a=t.target.lat*Math.PI/180,b=t.target.lon*Math.PI/180+simTime*2*Math.PI/86164.0905;const mark=new THREE.Mesh(new THREE.SphereGeometry(.007,8,6),new THREE.MeshBasicMaterial({color:0xff9c69}));mark.position.set(Math.cos(a)*Math.cos(b),Math.sin(a),Math.cos(a)*Math.sin(b)).multiplyScalar(1.007);targetGroup.add(mark);}}
   controls.update();renderer.setScissorTest(true);renderer.setViewport(0,0,w*split,h);renderer.setScissor(0,0,w*split,h);renderer.clear();renderer.render(scene,camera);
   renderer.setViewport(w*split,0,w*(1-split),h);renderer.setScissor(w*split,0,w*(1-split),h);renderer.clear();renderer.render(formation,fc);renderer.setScissorTest(false);
   renderer.domElement.dataset.graphEpoch=String(history?.epoch??s.graph_epoch);renderer.domElement.dataset.renderTime=simTime.toFixed(5);renderer.domElement.dataset.frame=String(frame++);requestId=requestAnimationFrame(animate);
  }
  let requestId=0;const resize=new ResizeObserver(()=>{w=el.clientWidth;h=el.clientHeight;split=w<600?.55:.6;renderer.setSize(w,h);camera.aspect=w*split/h;camera.updateProjectionMatrix();fc.aspect=w*(1-split)/h;fc.updateProjectionMatrix();});resize.observe(el);animate();
  const pointer=(e:PointerEvent|MouseEvent)=>{const rect=renderer.domElement.getBoundingClientRect(),x=e.clientX-rect.left;if(x<w*split)return false;mouse.set((x-w*split)/(w*(1-split))*2-1,-(e.clientY-rect.top)/h*2+1);ray.setFromCamera(mouse,fc);return true;};
  const down=(e:PointerEvent)=>{downX=e.clientX;downY=e.clientY;moved=false;};
  const move=(e:PointerEvent)=>{if(e.buttons&&Math.hypot(e.clientX-downX,e.clientY-downY)>4)moved=true;if(!pointer(e)){setHover('');return;}const hit=ray.intersectObjects([...bodies.values()],true)[0];if(hit){let o:THREE.Object3D|null=hit.object;while(o&&!o.userData.id)o=o.parent;setHover(o?.userData.id??'');}else{const line=ray.intersectObjects(graph.children.filter(x=>x instanceof THREE.Line))[0];const l=line?.object.userData.link;setHover(l?`${l.source} ↔ ${l.target} · w ${l.weight.toFixed(3)} · ${l.available?'beam clear':l.reason}`:'');}};
  const click=(e:MouseEvent)=>{if(moved||!pointer(e))return;const hit=ray.intersectObjects([...bodies.values()],true)[0];if(hit){let o:THREE.Object3D|null=hit.object;while(o&&!o.userData.id)o=o.parent;if(o)select.current(o.userData.id);}};
  renderer.domElement.addEventListener('pointerdown',down);renderer.domElement.addEventListener('pointermove',move);renderer.domElement.addEventListener('click',click);
  return ()=>{cancelAnimationFrame(requestId);resize.disconnect();controls.dispose();renderer.domElement.removeEventListener('pointerdown',down);renderer.domElement.removeEventListener('pointermove',move);renderer.domElement.removeEventListener('click',click);dispose(scene);dispose(formation);renderer.dispose();renderer.domElement.remove();};
 },[]);
 const historical=epoch==='live'?null:state.graph_history.find(g=>String(g.epoch)===epoch);
 const edgeReadout=(historical?.edges??state.links).filter(l=>l.target!=='GND'&&(l.source===selected||l.target===selected)).sort((a,b)=>a.weight-b.weight).slice(0,3);
 return <div className="globe-wrap"><div ref={host} className="globe" data-testid="globe"/>{error&&<div className="webgl-error">{error}</div>}<div className="globe-heading"><span className="live-tag">CONTINUOUS J2 ORBIT / ANNUAL SOLAR GEOMETRY</span><h2>One orbit. Two cooperating swarms.<br/><span>Earth spin + revolution · fixed 1361 W/m² sunlight</span></h2></div><div className="formation-heading"><b>3D FORMATION / 50 km spacing</b><small>Dark: weighted backbone · amber: ownership</small></div><div className="graph-epoch-control">Graph reconstruction history<select aria-label="Graph snapshot" value={epoch} onChange={e=>setEpoch(e.target.value)}><option value="live">Live · reconstruction {state.graph_epoch}</option>{state.graph_history.map(g=><option key={g.epoch} value={g.epoch}>{g.epoch===1?'Initial graph':`Reconstruction ${g.epoch}`} · T+{g.time_s.toFixed(0)}s</option>)}</select><div className="graph-tools"><label><input type="checkbox" checked={cones} onChange={e=>setCones(e.target.checked)}/>Antenna cones</label></div></div><button className="camera-reset secondary" onClick={()=>reset.current()}>Reset camera ↗</button>{hover&&<div className="graph-hover">{hover}</div>}<div className="weight-readout"><b>{selected} · edge weights</b>{edgeReadout.map(l=><span key={l.key}>{l.source===selected?l.target:l.source} ↔ <strong>{l.weight.toFixed(3)}</strong>{l.available?'':' · blocked'}</span>)}</div><div className="formation-note">{historical?`Archived graph: ${historical.reason}. Positions and weights frozen at T+${historical.time_s.toFixed(0)}s.`:'Live geometry. Dark solid edges form the valid minimum-cost spanning forest. Hover any edge for its weight and link gate.'}<br/>CubeSat icons are enlarged; positions use 50 km per formation unit.</div><div className="globe-tooltip">Drag to orbit both views · Scroll to zoom · Click a CubeSat in formation view</div><div className="globe-legend"><span><i className="cyan"/> Swarm 01</span>{state.config.swarm_count===2&&<span><i className="violet"/> Swarm 02</span>}<span><i className="green"/> Product delivery</span><span><i className="amber"/> Allocation / lease</span><span>◐ {state.metrics.eclipse_nodes} eclipsed</span></div></div>;
}
