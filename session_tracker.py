import os
from flask import request
from collections import defaultdict

ip_tracker = defaultdict(int)
session_tracker = defaultdict(int)
ALLOW_OVERRIDE = False  # Set True if key is used

def get_ip():
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0]
    return request.remote_addr or "unknown"

def get_session_id():
    return request.cookies.get("session_id") or get_ip()

def can_process():
    if ALLOW_OVERRIDE:
        return True

    ip = get_ip()
    sid = get_session_id()

    # Limit: 2 uploads per session or IP
    if ip_tracker[ip] >= 2 or session_tracker[sid] >= 2:
        return False

    ip_tracker[ip] += 1
    session_tracker[sid] += 1
    return True

def force_allow_key_use():
    global ALLOW_OVERRIDE
    ALLOW_OVERRIDE = True