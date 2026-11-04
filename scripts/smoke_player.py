"""Execute the actual player script in QuickJS with a small event-driven DOM.

Test-only dependency: uv run --locked --with quickjs==1.19.4 python scripts/smoke_player.py
This checks player state, not browser media decoding or screen-reader support.
"""
import json
import re

import quickjs

from audiopod.player import player_html


DOM = r'''
function assert(ok, message) {if(!ok) throw Error(message);}
const writes=[], timers=new Map(), elements={}, windowEvents={}; let timerId=0;
function element(tag='DIV') {
  return {tagName:tag, children:[], events:{}, value:'', textContent:'', disabled:false,
    append(child){this.children.push(child);}, setAttribute(k,v){this[k]=v;},
    addEventListener(k,fn){this.events[k]=fn;}, emit(k){if(this.events[k])this.events[k]();}};
}
for(const id of ['audio','speed','status','current','reading','prev','next','back','ahead','sleep','restart','list']) elements[id]=element();
Object.assign(elements.audio, {currentTime:0, duration:NaN, paused:true,
  play(){this.paused=false;return {catch(){}};}, pause(){this.paused=true;this.emit('pause');}});
elements.speed.options=['.5','.75','1','1.25','1.5','1.75','2'].map(value=>({value}));
elements.speed.value='1'; elements.sleep.value='0';
const document={getElementById:id=>elements[id],createElement:element,
  querySelectorAll:q=>q==='#list button'?elements.list.children.map(li=>li.children[0]):Object.values(elements),
  addEventListener(){}};
const window={addEventListener:(k,fn)=>windowEvents[k]=fn};
const localStorage={getItem(){if(blocked)throw Error('storage blocked');return bookmark;},
  setItem(k,v){if(blocked)throw Error('storage blocked');writes.push(JSON.parse(v));}};
function setTimeout(fn,ms){timers.set(++timerId,{fn,ms});return timerId;}
function clearTimeout(id){timers.delete(id);}
function latest(){return writes[writes.length-1];}
'''


def context(bookmark='{}', blocked=False, tracks=None):
    tracks = tracks if tracks is not None else [
        {'file': '0001.wav', 'title': 'First', 'text': 'One.'},
        {'file': '0002.wav', 'title': 'Second', 'text': 'Two.'},
    ]
    html = player_html('Test', 'Author', tracks, 'test', 'en-GB')
    script = re.search(r'<script>(.*?)</script>', html, re.S)[1]
    ctx = quickjs.Context()
    ctx.eval(f'const bookmark={json.dumps(bookmark)}, blocked={json.dumps(blocked)};')
    ctx.eval(DOM)
    ctx.eval(script)
    return ctx


ctx = context('{"index":1,"time":42,"speed":"1.25"}')
ctx.eval('''
assert(elements.audio.src==='0002.wav','restored chapter');
elements.audio.emit('pause'); elements.audio.emit('timeupdate'); windowEvents.pagehide();
assert(writes.length===0,'loading events must not clobber a saved bookmark');
elements.audio.duration=100; elements.audio.emit('loadedmetadata');
assert(elements.audio.currentTime===42 && latest().time===42,'restored time');
assert(elements.audio.playbackRate===1.25,'restored speed');
elements.back.onclick(); assert(latest().time===27,'back 15 seconds');
elements.ahead.onclick(); assert(latest().time===42,'forward 15 seconds');
elements.sleep.onchange({target:{value:'5'}});
assert([...timers.values()][0].ms===300000,'sleep duration');
elements.sleep.onchange({target:{value:'15'}});
assert(timers.size===1,'replacing sleep cancels previous timer');
[...timers.values()][0].fn();
assert(elements.audio.paused && elements.sleep.value==='0','sleep pauses playback');
elements.restart.onclick();
assert(elements.audio.src==='0001.wav' && elements.audio.paused,'restart selects first chapter paused');
elements.audio.emit('loadedmetadata'); assert(latest().index===0 && latest().time===0,'restart resets bookmark');
elements.audio.emit('ended'); elements.audio.emit('loadedmetadata');
assert(latest().index===1 && !elements.audio.paused,'advance to next chapter');
''')
for stored, blocked in (('{invalid', False), ('null', False), ('{}', True)):
    context(stored, blocked).eval('''
elements.audio.duration=100; elements.audio.emit('loadedmetadata');
elements.next.onclick(); elements.audio.emit('loadedmetadata');
assert(elements.audio.src==='0002.wav','controls work without usable storage');
''')
context(tracks=[]).eval("assert(elements.next.disabled && elements.restart.disabled,'empty player controls disabled')")
print('Player bookmarks, seeking, chapter advance, restart, sleep timer and unavailable storage passed.')
