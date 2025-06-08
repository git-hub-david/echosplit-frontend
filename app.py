import os
import json
import boto3
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from flask_cors import CORS

# === App Configuration ===
app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'separated'      # not used directly here, stems live on S3
KEY_FILE = 'keys.json'
BUCKET_NAME = 'echosplit-uploads' # your S3 bucket

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# === In-memory session tracking (by IP) ===
user_sessions = {}

# === Utilities ===

def load_keys():
    """Load the list of valid reusable keys from JSON."""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'r') as f:
            return json.load(f)
    return []

def check_s3_files_exist(bucket, base_filename):
    """
    Check S3 for each stem. Return (all_exist: bool, urls: dict).
    """
    s3 = boto3.client(
        's3',
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION")
    )
    stems = ['vocals', 'drums', 'bass', 'other']
    urls = {}
    for stem in stems:
        key = f"{base_filename}/{stem}.mp3"
        try:
            s3.head_object(Bucket=bucket, Key=key)
            urls[stem] = f"https://{bucket}.s3.amazonaws.com/{base_filename}/{stem}.mp3"
        except s3.exceptions.ClientError:
            return False, {}
    return True, urls

# === Routes ===

@app.route('/')
def index():
    """Render the main upload page."""
    return render_template('index.html', bucket_name=BUCKET_NAME)

@app.route('/', methods=['POST'])
def upload_file():
    """Handle file uploads, enforce free-usage limit or key unlock."""
    ip = request.remote_addr
    user = user_sessions.get(ip, {'count': 0, 'key': False})

    # If no key and already used 2 uploads, block
    if not user['key'] and user['count'] >= 2:
        return jsonify({'blocked': True}), 200

    # Validate incoming file
    if 'file' not in request.files or request.files['file'].filename == '':
        return 'No file uploaded', 400

    file = request.files['file']
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # TODO: Trigger your RunPod processing here, e.g. via requests.post(...)
    print(f"[INFO] Upload received: {filename} (IP: {ip})")

    # Increment upload count
    user['count'] += 1
    user_sessions[ip] = user

    return jsonify({'blocked': False}), 200

@app.route('/status')
def status():
    """
    Polling endpoint: checks S3 for separated stems.
    Returns {"done":true,"urls":{...}} or {"done":false}.
    """
    filename = request.args.get('filename')
    if not filename:
        return jsonify({'error': 'Filename required'}), 400

    base = os.path.splitext(filename)[0]
    exists, urls = check_s3_files_exist(BUCKET_NAME, base)
    if exists:
        return jsonify({'done': True, 'urls': urls})
    else:
        return jsonify({'done': False})

@app.route('/use_key', methods=['POST'])
def use_key():
    """
    Accept a reusable key to reset the user's count and unlock unlimited use.
    """
    data = request.get_json() or {}
    key = data.get('key', '').strip()
    ip = request.remote_addr

    valid_keys = load_keys()
    if key in valid_keys:
        # Reset their count and mark key-active
        user_sessions[ip] = {'count': 0, 'key': True}
        print(f"[KEY] {ip} unlocked with key: {key}")
        return '', 200

    return 'Invalid key', 403

# === Entry Point ===
if __name__ == '__main__':
    # Bind to 0.0.0.0:5000 for Render
    app.run(host='0.0.0.0', port=5000)