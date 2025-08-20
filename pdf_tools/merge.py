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
merge_bp = Blueprint('merge', __name__, url_prefix='/api/pdf-tools')

def allowed_file(filename):
    return '.' in filename and filename.lower().endswith('.pdf')

@merge_bp.route('/merge', methods=['POST'])
def merge_pdfs():
    try:
        # Validate file upload
        if 'files' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400

        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400

        # Check if at least 2 files are provided for merging
        if len(files) < 2:
            return jsonify({'error': 'At least 2 PDFs required for merging'}), 400

        # Setup upload folder
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        # Create batch folder
        batch_id = str(uuid.uuid4())
        batch_folder = os.path.join(upload_folder, batch_id)
        os.makedirs(batch_folder, exist_ok=True)
        
        # Save all uploaded files
        original_filenames = []
        total_original_size = 0
        
        for file in files:
            if not allowed_file(file.filename):
                logger.warning(f"Skipping invalid file: {file.filename}")
                continue

            # Save original file
            original_filename = secure_filename(file.filename)
            original_path = os.path.join(batch_folder, original_filename)
            file.save(original_path)
            original_filenames.append(original_filename)
            total_original_size += os.path.getsize(original_path)
            logger.info(f"File saved: {original_path}")

        if len(original_filenames) < 2:
            return jsonify({'error': 'Not enough valid PDFs for merging'}), 400

        # Initialize iLovePDF
        public_key = current_app.config['ILOVEPDF_PUBLIC_KEY']
        ilovepdf = ILovePdf(public_key, verify_ssl=True)
        task = ilovepdf.new_task('merge')
        
        # Add all files to the merge task
        for filename in original_filenames:
            file_path = os.path.join(batch_folder, filename)
            task.add_file(file_path)
        
        task.set_output_folder(batch_folder)
        task.execute()
        task.download()

        # Find merged file (should be the newest PDF in the folder)
        pdf_files = [f for f in os.listdir(batch_folder) if f.endswith('.pdf')]
        pdf_files.sort(key=lambda x: os.path.getmtime(os.path.join(batch_folder, x)), 
                     reverse=True)

        if not pdf_files:
            logger.error("No merged file found")
            return jsonify({'error': 'Merge operation failed'}), 500

        merged_file = pdf_files[0]
        merged_path = os.path.join(batch_folder, merged_file)

        # Rename merged file
        today = datetime.now().strftime("%Y%m%d")
        new_filename = f"merged_{today}.pdf"
        new_path = os.path.join(batch_folder, new_filename)
        os.rename(merged_path, new_path)

        # Calculate stats
        merged_size = os.path.getsize(new_path)
        reduction = ((total_original_size - merged_size) / total_original_size) * 100 if total_original_size > 0 else 0

        # Clean up original files
        for filename in original_filenames:
            file_path = os.path.join(batch_folder, filename)
            if os.path.exists(file_path):
                os.remove(file_path)

        return jsonify({
            'success': True,
            'batch_id': batch_id,
            'merged_filename': new_filename,
            'merged_size': merged_size,
            'total_original_size': total_original_size,
            'size_reduction': round(reduction, 2),
            'files_merged': len(original_filenames)
        })

    except Exception as e:
        logger.error(f"PDF merge error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to merge PDFs',
            'details': str(e)
        }), 500

@merge_bp.route('/download/<batch_id>/<filename>')
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