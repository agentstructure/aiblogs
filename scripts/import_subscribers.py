"""Copy each site's existing subscribers (stored on its own server) into its Brevo list.

Reads the subscriber file through the Hostinger API and adds every address to the site's
Brevo list (created if needed). Safe to re-run: existing contacts are updated, not duplicated.
Prints counts only, never addresses.
"""

from __future__ import annotations

import json
import re
import sys

from brevo import Brevo
from common import load_sites
from hostinger import Hostinger, HostingerError

CANDIDATES = ["subscribers.json", "data/subscribers.json"]


def main() -> int:
    h, b = Hostinger(), Brevo()
    failed = False
    for slug, site in load_sites().items():
        domain = site.get("hosting_domain", site["domain"])
        user = h.username_for(domain)
        rows = None
        for path in CANDIDATES:
            try:
                rows = json.loads(h.read_file(user, domain, path) or "[]")
                break
            except (HostingerError, ValueError):
                continue
        if rows is None:
            print(f"[{slug}] no subscriber file found")
            continue
        if isinstance(rows, dict):
            rows = rows.get("subscribers", [])
        list_id = b.ensure_list(site)
        added = 0
        for r in rows:
            email = str(r.get("email", "")).strip().lower()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                continue
            contact = {"email": email, "listIds": [list_id], "updateEnabled": True}
            if r.get("name"):
                contact["attributes"] = {"FIRSTNAME": str(r["name"]).split()[0][:50]}
            try:
                b._req("POST", "/contacts", json=contact)
                added += 1
            except RuntimeError as e:
                failed = True
                print(f"::warning title={slug}::one contact was not added ({str(e).split(':')[0]})")
        print(f"[{slug}] {added} of {len(rows)} subscribers in Brevo list {list_id}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
