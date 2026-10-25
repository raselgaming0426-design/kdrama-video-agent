from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = {
            "name": "K-Drama AI Agent",
            "status": "Backend test successful",
            "features": [
                "Bangla script generation",
                "Female Bangla AI voice",
                "Video editing",
                "MP4 export"
            ],
            "ready": False,
            "message": "AI processing is not configured yet."
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            json.dumps(data, ensure_ascii=False).encode("utf-8")
        )

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8000), Handler)
    print("K-Drama AI Agent backend started on port 8000")
    server.serve_forever()
