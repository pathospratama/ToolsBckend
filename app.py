from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
import os

# Import semua blueprint
from documentasi.public import doc_bp
from pdf_tools.filecompress import compress_bp
from pdf_tools.merge import merge_bp
from pdf_tools.split import split_bp
from pdf_tools.watermark import watermark_bp
from otherTools.aiagentCode import project_bp

# Load .env
load_dotenv()


def create_app():
    app = Flask(__name__)
    CORS(app)

    # Konfigurasi upload folder pakai /tmp (wajib di serverless Vercel)
    app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', '/tmp/uploads')
    app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_FILE_SIZE_MB', 50)) * 1024 * 1024
    app.config['ILOVEPDF_PUBLIC_KEY'] = os.getenv('ILOVEPDF_PUBLIC_KEY')

    # Warning saja kalau env belum di-set
    if not app.config['ILOVEPDF_PUBLIC_KEY']:
        print("⚠️  Warning: ILOVEPDF_PUBLIC_KEY is not set, some features may not work.")

    # Register semua blueprint
    app.register_blueprint(compress_bp)
    app.register_blueprint(merge_bp)
    app.register_blueprint(split_bp)
    app.register_blueprint(watermark_bp)
    app.register_blueprint(doc_bp)
    app.register_blueprint(project_bp)

    # Pastikan folder upload ada (di /tmp)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    return app
