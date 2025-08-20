from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def create_app():
    app = Flask(__name__)
    CORS(app)
    
    # Configure the app from .env
    app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')
    app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_FILE_SIZE_MB', 50)) * 1024 * 1024
    app.config['ILOVEPDF_PUBLIC_KEY'] = os.getenv('ILOVEPDF_PUBLIC_KEY')
    
    # Validate required config
    if not app.config['ILOVEPDF_PUBLIC_KEY']:
        raise ValueError("ILOVEPDF_PUBLIC_KEY must be set in .env file")
    
    # Import dan register blueprints di dalam fungsi create_app
    from documentasi.public import doc_bp
    from pdf_tools.filecompress import compress_bp
    from pdf_tools.merge import merge_bp
    from pdf_tools.split import split_bp
    from pdf_tools.watermark import watermark_bp
    from otherTools.aiagentCode import project_bp
    
    app.register_blueprint(compress_bp)
    app.register_blueprint(merge_bp)
    app.register_blueprint(split_bp)
    app.register_blueprint(watermark_bp)
    app.register_blueprint(doc_bp)
    app.register_blueprint(project_bp)
    
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    return app

# HANYA ini yang boleh di level global
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, threaded=True)
