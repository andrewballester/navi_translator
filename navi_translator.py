#!/usr/bin/env python3.12
"""Na'vi language translator — local web UI, no extra dependencies."""

import getpass
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import anthropic


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    print("\nANTHROPIC_API_KEY is not set in your environment.")
    print("Paste your key now (input is hidden) or set the env var and restart.\n")
    key = getpass.getpass("ANTHROPIC_API_KEY: ").strip()
    if not key:
        raise SystemExit("No API key provided — exiting.")
    os.environ["ANTHROPIC_API_KEY"] = key  # available to the anthropic client
    return key

PORT = 7777

SYSTEM_PROMPT = """\
You are an expert Na'vi language translator. Na'vi is the constructed language \
spoken by the Na'vi people of Pandora in James Cameron's Avatar, created by \
linguist Paul Frommer. You have deep knowledge of the Na'vi dictionary and grammar.

STEP 1 — DETECT LANGUAGE
First decide: is the input Na'vi or English?
Na'vi indicators: known Na'vi roots/words, Na'vi case suffixes (-ìl, -it, -ti, \
-ä, -yä, -ru, -ur, -ri, -r), Na'vi tense/aspect infixes (<ul>, <iv>, <us>, \
<awn>), or words from the Na'vi lexicon. When in doubt about a single unfamiliar \
word, treat it as Na'vi and look it up — do NOT guess that it is English.

Core Na'vi vocabulary reference (non-exhaustive):
  kaltxì=hello, irayo=thank you, mawey=be calm/peaceful, sìlpey=hope,
  oel=I (agent), ngati=you (patient), kameie=see (spiritual), tìftia=learning,
  txon=night, eywa=Eywa (deity), na'vi=the people, tsaheylu=bond,
  skxawng=moron, nìprrte=gladly/with pleasure, srane=yes, kehe=no,
  ftang=stop, tìng mikyun=listen, zola'u=come, tìran=walk, plltxe=speak,
  nìmwey=calmly, txo=if, nìngay=truly, ulte=and, fte=so that, fkol=one/they

STEP 2 — RESPOND
If input is ENGLISH → translate to Na'vi.
If input is NA'VI   → translate to English.

Format every response exactly like this:

**Na'vi:** [Na'vi text]  OR  **English:** [English text]
**Pronunciation:** [phonetic guide, syllable-stressed, e.g. ma-WEY]
**Key words:** [gloss of the most important words]

Accuracy matters more than completeness. If you are uncertain about a word, \
say so rather than inventing vocabulary.
"""

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Na'vi Translator — Pandora</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "Segoe UI", sans-serif;
    background: #070f1d;
    color: #c4e4f5;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  header {
    background: #0b1d35;
    padding: 14px 20px;
    border-bottom: 1px solid #1a3050;
    text-align: center;
  }
  header h1 { font-size: 1.2rem; color: #7dd8f8; font-weight: 600; }
  header p  { font-size: 0.82rem; color: #3d9c6c; margin-top: 3px; }

  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    background: #1a3a56;
  }

  .bubble { max-width: 80%; line-height: 1.55; }
  .bubble.you   { align-self: flex-end; }
  .bubble.bot   { align-self: flex-start; }

  .label {
    font-size: 0.72rem;
    font-weight: 600;
    margin-bottom: 4px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .you .label { color: #7dd8f8; text-align: right; }
  .bot .label { color: #3dbe7e; }

  .text {
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 0.93rem;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .you .text { background: #2d6090; color: #e8f4ff; border-bottom-right-radius: 3px; }
  .bot .text { background: #1e5080; color: #d0eaff;  border-bottom-left-radius: 3px; }
  .bot .text strong { color: #7dd8f8; }

  .thinking .text { color: #4a7a6a; font-style: italic; }

  footer {
    background: #0b1d35;
    border-top: 1px solid #1a3050;
    padding: 12px 16px;
    display: flex;
    gap: 10px;
    align-items: flex-end;
  }
  textarea {
    flex: 1;
    background: #122438;
    color: #c4e4f5;
    border: 1px solid #1e3d5a;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 0.93rem;
    font-family: inherit;
    resize: none;
    outline: none;
    min-height: 46px;
    max-height: 140px;
    line-height: 1.45;
  }
  textarea:focus { border-color: #3d7aaa; }
  button {
    background: #1a6e48;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-size: 0.88rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    height: 46px;
  }
  button:hover   { background: #22925f; }
  button:disabled { background: #1a3a28; color: #4a7a5a; cursor: default; }

  .replay-btn {
    background: none;
    border: 1px solid #1e4a60;
    border-radius: 6px;
    color: #4a8a7a;
    cursor: pointer;
    font-size: 0.78rem;
    height: auto;
    margin-top: 6px;
    padding: 3px 9px;
    width: auto;
    display: inline-block;
    align-self: flex-start;
  }
  .replay-btn:hover { background: #0d2a3a; border-color: #3dbe7e; color: #3dbe7e; }

  #mic {
    background: #1a3a5a;
    color: #7dd8f8;
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 1rem;
    cursor: pointer;
    height: 46px;
    flex-shrink: 0;
  }
  #mic:hover   { background: #224a70; }
  #mic:disabled { background: #122030; color: #2a4a6a; cursor: default; }
  #mic.listening {
    background: #5a1a1a;
    color: #ff7070;
    animation: mic-pulse 1s ease-in-out infinite;
  }
  @keyframes mic-pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.55; }
  }

  #status {
    text-align: center;
    font-size: 0.75rem;
    color: #2a5060;
    padding: 4px 0 2px;
    background: #050c18;
  }

  /* markdown-light: bold */
  .bot .text b, .bot .text strong { font-weight: 700; color: #7dd8f8; }
</style>
</head>
<body>
<header>
  <h1>&#127807; Na&apos;vi Language Translator &#127807;</h1>
  <p>Kaltx&igrave;! Type English (or Na&apos;vi) and press Enter to translate.</p>
</header>

<div id="chat"></div>

<div id="status">Oel ngati kameie &nbsp;&#8226;&nbsp; I see you &nbsp;&#8226;&nbsp; Ready</div>

<footer>
  <textarea id="input" rows="1" placeholder="Type a phrase..." autofocus></textarea>
  <button id="mic" title="Speak">🎤</button>
  <button id="send">Translate</button>
</footer>

<script>
const chat   = document.getElementById('chat');
const input  = document.getElementById('input');
const send   = document.getElementById('send');
const mic    = document.getElementById('mic');
const status = document.getElementById('status');

// ── Speech recognition ────────────────────────────────────────────────────
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SR) {
  mic.disabled = true;
  mic.title = 'Speech input requires Chrome or Edge';
} else {
  const recognition = new SR();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  let listening = false;

  mic.addEventListener('click', () => {
    if (listening) { recognition.stop(); return; }
    recognition.start();
  });

  recognition.addEventListener('start', () => {
    listening = true;
    mic.classList.add('listening');
    mic.textContent = '⏹';
    status.textContent = 'Listening…';
  });

  recognition.addEventListener('result', e => {
    const transcript = e.results[0][0].transcript.trim();
    input.value = transcript;
    input.dispatchEvent(new Event('input')); // trigger auto-grow
    doSend();
  });

  recognition.addEventListener('end', () => {
    listening = false;
    mic.classList.remove('listening');
    mic.textContent = '🎤';
  });

  recognition.addEventListener('error', e => {
    listening = false;
    mic.classList.remove('listening');
    mic.textContent = '🎤';
    if (e.error !== 'no-speech') status.textContent = '⚠ Mic error: ' + e.error;
  });
}
// ─────────────────────────────────────────────────────────────────────────

// auto-grow textarea
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 140) + 'px';
});

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); }
});
send.addEventListener('click', doSend);

function addBubble(role, text, id) {
  const wrap = document.createElement('div');
  wrap.className = `bubble ${role}`;
  if (id) wrap.id = id;

  const lbl = document.createElement('div');
  lbl.className = 'label';
  lbl.textContent = role === 'you' ? 'You' : '🌿 Translator';
  wrap.appendChild(lbl);

  const txt = document.createElement('div');
  txt.className = 'text';
  txt.textContent = text;
  wrap.appendChild(txt);

  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return txt;
}

function renderMarkdown(el, raw) {
  // minimal: **bold**
  el.innerHTML = raw
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

// Welcome message
addBubble('bot',
  "Kaltxi! (Hello!)\n\n" +
  "Type any English phrase and I will translate it into Na'vi.\n" +
  "You can also type Na'vi and I'll translate it to English.\n\n" +
  'Try: "I see you"  •  "The forest is beautiful"  •  "Oel ngati kameie"'
);

// ── Text-to-speech helpers ────────────────────────────────────────────────
let _voices = [];
function loadVoices() { _voices = speechSynthesis.getVoices(); }
loadVoices();
if (speechSynthesis.onvoiceschanged !== undefined) {
  speechSynthesis.addEventListener('voiceschanged', loadVoices);
}

function pickFemaleVoice() {
  const voices = _voices.length ? _voices : speechSynthesis.getVoices();
  // explicit "female" label (Chrome remote voices)
  let v = voices.find(v => v.name.toLowerCase().includes('female') && v.lang.startsWith('en'));
  if (v) return v;
  // well-known female system voices
  const femaleNames = ['Samantha', 'Victoria', 'Karen', 'Moira', 'Tessa',
                       'Zira', 'Hazel', 'Susan', 'Ava', 'Allison'];
  v = voices.find(v => femaleNames.some(n => v.name.includes(n)));
  if (v) return v;
  // fallback: any English voice
  return voices.find(v => v.lang.startsWith('en')) || voices[0] || null;
}

function speakNavi(reply, userText) {
  if (!window.speechSynthesis) return;
  const naviMatch = reply.match(/\*\*Na'vi:\*\*\s*([^\n]+)/);
  const phrase = naviMatch ? naviMatch[1].trim() : userText;
  if (!phrase) return;
  speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(phrase);
  const voice = pickFemaleVoice();
  if (voice) utter.voice = voice;
  utter.rate  = 0.82;
  utter.pitch = 1.15;
  speechSynthesis.speak(utter);
}
// ─────────────────────────────────────────────────────────────────────────

async function doSend() {
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = '';
  send.disabled = true;
  status.textContent = 'Translating…';

  addBubble('you', text);

  const respId = 'resp-' + Date.now();
  const respEl = addBubble('bot', '⋯', respId);

  try {
    const res = await fetch('/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (data.error) {
      respEl.textContent = '⚠ ' + data.error;
    } else {
      renderMarkdown(respEl, data.reply);
      speakNavi(data.reply, text);

      const replayBtn = document.createElement('button');
      replayBtn.className = 'replay-btn';
      replayBtn.title = "Replay Na'vi pronunciation";
      replayBtn.textContent = '🔊 Replay';
      replayBtn.addEventListener('click', () => speakNavi(data.reply, text));
      document.getElementById(respId).appendChild(replayBtn);
    }
  } catch (err) {
    respEl.textContent = '⚠ ' + err.message;
  }

  chat.scrollTop = chat.scrollHeight;
  send.disabled = false;
  status.textContent = 'Oel ngati kameie • I see you • Ready';
  input.focus();
}
</script>
</body>
</html>
"""

# conversation history shared across requests
_history: list[dict] = []
_client = anthropic.Anthropic(api_key=_get_api_key())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # silence request logs

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.encode())

    def do_POST(self):
        if self.path != "/translate":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        user_text = body.get("text", "").strip()

        _history.append({"role": "user", "content": user_text})

        try:
            response = _client.messages.create(
                model="claude-opus-4-8",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=_history,
            )
            reply = response.content[0].text
            _history.append({"role": "assistant", "content": reply})
            payload = {"reply": reply}
        except Exception as exc:
            _history.pop()  # don't keep the failed user turn
            payload = {"error": str(exc)}

        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    import socket
    local_ip = socket.gethostbyname(socket.gethostname())
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Na'vi Translator running at http://127.0.0.1:{PORT}")
    print(f"On your network:           http://{local_ip}:{PORT}")
    print("Press Ctrl-C to quit.")
    threading.Timer(0.4, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nKiyevame! (Farewell!)")


if __name__ == "__main__":
    main()
