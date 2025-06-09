import os
import json
from flask import request
from collections import defaultdict

class SessionTracker:
    def __init__(self, keys_file="keys.json"):
        # Track upload counts per IP and per session
        self.ip_tracker = defaultdict(int)
        self.session_tracker = defaultdict(int)
        self.allow_override = False

        # Load valid API keys
        self.keys = set()
        if os.path.exists(keys_file):
            with open(keys_file, "r") as f:
                try:
                    self.keys = set(json.load(f))
                except Exception:
                    self.keys = set()

    def validate(self, key):
        """
        Returns True if:
          - the key is in keys.json (or override is on), AND
          - this IP/session hasn’t uploaded >2 times.
        """
        # Key check
        if not self.allow_override and key not in self.keys:
            return False

        # Rate‐limit: max 2 uploads per IP or session
        ip = self._get_ip()
        sid = self._get_session_id()
        if self.ip_tracker[ip] >= 2 or self.session_tracker[sid] >= 2:
            return False

        # All good: consume one upload
        self.ip_tracker[ip] += 1
        self.session_tracker[sid] += 1
        return True

    def force_allow_key_use(self):
        """Call this once if you want to disable the key check entirely."""
        self.allow_override = True

    def _get_ip(self):
        # Respect X-Forwarded-For when behind a proxy
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        return request.remote_addr or "unknown"

    def _get_session_id(self):
        # Use a session cookie if set, else fall back to IP
        return request.cookies.get("session_id") or self._get_ip()