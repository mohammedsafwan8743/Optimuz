"""OPTIMUZ v2 - AI Voice Companion"""

import os, json, base64, re, tempfile, asyncio
from pathlib import Path
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
EDGE_VOICE   = os.getenv("EDGE_VOICE", "en-US-ChristopherNeural")

DATA_DIR     = Path("data")
MEMORY_FILE  = DATA_DIR / "memory.json"
HISTORY_FILE = DATA_DIR / "history.jsonl"
DATA_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="OPTIMUZ", page_icon="🤖", layout="centered", initial_sidebar_state="collapsed")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@300;400;600;700&display=swap');
#MainMenu,footer,header,.stDeployButton,.stToolbar{display:none!important}
.block-container{padding:0.5rem 0.8rem!important;max-width:580px!important;margin:0 auto!important}
.stApp{
  background:linear-gradient(160deg,#06111c 0%,#040d16 40%,#020810 70%,#010508 100%) !important;
  min-height:100vh !important;
}
.stAudio>label{display:none!important}
div[data-testid="stAudioInput"]{
  background:rgba(5,15,28,0.95)!important;
  border:1px solid rgba(50,100,160,0.3)!important;
  border-radius:12px!important;
  padding:12px!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.03),0 0 25px rgba(0,60,140,0.15)!important;
}
::-webkit-scrollbar{width:2px}
::-webkit-scrollbar-thumb{background:rgba(50,120,200,0.3);border-radius:2px}
@keyframes orbFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
@keyframes orbListen{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}
@keyframes orbSpeak{0%,100%{transform:scale(1)}50%{transform:scale(1.04)}}
@keyframes ringRot{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
@keyframes ringRotR{from{transform:rotate(0deg)}to{transform:rotate(-360deg)}}
@keyframes glowPulse{0%,100%{opacity:0.2}50%{opacity:0.65}}
@keyframes waveAnim{0%,100%{transform:scaleY(0.2)}50%{transform:scaleY(1)}}
@keyframes dotBounce{0%,100%{transform:translateY(0);opacity:0.2}50%{transform:translateY(-8px);opacity:1}}
@keyframes scanAnim{0%{top:-2px}100%{top:102%}}
@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes titleGlow{
  0%,100%{filter:drop-shadow(0 0 12px rgba(80,160,255,0.25))}
  50%{filter:drop-shadow(0 0 28px rgba(100,180,255,0.5))}
}
@keyframes platePulse{
  0%,100%{border-color:rgba(40,90,150,0.3)}
  50%{border-color:rgba(70,140,220,0.6)}
}
.msg-anim{animation:fadeUp 0.35s ease-out forwards}
</style>""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_memory():
    if MEMORY_FILE.exists():
        try: return json.loads(MEMORY_FILE.read_text())
        except: pass
    return {"facts":[],"name":None,"last_seen":None,"mood_history":[]}

def save_memory(m): MEMORY_FILE.write_text(json.dumps(m, indent=2, ensure_ascii=False))

def append_history(role, content, emotion="neutral"):
    with open(HISTORY_FILE,"a",encoding="utf-8") as f:
        f.write(json.dumps({"ts":datetime.now().isoformat(),"role":role,"content":content,"emotion":emotion},ensure_ascii=False)+"\n")

def load_recent_history(n=16):
    if not HISTORY_FILE.exists(): return []
    lines = HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
    return [json.loads(l) for l in lines[-n:] if l.strip()]

def update_memory(text, emotion="neutral"):
    m = load_memory()
    m["last_seen"] = datetime.now().isoformat()
    match = re.search(r"(?:my name is|i'm|i am|call me)\s+([A-Z][a-z]+)", text, re.IGNORECASE)
    if match and not m.get("name"): m["name"] = match.group(1)
    if emotion != "neutral":
        m.setdefault("mood_history",[]).append({"emotion":emotion,"ts":datetime.now().isoformat()[:10]})
        if len(m["mood_history"])>20: m["mood_history"]=m["mood_history"][-20:]
    for kw in ["i like","i love","i work","i live","my job","i study","i am","i enjoy","my goal"]:
        if kw in text.lower() and len(text)<250 and text not in m["facts"]:
            m["facts"].append(text.strip())
            if len(m["facts"])>60: m["facts"]=m["facts"][-60:]
            break
    save_memory(m); return m

def detect_emotion(t):
    t=t.lower()
    if any(w in t for w in ["sad","depressed","crying","hurt","lonely","heartbreak"]): return "sad"
    if any(w in t for w in ["anxious","worried","stressed","panic","scared","overwhelmed"]): return "anxious"
    if any(w in t for w in ["happy","great","amazing","excited","love","awesome","wonderful"]): return "happy"
    if any(w in t for w in ["angry","frustrated","annoyed","mad","furious"]): return "angry"
    if any(w in t for w in ["tired","exhausted","sleepy","drained"]): return "tired"
    if any(w in t for w in ["motivated","ready","focused","let's go","pumped"]): return "motivated"
    return "neutral"

def check_wake_word(text):
    patterns = [r"hey\s+opti(?:muz)?",r"hi\s+opti(?:muz)?",r"ok\s+opti(?:muz)?",
                r"okay\s+opti(?:muz)?",r"hello\s+opti(?:muz)?",r"yo\s+opti(?:muz)?"]
    t = text.lower()
    for p in patterns:
        if re.search(p, t):
            clean = re.sub(p,"",t,flags=re.IGNORECASE).strip(" .,!?")
            return True, clean
    return False, text

def ask_groq(message, memory, emotion):
    from groq import Groq
    ctx = ""
    if memory.get("name"): ctx += f"User's name: {memory['name']}. Use it naturally.\n"
    if memory.get("facts"): ctx += "Known facts:\n" + "\n".join(f"  - {f}" for f in memory["facts"][-10:]) + "\n"
    if memory.get("mood_history"):
        moods = [x["emotion"] for x in memory["mood_history"][-5:]]
        ctx += f"Recent moods: {', '.join(moods)}\n"
    eguide = {
        "sad":"Lead with empathy. Be warm and present. Don't rush to fix.",
        "anxious":"Be calm and grounding. Speak with steady reassurance.",
        "happy":"Match their energy! Be warm and celebratory.",
        "angry":"Acknowledge feelings first. Don't dismiss.",
        "tired":"Be gentle and brief. Don't overwhelm.",
        "motivated":"Be bold and energizing!",
    }.get(emotion,"Respond naturally and warmly.")
    system = f"""You are OPTIMUZ — a powerful AI companion inspired by Optimus Prime. Strong, wise, loyal, deeply caring.

{ctx}
Emotional context: {eguide}

CRITICAL — spoken aloud:
- 1-3 sentences MAX. Short and powerful.
- NO bullet points, NO markdown, NO asterisks.
- Calm authority + warmth, like Optimus Prime.
- Auto-detect language and reply in same language.
- Never robotic. Always genuine and present."""

    history = load_recent_history(14)
    msgs = [{"role":"system","content":system}]
    for h in history[-12:]:
        if h["role"] in ["user","assistant"]:
            msgs.append({"role":h["role"],"content":h["content"]})
    msgs.append({"role":"user","content":message})
    client = Groq(api_key=GROQ_API_KEY)
    resp = client.chat.completions.create(model="llama-3.3-70b-versatile",messages=msgs,max_tokens=180,temperature=0.82)
    return resp.choices[0].message.content.strip()

def transcribe_audio(audio_bytes):
    from groq import Groq
    with tempfile.NamedTemporaryFile(suffix=".wav",delete=False) as f:
        f.write(audio_bytes); path=f.name
    try:
        client = Groq(api_key=GROQ_API_KEY)
        with open(path,"rb") as af:
            result = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=("audio.wav",af,"audio/wav"),
                response_format="text"
            )
        return result.strip() if isinstance(result,str) else result.text.strip()
    finally:
        os.unlink(path)

def speak(text):
    import edge_tts
    clean = re.sub(r"[*_`#\[\]]","",text).strip()
    with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as f: out_path=f.name
    async def _gen():
        c = edge_tts.Communicate(clean, EDGE_VOICE, rate="-8%", pitch="-15Hz", volume="+10%")
        await c.save(out_path)
    asyncio.run(_gen())
    with open(out_path,"rb") as f: data=f.read()
    os.unlink(out_path)
    return base64.b64encode(data).decode()

# ── Orb HTML builder ──────────────────────────────────────────────────────────
def build_orb_html(state, status, transcript, name):
    cfgs = {
        "idle":      ("#0a1520","#162535","#1e3a50","rgba(30,80,140,0.3)", "orbFloat 5s ease-in-out infinite",          "#3a7abf"),
        "listening": ("#0a1e30","#1a3d60","#2a6090","rgba(40,120,200,0.5)","orbListen 0.9s ease-in-out infinite",        "#4da6ff"),
        "thinking":  ("#150d25","#2a1845","#3d2260","rgba(80,40,160,0.45)","none",                                       "#8855ee"),
        "speaking":  ("#0a2015","#153520","#1e5030","rgba(20,140,80,0.45)","orbSpeak 0.5s ease-in-out infinite",         "#33cc77"),
        "wake":      ("#0a2010","#155020","#209040","rgba(20,180,80,0.4)", "orbListen 0.6s ease-in-out infinite",        "#22ee66"),
    }
    c1,c2,c3,glow,anim,dot = cfgs.get(state, cfgs["idle"])
    labels = {"idle":"STANDBY","listening":"LISTENING","thinking":"PROCESSING","speaking":"SPEAKING","wake":"WAKE WORD DETECTED"}

    if state == "speaking":
        inner = "<div style='display:flex;gap:4px;align-items:center'>" + \
            "".join(f"<div style='width:3px;height:{h}px;background:rgba(0,255,150,0.9);border-radius:2px;animation:waveAnim 0.5s ease-in-out infinite;animation-delay:{i*0.08}s'></div>"
                    for i,h in enumerate([8,14,22,30,22,14,8])) + "</div>"
    elif state in ("listening","wake"):
        inner = "<div style='font-size:32px;filter:drop-shadow(0 0 12px rgba(0,180,255,0.9))'>🎙️</div>"
    elif state == "thinking":
        inner = "<div style='display:flex;gap:7px'>" + \
            "".join(f"<div style='width:9px;height:9px;border-radius:50%;background:rgba(160,80,255,0.95);animation:dotBounce 1.1s ease-in-out infinite;animation-delay:{i*0.2}s'></div>"
                    for i in range(3)) + "</div>"
    else:
        inner = "<div style='font-size:32px;opacity:0.35;color:#0080cc;font-family:Orbitron,monospace'>&#8853;</div>"

    subtitle = ("ONLINE &middot; " + name.upper()) if name else "v2.0 &middot; ALWAYS READY"
    transcript_html = ""
    if transcript:
        transcript_html = "<div style='font-family:Exo 2,sans-serif;font-size:14px;color:#4a7090;margin-top:6px;padding:6px 14px;border-left:2px solid rgba(60,130,200,0.4);max-width:360px;margin-left:auto;margin-right:auto'>&ldquo;" + transcript + "&rdquo;</div>"

    return f"""
<div style="position:relative;z-index:1">
  <div style="text-align:center;padding:12px 0 6px">
    <div style="font-family:Orbitron,monospace;font-size:clamp(30px,8vw,46px);font-weight:900;
      letter-spacing:clamp(5px,2vw,12px);background:linear-gradient(135deg,#a8d4f8 0%,#4a90d9 30%,#c8e8ff 55%,#5ba3e8 75%,#8ec8ff 100%);background-size:200% auto;animation:titleGlow 3s ease-in-out infinite;
      -webkit-background-clip:text;background-clip:text;color:transparent;animation:titleGlow 3s ease-in-out infinite">
      OPTIMUZ
    </div>
    <div style="font-family:Orbitron,monospace;font-size:clamp(8px,2vw,10px);letter-spacing:clamp(2px,1vw,5px);
      color:#1e3a55;text-transform:uppercase;margin-top:3px;letter-spacing:4px">{subtitle}</div>
  </div>

  <div style="position:relative;width:clamp(180px,48vw,220px);height:clamp(180px,48vw,220px);
    display:flex;align-items:center;justify-content:center;margin:8px auto">
    <div style="position:absolute;width:110%;height:110%;border-radius:50%;
      background:radial-gradient(circle,{glow} 0%,transparent 65%);animation:glowPulse 2.5s ease-in-out infinite"></div>
    <div style="position:absolute;width:100%;height:100%;border-radius:50%;
      border:1px solid rgba(0,180,255,0.12);animation:ringRot 10s linear infinite">
      <div style="position:absolute;top:-4px;left:50%;width:7px;height:7px;background:{dot};border-radius:50%;box-shadow:0 0 14px {dot}"></div>
    </div>
    <div style="position:absolute;width:85%;height:85%;border-radius:50%;
      border:1px solid rgba(50,120,200,0.1);animation:ringRotR 7s linear infinite">
      <div style="position:absolute;bottom:-3px;left:40%;width:5px;height:5px;background:#4a90d9;border-radius:50%;box-shadow:0 0 10px #4a90d9"></div>
    </div>
    <div style="width:72%;height:72%;border-radius:50%;
      background:radial-gradient(circle at 32% 32%,{c3} 0%,{c2} 40%,{c1} 100%);
      box-shadow:0 0 50px {glow},inset 0 0 30px rgba(0,0,0,0.6),inset 0 3px 8px rgba(255,255,255,0.06);
      animation:{anim};display:flex;align-items:center;justify-content:center;
      position:relative;overflow:hidden;transition:all 0.6s ease">
      <div style="position:absolute;top:12%;left:16%;width:38%;height:22%;border-radius:50%;
        background:radial-gradient(ellipse,rgba(255,255,255,0.09) 0%,transparent 100%)"></div>
      <div style="position:absolute;width:100%;height:2px;
        background:linear-gradient(90deg,transparent,rgba(0,220,255,0.3),transparent);
        animation:scanAnim 2.5s linear infinite"></div>
      {inner}
    </div>
  </div>

  <div style="text-align:center;margin:6px 0 10px">
    <div style="font-family:Orbitron,monospace;font-size:clamp(8px,2vw,10px);letter-spacing:3px;
      text-transform:uppercase;color:{dot};margin-bottom:5px">&#9679; {labels.get(state,"STANDBY")}</div>
    <div style="font-family:Exo 2,sans-serif;font-size:clamp(13px,3.5vw,15px);color:#1e3a55;font-style:italic;min-height:20px">{status}</div>
    {transcript_html}
  </div>
</div>"""

def render_orb(state="idle", status="", transcript=""):
    memory = st.session_state.get("memory", {})
    name = memory.get("name","")
    html = build_orb_html(state, status, transcript, name)
    st.markdown(html, unsafe_allow_html=True)

# ── Chat renderer ─────────────────────────────────────────────────────────────
def render_chat(messages):
    if not messages: return
    st.markdown("<div style='font-family:Orbitron,monospace;font-size:9px;letter-spacing:3px;color:#1a3248;text-transform:uppercase;margin:12px 0 8px;padding-bottom:6px;border-bottom:1px solid rgba(0,100,150,0.12)'>&#9672; Transmission Log</div>", unsafe_allow_html=True)
    rows = ""
    for m in messages[-16:]:
        content = m["content"].replace("<","&lt;").replace(">","&gt;")
        if m["role"] == "user":
            rows += f"<div class='msg-anim' style='display:flex;justify-content:flex-end;margin:5px 0'><div style='max-width:80%;background:linear-gradient(135deg,rgba(20,60,120,0.75),rgba(10,30,65,0.65));border:1px solid rgba(50,110,200,0.25);border-radius:16px 16px 3px 16px;padding:9px 14px;font-family:Exo 2,sans-serif;font-size:clamp(12px,3vw,14px);color:#8bbfe0;line-height:1.5'>{content}</div></div>"
        else:
            rows += f"<div class='msg-anim' style='display:flex;justify-content:flex-start;margin:5px 0'><div style='max-width:80%;background:rgba(8,18,32,0.9);border:1px solid rgba(40,90,150,0.2);border-radius:16px 16px 16px 3px;padding:9px 14px;font-family:Exo 2,sans-serif;font-size:clamp(12px,3vw,14px);color:#7aaec8;line-height:1.5'>{content}</div></div>"
    st.markdown(f"<div style='max-height:260px;overflow-y:auto;padding-right:4px'>{rows}</div>", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for k,v in [("messages",[]),("memory",load_memory()),("last_audio_id",None),("total",0),
             ("orb_state","idle"),("orb_status","Speak to OPTIMUZ below ↓"),("orb_transcript","")]:
    if k not in st.session_state: st.session_state[k]=v

if not GROQ_API_KEY:
    st.error("Add GROQ_API_KEY to your .env file! Get it free at https://console.groq.com")
    st.stop()

# ── Single Orb (updates in place) ────────────────────────────────────────────
orb_slot = st.empty()

def update_orb(state, status="", transcript=""):
    st.session_state.orb_state      = state
    st.session_state.orb_status     = status
    st.session_state.orb_transcript = transcript
    orb_slot.markdown(build_orb_html(
        state, status, transcript,
        st.session_state.get("memory",{}).get("name","")
    ), unsafe_allow_html=True)

update_orb(st.session_state.orb_state, st.session_state.orb_status, st.session_state.orb_transcript)

# ── Hide the default audio widget UI, show only mic button ────────────────────
st.markdown("""
<style>
div[data-testid="stAudioInput"] > div:first-child { display:none!important }
div[data-testid="stAudioInput"] { background:transparent!important; border:none!important; padding:0!important; box-shadow:none!important; }
div[data-testid="stAudioInput"] button {
    width:72px!important; height:72px!important; border-radius:50%!important;
    background:linear-gradient(135deg,rgba(20,50,110,0.9),rgba(10,30,70,0.95))!important;
    border:2px solid rgba(60,120,220,0.5)!important;
    box-shadow:0 0 25px rgba(0,80,200,0.3), inset 0 1px 0 rgba(255,255,255,0.05)!important;
    display:flex!important; align-items:center!important; justify-content:center!important;
    margin:0 auto!important; cursor:pointer!important; transition:all .3s!important;
}
div[data-testid="stAudioInput"] button:hover {
    box-shadow:0 0 40px rgba(0,120,255,0.5)!important;
    border-color:rgba(80,160,255,0.7)!important;
}
div[data-testid="stAudioInput"] button svg { width:28px!important; height:28px!important; color:#4da6ff!important; }
div[data-testid="stAudioInput"] audio { display:none!important; }
</style>
<div style="text-align:center;margin:8px 0 4px;font-family:Orbitron,monospace;font-size:9px;letter-spacing:3px;color:#1a3248">
  &#9672; TAP TO SPEAK
</div>
""", unsafe_allow_html=True)

# Center the mic button
col1, col2, col3 = st.columns([1,1,1])
with col2:
    audio_value = st.audio_input("", key="mic_input", label_visibility="collapsed")

st.markdown("""
<div style="text-align:center;margin-top:6px;font-family:Rajdhani,sans-serif;font-size:12px;color:#1a3248;letter-spacing:1px">
  Hold to record &middot; release to send
</div>
""", unsafe_allow_html=True)

# ── Process audio ──────────────────────────────────────────────────────────────
if audio_value is not None:
    audio_id = id(audio_value)
    if audio_id != st.session_state.last_audio_id:
        st.session_state.last_audio_id = audio_id
        audio_bytes = audio_value.read()

        if len(audio_bytes) > 800:
            update_orb("thinking","Transcribing your voice...")
            try:
                transcript = transcribe_audio(audio_bytes)
            except Exception as e:
                update_orb("idle","Error. Try again."); st.stop()

            if not transcript or len(transcript.strip()) < 2:
                update_orb("idle","Couldn't hear that. Try again.")
                st.stop()

            wake, clean = check_wake_word(transcript)
            if wake and not clean.strip():
                update_orb("wake","Wake word heard! Speak your message...")
                st.stop()

            final = clean if wake else transcript
            emotion = detect_emotion(final)
            memory  = update_memory(final, emotion)
            st.session_state.memory = memory

            update_orb("listening","Got it!", final)
            st.session_state.messages.append({"role":"user","content":final})
            append_history("user", final, emotion)

            update_orb("thinking","OPTIMUZ is thinking...")
            try:
                reply = ask_groq(final, memory, emotion)
            except Exception as e:
                update_orb("idle","AI error. Try again."); st.stop()

            st.session_state.messages.append({"role":"assistant","content":reply})
            append_history("assistant", reply)
            st.session_state.total += 1

            update_orb("speaking", reply[:70]+"..." if len(reply)>70 else reply)
            try:
                audio_out = speak(reply)
                st.audio(base64.b64decode(audio_out), format="audio/mp3", autoplay=True)
            except Exception as e:
                st.write(f"**OPTIMUZ:** {reply}")

            update_orb("idle","Tap the mic and speak!")

# ── Chat log ──────────────────────────────────────────────────────────────────
render_chat(st.session_state.messages)

# ── Footer ────────────────────────────────────────────────────────────────────
name = st.session_state.memory.get("name","")
name_bit = f"&middot; {name.upper()} " if name else ""
st.markdown(f"<div style='text-align:center;font-family:Orbitron,monospace;font-size:7px;letter-spacing:2px;color:#0e1f30;text-transform:uppercase;margin-top:10px;padding-bottom:6px'>OPTIMUZ v2 {name_bit}&middot; GROQ &middot; LLAMA 3.3 &middot; EDGE TTS &middot; {st.session_state.total} TRANSMISSIONS</div>", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🤖 OPTIMUZ Memory")
    m = load_memory()
    if m.get("name"): st.success(f"Name: **{m['name']}**")
    if m.get("last_seen"): st.caption(f"Last seen: {m['last_seen'][:10]}")
    if m.get("facts"):
        st.markdown("**Known facts:**")
        for f in m["facts"][-8:]: st.caption(f"• {f[:80]}")
    if m.get("mood_history"):
        moods = [x["emotion"] for x in m["mood_history"][-5:]]
        st.caption(f"Moods: {' → '.join(moods)}")
    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    st.caption(f"Voice: {EDGE_VOICE}")
    st.caption("Model: llama-3.3-70b-versatile")
    st.caption("STT: Groq Whisper Large v3 Turbo")
    st.markdown("---")
    st.markdown("**Wake words:**")
    st.caption("Hey / Hi / OK / Hello Optimuz")
    st.markdown("**Voice options (.env):**")
    st.caption("en-US-ChristopherNeural\nen-US-GuyNeural\nen-GB-RyanNeural\nen-US-DavisNeural")
    st.markdown("---")
    c1,c2 = st.columns(2)
    with c1:
        if st.button("🗑 Memory",use_container_width=True):
            save_memory({"facts":[],"name":None,"last_seen":None,"mood_history":[]})
            st.session_state.memory = load_memory()
            st.rerun()
    with c2:
        if st.button("🗑 History",use_container_width=True):
            if HISTORY_FILE.exists(): HISTORY_FILE.unlink()
            st.session_state.messages = []
            st.rerun()