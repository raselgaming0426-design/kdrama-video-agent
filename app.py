from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import tempfile
import cgi
import uuid

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "kdrama_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE = 100 * 1024 * 1024

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_json(200, {"ok": True})

    def do_GET(self):
        self.send_json(200, {
            "name": "K-Drama AI Agent",
            "status": "Backend running",
            "upload_endpoint": "/upload",
            "max_file_size_mb": 100,
            "video_editing_ready": False,
            "message": "Upload testing backend. Video editing is not implemented."
        })

    def do_POST(self):
        if self.path != "/upload":
            self.send_json(404, {"error": "Endpoint not found"})
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_json(400, {
                "error": "Send video and voice as multipart/form-data"
            })
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        if length <= 0:
            self.send_json(400, {"error": "No files received"})
            return

        if length > 2 * MAX_FILE_SIZE:
            self.send_json(413, {"error": "Combined upload exceeds limit"})
            return

        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": content_type,
                    "CONTENT_LENGTH": str(length)
                }
            )

            saved = {}

            for field in ("video", "voice"):
                if field not in form:
                    self.send_json(400, {
                        "error": f"Missing {field} file"
                    })
                    return

                item = form[field]
                if isinstance(item, list):
                    item = item[0]

                if not item.filename:
                    self.send_json(400, {
                        "error": f"No {field} filename supplied"
                    })
                    return

                data = item.file.read(MAX_FILE_SIZE + 1)

                if len(data) > MAX_FILE_SIZE:
                    self.send_json(413, {
                        "error": f"{field} file exceeds 100 MB"
                    })
                    return

                ext = os.path.splitext(item.filename)[1].lower()
                if field == "video" and ext not in (
                    ".mp4", ".mov", ".mkv", ".webm"
                ):
                    self.send_json(400, {
                        "error": "Video must be MP4, MOV, MKV, or WEBM"
                    })
                    return

                if field == "voice" and ext not in (
                    ".mp3", ".wav", ".m4a", ".ogg"
                ):
                    self.send_json(400, {
                        "error": "Voice must be MP3, WAV, M4A, or OGG"
                    })
                    return

                filename = f"{uuid.uuid4().hex}_{field}{ext}"
                path = os.path.join(UPLOAD_DIR, filename)

                with open(path, "wb") as output:
                    output.write(data)

                saved[field] = {
                    "filename": filename,
                    "size_bytes": len(data)
                }

            self.send_json(200, {
                "success": True,
                "message": "Files uploaded to temporary server storage.",
                "files": saved,
                "video_editing_ready": False
            })

        except Exception:
            self.send_json(500, {
                "error": "Upload failed. Try smaller files."
            })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"K-Drama AI Agent running on port {port}")
    server.serve_forever()
