
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from PIL import Image
import os
import easyocr

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

_reader = None
def get_reader():
    global _reader
    if _reader is None:
        # Keep it lean: English only, CPU
        _reader = easyocr.Reader(['en'], gpu=False)
    return _reader

def allowed_file(filename: str) -> bool:
    return bool(filename) and '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def downscale_image(path, max_dim=1600):
    try:
        with Image.open(path) as img:
            img = img.convert('RGB')
            w, h = img.size
            scale = min(1.0, max_dim / max(w, h))
            if scale < 1.0:
                img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
            img.save(path, format='JPEG', quality=85)
    except Exception:
        pass  # fail-safe: continue even if downscale fails

@app.route('/')
def serve_home():
    index_path = os.path.join('.', 'index.html')
    if os.path.exists(index_path):
        return send_from_directory('.', 'index.html')
    return "Flask EasyOCR API is running."

@app.route('/ocr', methods=['POST'])
def ocr_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    if not allowed_file(image_file.filename):
        return jsonify({"error": "Only PNG and JPG images are allowed"}), 400

    safe_name = secure_filename(image_file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    image_file.save(file_path)

    # downscale to reduce memory during inference
    downscale_image(file_path, max_dim=1600)

    try:
        reader = get_reader()
        result = reader.readtext(file_path)

        extracted_text = [det[1] for det in result if len(det) > 1]
        text = " ".join(extracted_text).strip()

        lower_text = text.lower()
        if any(k in lower_text for k in ("birth certificate", "child", "registry", "philippine statistics")):
            doc_type = "Birth Certificate"
        elif any(k in lower_text for k in ("id", "republic", "philippines", "national id", "license", "passport")):
            doc_type = "Identification Card"
        else:
            doc_type = "Unknown"

        return jsonify({
            "document_type": doc_type,
            "text": text,
            "fields": {"example_field": "Sample extracted info"}
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

@app.errorhandler(413)
def request_entity_too_large(e):
    return jsonify({"error": "File too large. Max 5 MB"}), 413

if __name__ == '__main__':
    # Use only for local testing; Render will start via gunicorn
    app.run(host='0.0.0.0', port=5000, debug=False)
