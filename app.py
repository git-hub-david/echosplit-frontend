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

# ─── App Setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "CHANGE_ME")

# AWS S3
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)
BUCKET = os.getenv("S3_BUCKET")

# RunPod webhook
RUNPOD_WEBHOOK = os.getenv("RUNPOD_WEBHOOK_URL")

# In-memory tracking of free uses per IP
user_sessions = {}  # { ip: { "count": int, "key_unlocked": bool } }

# Load valid keys
KEY_FILE = "keys.json"
valid_keys = set()
if os.path.exists(KEY_FILE):
    try:
        with open(KEY_FILE) as f:
            valid_keys = set(json.load(f))
    except:
        valid_keys = set()

# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        # init session record if needed
        user = user_sessions.setdefault(ip, {"count": 0, "key_unlocked": False})

        # did they submit a key?
        key = (request.form.get("api_key") or "").strip()
        if key and key in valid_keys:
            user["key_unlocked"] = True
            user["count"] = 0  # reset free count
        # enforce free-use limit
        if not user["key_unlocked"] and user["count"] >= 4:
            return jsonify({"blocked": True}), 200

        # consume a free use (if no key)
        if not user["key_unlocked"]:
            user["count"] += 1

        # handle file upload
        f = request.files.get("file")
        if not f:
            return jsonify({"error": "No file uploaded"}), 400

        # save locally
        os.makedirs("uploads", exist_ok=True)
        filename = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
        path = os.path.join("uploads", filename)
        f.save(path)

        # upload original to S3
        s3.upload_file(path, BUCKET, filename)

        # trigger RunPod
        resp = requests.post(RUNPOD_WEBHOOK, json={
            "filename": filename,
            "bucket": BUCKET
        })
        if not resp.ok:
            return jsonify({"error": "Failed to trigger processing"}), 500

        # return filename so the frontend can poll /status
        return jsonify({"filename": filename}), 200

    return render_template("index.html")


@app.route("/status")
def status():
    """
    Usage: GET /status?file=<filename>
    Returns JSON:
      { status: "pending" }
      { status: "done", files: { vocals: url, drums: url, ... } }
      { status: "error", error: msg }
    """
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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))