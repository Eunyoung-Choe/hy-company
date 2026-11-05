"""4단계 송출: 마스킹된 JPEG만 MJPEG 스트림으로 내보낸다 (127.0.0.1 전용).

GET /stream.mjpg  마스킹 완성본 실시간 스트림
GET /snapshot.jpg 마스킹 완성본 한 장
GET /status       처리 상태(JSON, 개인정보 텍스트 없음)
POST /control?sharing=on|off  원격 켜기/끄기 (허용된 Origin만)
POST /record?action=start|stop 녹화 시작/종료 (허용된 Origin만, 마스킹 완성본만 녹화)
GET /recordings/<파일>.mp4    녹화 파일 다운로드
"""
from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from .recorder import NAME_RE, Recorder
from .workers import LatestJpeg

BOUNDARY = b"frame"


def make_server(host: str, port: int, out: LatestJpeg, status: Callable[[], dict],
                set_sharing: Callable[[bool], None], allowed_origins: list[str],
                recorder: Recorder) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 접근 로그 생략
            pass

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")

        def _origin_ok(self) -> bool:
            # 다른 웹사이트가 브라우저를 통해 원격을 켜고 끄지 못하도록 Origin 확인
            origin = self.headers.get("Origin")
            return origin is None or origin in allowed_origins

        def do_OPTIONS(self):
            origin = self.headers.get("Origin", "")
            if origin not in allowed_origins:
                self.send_error(403)
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, GET")
            self.send_header("Access-Control-Max-Age", "600")
            self.end_headers()

        def do_POST(self):
            path, _, query = self.path.partition("?")
            if path not in ("/control", "/record"):
                self.send_error(404)
                return
            if not self._origin_ok():
                self.send_error(403, "origin not allowed")
                return
            params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            if path == "/control":
                value = params.get("sharing")
                if value not in ("on", "off"):
                    self.send_error(400, "sharing=on|off")
                    return
                set_sharing(value == "on")
            else:
                action = params.get("action")
                if action not in ("start", "stop"):
                    self.send_error(400, "action=start|stop")
                    return
                recorder.start() if action == "start" else recorder.stop()  # stop은 파일 마무리까지 기다림
            body = json.dumps(status()).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/status":
                body = json.dumps(status()).encode()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path.startswith("/recordings/"):
                name = path.rsplit("/", 1)[1]
                f = recorder.out_dir / name
                if not NAME_RE.match(name) or not f.is_file():
                    self.send_error(404)
                    return
                self.send_response(200)
                origin = self.headers.get("Origin")
                if origin in allowed_origins:  # 뷰어가 '다른 이름으로 저장'할 때 fetch로 받는다
                    self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(f.stat().st_size))
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.end_headers()
                with f.open("rb") as fh:
                    while chunk := fh.read(1 << 20):
                        self.wfile.write(chunk)
            elif path == "/snapshot.jpg":
                _, jpg = out.wait(-1, timeout=2.0)
                if jpg is None:
                    self.send_error(503, "no frame yet")
                    return
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpg)))
                self.end_headers()
                self.wfile.write(jpg)
            elif path == "/stream.mjpg":
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY.decode()}")
                self.end_headers()
                n = 0
                try:
                    while True:
                        n, jpg = out.wait(n)
                        if jpg is None:
                            time.sleep(0.05)
                            continue
                        self.wfile.write(b"--" + BOUNDARY + b"\r\nContent-Type: image/jpeg\r\n"
                                         + f"Content-Length: {len(jpg)}\r\n\r\n".encode() + jpg + b"\r\n")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
            else:
                self.send_error(404)

    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv
