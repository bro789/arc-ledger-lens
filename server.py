"""Loopback-only Arc Ledger Lens development server. No wallet or write RPC routes."""
from __future__ import annotations

import argparse
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from arc_lens import LensError, ReadOnlyRPC, account_evidence, transaction_evidence, verify_evidence

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
WORKERS = threading.BoundedSemaphore(3)


class Handler(BaseHTTPRequestHandler):
    server_version = "ArcLedgerLens/0.1"

    def send(self, status, data, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' https://rpc.mainnet.arc.io; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def json(self, status, data):
        self.send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        if not self.valid_host():
            return self.json(403, {"error": "Only a localhost Host is accepted."})
        route = urlsplit(self.path).path
        if route == "/api/health":
            return self.json(200, {"ok": True, "service": "Arc Ledger Lens", "network": "Arc mainnet", "read_only": True})
        if route in ("/api/demo", "/evidence/demo-bundle.json"):
            try:
                return self.json(200, json.loads((ROOT / "evidence" / "demo-bundle.json").read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                return self.json(404, {"error": "No recorded mainnet evidence yet. Use the live tools or run capture_demo.py."})
        # An explicit asset allowlist avoids path traversal and serves no repo secrets.
        assets = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/rpc.js": "rpc.js", "/style.css": "style.css", "/LICENSE": "LICENSE", "/logo.svg": "logo.svg", "/logo.png": "logo.png"}
        if route not in assets:
            return self.json(404, {"error": "Not found"})
        path = WEB / assets[route]
        self.send(200, path.read_bytes(), (mimetypes.guess_type(str(path))[0] or "application/octet-stream") + "; charset=utf-8")

    def do_POST(self):
        if not self.valid_host():
            return self.json(403, {"error": "Only a localhost Host is accepted."})
        # Require same-origin JSON so websites cannot drive the local RPC bridge.
        expected = f"http://{self.headers.get('Host', '')}"
        origin = self.headers.get("Origin")
        if origin is not None and origin != expected:
            return self.json(403, {"error": "Cross-origin requests are not accepted."})
        if self.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
            return self.json(415, {"error": "Content-Type must be application/json."})
        if not WORKERS.acquire(blocking=False):
            return self.json(429, {"error": "Three read-only audits are already running; retry shortly."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2 * 1024 * 1024:
                return self.json(413, {"error": "Request body must be between 1 byte and 2 MB."})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise LensError("JSON body must be an object.")
            route = urlsplit(self.path).path
            if route == "/api/account":
                if set(body) - {"address", "amount", "gas_limit", "max_fee_gwei"}:
                    raise LensError("Unknown account request field.")
                result = account_evidence(ReadOnlyRPC(), body.get("address", ""), body.get("amount", "1"),
                                          int(body.get("gas_limit", 21000)), body.get("max_fee_gwei") or None)
            elif route == "/api/transaction":
                if set(body) != {"hash"}:
                    raise LensError("Only a transaction hash is accepted.")
                result = transaction_evidence(ReadOnlyRPC(), body["hash"])
            elif route == "/api/verify":
                result = verify_evidence(body)
            else:
                return self.json(404, {"error": "Not found"})
            self.json(200, result)
        except (LensError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.json(400, {"error": str(exc)})
        except Exception:
            self.json(500, {"error": "Audit could not complete. No chain state was changed."})
        finally:
            WORKERS.release()

    def log_message(self, format, *args):
        # Avoid storing entered addresses/hashes or evidence request bodies.
        pass

    def valid_host(self):
        host = self.headers.get("Host", "").lower()
        port = self.server.server_address[1]
        return host in {f"127.0.0.1:{port}", f"localhost:{port}"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8786)
    args = parser.parse_args()
    print(f"Arc Ledger Lens: http://127.0.0.1:{args.port} (loopback only, read-only)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
