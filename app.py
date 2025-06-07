import os
import threading
from flask import Flask, request, render_template, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import boto3
import requests

# Load local .env when testing locally
load_dotenv()

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# AWS S3 setup
bucket_name = os.getenv("S3_BUCKET")
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)

# Webhook base URL (no trailing slash)
RUNPOD_WEBHOOK = os.getenv("RUNPOD_WEBHOOK").rstrip("/")

def trigger_runpod(filename: str):
    """
    Fire-and-forget POST to RunPod webhook.
    Short timeout so this thread never hangs.
    """
    try:
        requests.post(
            RUNPOD_WEBHOOK,
            json={"filename": filename},
            timeout=2  # short so thread finishes quickly
        )
    except Exception:
        pass  # ignore all errors

@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file provided"}), 400

        filename = secure_filename(file.filename)
        local_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(local_path)

        # 1) Upload to S3
        try:
            s3.upload_file(local_path, bucket_name, filename)
            app.logger.info(f"Uploaded {filename} to s3://{bucket_name}/{filename}")
        except Exception as e:
            return jsonify({"error": f"S3 upload failed: {e}"}), 500

        # 2) Trigger RunPod webhook in background
        threading.Thread(target=trigger_runpod, args=(filename,), daemon=True).start()

        # 3) Return immediately so frontend enters processing stage
        return ("", 200)

    # GET → render upload page
    return render_template("index.html", bucket_name=bucket_name)

@app.route("/status")
def status_proxy():
    """
    Proxy status check to the RunPod backend's /status endpoint.
    Frontend JS polls this to detect when stems are ready.
    """
    filename = request.args.get("filename", "")
    if not filename:
        return jsonify({"error": "No filename provided"}), 400

    backend_status_url = f"{RUNPOD_WEBHOOK}/status"
    try:
        resp = requests.get(
            backend_status_url,
            params={"filename": filename},
            timeout=5
        )
        # Return the backend JSON (either {"done":false} or {"done":true,"urls":{…}})
        return (resp.text, resp.status_code, {"Content-Type": "application/json"})
    except Exception:
        # On failure, signal not done so polling continues
        return jsonify({"done": False}), 500

@app.route("/feedback", methods=["POST"])
def feedback():
    msg = request.form.get("message", "").strip()
    if msg:
        with open("feedback.txt", "a", encoding="utf-8") as f:
            f.write(msg + "\n---\n")
    return ("", 200)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)