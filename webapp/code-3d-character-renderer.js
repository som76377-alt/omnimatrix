/* Procedural, code-authored 3D character renderer. No image/asset inputs. */
(function(root){"use strict";
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
async function renderVideo(o){
 const T=await import("https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js");
 const w=clamp(Number(o.width)||960,540,1280),h=clamp(Number(o.height)||540,540,1280),duration=clamp(Number(o.duration)||6,4,12),brief=String(o.brief||"").toLowerCase();
 const wave=/\b(wav(?:e|es|ing)|greet|hello|hi)\b/.test(brief),walk=/\b(walk|run|jog|march)/.test(brief),portrait=h>w;
 const canvas=document.createElement("canvas");canvas.width=w;canvas.height=h;
 const renderer=new T.WebGLRenderer({canvas,antialias:true,alpha:false,powerPreference:"high-performance"});
 renderer.setSize(w,h,false);renderer.setPixelRatio(1);renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;
 const scene=new T.Scene();scene.background=new T.Color("#b8bbb8");scene.fog=new T.Fog("#b8bbb8",9,24);
 const camera=new T.PerspectiveCamera(32,w/h,.1,50);camera.position.set(portrait?4.7:4.2,3.1,portrait?9.4:8);camera.lookAt(0,2.05,0);
 scene.add(new T.HemisphereLight(0xf0f2ff,0x55483d,2));
 const light=(color,intensity,pos,shadow=false)=>{const l=new T.DirectionalLight(color,intensity);l.position.set(...pos);l.castShadow=shadow;if(shadow){l.shadow.mapSize.set(1024,1024);l.shadow.bias=-.0003;}scene.add(l);};
 light(0xffdfc3,3.2,[-4,8,6],true);light(0xcbdcff,1.6,[5,4,2]);light(0xffc58c,1.8,[1,5,-5]);
 const material=(c,r=.8,m=0)=>new T.MeshStandardMaterial({color:c,roughness:r,metalness:m});
 const skin=material("#bd8667"),skinHi=material("#d09a79"),skinShade=material("#895b49"),shirt=material("#344b55"),trim=material("#526b73"),pants=material("#292e35"),shoe=material("#292521"),hair=material("#33251f"),white=material("#e7e1d5",.45),iris=material("#4a665e",.4),pupil=material("#171614",.3),mouth=material("#684139"),groundMat=material("#969b97");
 const ground=new T.Mesh(new T.PlaneGeometry(100,100),groundMat);ground.rotation.x=-Math.PI/2;ground.position.y=-.04;ground.receiveShadow=true;scene.add(ground);
 const platform=new T.Mesh(new T.CylinderGeometry(1.35,1.45,.06,48),material("#818681"));platform.position.y=0;platform.receiveShadow=true;scene.add(platform);
 const rootG=new T.Group();scene.add(rootG);
 function mesh(g,m,p,pos=[0,0,0]){const x=new T.Mesh(g,m);x.position.set(...pos);x.castShadow=true;x.receiveShadow=true;p.add(x);return x;}
 function ball(p,m,pos,sc,seg=24){const x=mesh(new T.SphereGeometry(1,seg,Math.max(12,seg>>1)),m,p,pos);x.scale.set(...sc);return x;}
 function rod(p,m,a,b,r1,r2){const A=new T.Vector3(...a),B=new T.Vector3(...b),d=B.clone().sub(A);const x=mesh(new T.CylinderGeometry(r1,r2,d.length(),18),m,p,A.clone().add(B).multiplyScalar(.5).toArray());x.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),d.normalize());return x;}
 function lathe(p,m,profile,pos){return mesh(new T.LatheGeometry(profile.map(v=>new T.Vector2(...v)),32),m,p,pos);}
 const torso=new T.Group();torso.position.y=2.8;rootG.add(torso);
 lathe(torso,shirt,[[0,-.68],[.23,-.68],[.33,-.56],[.37,-.32],[.43,-.04],[.49,.22],[.47,.42],[.34,.58],[.22,.64],[0,.64]],[0,0,0]);
 for(const s of [-1,1])ball(torso,shirt,[s*.39,.36,0],[.25,.23,.28]);
 ball(torso,trim,[0,.15,.304],[.18,.37,.045]);mesh(new T.TorusGeometry(.16,.032,10,28),trim,torso,[0,.59,0]).rotation.x=Math.PI/2;
 const legs=[],arms=[];
 for(const s of [-1,1]){const leg=new T.Group();leg.position.set(s*.19,2.0,0);rootG.add(leg);legs.push({s,g:leg});ball(leg,pants,[0,-.32,0],[.18,.43,.19]);rod(leg,pants,[0,-.45,0],[s*.02,-.92,.015],.13,.1);ball(leg,shoe,[.035,-.98,.1],[.14,.1,.24]);ball(leg,shoe,[.035,-1.02,.17],[.14,.06,.18]);
 const sh=new T.Group();sh.position.set(s*.48,3.15,0);rootG.add(sh);ball(sh,shirt,[0,-.1,0],[.19,.23,.2]);rod(sh,shirt,[0,-.12,0],[s*.1,-.5,.015],.16,.12);
 const el=new T.Group();el.position.set(s*.1,-.5,.015);sh.add(el);ball(el,shirt,[0,0,0],[.13,.14,.13]);rod(el,skinHi,[0,0,0],[s*.05,-.4,.04],.105,.077);
 const wr=new T.Group();wr.position.set(s*.05,-.4,.04);el.add(wr);ball(wr,skinHi,[0,-.06,.01],[.08,.11,.08]);ball(wr,skinHi,[0,-.15,.025],[.1,.12,.055]);
 for(let f=0;f<4;f++){const x=(f-1.5)*.043,len=[.105,.13,.12,.095][f];rod(wr,skinHi,[x,-.21,.03],[x*1.12,-.21-len,.04],.021,.014);ball(wr,skinHi,[x*1.12,-.21-len,.04],[.016,.022,.016],12);}rod(wr,skinHi,[s*-.07,-.14,.025],[s*-.13,-.23,.05],.027,.019);
 arms.push({s,sh,el,wr});}
 mesh(new T.CylinderGeometry(.12,.16,.25,24),skin,rootG,[0,3.52,0]);
 const head=new T.Group();head.position.set(0,3.9,.01);rootG.add(head);ball(head,skin,[0,0,0],[.265,.345,.235],32);ball(head,skinHi,[0,-.13,.09],[.19,.18,.16]);
 for(const s of [-1,1]){ball(head,skin,[s*.26,.005,0],[.06,.09,.055],16);ball(head,skinShade,[s*.265,.005,.04],[.025,.045,.018],12);ball(head,white,[s*.105,.035,.204],[.057,.037,.022],20);ball(head,iris,[s*.105,.034,.224],[.023,.026,.012],16);ball(head,pupil,[s*.105,.034,.234],[.012,.018,.008],12);rod(head,hair,[s*.16,.09,.205],[s*.05,.10,.22],.016,.012);ball(head,hair,[s*.105,.095,.207],[.074,.022,.025],16);}
 rod(head,skinHi,[0,.025,.225],[0,-.055,.255],.032,.021);ball(head,skinHi,[0,-.06,.25],[.045,.027,.035],16);ball(head,mouth,[0,-.17,.231],[.072,.012,.014],16);
 ball(head,hair,[0,.245,-.005],[.267,.17,.235],24);ball(head,hair,[-.11,.285,.09],[.14,.09,.16]);ball(head,hair,[.08,.31,.035],[.13,.075,.15]);
 for(const s of [-1,1])ball(head,hair,[s*.235,.055,.005],[.035,.13,.045],14);
 const stream=canvas.captureStream(24),mime=["video/webm;codecs=vp9","video/webm;codecs=vp8","video/webm"].find(x=>MediaRecorder.isTypeSupported(x));if(!mime)throw Error("This browser cannot encode WebM.");
 const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:Math.min(3200000,Math.max(1500000,w*h*4))}),chunks=[];
 const blob=await new Promise((resolve,reject)=>{let raf=0,stopped=false;const start=performance.now();const cleanup=()=>{if(raf)cancelAnimationFrame(raf);stream.getTracks().forEach(t=>t.stop());renderer.dispose();};recorder.ondataavailable=e=>{if(e.data?.size)chunks.push(e.data);};recorder.onerror=e=>{cleanup();reject(e.error||Error("3D recording failed"));};recorder.onstop=()=>{cleanup();const b=new Blob(chunks,{type:mime});b.size?resolve(b):reject(Error("3D renderer produced an empty video"));};
 const frame=now=>{if(stopped)return;const t=Math.min(duration,(now-start)/1000),phase=t*Math.PI*1.45;rootG.position.y=.018*Math.sin(phase*.5);rootG.rotation.y=.06*Math.sin(phase*.25);torso.rotation.z=.025*Math.sin(phase*.5);head.rotation.y=.025*Math.sin(phase*.33);
 arms.forEach(({s,sh,el,wr})=>{if(wave&&s===1){const k=(.15<t/duration&&t/duration<.98)?1:0;sh.rotation.z=-k*2.05+.035*Math.sin(phase);el.rotation.z=k*.78+.08*Math.sin(phase*2);wr.rotation.z=k*.38*Math.sin(phase*2.4);}else{sh.rotation.z=s*(.04+.035*Math.sin(phase));el.rotation.z=s*.08;}});
 legs.forEach(({s,g})=>g.rotation.x=walk?Math.sin(phase*1.2+(s>0?0:Math.PI))*.24:0);
 renderer.render(scene,camera);if(t>=duration){stopped=true;recorder.stop();return;}raf=requestAnimationFrame(frame);};
 recorder.start();raf=requestAnimationFrame(frame);setTimeout(()=>{if(!stopped&&recorder.state!=="inactive"){stopped=true;recorder.stop();}},duration*1000+8000);});
 return {file:new File([blob],"omnitrix-code-3d-character.webm",{type:blob.type,lastModified:Date.now()}),duration,width:w,height:h,renderer:"procedural-threejs-3d",visualStatus:"requires-frame-review"};
}
root.OmnitrixCode3D=Object.freeze({renderVideo});
})(window);
