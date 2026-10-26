from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import tempfile
import uuid
import re

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "kdrama_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE = 100 * 1024 * 1024

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
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
            "video_editing_ready": False
        })

    def do_POST(self):
        if self.path != "/upload":
            self.send_json(404, {"error": "Endpoint not found"})
            return

        content_type = self.headers.get("Content-Type", "")
        match = re.search(r'boundary="?([^";]+)', content_type)

        if "multipart/form-data" not in content_type or not match:
            self.send_json(400, {"error": "Invalid multipart upload"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        if length <= 0 or length > 2 * MAX_FILE_SIZE:
            self.send_json(413, {"error": "Invalid upload size"})
            return

        body = self.rfile.read(length)
        boundary = b"--" + match.group(1).encode()
        parts = body.split(boundary)
        saved = {}

        for part in parts:
            part = part.strip(b"\r\n-")
            if b"\r\n\r\n" not in part:
                continue

            header, data = part.split(b"\r\n\r\n", 1)
            data = data.rstrip(b"\r\n")
            header_text = header.decode("utf-8", errors="ignore")

            field_match = re.search(
                r'name="(video|voice)"', header_text
            )
            file_match = re.search(
                r'filename="([^"]*)"', header_text
            )

            if not field_match or not file_match:
                continue

            field = field_match.group(1)
            original_name = os.path.basename(file_match.group(1))
            ext = os.path.splitext(original_name)[1].lower()

            allowed = {
                "video": {".mp4", ".mov", ".mkv", ".webm"},
                "voice": {".mp3", ".wav", ".m4a", ".ogg"}
            }

            if ext not in allowed[field]:
                self.send_json(400, {
                    "error": f"Unsupported {field} file type"
                })
                return

            if len(data) > MAX_FILE_SIZE:
                self.send_json(413, {"error": "File too large"})
                return

            filename = f"{uuid.uuid4().hex}_{field}{ext}"
            filepath = os.path.join(UPLOAD_DIR, filename)

            with open(filepath, "wb") as f:
                f.write(data)

            saved[field] = {
                "filename": filename,
                "size_bytes": len(data)
            }

        if "video" not in saved or "voice" not in saved:
            self.send_json(400, {
                "error": "Both video and voice files are required"
            })
            return

        self.send_json(200, {
            "success": True,
            "message": "Files uploaded to temporary storage",
            "files": saved,
            "video_editing_ready": False
        })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"K-Drama AI Agent running on port {port}")
    server.serve_forever()
