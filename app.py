import os
import uuid
import json
import boto3
import requests
from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, jsonify
)
from session_tracker import SessionTracker

# ─── App Setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "CHANGE_ME")

# S3 client
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)
BUCKET = os.getenv("S3_BUCKET")

# Tracker for key-based limits
tracker = SessionTracker("keys.json")

# RunPod webhook URL
RUNPOD_WEBHOOK = os.getenv("RUNPOD_WEBHOOK_URL")


# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        user_key = request.form.get("api_key", "").strip()
        if not tracker.validate(user_key):
            flash("Invalid or expired key.", "error")
            return redirect(url_for("index"))

        f = request.files.get("file")
        if not f:
            flash("No file selected.", "error")
            return redirect(url_for("index"))

        # ensure upload folder exists
        os.makedirs("uploads", exist_ok=True)

        # secure, unique filename
        filename = f"{uuid.uuid4().hex}_{f.filename}"
        local_path = os.path.join("uploads", filename)
        f.save(local_path)

        # 1) upload to S3
        try:
            s3.upload_file(local_path, BUCKET, filename)
        except Exception as e:
            flash(f"S3 upload failed: {e}", "error")
            return redirect(url_for("index"))

        # 2) trigger RunPod
        resp = requests.post(RUNPOD_WEBHOOK, json={
            "bucket": BUCKET,
            "filename": filename
        })
        if not resp.ok:
            flash("Failed to trigger processing.", "error")
            return redirect(url_for("index"))

        flash("Upload successful! Processing started.", "success")
        return redirect(url_for("status", file=filename))

    return render_template("index.html")


@app.route("/status")
def status():
    """
    Poll this endpoint with ?file=<filename>.
    Returns JSON: { status: "pending"|"done"|"error", files: {...} }
    """
    filename = request.args.get("file")
    if not filename:
        return jsonify({"error": "file param required"}), 400

    # check for results in S3 under "separated/"
    key = f"separated/{filename}"
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
        # if found, list both stems
        base = filename.rsplit(".", 1)[0]
        return jsonify({
            "status": "done",
            "files": {
                "vocals": f"{base}/vocals.wav",
                "instrumental": f"{base}/no_vocals.wav"
            }
        })
    except s3.exceptions.NoSuchKey:
        # still processing
        return jsonify({"status": "pending"}), 202
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ─── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Render automatically picks this up
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))