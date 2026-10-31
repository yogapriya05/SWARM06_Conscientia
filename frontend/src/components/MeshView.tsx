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
export default function MeshView({state,selected,onSelect}:{state:SimulationState;selected:string|null;onSelect:(id:string)=>void;activeRoute?:string[]}){
 const host=useRef<HTMLDivElement>(null),stateRef=useRef(state),selectRef=useRef(onSelect),selectedRef=useRef(selected);stateRef.current=state;selectRef.current=onSelect;selectedRef.current=selected;
 const [error,setError]=useState(''),[hover,setHover]=useState('');const resetRef=useRef<()=>void>(()=>{});
 useEffect(()=>{
  const el=host.current!;let renderer:THREE.WebGLRenderer;
  try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});}catch{setError('WebGL is unavailable. Enable hardware acceleration in your browser to use the 3D globe.');return;}
  renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));renderer.outputColorSpace=THREE.SRGBColorSpace;el.appendChild(renderer.domElement);
  const scene=new THREE.Scene();scene.background=new THREE.Color('#050e18');const camera=new THREE.PerspectiveCamera(38,1,.01,100);camera.position.set(2.5,1.65,2.8);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.minDistance=1.55;controls.maxDistance=7;controls.enablePan=false;
  resetRef.current=()=>{camera.position.set(2.5,1.65,2.8);controls.target.set(0,0,0);};
  scene.add(new THREE.AmbientLight(0xaacbff,.5));const sun=new THREE.DirectionalLight(0xffffff,2.9);sun.position.set(5,.7,.4);scene.add(sun);
  const earth=new THREE.Mesh(new THREE.SphereGeometry(1,72,48),new THREE.MeshPhongMaterial({map:earthTexture(),shininess:10,specular:new THREE.Color('#174960')}));scene.add(earth);
  const atmosphere=new THREE.Mesh(new THREE.SphereGeometry(1.014,48,32),new THREE.MeshBasicMaterial({color:0x3ea3e8,transparent:true,opacity:.075,side:THREE.BackSide}));scene.add(atmosphere);
  const starGeom=new THREE.BufferGeometry(),starPos=[];let seed=7;for(let i=0;i<850;i++){seed=(seed*16807)%2147483647;const a=seed/2147483647*Math.PI*2;seed=(seed*16807)%2147483647;const z=seed/2147483647*2-1;const v=Math.sqrt(1-z*z);starPos.push(12*v*Math.cos(a),12*z,12*v*Math.sin(a));}starGeom.setAttribute('position',new THREE.Float32BufferAttribute(starPos,3));scene.add(new THREE.Points(starGeom,new THREE.PointsMaterial({color:0x80a6bf,size:.009,transparent:true,opacity:.6})));
  const satellites=new Map<string,THREE.Group>();const linkGroup=new THREE.Group(),orbitGroup=new THREE.Group(),targetGroup=new THREE.Group();scene.add(linkGroup,orbitGroup,targetGroup);
  const ground=new THREE.Mesh(new THREE.OctahedronGeometry(.022),new THREE.MeshBasicMaterial({color:0x59e8ae}));ground.add(label('PUNE · GND','#6ff0c6'));ground.children[0].position.y=.055;scene.add(ground);
  let signature='',lastVersion='',frame=0;const raycaster=new THREE.Raycaster(),mouse=new THREE.Vector2();raycaster.params.Line={threshold:.008};let moved=false;let downX=0,downY=0;
  const disposeGroup=(group:THREE.Group)=>{group.children.forEach(o=>{const a=o as THREE.Line;a.geometry?.dispose();const m=a.material;if(Array.isArray(m))m.forEach(q=>q.dispose());else m?.dispose();});group.clear();};
  function sync(){const s=stateRef.current;const sig=`${s.run_epoch}:${s.satellites.length}`;
   if(sig!==signature){signature=sig;for(const sat of satellites.values()){scene.remove(sat);sat.traverse(o=>{const m=o as THREE.Mesh;m.geometry?.dispose();if(m.material){const a=Array.isArray(m.material)?m.material:[m.material];a.forEach(q=>{if(q instanceof THREE.SpriteMaterial)q.map?.dispose();q.dispose();});}});}satellites.clear();disposeGroup(orbitGroup);
    for(const sat of s.satellites){const g=new THREE.Group();g.userData.id=sat.id;
     const body=new THREE.Mesh(new THREE.BoxGeometry(.021,.034,.022),new THREE.MeshPhongMaterial({color:sat.swarm==='SWARM-01'?0x44c9f5:0xb68cff,emissive:0x13374b}));g.add(body);
     for(const sign of [-1,1]){const panel=new THREE.Mesh(new THREE.BoxGeometry(.045,.002,.025),new THREE.MeshPhongMaterial({color:0x244992,emissive:0x11234a}));panel.position.x=sign*.034;g.add(panel);}
     const halo=new THREE.Mesh(new THREE.SphereGeometry(.027,12,8),new THREE.MeshBasicMaterial({color:0x56d4ff,wireframe:true,transparent:true,opacity:.4}));halo.name='halo';g.add(halo);
     const tag=label(sat.id,sat.swarm==='SWARM-01'?'#88d8f8':'#c7acff');tag.position.y=.055;g.add(tag);satellites.set(sat.id,g);scene.add(g);}
    for(let swarm=0;swarm<s.config.swarm_count;swarm++){const p=[];const inc=THREE.MathUtils.degToRad(swarm===0?51.6:74),raan=swarm===0?0:THREE.MathUtils.degToRad(80),r=(R+550+swarm*100)/R;
     for(let i=0;i<=240;i++){const u=i/240*Math.PI*2,x=Math.cos(u)*r,y=Math.sin(u)*Math.sin(inc)*r,z=Math.sin(u)*Math.cos(inc)*r;p.push(new THREE.Vector3(Math.cos(raan)*x-Math.sin(raan)*z,y,Math.sin(raan)*x+Math.cos(raan)*z));}
     orbitGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(p),new THREE.LineBasicMaterial({color:swarm===0?0x3ab7e0:0xa17fe3,transparent:true,opacity:.24})));}
   }
   const gp=new THREE.Vector3(...s.ground.position.map(x=>x/R) as [number,number,number]);ground.position.copy(gp.multiplyScalar(1.004));
   earth.rotation.y=-s.time_s*2*Math.PI/86164;
   for(const sat of s.satellites){const g=satellites.get(sat.id)!;g.position.set(sat.position[0]/R,sat.position[1]/R,sat.position[2]/R);g.lookAt(0,0,0);if(sat.attitude_error_deg)g.rotateZ(.7);
    const halo=g.getObjectByName('halo') as THREE.Mesh;const m=halo.material as THREE.MeshBasicMaterial;m.color.set(sat.health==='isolated'?0xff5c78:sat.health==='degraded'?0xffbd65:sat.eclipse?0x627ea0:sat.swarm==='SWARM-01'?0x48caff:0xb493ff);m.opacity=sat.id===selectedRef.current?1:.35;halo.scale.setScalar(sat.id===selectedRef.current?1.6:1);}
   const stamp=`${s.run_epoch}:${s.version}:${s.time_s}:${selectedRef.current}`;if(lastVersion===stamp)return;lastVersion=stamp;disposeGroup(linkGroup);
   targetGroup.children.forEach(o=>o.traverse(n=>{const m=n as THREE.Mesh;m.geometry?.dispose();if(m.material){const materials=Array.isArray(m.material)?m.material:[m.material];materials.forEach(q=>{if(q instanceof THREE.SpriteMaterial)q.map?.dispose();q.dispose();});}}));targetGroup.clear();
   const targets=new Map<string,typeof s.tasks[number]>();for(const t of s.tasks)if(!['delivered','expired','failed'].includes(t.status))targets.set(t.event_id,t);
   for(const [event,t] of [...targets].slice(0,16)){
    const lat=t.target.lat*Math.PI/180,lon=t.target.lon*Math.PI/180+s.time_s*2*Math.PI/86164;
    const pos=new THREE.Vector3(Math.cos(lat)*Math.cos(lon),Math.sin(lat),Math.cos(lat)*Math.sin(lon)).multiplyScalar(1.012);
    const marker=new THREE.Mesh(new THREE.ConeGeometry(.012,.035,8),new THREE.MeshBasicMaterial({color:t.priority>=5?0xff9470:0xffcf84}));marker.position.copy(pos);marker.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),pos.clone().normalize());targetGroup.add(marker);
    const tag=label(event.slice(0,18),'#edba89');tag.position.copy(pos.clone().multiplyScalar(1.055));tag.scale.multiplyScalar(.7);targetGroup.add(tag);
    if(t.status==='assigned'&&t.owner){const observer=satellites.get(t.owner);if(observer){const beam=new THREE.Line(new THREE.BufferGeometry().setFromPoints([observer.position,pos]),new THREE.LineDashedMaterial({color:0xf1ba73,dashSize:.02,gapSize:.02,transparent:true,opacity:.3}));beam.computeLineDistances();targetGroup.add(beam);}}
   }
   const active=new Set<string>();for(const task of s.tasks.filter(t=>t.status==='processed'))for(let i=0;i<task.route.length-1;i++)active.add([task.route[i],task.route[i+1]].sort().join('|'));
   for(const l of s.links){const a=satellites.get(l.source)?.position,b=l.target==='GND'?ground.position:satellites.get(l.target)?.position;if(!a||!b)continue;
    const arc:THREE.Vector3[]=[];const na=a.clone().normalize(),nb=b.clone().normalize();const dot=THREE.MathUtils.clamp(na.dot(nb),-.9999,.9999);const angle=Math.acos(dot);
    for(let i=0;i<=16;i++){const t=i/16;const v=angle<.001?na.clone().lerp(nb,t):na.clone().multiplyScalar(Math.sin((1-t)*angle)/Math.sin(angle)).add(nb.clone().multiplyScalar(Math.sin(t*angle)/Math.sin(angle)));
     v.normalize().multiplyScalar(a.length()*(1-t)+b.length()*t+.06*Math.sin(Math.PI*t));arc.push(v);}
    const inRoute=active.has(l.key),isSelected=l.source===selectedRef.current||l.target===selectedRef.current;
    const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(arc),new THREE.LineDashedMaterial({color:!l.available?0xff5979:inRoute?0x6cf0b1:isSelected?0x80c8e8:0x456a85,dashSize:inRoute?.025:.012,gapSize:.013,transparent:true,opacity:!l.available?.28:inRoute?.9:isSelected?.45:.15}));line.computeLineDistances();line.userData.link=l;linkGroup.add(line);}
  }
  const observer=new ResizeObserver(()=>{const w=el.clientWidth,h=el.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();});observer.observe(el);
  function animate(){sync();controls.update();renderer.render(scene,camera);frame=requestAnimationFrame(animate);}animate();
  const pointer=(event:PointerEvent)=>{const rect=renderer.domElement.getBoundingClientRect();mouse.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);raycaster.setFromCamera(mouse,camera);};
  const down=(e:PointerEvent)=>{moved=false;downX=e.clientX;downY=e.clientY;};const move=(e:PointerEvent)=>{if(e.buttons&&Math.hypot(e.clientX-downX,e.clientY-downY)>4)moved=true;pointer(e);const hit=raycaster.intersectObjects([...satellites.values()],true)[0];if(hit){let o:THREE.Object3D|null=hit.object;while(o&&!o.userData.id)o=o.parent;setHover(o?.userData.id??'');renderer.domElement.style.cursor='pointer';}else{renderer.domElement.style.cursor='grab';const h=raycaster.intersectObjects(linkGroup.children)[0];const l=h?.object.userData.link;setHover(l?`${l.source} ↔ ${l.target} · w ${l.weight.toFixed(2)} · ${l.rate_mbps.toFixed(1)} Mbps · ${(l.latency_s*1000).toFixed(0)} ms`:'');}};
  const click=(e:MouseEvent)=>{if(moved)return;pointer(e as unknown as PointerEvent);const hit=raycaster.intersectObjects([...satellites.values()],true)[0];if(hit){let o:THREE.Object3D|null=hit.object;while(o&&!o.userData.id)o=o.parent;if(o)selectRef.current(o.userData.id);}};
  renderer.domElement.addEventListener('pointerdown',down);renderer.domElement.addEventListener('pointermove',move);renderer.domElement.addEventListener('click',click);
  return ()=>{cancelAnimationFrame(frame);observer.disconnect();controls.dispose();renderer.domElement.removeEventListener('pointerdown',down);renderer.domElement.removeEventListener('pointermove',move);renderer.domElement.removeEventListener('click',click);scene.traverse(o=>{const m=o as THREE.Mesh;m.geometry?.dispose();if(m.material){const a=Array.isArray(m.material)?m.material:[m.material];a.forEach(q=>{if(q instanceof THREE.MeshPhongMaterial)q.map?.dispose();if(q instanceof THREE.SpriteMaterial)q.map?.dispose();q.dispose();});}});renderer.dispose();renderer.domElement.remove();};
 },[]);
 return <div className="globe-wrap"><div className="globe" ref={host} data-testid="globe" />{error&&<div className="webgl-error">{error}</div>}<div className="globe-heading"><span className="live-tag">3D ORBITAL THEATRE</span><h2>Earth observation<br/><span>without a single point of failure.</span></h2></div><button className="camera-reset secondary" onClick={()=>resetRef.current()}>Reset camera ↗</button><div className="globe-tooltip">{hover||'Drag to orbit · Scroll to zoom · Click a CubeSat to inspect'}</div><div className="globe-legend"><span><i className="cyan"/> Swarm 01</span>{state.config.swarm_count===2&&<span><i className="violet"/> Swarm 02</span>}<span><i className="green"/> Product route</span><span><i className="red"/> Fault / unavailable</span><span>◐ {state.metrics.eclipse_nodes} in eclipse</span></div></div>;
}
