"""
receiver.py - Recibe frames del sender y los sirve como stream

Endpoints:
  POST /upload     — recibe frame base64 del sender
  GET  /snapshot   — ultimo frame como JPEG (para JS polling)
  GET  /           — viewer HTML con auto-refresh
  GET  /status     — estado JSON
  POST /reset      — reinicia sesion
"""

import os
import time
import hashlib
import base64
import io
from datetime import datetime

from flask import Flask, request, jsonify, Response

app = Flask(__name__)

start_time = time.time()
latest_jpeg: dict = {'data': None, 'ts': 0.0}

class Session:
    def __init__(self):
        self.id = hashlib.md5(str(time.time()).encode()).hexdigest()[:16]
        self.frame_count = 0
        self.last_frame_time = time.time()

    def process(self, b64_data: str) -> bool:
        try:
            raw = base64.b64decode(b64_data)
            latest_jpeg['data'] = raw
            latest_jpeg['ts']   = time.time()
            self.frame_count   += 1
            self.last_frame_time = time.time()
            return True
        except Exception:
            return False

session = Session()


@app.route('/upload', methods=['POST'])
def upload():
    data = request.get_json(silent=True) or {}
    if 'image' not in data:
        return jsonify({'status': 'error', 'detail': 'missing image'}), 400
    if session.process(data['image']):
        return jsonify({'status': 'ok', 'frame_count': session.frame_count}), 200
    return jsonify({'status': 'error', 'detail': 'decode failed'}), 400


@app.route('/snapshot')
def snapshot():
    """Ultimo frame como JPEG. El browser lo refresca via JS."""
    jpeg = latest_jpeg['data']
    if jpeg is None:
        # Imagen placeholder mientras no hay frames
        placeholder = _placeholder_jpeg()
        return Response(placeholder, mimetype='image/jpeg')
    return Response(jpeg, mimetype='image/jpeg')


@app.route('/status')
def status():
    return jsonify({
        'status': 'running',
        'session_id': session.id,
        'frame_count': session.frame_count,
        'last_frame_ago': round(time.time() - session.last_frame_time, 1),
        'uptime': round(time.time() - start_time, 1),
    })


@app.route('/reset', methods=['POST'])
def reset():
    global session
    session = Session()
    latest_jpeg['data'] = None
    latest_jpeg['ts']   = 0.0
    return jsonify({'status': 'reset', 'new_session': session.id})


@app.route('/')
def index():
    return """<!doctype html>
<html>
<head>
  <title>Screen Receiver</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #0d0d0d; color: #ddd; font-family: monospace; }
    #bar { display: flex; gap: 16px; align-items: center; padding: 10px 16px;
           background: #1a1a1a; border-bottom: 1px solid #333; font-size: 13px; }
    #bar span { color: #888; }
    #bar b { color: #eee; }
    #screen { display: block; width: 100%; height: calc(100vh - 42px);
              object-fit: contain; background: #000; }
  </style>
</head>
<body>
  <div id="bar">
    <span>frames: <b id="fc">-</b></span>
    <span>ultimo: <b id="ago">-</b>s</span>
    <span>fps: <b id="fps">-</b></span>
    <span style="margin-left:auto;color:#555" id="sid">-</span>
  </div>
  <img id="screen" src="/snapshot" alt="stream">

  <script>
    const img = document.getElementById('screen');
    let last = Date.now(), frameCount = 0, prevCount = 0;

    function refresh() {
      // Forzar recarga de /snapshot agregando timestamp para evitar cache
      img.src = '/snapshot?' + Date.now();
    }

    img.onload = function() {
      frameCount++;
      refresh(); // pedir el siguiente frame apenas carga el actual
    };

    img.onerror = function() {
      setTimeout(refresh, 500); // reintentar si hay error
    };

    // Actualizar barra de estado cada segundo
    setInterval(async () => {
      try {
        const r = await fetch('/status');
        const s = await r.json();
        document.getElementById('fc').textContent  = s.frame_count;
        document.getElementById('ago').textContent = s.last_frame_ago;
        document.getElementById('sid').textContent = s.session_id;
        const fps = s.frame_count - prevCount;
        document.getElementById('fps').textContent = fps;
        prevCount = s.frame_count;
      } catch(e) {}
    }, 1000);

    refresh(); // arrancar
  </script>
</body>
</html>"""


def _placeholder_jpeg() -> bytes:
    """JPEG negro minimo para cuando no hay frames todavia."""
    try:
        from PIL import Image
        import io
        img = Image.new('RGB', (640, 360), color=(10, 10, 10))
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=50)
        return buf.getvalue()
    except Exception:
        # JPEG minimo hardcodeado como fallback
        return (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
            b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1eB'
            b'\xed\xa0!\x02\xff\xd9'
        )


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    print(f"[receiver] http://0.0.0.0:{port}")
    print(f"[receiver] viewer: http://localhost:{port}/")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
