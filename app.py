import os
from flask import Flask, request, render_template, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import boto3

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

@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        # JS sends FormData with 'file'
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file provided"}), 400

        filename = secure_filename(file.filename)
        local_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(local_path)

        try:
            # Upload to S3
            s3.upload_file(local_path, bucket_name, filename)
            print(f"✅ Uploaded {filename} to S3://{bucket_name}/{filename}")
            return ("", 200)
        except Exception as e:
            print(f"❌ S3 upload error: {e}")
            return jsonify({"error": str(e)}), 500

    # GET → serve the page, giving it the bucket name for JS
    return render_template("index.html", bucket_name=bucket_name)

@app.route("/feedback", methods=["POST"])
def feedback():
    msg = request.form.get("message", "").strip()
    if msg:
        with open("feedback.txt", "a", encoding="utf-8") as f:
            f.write(msg + "\n---\n")
    return ("", 200)

if __name__ == "__main__":
    # Use the PORT env var on Render, default to 5000 locally
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)