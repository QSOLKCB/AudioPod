"""A portable listening page with no server, CDN, or telemetry."""

from html import escape
import json
import re


def player_html(title, author, tracks, identity, language="en"):
    data = json.dumps(tracks, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    language = language if re.fullmatch(r"[A-Za-z0-9-]{1,40}", language) else "en"
    values = {"TITLE": escape(title), "AUTHOR": escape(author), "KEY": identity, "TRACKS": data, "LANG": language}
    return re.sub(r"__(TITLE|AUTHOR|KEY|TRACKS|LANG)__", lambda m: values[m[1]], TEMPLATE)


TEMPLATE = '''<!doctype html>
<html lang="__LANG__"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; base-uri 'none'">
<title>__TITLE__ — AudioPod</title>
<style>
:root {color-scheme:dark light;font:18px/1.6 system-ui,sans-serif;background:#101d26;color:#edf4f5}
body {max-width:850px;margin:0 auto;padding:32px 20px} h1 {font-size:clamp(2rem,6vw,3.5rem);line-height:1.1;margin:.3em 0}
.brand {color:#81d9c9;letter-spacing:.16em;font-size:.8rem} .muted {color:#b5c7cf}
section {background:#192c38;border:1px solid #48606c;border-radius:16px;padding:20px;margin:24px 0}
audio {width:100%;margin:16px 0} button,select {font:inherit;padding:9px 14px;margin:4px;border-radius:7px;border:1px solid #6d919d;background:#223e4b;color:#fff;cursor:pointer}
button:hover {background:#365763} :focus-visible {outline:3px solid #ffdb8a;outline-offset:3px}
ol {padding-left:1.8em} li {margin:8px 0} li button {text-align:left;width:95%;margin:0} li button[aria-current=true] {border-color:#81d9c9;background:#224f4e}
#reading {white-space:pre-wrap;font-size:1.1rem} summary {cursor:pointer} .row {display:flex;flex-wrap:wrap;align-items:center;gap:6px}
</style>
<main><p class="brand">AUDIOPOD · LOCAL LISTENING</p><h1>__TITLE__</h1><p class="muted">__AUTHOR__</p>
<section aria-label="Playback"><h2 id="current">Choose a chapter</h2><audio id="audio" controls preload="metadata"></audio>
<div class="row"><button id="prev" aria-label="Previous chapter">Previous</button><button id="back" aria-label="Back 15 seconds">−15 s</button><button id="ahead" aria-label="Forward 15 seconds">+15 s</button><button id="next" aria-label="Next chapter">Next</button>
<label for="speed">Speed</label><select id="speed"><option>.5</option><option>.75</option><option selected>1</option><option>1.25</option><option>1.5</option><option>1.75</option><option>2</option></select></div>
<div class="row"><label for="sleep">Sleep timer</label><select id="sleep"><option value="0">Off</option><option value="5">5 minutes</option><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">60 minutes</option></select><button id="restart">Start book again</button></div>
<p id="status" class="muted" role="status"></p><p class="muted">Space: play/pause · Left/Right: seek 15 seconds. Position is saved in this browser when local storage is available.</p></section>
<section aria-labelledby="chapters"><h2 id="chapters">Chapters</h2><ol id="list"></ol></section>
<section><details><summary>Read the current chapter</summary><p id="reading"></p></details></section>
<p class="muted">Synthetic narration made locally with AudioPod. Keep this page beside its audio files. No account or connection is needed.</p></main>
<script>
'use strict';
const tracks=__TRACKS__, key='audiopod-__KEY__', audio=document.getElementById('audio'), speed=document.getElementById('speed'), status=document.getElementById('status');
let index=0, restore=0, ready=false, lastSave=0, sleepTimer=null;
function save(){if(!ready||!tracks.length)return;try{localStorage.setItem(key,JSON.stringify({index,time:audio.currentTime,speed:speed.value}));}catch{status.textContent='This browser cannot save local bookmarks. Playback still works.';}}
function select(i,play=false,time=0){if(!tracks.length)return;ready=false;index=Math.max(0,Math.min(i,tracks.length-1));restore=time;audio.src=tracks[index].file;audio.playbackRate=Number(speed.value);document.getElementById('current').textContent=tracks[index].title;document.getElementById('reading').textContent=tracks[index].text;document.querySelectorAll('#list button').forEach((b,n)=>b.setAttribute('aria-current',String(n===index)));document.getElementById('prev').disabled=index===0;document.getElementById('next').disabled=index===tracks.length-1;if(play)audio.play().catch(()=>status.textContent='Press Play to begin.');}
tracks.forEach((t,i)=>{const li=document.createElement('li'),b=document.createElement('button');b.textContent=t.title;b.onclick=()=>{select(i,true);save();};li.append(b);document.getElementById('list').append(li);});
let saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')||{};}catch{}
if([...speed.options].some(o=>o.value===saved.speed))speed.value=saved.speed;
select(Number.isInteger(saved.index)?saved.index:0,false,Number.isFinite(saved.time)?Math.max(0,saved.time):0);
audio.addEventListener('loadedmetadata',()=>{if(!Number.isFinite(audio.duration))return;audio.currentTime=Math.min(restore,Math.max(0,audio.duration-.1));restore=0;audio.playbackRate=Number(speed.value);ready=true;save();});
audio.addEventListener('timeupdate',()=>{if(Date.now()-lastSave>2000){lastSave=Date.now();save();}});audio.addEventListener('pause',save);window.addEventListener('pagehide',save);
audio.addEventListener('ended',()=>{if(index+1<tracks.length){select(index+1,true);save();}});
audio.addEventListener('error',()=>status.textContent='Audio could not be opened. Keep the audio files beside this page, or open them in your audio player.');
speed.onchange=()=>{audio.playbackRate=Number(speed.value);save();};
document.getElementById('sleep').onchange=e=>{clearTimeout(sleepTimer);sleepTimer=null;const minutes=Number(e.target.value);if(minutes>0){sleepTimer=setTimeout(()=>{audio.pause();document.getElementById('sleep').value='0';status.textContent='Sleep timer finished. Playback paused.';},minutes*60000);status.textContent='Playback will pause in '+minutes+' minutes.';}else status.textContent='Sleep timer off.';};
document.getElementById('restart').onclick=()=>{select(0,false,0);audio.pause();};
function seek(delta){if(Number.isFinite(audio.duration)){audio.currentTime=Math.min(audio.duration,Math.max(0,audio.currentTime+delta));save();}}
document.getElementById('prev').onclick=()=>{select(index-1,true);save();};document.getElementById('next').onclick=()=>{select(index+1,true);save();};document.getElementById('back').onclick=()=>seek(-15);document.getElementById('ahead').onclick=()=>seek(15);
document.addEventListener('keydown',e=>{if(/^(INPUT|TEXTAREA|SELECT|BUTTON|AUDIO|SUMMARY)$/.test(e.target.tagName)||e.altKey||e.ctrlKey||e.metaKey)return;if(e.code==='Space'){e.preventDefault();if(audio.paused)audio.play().catch(()=>{});else audio.pause();}if(e.code==='ArrowLeft'){e.preventDefault();seek(-15);}if(e.code==='ArrowRight'){e.preventDefault();seek(15);}});
if(!tracks.length){status.textContent='No completed chapters yet. Resume narration to add audio.';document.querySelectorAll('button,select').forEach(b=>b.disabled=true);}
</script></html>'''
