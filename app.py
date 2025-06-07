import os
from flask import Flask, request, render_template, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import boto3
import requests

load_dotenv()

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# AWS S3
bucket_name = os.getenv("S3_BUCKET")
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)

# Your RunPod webhook URL (ensure this is set in Render ENV as well)
RUNPOD_WEBHOOK = os.getenv("RUNPOD_WEBHOOK")

@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file provided"}), 400

        filename = secure_filename(file.filename)
        local_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(local_path)

        try:
            # 1) Upload to S3
            s3.upload_file(local_path, bucket_name, filename)
            print(f"✅ Uploaded {filename} to S3://{bucket_name}/{filename}")
        except Exception as e:
            return jsonify({"error": f"S3 upload failed: {e}"}), 500

        try:
            # 2) Trigger RunPod processing
            resp = requests.post(RUNPOD_WEBHOOK, json={"filename": filename})
            print(f"📨 RunPod webhook response: {resp.status_code} {resp.text}")
            if resp.status_code != 200:
                raise Exception(resp.text)
        except Exception as e:
            return jsonify({"error": f"Failed to trigger RunPod: {e}"}), 500

        # 3) Return 200 so the spinner stays up while RunPod runs
        return ("", 200)

    # GET → render frontend
    return render_template("index.html", bucket_name=bucket_name)

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

@app.route("/status")
def status_proxy():
    filename = request.args.get("filename", "")
    if not filename:
        return jsonify({"error": "No filename provided"}), 400

    # Forward to your RunPod backend
    backend_url = os.getenv("RUNPOD_WEBHOOK") + "/status"
    try:
        resp = requests.get(backend_url, params={"filename": filename}, timeout=5)
        return (resp.text, resp.status_code, {"Content-Type": "application/json"})
    except Exception:
        return jsonify({"done": False}), 500