"""Read-only local viewer for Site Safety Watch.

Serves the static console, proxies GET requests to the event API and exposes only evidence
files that resolve inside the configured frames root.
"""

import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
STATIC_ROOT = HERE / "static"
EVENT_ID_RE = re.compile(r"^[0-9]{1,18}$")
BUFFER_SIZE = 64 * 1024


def _resolved_env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _api_base() -> str:
    return os.environ.get("SSW_API_URL", "http://127.0.0.1:8100").rstrip("/")


def _scene_base() -> str:
    return os.environ.get("SCENE_URL", "http://127.0.0.1:8300").rstrip("/")


def _twin_base() -> str:
    return os.environ.get("TWIN_URL", "http://127.0.0.1:8400").rstrip("/")


class Handler(BaseHTTPRequestHandler):
    server_version = "ssw-viewer/1"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.log_date_time_string()} {self.address_string()} {fmt % args}\n")

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path == "/numbers":
            self._serve_numbers()
        elif path == "/clip":
            self._serve_clip()
        elif path == "/room.glb":
            self._serve_room_scan()
        elif path.startswith("/frames/"):
            self._serve_frame(path.removeprefix("/frames/"))
        elif path == "/scene3d" or path.startswith("/scene3d/"):
            suffix = path.removeprefix("/scene3d") or "/"
            if ".." in suffix.split("/"):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if parsed.query:
                suffix += "?" + parsed.query
            self._proxy(_scene_base(), suffix, "scene service unavailable")
        elif path.startswith("/twin/"):
            if ".." in path.split("/"):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            target = quote(path, safe="/") + ("?" + parsed.query if parsed.query else "")
            self._proxy(_twin_base(), target, "twin service unavailable")
        elif path == "/api" or path.startswith("/api/"):
            suffix = path.removeprefix("/api") or "/"
            if parsed.query:
                suffix += "?" + parsed.query
            self._proxy(_api_base(), suffix, "event api unavailable")
        else:
            self._serve_static(path)

    def do_HEAD(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/clip":
            self._serve_clip(head_only=True)
        else:
            self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def _headers(self, status: int, content_type: str, length: int | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; media-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' blob:; frame-ancestors 'self'")
        if length is not None:
            self.send_header("Content-Length", str(length))

    def _send_bytes(self, status: int, body: bytes, content_type: str):
        self._headers(status, content_type, len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_json_error(self, status: int, message: str):
        self._send_bytes(status, json.dumps({"error": message}).encode(), "application/json")

    def _serve_static(self, raw_path: str):
        relative = "index.html" if raw_path in ("", "/") else raw_path.lstrip("/")
        candidate = (STATIC_ROOT / relative).resolve()
        if not _inside(candidate, STATIC_ROOT) or not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self._serve_file(candidate, mime)

    def _proxy(self, base_url: str, suffix: str, unavailable_message: str):
        request = urllib.request.Request(base_url + suffix, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read()
                content_type = response.headers.get_content_type() or "application/json"
                self._send_bytes(response.status, body, content_type)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            content_type = exc.headers.get_content_type() if exc.headers else "application/json"
            self._send_bytes(exc.code, body, content_type)
        except (urllib.error.URLError, TimeoutError, OSError):
            self._send_json_error(HTTPStatus.BAD_GATEWAY, unavailable_message)

    def _event(self, event_id: str) -> dict | None:
        request = urllib.request.Request(f"{_api_base()}/events/{quote(event_id)}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.load(response)
                return data if isinstance(data, dict) else None
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError,
                json.JSONDecodeError):
            return None

    def _serve_frame(self, event_id: str):
        if not EVENT_ID_RE.fullmatch(event_id):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        event = self._event(event_id)
        frame_path = event.get("frame_path") if event else None
        if not isinstance(frame_path, str) or not frame_path:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        root = _resolved_env_path("SSW_FRAMES_ROOT", REPO_ROOT)
        candidate = Path(frame_path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve()
        if not _inside(candidate, root) or not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if not mime.startswith("image/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._serve_file(candidate, mime)

    def _serve_numbers(self):
        numbers_path = REPO_ROOT / "story" / "numbers.json"
        if not numbers_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = numbers_path.read_bytes()
            parsed = json.loads(body)
            if not isinstance(parsed, dict):
                raise ValueError
        except (OSError, ValueError, json.JSONDecodeError):
            self._send_json_error(HTTPStatus.INTERNAL_SERVER_ERROR, "numbers unavailable")
            return
        self._send_bytes(HTTPStatus.OK, body, "application/json")

    def _serve_clip(self, head_only: bool = False):
        configured = os.environ.get("SSW_DEMO_CLIP")
        if not configured:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        clip = Path(configured).expanduser().resolve()
        if not clip.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        size = clip.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = int(last) if last else end
            elif last:
                length = int(last)
                start = max(0, size - length)
            if start >= size or end < start:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            end = min(end, size - 1)
            status = HTTPStatus.PARTIAL_CONTENT
        length = max(0, end - start + 1)
        self._headers(status, mimetypes.guess_type(clip.name)[0] or "video/mp4", length)
        self.send_header("Accept-Ranges", "bytes")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head_only:
            return
        with clip.open("rb") as source:
            source.seek(start)
            remaining = length
            while remaining:
                chunk = source.read(min(BUFFER_SIZE, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _serve_room_scan(self):
        configured = os.environ.get("TWIN_ROOM_GLB")
        if not configured:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        scan = Path(configured).expanduser().resolve()
        if not scan.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            source = scan.open("rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        with source:
            self._headers(HTTPStatus.OK, "model/gltf-binary", scan.stat().st_size)
            self.end_headers()
            while chunk := source.read(BUFFER_SIZE):
                self.wfile.write(chunk)

    def _serve_file(self, path: Path, content_type: str):
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send_bytes(HTTPStatus.OK, body, content_type)


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main():
    host = os.environ.get("VIEWER_HOST", "127.0.0.1")
    port = int(os.environ.get("VIEWER_PORT", "8200"))
    server = make_server(host, port)
    sys.stderr.write(f"ssw-viewer listening on {host}:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
