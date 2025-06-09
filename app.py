import os
import uuid
import json
import boto3
import requests
from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, jsonify
)
from werkzeug.utils import secure_filename
from flask_cors import CORS

# ─── PRINT-BASED DEBUGGING ─────────────────────────────────────────────────────
def debug(*args, **kwargs):
    print(*args, **kwargs, flush=True)

# ─── Critical config ─────────────────────────────────────────────────────────
RUNPOD_WEBHOOK = os.getenv("RUNPOD_WEBHOOK_URL")
if not RUNPOD_WEBHOOK:
    debug("❌ RUNPOD_WEBHOOK_URL is not set! Aborting startup.")
    raise RuntimeError("RUNPOD_WEBHOOK_URL environment variable is missing")
debug("✅ Using RunPod webhook:", RUNPOD_WEBHOOK)

# ─── App Setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "CHANGE_ME")

# AWS S3 client
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)
BUCKET = os.getenv("S3_BUCKET")

# In-memory tracking of free uses per IP
user_sessions = {}

# Load valid API keys
KEY_FILE = "keys.json"
valid_keys = set()
if os.path.exists(KEY_FILE):
    try:
        valid_keys = set(json.load(open(KEY_FILE)))
    except:
        valid_keys = set()

# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        user = user_sessions.setdefault(ip, {"count": 0, "key_unlocked": False})

        # Handle API key submission
        key = (request.form.get("api_key") or "").strip()
        if key and key in valid_keys:
            user["key_unlocked"] = True
            user["count"] = 0

        # Enforce 4 free splits
        if not user["key_unlocked"] and user["count"] >= 4:
            return jsonify({"blocked": True}), 200

        if not user["key_unlocked"]:
            user["count"] += 1

        # Handle file upload
        f = request.files.get("file")
        if not f:
            return jsonify({"error": "No file uploaded"}), 400

        os.makedirs("uploads", exist_ok=True)
        filename = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
        path = os.path.join("uploads", filename)
        f.save(path)

        # Upload original to S3
        s3.upload_file(path, BUCKET, filename)

        # ─── DEBUG: POST to RunPod with print() ───────────────────────
        payload = {"filename": filename, "bucket": BUCKET}
        debug("▶️  About to POST to RunPod at:", RUNPOD_WEBHOOK)
        debug("   Payload:", payload)

        try:
            resp = requests.post(RUNPOD_WEBHOOK, json=payload, timeout=10)
            debug("💡 RunPod response status:", resp.status_code, "body:", resp.text)
            resp.raise_for_status()
        except Exception as e:
            debug("❌ Exception while triggering RunPod:", e)
            return jsonify({"error": f"RunPod trigger error: {e}"}), 500
        # ───────────────────────────────────────────────────────────────

        return jsonify({"filename": filename}), 200

    return render_template("index.html")


@app.route("/status")
def status():
    filename = request.args.get("file")
    if not filename:
        return jsonify({"error": "file param required"}), 400

    base = filename.rsplit(".", 1)[0]
    stems = ["vocals", "drums", "bass", "other"]
    urls = {}
    try:
        for stem in stems:
            key = f"{base}/{stem}.mp3"
            s3.head_object(Bucket=BUCKET, Key=key)
            urls[stem] = f"https://{BUCKET}.s3.amazonaws.com/{key}"
        return jsonify({"status": "done", "files": urls}), 200
    except s3.exceptions.NoSuchKey:
        return jsonify({"status": "pending"}), 202
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ─── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug(f"🚀 Starting EchoSplit on port {port}")
    app.run(host="0.0.0.0", port=port)