"""Hostinger API helper: list websites, back up a site's files, upload files.

Needs HOSTINGER_API_TOKEN (hPanel > profile > API). Never prints file contents, so it is
safe to run in Actions logs; the backup itself must only be published from a private repo.

Usage:
  python scripts/hostinger.py inventory
  python scripts/hostinger.py backup <domain> <out_dir>
  python scripts/hostinger.py upload <domain> <local_file> <remote_path>   (path under public_html)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://developers.hostinger.com"


def _request(method: str, url: str, *, body: bytes | None = None, headers: dict | None = None,
             retries: int = 4) -> tuple[int, dict, bytes]:
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return e.code, dict(e.headers), e.read()
        except urllib.error.URLError:
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


class Hostinger:
    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("HOSTINGER_API_TOKEN")
        if not self.token:
            raise SystemExit("HOSTINGER_API_TOKEN is not set")

    def call(self, method: str, path: str, params: dict | None = None, json_body=None, ok=(200,)):
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        status, _, data = _request(method, url, body=body, headers=headers)
        if status not in ok:
            # error bodies are API messages, never file contents
            raise HostingerError(status, data.decode(errors="replace")[:300])
        return json.loads(data) if data else None

    # --- websites -------------------------------------------------------------------------

    def websites(self) -> list[dict]:
        out, page = [], 1
        while True:
            res = self.call("GET", "/api/hosting/v1/websites", {"page": page, "per_page": 100})
            out += res.get("data", [])
            meta = res.get("meta") or {}
            if page >= (meta.get("last_page") or 1):
                return out
            page += 1

    def horizons_websites(self) -> list[dict]:
        res = self.call("GET", "/api/horizons/v1/websites")
        return res.get("data", res) if isinstance(res, dict) else res

    def username_for(self, domain: str) -> str:
        for w in self.websites():
            if w.get("domain") == domain:
                return w["username"]
        raise SystemExit(f"{domain} is not a website on this Hostinger account")

    # --- files ----------------------------------------------------------------------------

    def list_files(self, username: str, domain: str, directory: str = "") -> list[dict]:
        """Every entry under directory (relative to the document root), recursively."""
        out, offset = [], 0
        path = f"/api/hosting/v1/accounts/{username}/domains/{domain}/files"
        while True:
            params = {"max_depth": 10, "max_items": 2000, "offset": offset}
            if directory:
                params["directory"] = directory
            res = self.call("GET", path, params)
            out += res["items"]
            offset += res["total_items_current_page"]
            if not res["total_items_current_page"] or offset >= res["total_items"]:
                break
        # entries at depth 10 may hide deeper files; list those directories too
        deep = [e["path"] for e in out if e["type"] == "directory"
                and e["path"].count("/") - directory.count("/") >= 9]
        for d in deep:
            out += self.list_files(username, domain, d)
        return out

    def read_file(self, username: str, domain: str, path: str) -> str:
        url = f"/api/hosting/v1/accounts/{username}/domains/{domain}/files/content"
        parts, line = [], 0
        while True:
            res = self.call("GET", url, {"path": path, "from_line": line, "max_lines": 5000})
            chunk = res["content"]
            parts.append(chunk)
            got = chunk.count("\n") + (0 if chunk.endswith("\n") or not chunk else 1)
            line += got
            if not got or line >= res["total_lines"]:
                return "".join(parts)

    def upload(self, username: str, domain: str, data: bytes, remote_path: str) -> None:
        """Write one file under the site's public_html (overwrites)."""
        u = self.call("POST", "/api/hosting/v1/files/upload-urls",
                      json_body={"username": username, "domain": domain})
        target = u["url"].rstrip("/") + "/" + urllib.parse.quote(remote_path.lstrip("/")) + "?override=true"
        auth = {"X-Auth": u["auth_key"], "X-Auth-Rest": u["rest_auth_key"], "Tus-Resumable": "1.0.0"}
        status, headers, msg = _request("POST", target, body=b"", headers={
            **auth, "Upload-Length": str(len(data)), "Upload-Offset": "0"})
        if status not in (200, 201):
            raise HostingerError(status, f"create upload for {remote_path}: {msg[:200]!r}")
        location = headers.get("Location") or headers.get("location")
        if location:
            target = urllib.parse.urljoin(target, location)
        status, _, msg = _request("PATCH", target, body=data, headers={
            **auth, "Upload-Offset": "0", "Content-Type": "application/offset+octet-stream"})
        if status not in (200, 204):
            raise HostingerError(status, f"upload {remote_path}: {msg[:200]!r}")


class HostingerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def cmd_inventory(h: Hostinger):
    for w in h.websites():
        print(f"{w.get('domain')}\ttype={w.get('website_type') or w.get('vhost_type')}"
              f"\troot={w.get('root_directory')}\tenabled={w.get('is_enabled')}")
    try:
        hz = h.horizons_websites()
        print(f"Horizons websites: {len(hz)}")
        for w in hz:
            print(f"  horizons: {w.get('domain') or w.get('name') or w.get('id')}")
    except HostingerError as e:
        print(f"Horizons websites: not available ({e.status})")


def cmd_backup(h: Hostinger, domain: str, out_dir: str):
    user = h.username_for(domain)
    out = Path(out_dir)
    entries = h.list_files(user, domain)
    files = [e for e in entries if e["type"] == "file"]
    skipped = []
    for e in files:
        dest = out / e["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_text(h.read_file(user, domain, e["path"]))
        except HostingerError as err:  # binary files and files the API flags as secret
            skipped.append({"path": e["path"], "size_bytes": e["size_bytes"], "reason": str(err)[:200]})
    (out / "_listing.json").write_text(json.dumps(entries, indent=1))
    (out / "_skipped.json").write_text(json.dumps(skipped, indent=1))
    print(f"{domain}: {len(files)} files listed, {len(files) - len(skipped)} saved, "
          f"{len(skipped)} not readable as text (see _skipped.json)")


def cmd_upload(h: Hostinger, domain: str, local: str, remote: str):
    h.upload(h.username_for(domain), domain, Path(local).read_bytes(), remote)
    print(f"uploaded {remote} to {domain}")


def main(argv: list[str]):
    if not argv:
        raise SystemExit(__doc__)
    h = Hostinger()
    cmd, args = argv[0], argv[1:]
    {"inventory": cmd_inventory, "backup": cmd_backup, "upload": cmd_upload}[cmd](h, *args)


if __name__ == "__main__":
    main(sys.argv[1:])
