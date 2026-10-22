#!/usr/bin/env python3
"""
Tome Vault server - a self-hosted PDF library for your D&D books.

Python 3.8+ only, nothing extra to install. Books are stored in the
"library" folder next to this file. The Tome Vault Android app and any
web browser can connect to it.

Usage:
    python3 server.py                          start the vault (port 8080)
    python3 server.py --port 9000              use another port
    python3 server.py --password KEEPERPASS    set the keeper password, then exit
    python3 server.py --party-password PASS    set the party password, then exit
    python3 server.py --no-party-password      let anyone read without a password
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
_web = os.path.normpath(os.path.join(ROOT, "..", "web"))
STATIC = os.path.join(ROOT, "static") if os.path.isdir(os.path.join(ROOT, "static")) else _web
LIBRARY = os.path.join(ROOT, "library")
CONFIG = os.path.join(ROOT, "config.json")
BOOKS_JSON = os.path.join(LIBRARY, "books.json")
MAX_UPLOAD = 4 * 1024 ** 3  # 4 GB per file
ID_RE = re.compile(r"^[a-f0-9]{16}$")
FILES = {"pdf": ("book.pdf", "application/pdf"),
         "cover": ("cover.jpg", "image/jpeg"),
         "text": ("text.json", "application/json")}
LOCK = threading.Lock()
_pw_cache = {}


# ---------- passwords ----------
def hash_pw(pw, salt):
    key = (pw, salt)
    if key not in _pw_cache:
        if len(_pw_cache) > 256:
            _pw_cache.clear()
        _pw_cache[key] = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return _pw_cache[key]


def load_config():
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def set_secret(prefix, pw):
    cfg = load_config()
    if pw is None:
        cfg.pop(prefix + "salt", None)
        cfg.pop(prefix + "hash", None)
    else:
        salt = secrets.token_hex(16)
        cfg.update({prefix + "salt": salt, prefix + "hash": hash_pw(pw, salt)})
    save_config(cfg)


def check_secret(cfg, prefix, pw):
    if not pw or (prefix + "hash") not in cfg:
        return False
    return hmac.compare_digest(hash_pw(pw, cfg[prefix + "salt"]), cfg[prefix + "hash"])


# ---------- library storage ----------
def load_books():
    if not os.path.exists(BOOKS_JSON):
        return {}
    with open(BOOKS_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_books(books):
    tmp = BOOKS_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(books, f, indent=2)
    os.replace(tmp, BOOKS_JSON)


def book_dir(book_id):
    return os.path.join(LIBRARY, book_id)


def is_ready(book_id):
    d = book_dir(book_id)
    return all(os.path.exists(os.path.join(d, name)) for name, _ in FILES.values())


def touch(book_id):
    with LOCK:
        books = load_books()
        if book_id in books:
            books[book_id]["updatedAt"] = int(time.time() * 1000)
            save_books(books)


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    server_version = "TomeVault/2.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("TOME_VAULT_QUIET"):
            return
        msg = (fmt % args).replace(self.path, self.path.split("?")[0]) if self.path else fmt % args
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), msg))

    # ---- helpers
    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Keeper-Password, X-Party-Password, Content-Type, Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Accept-Ranges, Content-Length")
        self.send_header("Access-Control-Max-Age", "86400")

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def error(self, status, msg):
        self.drain()
        self.send_json({"error": msg}, status)

    def drain(self):
        """Read and discard any unread request body so the connection stays usable."""
        n = int(self.headers.get("Content-Length") or 0)
        if n and not getattr(self, "_body_read", False):
            self._body_read = True
            while n > 0:
                chunk = self.rfile.read(min(65536, n))
                if not chunk:
                    break
                n -= len(chunk)

    def query(self):
        return parse_qs(urlparse(self.path).query)

    def is_keeper(self):
        return check_secret(load_config(), "", self.headers.get("X-Keeper-Password", ""))

    def can_read(self):
        cfg = load_config()
        if "party_hash" not in cfg:
            return True
        pw = self.headers.get("X-Party-Password") or (self.query().get("p") or [""])[0]
        if check_secret(cfg, "party_", pw):
            return True
        return check_secret(cfg, "", self.headers.get("X-Keeper-Password", ""))

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._body_read = True
        if n <= 0 or n > 2_000_000:
            if n > 0:
                self._body_read = False
                self.drain()
            return None
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return None

    def route(self):
        return [p for p in unquote(urlparse(self.path).path).split("/") if p]

    # ---- CORS preflight
    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- reads
    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        parts = self.route()
        if parts == ["api", "info"]:
            cfg = load_config()
            return self.send_json({"name": "Tome Vault", "version": 2, "partyRequired": "party_hash" in cfg})
        if parts == ["api", "check"]:
            ok = self.is_keeper()
            return self.send_json({"ok": ok}, 200 if ok else 401)
        if parts == ["api", "books"]:
            if not self.can_read():
                return self.error(401, "Party password needed")
            with LOCK:
                books = load_books()
            out = []
            for i, b in books.items():
                if is_ready(i):
                    b = dict(b, id=i)
                    b.setdefault("updatedAt", b.get("addedAt", 0))
                    out.append(b)
            out.sort(key=lambda b: b.get("title", "").lower())
            return self.send_json(out)
        if len(parts) == 3 and parts[0] == "files" and ID_RE.match(parts[1]):
            if not self.can_read():
                return self.error(401, "Party password needed")
            match = [v for v in FILES.values() if v[0] == parts[2]]
            if match:
                return self.send_file(os.path.join(book_dir(parts[1]), match[0][0]), match[0][1], head)
            return self.error(404, "Not found")
        # the web app (the same screens as the Android app)
        name = "index.html" if not parts else "/".join(parts)
        full = os.path.normpath(os.path.join(STATIC, name))
        if not full.startswith(STATIC + os.sep) or not os.path.isfile(full):
            return self.error(404, "Not found")
        ext = full.rsplit(".", 1)[-1].lower()
        ctype = {"html": "text/html; charset=utf-8", "js": "text/javascript", "css": "text/css",
                 "png": "image/png", "svg": "image/svg+xml", "json": "application/json",
                 "woff2": "font/woff2", "pdf": "application/pdf", "jpg": "image/jpeg",
                 "txt": "text/plain; charset=utf-8",
                 "webmanifest": "application/manifest+json"}.get(ext, "application/octet-stream")
        self.send_file(full, ctype, head, cache=(ext in ("woff2",) or "vendor" in parts))

    def send_file(self, full, ctype, head=False, cache=True):
        if not os.path.isfile(full):
            return self.error(404, "Not found")
        size = os.path.getsize(full)
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
            if m:
                a, b = m.groups()
                if a == "" and b:
                    start = max(0, size - int(b))
                else:
                    start = int(a or 0)
                    if b:
                        end = min(int(b), size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.cors()
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "private, max-age=86400" if cache else "no-cache")
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if head:
            return
        try:
            with open(full, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(1024 * 256, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    # ---- writes (keeper only)
    def do_POST(self):
        if self.route() != ["api", "books"]:
            return self.error(404, "Not found")
        if not self.is_keeper():
            return self.error(401, "Wrong keeper password")
        data = self.read_json() or {}
        title = str(data.get("title", "")).strip()[:200] or "Untitled book"
        book_id = secrets.token_hex(8)
        os.makedirs(book_dir(book_id), exist_ok=True)
        now = int(time.time() * 1000)
        with LOCK:
            books = load_books()
            books[book_id] = {"title": title, "pages": int(data.get("pages") or 0),
                              "size": int(data.get("size") or 0), "addedAt": now, "updatedAt": now}
            save_books(books)
        self.send_json({"id": book_id}, 201)

    def do_PUT(self):
        parts = self.route()
        if len(parts) != 4 or parts[:2] != ["api", "books"] or not ID_RE.match(parts[2]) or parts[3] not in FILES:
            return self.error(404, "Not found")
        if not self.is_keeper():
            return self.error(401, "Wrong keeper password")
        with LOCK:
            known = parts[2] in load_books()
        if not known:
            return self.error(404, "No such book")
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return self.error(400, "Empty upload")
        if n > MAX_UPLOAD:
            self.close_connection = True
            return self.send_json({"error": "File is too large"}, 413)
        target = os.path.join(book_dir(parts[2]), FILES[parts[3]][0])
        tmp = target + ".part"
        left = n
        self._body_read = True
        with open(tmp, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1024 * 1024, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            os.remove(tmp)
            self.close_connection = True
            return self.send_json({"error": "Upload was cut off"}, 400)
        os.replace(tmp, target)
        touch(parts[2])
        self.send_json({"ok": True})

    def do_PATCH(self):
        parts = self.route()
        if len(parts) != 3 or parts[:2] != ["api", "books"] or not ID_RE.match(parts[2]):
            return self.error(404, "Not found")
        if not self.is_keeper():
            return self.error(401, "Wrong keeper password")
        data = self.read_json() or {}
        title = str(data.get("title", "")).strip()[:200]
        if not title:
            return self.error(400, "Title can't be empty")
        with LOCK:
            books = load_books()
            if parts[2] not in books:
                return self.send_json({"error": "No such book"}, 404)
            books[parts[2]]["title"] = title
            books[parts[2]]["updatedAt"] = int(time.time() * 1000)
            save_books(books)
        self.send_json({"ok": True})

    def do_DELETE(self):
        parts = self.route()
        if len(parts) != 3 or parts[:2] != ["api", "books"] or not ID_RE.match(parts[2]):
            return self.error(404, "Not found")
        if not self.is_keeper():
            return self.error(401, "Wrong keeper password")
        with LOCK:
            books = load_books()
            books.pop(parts[2], None)
            save_books(books)
        shutil.rmtree(book_dir(parts[2]), ignore_errors=True)
        self.send_json({"ok": True})


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser(description="Tome Vault PDF library server")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--password", help="set or change the keeper password, then exit")
    ap.add_argument("--party-password", help="set or change the party password friends use to read, then exit")
    ap.add_argument("--no-party-password", action="store_true", help="remove the party password, then exit")
    args = ap.parse_args()

    os.makedirs(LIBRARY, exist_ok=True)
    changed = False
    if args.password:
        set_secret("", args.password)
        print("Keeper password saved.")
        changed = True
    if args.party_password:
        set_secret("party_", args.party_password)
        print("Party password saved.")
        changed = True
    if args.no_party_password:
        set_secret("party_", None)
        print("Party password removed. Anyone who can reach the vault can read it.")
        changed = True
    if changed:
        print("Start the vault normally now. If it's already running, restart it.")
        return

    cfg = load_config()
    if "hash" not in cfg:
        if not sys.stdin.isatty():
            sys.exit("No keeper password yet. Run once with:  python3 server.py --password YOURPASSWORD")
        pw = input("Choose a keeper password (needed to add or remove books): ").strip()
        while len(pw) < 4:
            pw = input("Use at least 4 characters: ").strip()
        set_secret("", pw)
        party = input("Choose a party password for friends (leave blank for none): ").strip()
        if party:
            set_secret("party_", party)

    if not os.path.isfile(os.path.join(STATIC, "index.html")):
        sys.exit("Can't find the app files. Keep server.py inside the tome-vault folder next to the 'web' folder.")

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    print("\nTome Vault is running.")
    print("  On this computer:      http://localhost:%d" % args.port)
    print("  On your Wi-Fi:         http://%s:%d" % (local_ip(), args.port))
    print("  Party password:        %s" % ("on" if "party_hash" in load_config() else "off (anyone can read)"))
    print("Press Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
