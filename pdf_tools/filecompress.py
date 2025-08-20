import os
from flask import Flask, Blueprint, request, jsonify, send_from_directory, current_app
from pylovepdf.ilovepdf import ILovePdf
from werkzeug.utils import secure_filename
from datetime import datetime
import logging
import uuid
from flask_cors import CORS

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask Blueprint
compress_bp = Blueprint('compress', __name__, url_prefix='/api/pdf-tools')

def allowed_file(filename):
    return '.' in filename and filename.lower().endswith('.pdf')

@compress_bp.route('/compress', methods=['POST'])
def compress_pdf():
    try:
        # Get and validate compression level
        frontend_level = request.form.get('compression_level', 'medium')
        
        # Map frontend levels to pylovepdf accepted values
        compression_mapping = {
            'low': 'low',
            'medium': 'recommended',
            'high': 'extreme'
        }
        
        # Default to 'recommended' if invalid value
        compression_level = compression_mapping.get(frontend_level, 'recommended')
        
        # Validate file upload
        if 'files' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400

        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400

        # Setup upload folder
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        # Create batch folder
        batch_id = str(uuid.uuid4())
        batch_folder = os.path.join(upload_folder, batch_id)
        os.makedirs(batch_folder, exist_ok=True)
        
        results = []
        total_original_size = 0
        total_compressed_size = 0
        
        for file in files:
            if not allowed_file(file.filename):
                logger.warning(f"Skipping invalid file: {file.filename}")
                continue

            # Save original file
            original_filename = secure_filename(file.filename)
            original_path = os.path.join(batch_folder, original_filename)
            file.save(original_path)
            logger.info(f"File saved: {original_path}")

            # Initialize iLovePDF with compression level
            public_key = current_app.config['ILOVEPDF_PUBLIC_KEY']
            ilovepdf = ILovePdf(public_key, verify_ssl=True)
            task = ilovepdf.new_task('compress')
            
            # Set the validated compression level
            task.compression_level = compression_level
            
            task.add_file(original_path)
            task.set_output_folder(batch_folder)
            task.execute()
            task.download()

            # Find compressed file
            pdf_files = [f for f in os.listdir(batch_folder) 
                        if f.endswith('.pdf') and f != original_filename]
            pdf_files.sort(key=lambda x: os.path.getmtime(os.path.join(batch_folder, x)), 
                         reverse=True)

            if not pdf_files:
                logger.error(f"No compressed file found for {original_filename}")
                continue

            compressed_file = pdf_files[0]
            compressed_path = os.path.join(batch_folder, compressed_file)

            # Rename compressed file
            name_wo_ext = os.path.splitext(original_filename)[0]
            today = datetime.now().strftime("%Y%m%d")
            new_filename = f"{name_wo_ext}_compressed_{frontend_level}_{today}.pdf"
            new_path = os.path.join(batch_folder, new_filename)
            os.rename(compressed_path, new_path)

            # Calculate stats
            original_size = os.path.getsize(original_path)
            compressed_size = os.path.getsize(new_path)
            reduction = ((original_size - compressed_size) / original_size) * 100
            
            total_original_size += original_size
            total_compressed_size += compressed_size

            results.append({
                'original_filename': original_filename,
                'compressed_filename': new_filename,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'reduction': round(reduction, 2),
                'compression_level': frontend_level  # Using frontend value for UI
            })

            # Remove original file
            os.remove(original_path)
            logger.info(f"Compression complete for {original_filename}")

        if not results:
            return jsonify({'error': 'No valid PDF files processed'}), 400

        total_reduction = ((total_original_size - total_compressed_size) / total_original_size) * 100

        return jsonify({
            'success': True,
            'batch_id': batch_id,
            'compression_level': frontend_level,
            'results': results,
            'total_original_size': total_original_size,
            'total_compressed_size': total_compressed_size,
            'total_reduction': round(total_reduction, 2)
        })

    except Exception as e:
        logger.error(f"PDF compression error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to compress PDF',
            'details': str(e)
        }), 500

@compress_bp.route('/download/<batch_id>/<filename>')
def download_file(batch_id, filename):
    try:
        upload_folder = current_app.config['UPLOAD_FOLDER']
        batch_folder = os.path.join(upload_folder, batch_id)
        
        if not os.path.exists(batch_folder):
            logger.error(f"Batch folder not found: {batch_folder}")
            return jsonify({'error': 'File not found'}), 404
            
        return send_from_directory(
            batch_folder,
            filename,
            as_attachment=True,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to download file',
            'details': str(e)
        }), 500

