from flask import Flask, request, render_template
import os
import boto3
import requests
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Load environment variables (keys, bucket names, etc.)
load_dotenv()

# === Flask Setup ===
UPLOAD_FOLDER = "uploads"
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# === AWS S3 Setup ===
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)

bucket_name = os.getenv("S3_BUCKET")
runpod_webhook = os.getenv("RUNPOD_WEBHOOK")  # e.g., https://api.runpod.ai/v2/<endpoint>/run

# === Upload Route ===
@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files.get("file")  # safer with .get() in case no file is sent
        if not file:
            return "No file uploaded", 400
        
        filename = secure_filename(file.filename)  # sanitize filename
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # === Upload to S3 ===
        try:
            s3.upload_file(filepath, bucket_name, filename)
        except Exception as e:
            return f"S3 upload failed: {e}", 500

        # === Trigger RunPod Processing ===
        try:
            response = requests.post(runpod_webhook, json={"filename": filename})
            if response.status_code != 200:
                return f"RunPod processing error: {response.text}", 500
        except Exception as e:
            return f"Failed to reach RunPod: {e}", 500

        return render_template("index.html", stems="processing", song=filename)

    # === GET Route for Page Load ===
    return render_template("index.html", stems=None)

# === Optional Feedback Form Handler ===
@app.route("/feedback", methods=["POST"])
def feedback():
    msg = request.form["message"]
    with open("feedback.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n---\n")
    return "✅ Thanks for your feedback!"

# === Start App ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
