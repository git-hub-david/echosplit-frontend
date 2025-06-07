import os
import threading
from flask import Flask, request, render_template, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import boto3
import requests

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

# RunPod webhook (no trailing slash)
RUNPOD_WEBHOOK = os.getenv("RUNPOD_WEBHOOK").rstrip("/")

def trigger_runpod(filename: str):
    try:
        requests.post(RUNPOD_WEBHOOK, json={"filename": filename}, timeout=2)
    except Exception:
        pass

@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file provided"}), 400

        # save & sanitize filename
        filename = secure_filename(file.filename)
        local_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(local_path)

        # upload to S3
        try:
            s3.upload_file(local_path, bucket_name, filename)
        except Exception as e:
            return jsonify({"error": f"S3 upload failed: {e}"}), 500

        # trigger RunPod in background
        threading.Thread(target=trigger_runpod, args=(filename,), daemon=True).start()

        # return the safe filename for polling
        return jsonify({"filename": filename}), 200

    return render_template("index.html", bucket_name=bucket_name)

@app.route("/status")
def status_proxy():
    filename = request.args.get("filename", "")
    if not filename:
        return jsonify({"error": "No filename provided"}), 400

    try:
        resp = requests.get(f"{RUNPOD_WEBHOOK}/status",
                            params={"filename": filename}, timeout=5)
        return (resp.text, resp.status_code, {"Content-Type": "application/json"})
    except Exception:
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