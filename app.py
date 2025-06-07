import os
import json
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'separated'
KEY_FILE = 'keys.json'
BUCKET_NAME = 'echosplit-uploads'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# IP session tracking
user_sessions = {}

# Load reusable keys from keys.json
def load_keys():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            return json.load(f)
    return []

# Homepage
@app.route('/')
def index():
    return render_template('index.html', bucket_name=BUCKET_NAME)

# Upload route
@app.route('/', methods=['POST'])
def upload_file():
    ip = request.remote_addr
    user = user_sessions.get(ip, {'count': 0, 'key': False})

    if not user['key'] and user['count'] >= 2:
        return jsonify({'blocked': True}), 200

    if 'file' not in request.files:
        return 'No file part', 400

    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    # Simulate RunPod trigger (your real webhook call goes here)
    print(f"[INFO] Received upload: {filename} from {ip}")

    user['count'] += 1
    user_sessions[ip] = user

    return jsonify({'blocked': False}), 200

# Status check
@app.route('/status')
def check_status():
    filename = request.args.get('filename')
    if not filename:
        return jsonify({'error': 'Filename required'}), 400

    base = os.path.splitext(filename)[0]
    s3_base = f"https://{BUCKET_NAME}.s3.amazonaws.com/{base}"
    stems = ['vocals', 'drums', 'bass', 'other']

    urls = {}
    for stem in stems:
        urls[stem] = f"{s3_base}/{stem}.mp3"

    # You could add actual file checks or ping S3 if needed
    return jsonify({'done': True, 'urls': urls})

# Key activation
@app.route('/use_key', methods=['POST'])
def use_key():
    data = request.get_json()
    key = data.get('key')
    ip = request.remote_addr

    valid_keys = load_keys()
    if key in valid_keys:
        user_sessions[ip] = {'count': 0, 'key': True}
        return '', 200
    return 'Invalid key', 403

# Run the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)