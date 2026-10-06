"""Minimal Brevo (email) API client: one contact list per site, campaigns for roundups."""

from __future__ import annotations

import os

import requests

API = "https://api.brevo.com/v3"
FOLDER_NAME = "AI Blogs"


class Brevo:
    def __init__(self, api_key: str | None = None):
        self.s = requests.Session()
        self.s.headers.update(
            {"api-key": api_key or os.environ["BREVO_API_KEY"], "accept": "application/json"}
        )

    def _req(self, method: str, path: str, **kw):
        r = self.s.request(method, API + path, timeout=30, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"Brevo {method} {path} -> {r.status_code}: {r.text}")
        return r.json() if r.content else {}

    def _folder_id(self) -> int:
        folders = self._req("GET", "/contacts/folders", params={"limit": 50}).get("folders", [])
        for f in folders:
            if f["name"] == FOLDER_NAME:
                return f["id"]
        return self._req("POST", "/contacts/folders", json={"name": FOLDER_NAME})["id"]

    def ensure_list(self, site: dict) -> int:
        """Return the id of the site's subscriber list, creating it if needed."""
        name = f"{site['name']} ({site['domain']})"
        offset = 0
        while True:
            page = self._req("GET", "/contacts/lists", params={"limit": 50, "offset": offset})
            for lst in page.get("lists", []):
                if lst["name"] == name:
                    return lst["id"]
            if len(page.get("lists", [])) < 50:
                break
            offset += 50
        return self._req("POST", "/contacts/lists", json={"name": name, "folderId": self._folder_id()})["id"]

    def send_campaign(self, *, name: str, subject: str, preview: str, html: str,
                      sender_name: str, sender_email: str, list_id: int) -> int:
        campaign = self._req("POST", "/emailCampaigns", json={
            "name": name,
            "subject": subject,
            "previewText": preview,
            "sender": {"name": sender_name, "email": sender_email},
            "htmlContent": html,
            "recipients": {"listIds": [list_id]},
        })
        self._req("POST", f"/emailCampaigns/{campaign['id']}/sendNow")
        return campaign["id"]
