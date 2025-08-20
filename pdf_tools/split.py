import os
import logging
import uuid
from flask import Flask, Blueprint, request, jsonify, send_from_directory, current_app
from pylovepdf.ilovepdf import ILovePdf
from werkzeug.utils import secure_filename
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask Blueprint
split_bp = Blueprint('split', __name__, url_prefix='/api/pdf-tools')

def allowed_file(filename):
    return '.' in filename and filename.lower().endswith('.pdf')

@split_bp.route('/split', methods=['POST'])
def split_pdf():
    try:
        # Validate request data
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only PDFs are allowed'}), 400

        # Get split parameters
        split_mode = request.form.get('mode', 'ranges')  # 'ranges' or 'interval'
        pages = request.form.get('pages', '')  # For ranges mode: '1,3-5,7'
        interval = request.form.get('interval', '1')  # For interval mode
        
        # Validate parameters
        try:
            interval = int(interval)
            if interval < 1:
                raise ValueError("Interval must be at least 1")
        except ValueError as e:
            return jsonify({'error': f'Invalid interval: {str(e)}'}), 400

        # Setup upload folder
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        # Create batch folder
        batch_id = str(uuid.uuid4())
        batch_folder = os.path.join(upload_folder, batch_id)
        os.makedirs(batch_folder, exist_ok=True)

        # Save original file
        original_filename = secure_filename(file.filename)
        original_path = os.path.join(batch_folder, original_filename)
        file.save(original_path)
        logger.info(f"File saved: {original_path}")

        # Initialize iLovePDF
        public_key = current_app.config['ILOVEPDF_PUBLIC_KEY']
        ilovepdf = ILovePdf(public_key, verify_ssl=True)
        task = ilovepdf.new_task('split')
        
        # Configure split based on mode
        if split_mode == 'ranges':
            if not pages:
                return jsonify({'error': 'Page ranges required for ranges mode'}), 400
            task.ranges = pages
        else:  # interval mode
            task.split_mode = 'interval'
            task.fixed_range = interval

        task.add_file(original_path)
        task.set_output_folder(batch_folder)
        task.execute()
        task.download()

        # Find split files
        split_files = [f for f in os.listdir(batch_folder) 
                     if f.endswith('.pdf') and f != original_filename]
        split_files.sort()

        if not split_files:
            logger.error("No split files found")
            return jsonify({'error': 'Split operation failed'}), 500

        # Prepare response data
        results = []
        for i, filename in enumerate(split_files):
            file_path = os.path.join(batch_folder, filename)
            size = os.path.getsize(file_path)
            
            # Rename file to be more descriptive
            new_filename = f"{os.path.splitext(original_filename)[0]}_part_{i+1}.pdf"
            new_path = os.path.join(batch_folder, new_filename)
            os.rename(file_path, new_path)
            
            results.append({
                'filename': new_filename,
                'size': size,
                'download_url': f"{request.host_url}api/pdf-tools/download/{batch_id}/{new_filename}"
            })

        # Remove original file
        os.remove(original_path)

        return jsonify({
            'success': True,
            'batch_id': batch_id,
            'split_mode': split_mode,
            'parameters': {
                'pages': pages if split_mode == 'ranges' else None,
                'interval': interval if split_mode == 'interval' else None
            },
            'results': results,
            'total_parts': len(results)
        })

    except Exception as e:
        logger.error(f"PDF split error: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Failed to split PDF',
            'details': str(e)
        }), 500

@split_bp.route('/download/<batch_id>/<filename>')
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