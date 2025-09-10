import * as THREE from "https://esm.sh/three@0.175.0";
import { OrbitControls } from "https://esm.sh/three@0.175.0/examples/jsm/controls/OrbitControls.js";

document.addEventListener("DOMContentLoaded", () => {
/* ========================= PRELOADER ========================= */
const loadingOverlay = document.getElementById("loading-overlay");
const preCanvas = document.getElementById("preloader-canvas");
if (preCanvas) {
  const ctx = preCanvas.getContext("2d");
  const cx = preCanvas.width / 2, cy = preCanvas.height / 2;
  const maxR = 80, circleCount = 5, dotCount = 24;
  let t = 0, lt = 0;
  const loop = (ts) => {
    if (!lt) lt = ts; const dt = ts - lt; lt = ts; t += dt * 0.001;
    ctx.clearRect(0,0,preCanvas.width,preCanvas.height);
    ctx.beginPath(); ctx.arc(cx,cy,3,0,Math.PI*2); ctx.fillStyle="rgba(102,230,255,.9)"; ctx.fill();
    for (let c=0;c<circleCount;c++){
      const phase = (t*0.35 + c/circleCount) % 1;
      const r = phase*maxR; const o = 1 - phase;
      ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2);
      ctx.strokeStyle = `rgba(102,230,255,${o*0.18})`; ctx.lineWidth = 1; ctx.stroke();
      for (let i=0;i<dotCount;i++){
        const a = (i/dotCount)*Math.PI*2;
        const x = cx + Math.cos(a)*r; const y = cy + Math.sin(a)*r;
        const size = 2 * (1 - phase*0.5);
        ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(x,y);
        ctx.strokeStyle = `rgba(102,230,255,${o*0.08})`; ctx.stroke();
        ctx.beginPath(); ctx.arc(x,y,size,0,Math.PI*2);
        ctx.fillStyle = `rgba(102,230,255,${o*.9})`; ctx.fill();
      }
    }
    if (loadingOverlay.style.display !== "none") requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}
const hidePreloader = () => {
  if (!loadingOverlay || loadingOverlay.style.display === "none") return;
  loadingOverlay.style.opacity = 0;
  setTimeout(() => (loadingOverlay.style.display = "none"), 500);
};
window.addEventListener("load", () => setTimeout(hidePreloader, 300));
setTimeout(hidePreloader, 4000);

/* ========================= HUD CLOCK ========================= */
const timestamp = document.getElementById("timestamp");
const updateClock = () => {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2,"0");
  const mm = String(now.getMinutes()).padStart(2,"0");
  const ss = String(now.getSeconds()).padStart(2,"0");
  if (timestamp) timestamp.textContent = `TIME: ${hh}:${mm}:${ss}`;
};
updateClock(); setInterval(updateClock, 1000);

/* ========================= NOTIFY ========================= */
const note = document.getElementById("notification");
function notify(msg, {type, timeout}={}) {
  if (!note) return;
  note.dataset.type = type || "";
  note.textContent = msg;
  note.classList.add("show");
  if (timeout === 0) return;
  setTimeout(() => note.classList.remove("show"), timeout ?? 3200);
}

/* ========================= AUDIO + LOCAL VAD ========================= */
let audioContext=null, analyser=null;
let audioData=null, freqData=null;
let micSource=null, micActive=false;

let audioSensitivity=5.0, audioReactivity=1.0;

const vadState = {
  speaking:false, noiseFloor:0.015, speakHold:0, silenceHold:0,
  attackFrames:3, releaseFrames:12, thresholdRatio:3.0, zcrWeight:0.6
};

function initAudio(){
  if (audioContext) return;
  try{
    audioContext = new (window.AudioContext||window.webkitAudioContext)();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.85;
    audioData = new Float32Array(analyser.fftSize);
    freqData = new Uint8Array(analyser.frequencyBinCount);
    notify("AUDIO ANALYZER READY • TAP ORB TO ENABLE MIC",{type:"ok"});
  }catch(e){ console.error(e); notify("AUDIO INIT ERROR",{type:"error"}); }
}

async function attachMic(){
  const stream = await navigator.mediaDevices.getUserMedia({
    audio:{ echoCancellation:true, noiseSuppression:true, autoGainControl:true }
  });
  if (!audioContext) initAudio();
  if (audioContext.state === "suspended") await audioContext.resume();
  micSource = audioContext.createMediaStreamSource(stream);
  micSource.connect(analyser);
  micActive = true;
  notify("MIC CONNECTED • VAD ACTIVE",{type:"ok"});
  // Start realtime transcription after mic is live
  startRealtimeTranscription();
}

function vadTick(){
  if (!analyser||!audioData) return false;
  analyser.getFloatTimeDomainData(audioData);
  // RMS
  let sum=0; for (let i=0;i<audioData.length;i++){ const s=audioData[i]; sum += s*s; }
  const rms = Math.sqrt(sum / audioData.length);
  // ZCR
  let zc=0, prev=audioData[0]; for (let i=1;i<audioData.length;i++){ const cur=audioData[i];
    if ((prev>=0 && cur<0) || (prev<0 && cur>=0)) zc++; prev=cur; }
  const zcr = zc / audioData.length;
  if (!vadState.speaking){
    vadState.noiseFloor = 0.97*vadState.noiseFloor + 0.03*Math.min(rms,0.05);
  }
  const ratio = rms / Math.max(1e-6, vadState.noiseFloor);
  const score = ratio + vadState.zcrWeight*zcr;
  let speaking = vadState.speaking;
  if (!speaking){
    if (score > vadState.thresholdRatio){
      vadState.speakHold++;
      if (vadState.speakHold >= vadState.attackFrames){ speaking=true; vadState.speakHold=0; }
    } else vadState.speakHold=0;
    vadState.silenceHold=0;
  } else {
    if (score < vadState.thresholdRatio*0.6){
      vadState.silenceHold++;
      if (vadState.silenceHold >= vadState.releaseFrames){ speaking=false; vadState.silenceHold=0; }
    } else vadState.silenceHold=0;
    vadState.speakHold=0;
  }
  const changed = speaking !== vadState.speaking;
  vadState.speaking = speaking;
  return changed ? (speaking?"start":"end") : false;
}

/* ========================= MINI WAVEFORM ========================= */
const wfCanvas = document.getElementById("waveform-canvas");
const wfCtx = wfCanvas ? wfCanvas.getContext("2d") : null;
function resizeWF(){
  if (!wfCanvas||!wfCtx) return;
  wfCanvas.width = wfCanvas.offsetWidth*devicePixelRatio;
  wfCanvas.height= wfCanvas.offsetHeight*devicePixelRatio;
  wfCtx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
}
resizeWF(); window.addEventListener("resize", resizeWF);
(function drawWF(){
  if (wfCanvas&&wfCtx){
    const w = wfCanvas.width/devicePixelRatio;
    const h = wfCanvas.height/devicePixelRatio;
    wfCtx.clearRect(0,0,w,h);
    wfCtx.fillStyle="rgba(0,0,0,.22)"; wfCtx.fillRect(0,0,w,h);
    wfCtx.beginPath(); wfCtx.strokeStyle="rgba(102,230,255,.9)"; wfCtx.lineWidth=2;
    const slice = w / (audioData?audioData.length:120);
    let x=0;
    if (audioData && analyser){
      analyser.getFloatTimeDomainData(audioData);
      for (let i=0;i<audioData.length;i++){
        const v = audioData[i]*0.5+0.5; const y = v*h;
        i===0? wfCtx.moveTo(x,y) : wfCtx.lineTo(x,y);
        x += slice;
      }
    } else {
      const t = performance.now()*0.001;
      for (let i=0;i<120;i++){
        const v = Math.sin(i*0.25+t)*.2 + Math.sin(i*.05+t*1.7)*.1;
        const y = h*.5 + v*h*.4;
        i===0? wfCtx.moveTo(x,y) : wfCtx.lineTo(x,y);
        x += slice;
      }
    }
    wfCtx.stroke();
  }
  requestAnimationFrame(drawWF);
})();

/* ========================= CIRCULAR VISUALIZER ========================= */
const circCanvas = document.getElementById("circular-canvas");
const circCtx = circCanvas.getContext("2d");
function resizeCirc(){ circCanvas.width = circCanvas.offsetWidth; circCanvas.height = circCanvas.offsetHeight; }
resizeCirc(); window.addEventListener("resize", resizeCirc);

function drawCircular(){
  if (!analyser) return;
  const w=circCanvas.width, h=circCanvas.height, cx=w/2, cy=h/2;
  analyser.getByteFrequencyData(freqData);
  circCtx.clearRect(0,0,w,h);
  const baseR = Math.min(w,h)*0.38, rings=3, points=180;
  for (let r=0;r<rings;r++){
    const ringR = baseR*(0.72+r*0.16), op=0.85-r*0.23; circCtx.beginPath();
    for (let i=0;i<points;i++){
      const s0 = Math.floor((r*analyser.frequencyBinCount)/(rings*1.5));
      const s1 = Math.floor(((r+1)*analyser.frequencyBinCount)/(rings*1.5));
      const seg = Math.max(1, Math.floor((s1-s0)/points));
      let sum=0, span=Math.max(1, s1-s0);
      for (let j=0;j<seg;j++){ const idx = s0 + ((i*seg+j)%span); sum += freqData[idx]||0; }
      const v = (sum/(seg*255))*(audioSensitivity/5)*audioReactivity;
      const dynR = ringR*(1+v*.5);
      const a = (i/points)*Math.PI*2;
      const x = cx + Math.cos(a)*dynR, y = cy + Math.sin(a)*dynR;
      i===0? circCtx.moveTo(x,y) : circCtx.lineTo(x,y);
    }
    circCtx.closePath();
    const g = circCtx.createRadialGradient(cx,cy, ringR*.75, cx,cy, ringR*1.25);
    g.addColorStop(0, `rgba(102,230,255,${op})`);
    g.addColorStop(1, `rgba(47,179,255,${op*.7})`);
    circCtx.strokeStyle=g; circCtx.lineWidth=2+(rings-r); circCtx.shadowBlur=14; circCtx.shadowColor="rgba(102,230,255,.7)";
    circCtx.stroke();
  }
  circCtx.shadowBlur=0;
}

const audioWave = document.getElementById("audio-wave");
function updateRing(){
  if (!analyser||!audioData) return;
  analyser.getFloatTimeDomainData(audioData);
  let sum=0; for (let i=0;i<audioData.length;i++) sum += Math.abs(audioData[i]);
  const avg = sum / audioData.length;
  const f = 1 + avg * audioReactivity * (audioSensitivity/5) * 1.4;
  audioWave.style.transform = `translate(-50%,-50%) scale(${f.toFixed(3)})`;
  audioWave.style.borderColor = `rgba(102,230,255,${0.10 + avg*0.35})`;
}

/* ========================= THREE.JS ORB ========================= */
let scene,camera,renderer,controls;
let orbGroup, updateOrbUniforms, updateBackground;
let clock = new THREE.Clock();
let rotationSpeed=1.0, distortionAmount=1.0, resolution=32;

function initThree(){
  scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x031018, 0.045);
  camera = new THREE.PerspectiveCamera(60, innerWidth/innerHeight, 0.1, 1000);
  camera.position.set(0,0,10);
  renderer = new THREE.WebGLRenderer({ antialias:true, alpha:true, powerPreference:"high-performance" });
  renderer.setSize(innerWidth, innerHeight);
  renderer.setPixelRatio(devicePixelRatio);
  renderer.setClearColor(0x000000, 0);
  document.getElementById("three-container").appendChild(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = 0.08; controls.enableZoom = false;
  scene.add(new THREE.AmbientLight(0x88aabb, 1.2));
  const dl = new THREE.DirectionalLight(0xffffff, 1.2); dl.position.set(3,2,2); scene.add(dl);
  const p1 = new THREE.PointLight(0x66e6ff, 1.1, 10); p1.position.set(2,2,2); scene.add(p1);
  const p2 = new THREE.PointLight(0x2fb3ff, 1.0, 10); p2.position.set(-2,-2,-2); scene.add(p2);
  updateOrbUniforms = createOrb();
  updateBackground = createStars();
  window.addEventListener("resize", onResize);
  animate();
}
function onResize(){ camera.aspect=innerWidth/innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth,innerHeight); resizeWF(); resizeCirc(); }

function createStars(){
  const g = new THREE.BufferGeometry(), count=2800;
  const pos = new Float32Array(count*3), col = new Float32Array(count*3);
  const c1=new THREE.Color(0x66e6ff), c2=new THREE.Color(0x2fb3ff), c3=new THREE.Color(0x8de6ff);
  for (let i=0;i<count;i++){
    pos[i*3]=(Math.random()-0.5)*110; pos[i*3+1]=(Math.random()-0.5)*110; pos[i*3+2]=(Math.random()-0.5)*110;
    const pick=Math.random(); const c=pick<.34?c1:pick<.67?c2:c3;
    col[i*3]=c.r; col[i*3+1]=c.g; col[i*3+2]=c.b;
  }
  g.setAttribute("position", new THREE.BufferAttribute(pos,3));
  g.setAttribute("color", new THREE.BufferAttribute(col,3));
  const m = new THREE.ShaderMaterial({
    uniforms:{ time:{value:0} },
    vertexShader:`varying vec3 vColor; uniform float time;
      void main(){ vColor=color; vec3 p=position;
        p.x+=sin(time*.1+position.z*.2)*.06; p.y+=cos(time*.1+position.x*.2)*.06;
        vec4 mv=modelViewMatrix*vec4(p,1.0); gl_PointSize=.9*(300.0 / -mv.z); gl_Position=projectionMatrix*mv; }`,
    fragmentShader:`varying vec3 vColor; void main(){
      float r=distance(gl_PointCoord, vec2(.5)); if(r>.5) discard;
      float glow=pow(1.0 - r*2.0, 2.0); gl_FragColor=vec4(vColor, glow); }`,
    transparent:true, depthWrite:false, blending:THREE.AdditiveBlending, vertexColors:true
  });
  const pts = new THREE.Points(g,m); scene.add(pts);
  return (time)=>{ m.uniforms.time.value=time; };
}

function createOrb(){
  if (orbGroup) scene.remove(orbGroup);
  orbGroup = new THREE.Group();
  const radius=2;
  const geo = new THREE.IcosahedronGeometry(radius, Math.max(1, Math.floor(resolution/8)));
  const mat = new THREE.ShaderMaterial({
    uniforms:{ time:{value:0}, color:{value:new THREE.Color(0x66e6ff)}, audioLevel:{value:0}, distortion:{value:distortionAmount} },
    vertexShader:`uniform float time,audioLevel,distortion; varying vec3 vN; varying vec3 vP;
      vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
      vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
      vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
      vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
      float snoise(vec3 v){const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
        vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
        vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
        vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy; i=mod289(i);
        vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
        float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx; vec4 j=p-49.0*floor(p*ns.z*ns.z);
        vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_); vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy;
        vec4 h=1.0-abs(x)-abs(y); vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw); vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
        vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
        vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
        vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
        p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
        vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m*=m;
        return 42.0*dot(m*m, vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3))); }
      void main(){ vN=normalize(normalMatrix*normal);
        float slow=time*.3; vec3 p=position; float n=snoise(vec3(position*.55 + slow));
        p += normal * n * 0.22 * distortion * (1.0 + audioLevel);
        vP=p; gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0); }`,
    fragmentShader:`uniform float time; uniform vec3 color; uniform float audioLevel; varying vec3 vN; varying vec3 vP;
      void main(){ vec3 viewDir=normalize(cameraPosition - vP);
        float fres=1.0 - max(0.0, dot(viewDir, normalize(vN))); fres=pow(fres, 2.2 + audioLevel*2.5);
        float pulse = 0.7 + 0.3*sin(time*2.0);
        vec3 col = color * fres * pulse * (1.0 + audioLevel*0.8);
        float a = fres * (0.75 - audioLevel*0.3);
        gl_FragColor = vec4(col, a); }`,
    wireframe:true, transparent:true
  });
  const mesh = new THREE.Mesh(geo, mat); orbGroup.add(mesh);

  const glowGeo = new THREE.SphereGeometry(radius*1.18, 32, 32);
  const glowMat = new THREE.ShaderMaterial({
    uniforms:{ time:{value:0}, color:{value:new THREE.Color(0x66e6ff)}, audioLevel:{value:0} },
    vertexShader:`varying vec3 vN; varying vec3 vP; uniform float audioLevel;
      void main(){ vN=normalize(normalMatrix*normal); vP=position*(1.0+audioLevel*0.22);
        gl_Position=projectionMatrix*modelViewMatrix*vec4(vP,1.0); }`,
    fragmentShader:`varying vec3 vN; varying vec3 vP; uniform vec3 color; uniform float time; uniform float audioLevel;
      void main(){ vec3 viewDir=normalize(cameraPosition - vP);
        float fres=1.0-max(0.0,dot(viewDir,normalize(vN))); fres=pow(fres,3.0 + audioLevel*3.0);
        float pulse=0.55 + 0.45*sin(time*2.0);
        float af = 1.0 + audioLevel*3.0;
        vec3 col = color * fres * (0.8 + 0.2*pulse) * af;
        float a = fres * (0.28 * af) * (1.0 - audioLevel*0.2);
        gl_FragColor = vec4(col, a); }`,
    transparent:true, side:THREE.BackSide, blending:THREE.AdditiveBlending, depthWrite:false
  });
  orbGroup.add(new THREE.Mesh(glowGeo, glowMat));
  scene.add(orbGroup);
  return (time, level)=>{ mat.uniforms.time.value=time; mat.uniforms.audioLevel.value=level; mat.uniforms.distortion.value=distortionAmount; glowMat.uniforms.time.value=time; glowMat.uniforms.audioLevel.value=level; };
}

function createStars(){ /* filled above */ }

function disturbOrb(){
  if (!orbGroup) return;
  const base = distortionAmount; distortionAmount = base + 0.6;
  setTimeout(()=> distortionAmount = base, 140);
  const ox = orbGroup.rotation.x, oy=orbGroup.rotation.y;
  gsap.fromTo(orbGroup.rotation, {x:ox+0.15, y:oy-0.25}, {x:ox,y:oy,duration:.35,ease:"power3.out"});
  gsap.fromTo(camera.position, {z:9.2}, {z:10,duration:.45,ease:"power2.out"});
  notify("VOICE DETECTED", {type:"ok", timeout:1200});
}

/* ========================= DOM PARTICLES ========================= */
const domParticles=[];
function initDOMParticles(){
  const holder = document.getElementById("floating-particles");
  holder.innerHTML=""; domParticles.length=0;
  const count=800, w=innerWidth, h=innerHeight, cx=w/2, cy=h/2;
  for (let i=0;i<count;i++){
    const el=document.createElement("div");
    el.style.position="absolute"; el.style.width="2px"; el.style.height="2px"; el.style.borderRadius="50%";
    el.style.backgroundColor = `rgba(102,230,255,${Math.random()*0.5+0.15})`;
    const ang=Math.random()*Math.PI*2; const minD=180, maxD=Math.max(w,h)*0.8;
    const d=minD + Math.sqrt(Math.random())*(maxD-minD);
    const x=Math.cos(ang)*d + cx, y=Math.sin(ang)*d + cy;
    el.style.left=x+"px"; el.style.top=y+"px"; holder.appendChild(el);
    domParticles.push({ el, x, y, speed:Math.random()*0.5+0.1, ang:Math.random()*Math.PI*2, angSp:(Math.random()-0.5)*0.02, amp:Math.random()*46+18, sz:1.6, pSp:Math.random()*0.04+0.01, pPh:Math.random()*Math.PI*2 });
  }
  (function anim(){
    const cx=innerWidth/2, cy=innerHeight/2, t=performance.now()*0.001;
    for (const p of domParticles){
      p.ang += p.angSp;
      const ox = cx + Math.cos(p.ang)*p.amp;
      const oy = cy + Math.sin(p.ang)*p.amp;
      const nx = Math.sin(t*p.speed + p.ang)*4;
      const ny = Math.cos(t*p.speed + p.ang*0.7)*4;
      const X=ox+nx, Y=oy+ny;
      p.el.style.left=X+"px"; p.el.style.top=Y+"px";
      const pulse = 1 + Math.sin(t*p.pSp + p.pPh)*0.35;
      const s = p.sz*pulse; p.el.style.width=s+"px"; p.el.style.height=s+"px";
      p.el.style.opacity = Math.min(.85, .25 + Math.sin(t*p.pSp + p.pPh)*.15 + .35);
    }
    requestAnimationFrame(anim);
  })();
}

/* ========================= REALTIME TRANSCRIPTION ========================= */
let rtWS=null, pcmSender=null, streaming=false;
const transcriptEl = document.getElementById("transcript-stream");
let currentFrag = "";

async function startRealtimeTranscription(){
  // 1) Get ephemeral token from your FastAPI
  let tokenResp;
  try{
    tokenResp = await fetch("/rt-token"); // same origin; change if your server differs
  }catch(e){ notify("AUTH REQUEST FAILED",{type:"error"}); console.error(e); return; }
  if (!tokenResp.ok){ notify("AUTH HTTP ERROR",{type:"error"}); return; }
  const tok = await tokenResp.json();
  const clientSecret = tok?.client_secret?.value || tok?.client_secret;
  if (!clientSecret){ notify("AUTH MISSING TOKEN",{type:"error"}); return; }

  // 2) Open WS with required subprotocols
  const url = "wss://api.openai.com/v1/realtime?intent=transcription";
  rtWS = new WebSocket(url, [
    "realtime",
    "openai-insecure-api-key." + clientSecret,
    "openai-beta.realtime-v1"
  ]);

  rtWS.onopen = () => {
    notify("REALTIME LINK ESTABLISHED",{type:"ok"});
    // Tell server our ASR settings (model + server-side VAD)
    const cfg = {
      type: "transcription_session.update",
      input_audio_format: "pcm16",
      input_audio_transcription: {
        model: "gpt-4o-mini-transcribe",   // or "gpt-4o-transcribe"
        prompt: "",
        language: ""                       // let it auto-detect
      },
      turn_detection: {
        type: "server_vad",
        threshold: 0.5,
        prefix_padding_ms: 300,
        silence_duration_ms: 500
      },
      input_audio_noise_reduction: { type: "near_field" },
      include: [ "item.input_audio_transcription.logprobs" ]
    };
    rtWS.send(JSON.stringify(cfg));

    // Start sending mic PCM16 chunks
    beginPCMAudioStream();
  };

  rtWS.onclose = (ev) => {
    notify("REALTIME LINK CLOSED",{type:"warn"});
    stopPCMAudioStream();
    rtWS=null;
  };

  rtWS.onerror = (ev) => {
    notify("REALTIME ERROR",{type:"error"});
    console.error("WS error", ev);
  };

  rtWS.onmessage = (ev) => {
    // Handle streaming events from API
    let msg;
    try{ msg = JSON.parse(ev.data); }catch{ return; }

    // A few likely event shapes (cover both delta + final):
    switch (msg.type) {
      case "transcript.text.delta":
      case "response.output_text.delta":
      case "response.transcript.delta":
        appendFrag(msg.delta || msg.text || msg.value || "");
        break;

      case "transcript.text.done":
      case "response.output_text.done":
      case "response.transcript.done":
        commitFrag(msg.text || msg.value || "");
        break;

      case "transcription.speech_started":
        // Server VAD says speech began
        // (We already have local VAD anims, but you can hook here too)
        break;

      case "transcription.speech_stopped":
        // Server VAD ended a segment
        break;

      case "input_audio_buffer.committed":
        // Server chunked a speech segment; contains item_id ordering if needed
        break;

      default:
        // console.debug("RT evt:", msg);
        break;
    }
  };
}

function appendFrag(text){
  if (!text) return;
  currentFrag += text;
  renderTranscript();
}
function commitFrag(text){
  if (text) currentFrag += text;
  // Wrap the fragment as a "final" line
  const div = document.createElement("div");
  div.className = "final";
  div.textContent = currentFrag.trim();
  if (div.textContent) transcriptEl.appendChild(div);
  currentFrag = "";
  renderTranscript();
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}
function renderTranscript(){
  // Show a single live line at the bottom
  let live = transcriptEl.querySelector(".frag");
  if (!live){ live = document.createElement("div"); live.className="frag"; transcriptEl.appendChild(live); }
  live.textContent = currentFrag;
}

function beginPCMAudioStream(){
  if (streaming || !audioContext || !micSource || !rtWS || rtWS.readyState !== 1) return;
  streaming = true;
  // Use ScriptProcessor to capture Float32 frames, convert to PCM16
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  const mute = audioContext.createGain(); mute.gain.value = 0;
  micSource.connect(processor); processor.connect(mute); mute.connect(audioContext.destination);
  const chunkMs = 250;
  let bufChunks = [], bufSamples = 0, lastFlush = performance.now();

  processor.onaudioprocess = (e) => {
    if (!streaming || !rtWS || rtWS.readyState !== 1) return;
    const ch = e.inputBuffer.getChannelData(0);
    // clone to detach from internal buffer
    bufChunks.push(new Float32Array(ch));
    bufSamples += ch.length;

    const now = performance.now();
    if (now - lastFlush >= chunkMs) {
      const merged = mergeFloat32(bufChunks, bufSamples);
      bufChunks = []; bufSamples = 0; lastFlush = now;

      // Convert to PCM16 and base64 encode
      const b64 = floatTo16BitPCMBase64(merged);
      rtWS.send(JSON.stringify({ type:"input_audio_buffer.append", audio: b64 }));
    }
  };

  // Keep a handle so we can stop cleanly
  pcmSender = { processor, mute, stop(){
    try{ processor.disconnect(); }catch{}
    try{ mute.disconnect(); }catch{}
    streaming=false;
  }};
}

function stopPCMAudioStream(){
  if (pcmSender){ pcmSender.stop(); pcmSender=null; }
}

function mergeFloat32(chunks, total){
  const out = new Float32Array(total);
  let off=0; for (const c of chunks){ out.set(c, off); off+=c.length; }
  return out;
}
function floatTo16BitPCMBase64(float32){
  const buf = new ArrayBuffer(float32.length*2);
  const view = new DataView(buf);
  for (let i=0;i<float32.length;i++){
    let s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i*2, s<0 ? s*0x8000 : s*0x7FFF, true);
  }
  const bytes = new Uint8Array(buf);
  // Faster base64 for large arrays
  let bin = "";
  const CHUNK = 0x8000;
  for (let i=0;i<bytes.length;i+=CHUNK){
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i+CHUNK));
  }
  return btoa(bin);
}

/* ========================= MAIN LOOP ========================= */
let lastVADEmit = 0;
function animate(){
  requestAnimationFrame(animate);
  controls && controls.update();
  const t = clock.getElapsedTime();

  let level=0;
  if (analyser && freqData){
    analyser.getByteFrequencyData(freqData);
    let sum=0; for (let i=0;i<freqData.length;i++) sum += freqData[i];
    level = ((sum / freqData.length) / 255) * (audioSensitivity/5);
    drawCircular(); updateRing();
  }

  if (micActive){
    const change = vadTick(); // "start"|"end"|false
    if (change === "start"){
      const now = performance.now();
      if (now - lastVADEmit > 120){ disturbOrb(); lastVADEmit = now; }
    }
  }

  updateOrbUniforms && updateOrbUniforms(t, level);
  updateBackground && updateBackground(t);

  if (orbGroup){
    const rotF = 1 + level * audioReactivity;
    orbGroup.rotation.y += 0.005 * rotationSpeed * rotF;
    orbGroup.rotation.z += 0.002 * rotationSpeed * rotF;
  }
  renderer.render(scene, camera);
}

/* ========================= BOOT ========================= */
initAudio();
initThree();
initDOMParticles();
notify("SYSTEM ONLINE • TAP THE ORB TO ENABLE MIC",{type:"ok"});

// Click anywhere (or the canvas) to start mic
window.addEventListener("click", async () => {
  try{
    if (!audioContext) initAudio();
    if (audioContext.state === "suspended") await audioContext.resume();
    if (!micActive) await attachMic();
  }catch(e){ console.warn(e); }
}, { once:false });

});
