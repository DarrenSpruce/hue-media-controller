"""Mock Home Assistant, just enough to exercise webapp/index.html locally.

Serves the app at /local/remote.html (same path shape as real HA) plus the two
API endpoints the app uses. Any token is accepted except the literal "bad".
"""
import json, pathlib, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

APP = str(pathlib.Path(__file__).with_name("index.html"))
state = {"mode": "Off", "tv": "off", "calls": []}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _auth_ok(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth == "Bearer bad":
            self._send(401, '{"message":"Unauthorized"}')
            return False
        return True

    def do_GET(self):
        if self.path.startswith("/local/"):
            return self._send(200, open(APP).read(), "text/html")
        if self.path.startswith("/api/states/"):
            if not self._auth_ok():
                return
            entity = self.path.rsplit("/", 1)[1]
            if entity == "input_select.media_system_mode":
                return self._send(200, json.dumps({"entity_id": entity, "state": state["mode"]}))
            return self._send(200, json.dumps({"entity_id": entity, "state": state["tv"]}))
        self._send(404, '{"message":"Not found"}')

    def do_POST(self):
        if not self.path.startswith("/api/services/script/"):
            return self._send(404, '{"message":"Not found"}')
        if not self._auth_ok():
            return
        name = self.path.rsplit("/", 1)[1]
        state["calls"].append(name)
        if name == "activate_audio_mode":
            state["mode"] = "Audio"
        elif name == "activate_cinema_mode":
            state["mode"], state["tv"] = "Cinema", "playing"
        elif name == "media_system_off":
            state["mode"], state["tv"] = "Off", "off"
        elif name == "toggle_tv":
            state["tv"] = "off" if state["tv"] != "off" else "playing"
        print(f"  → script.{name}   [mode={state['mode']} tv={state['tv']}]", flush=True)
        self._send(200, "[]")

    def log_message(self, *a):
        pass


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
print(f"mock HA on http://localhost:{port}/local/remote.html", flush=True)
HTTPServer(("127.0.0.1", port), H).serve_forever()
