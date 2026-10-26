from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import subprocess
import tempfile
import uuid
from urllib.parse import unquote
import imageio_ffmpeg

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "kdrama_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE = 100 * 1024 * 1024
MAX_REQUEST_SIZE = 2 * MAX_FILE_SIZE + 1024 * 1024
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


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
        if self.path == "/":
            self.send_json(200, {
                "name": "K-Drama AI Agent",
                "status": "Backend running",
                "upload_endpoint": "/upload",
                "video_editing_ready": True
            })
            return

        match = re.fullmatch(r"/download/([a-f0-9]{32})", self.path)
        if match:
            job_id = match.group(1)
            filepath = os.path.join(UPLOAD_DIR, job_id + ".mp4")

            if not os.path.isfile(filepath):
                self.send_json(404, {
                    "error": "ভিডিও পাওয়া যায়নি। আবার তৈরি করে দেখো।"
                })
                return

            try:
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header(
                    "Content-Disposition",
                    'attachment; filename="kdrama_explainer.mp4"'
                )
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(os.path.getsize(filepath)))
                self.end_headers()

                with open(filepath, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        self.send_json(404, {"error": "Endpoint not found"})

    def do_POST(self):
        if self.path != "/upload":
            self.send_json(404, {"error": "Endpoint not found"})
            return

        content_type = self.headers.get("Content-Type", "")
        boundary_match = re.search(
            r'boundary=(?:"([^"]+)"|([^;]+))', content_type
        )

        if "multipart/form-data" not in content_type or not boundary_match:
            self.send_json(400, {"error": "Invalid multipart upload"})
            return

        boundary_text = (boundary_match.group(1) or boundary_match.group(2)).strip()
        boundary = b"--" + boundary_text.encode("ascii", errors="strict")

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        if length <= 0 or length > MAX_REQUEST_SIZE:
            self.send_json(413, {"error": "Upload too large"})
            return

        body = self.rfile.read(length)
        saved_paths = {}

        try:
            for part in body.split(boundary)[1:]:
                if part.startswith(b"--"):
                    break
                if part.startswith(b"\r\n"):
                    part = part[2:]
                if part.endswith(b"\r\n"):
                    part = part[:-2]

                if b"\r\n\r\n" not in part:
                    continue

                headers, data = part.split(b"\r\n\r\n", 1)
                headers_text = headers.decode("utf-8", errors="replace")

                name_match = re.search(r'name="(video|voice)"', headers_text)
                filename_match = re.search(
                    r'filename="([^"]*)"', headers_text
                )

                if not name_match or not filename_match:
                    continue

                field = name_match.group(1)
                original_name = os.path.basename(filename_match.group(1))
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
                    self.send_json(413, {"error": f"{field} file is too large"})
                    return

                filename = uuid.uuid4().hex + "_" + field + ext
                filepath = os.path.join(UPLOAD_DIR, filename)

                with open(filepath, "wb") as f:
                    f.write(data)

                saved_paths[field] = filepath

            if "video" not in saved_paths or "voice" not in saved_paths:
                self.send_json(400, {
                    "error": "ভিডিও এবং ভয়েস—দুটিই আপলোড করতে হবে।"
                })
                return

            job_id = uuid.uuid4().hex
            output_path = os.path.join(UPLOAD_DIR, job_id + ".mp4")

            command = [
                FFMPEG, "-y",
                "-stream_loop", "-1",
                "-i", saved_paths["video"],
                "-i", saved_paths["voice"],
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "28",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                "-shortest",
                "-movflags", "+faststart",
                output_path
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode != 0 or not os.path.isfile(output_path):
                error_text = (result.stderr or "FFmpeg failed")[-1500:]
                self.send_json(500, {
                    "error": "ভিডিও তৈরি করা যায়নি।",
                    "details": error_text
                })
                return

            self.send_json(200, {
                "success": True,
                "message": "ভিডিও তৈরি হয়েছে!",
                "download_url": "/download/" + job_id,
                "video_editing_ready": True
            })

        except subprocess.TimeoutExpired:
            self.send_json(504, {
                "error": "ভিডিও তৈরিতে বেশি সময় লাগছে। ছোট ফাইল দিয়ে পরীক্ষা করো।"
            })
        except Exception as exc:
            self.send_json(500, {
                "error": "সার্ভারে সমস্যা হয়েছে।",
                "details": str(exc)[:1000]
            })

    def log_message(self, format, *args):
        print(format % args)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"K-Drama AI Agent running on port {port}")
    server.serve_forever()
