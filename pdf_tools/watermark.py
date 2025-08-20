import os
import logging
import uuid
from flask import Flask, Blueprint, request, jsonify, send_from_directory, current_app
from pylovepdf.ilovepdf import ILovePdf
from werkzeug.utils import secure_filename
from datetime import datetime
from PIL import Image
import io

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask Blueprint
watermark_bp = Blueprint('watermark', __name__, url_prefix='/api/pdf-tools')

def allowed_file(filename, extensions=None):
    if extensions is None:
        extensions = {'pdf'}
    return '.' in filename and filename.lower().split('.')[-1] in extensions

def convert_to_pdf(image_file, output_path):
    """Convert image file to PDF for watermarking"""
    try:
        image = Image.open(io.BytesIO(image_file.read()))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        image.save(output_path, "PDF", resolution=100.0)
        return True
    except Exception as e:
        logger.error(f"Image conversion error: {str(e)}")
        return False

@watermark_bp.route('/watermark', methods=['POST'])
def add_watermark():
    try:
        # Validate request data
        if 'file' not in request.files:
            return jsonify({'error': 'No PDF file uploaded'}), 400
        
        pdf_file = request.files['file']
        if pdf_file.filename == '':
            return jsonify({'error': 'No PDF file selected'}), 400
        
        if not allowed_file(pdf_file.filename):
            return jsonify({'error': 'Invalid file type. Only PDFs are allowed'}), 400

        # Validate watermark file if provided
        watermark_file = request.files.get('watermark_file')
        watermark_text = request.form.get('watermark_text', '').strip()
        
        if not watermark_file and not watermark_text:
            return jsonify({'error': 'Either watermark file or text is required'}), 400

        # Setup upload folder
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        # Create batch folder
        batch_id = str(uuid.uuid4())
        batch_folder = os.path.join(upload_folder, batch_id)
        os.makedirs(batch_folder, exist_ok=True)

        # Save original PDF
        original_pdf_name = secure_filename(pdf_file.filename)
        original_pdf_path = os.path.join(batch_folder, original_pdf_name)
        pdf_file.save(original_pdf_path)

        watermark_path = None
        if watermark_file:
            # Handle both PDF and image watermarks
            if allowed_file(watermark_file.filename, {'pdf'}):
                watermark_name = secure_filename(watermark_file.filename)
                watermark_path = os.path.join(batch_folder, watermark_name)
                watermark_file.save(watermark_path)
            elif allowed_file(watermark_file.filename, {'png', 'jpg', 'jpeg'}):
                # Convert image to PDF first
                watermark_name = secure_filename(watermark_file.filename.split('.')[0] + '.pdf')
                watermark_path = os.path.join(batch_folder, watermark_name)
                if not convert_to_pdf(watermark_file, watermark_path):
                    return jsonify({'error': 'Failed to process image watermark'}), 400
            else:
                return jsonify({'error': 'Watermark must be PDF or image (PNG/JPG)'}), 400

        # Get watermark parameters
        position = request.form.get('position', 'middle')
        opacity = int(request.form.get('opacity', 50))
        pages = request.form.get('pages', 'all')
        rotation = int(request.form.get('rotation', 0))

        # Validate parameters
        if opacity < 1 or opacity > 100:
            return jsonify({'error': 'Opacity must be between 1 and 100'}), 400
        
        if rotation < 0 or rotation > 360:
            return jsonify({'error': 'Rotation must be between 0 and 360 degrees'}), 400

        # Initialize iLovePDF
        public_key = current_app.config['ILOVEPDF_PUBLIC_KEY']
        ilovepdf = ILovePdf(public_key, verify_ssl=True)
        task = ilovepdf.new_task('watermark')
        
        # Configure watermark
        if watermark_path:
            task.file = watermark_path
            task.mode = 'image'
        else:
            task.text = watermark_text
            task.mode = 'text'
            task.font_family = request.form.get('font', 'Arial')
            
            font_style = request.form.get('font_style')
            if font_style in ['Bold', 'Italic']:
                task.font_style = font_style
                
            task.font_size = int(request.form.get('font_size', 20))
            task.font_color = request.form.get('color', '#000000')

        task.position = position
        task.transparency = opacity
        task.rotation = rotation
        task.pages = pages

        task.add_file(original_pdf_path)
        task.set_output_folder(batch_folder)
        task.execute()
        task.download()

        # Find watermarked file
        watermarked_files = [f for f in os.listdir(batch_folder) 
                          if f.endswith('.pdf') and f != original_pdf_name and (not watermark_path or f != os.path.basename(watermark_path))]
        
        if not watermarked_files:
            logger.error("No watermarked file found")
            return jsonify({'error': 'Watermark operation failed'}), 500

        # Prepare response
        watermarked_file = watermarked_files[0]
        watermarked_path = os.path.join(batch_folder, watermarked_file)
        
        # Rename file
        name_wo_ext = os.path.splitext(original_pdf_name)[0]
        new_filename = f"{name_wo_ext}_watermarked.pdf"
        new_path = os.path.join(batch_folder, new_filename)
        os.rename(watermarked_path, new_path)

        original_size = os.path.getsize(original_pdf_path)
        watermarked_size = os.path.getsize(new_path)

        # Clean up
        os.remove(original_pdf_path)
        if watermark_path and os.path.exists(watermark_path):
            os.remove(watermark_path)

        return jsonify({
            'success': True,
            'batch_id': batch_id,
            'watermarked_filename': new_filename,
            'original_size': original_size,
            'watermarked_size': watermarked_size,
            'download_url': f"{request.host_url}api/pdf-tools/download/{batch_id}/{new_filename}",
            'parameters': {
                'type': 'image' if watermark_path else 'text',
                'position': position,
                'opacity': opacity,
                'pages': pages,
                'rotation': rotation,
                'font_style': font_style if not watermark_path else None
            }
        })

    except Exception as e:
        logger.error(f"PDF watermark error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to add watermark',
            'details': str(e)
        }), 500 