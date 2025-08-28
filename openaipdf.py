from flask import request, jsonify
import io
import PyPDF2
import os
from werkzeug.utils import secure_filename

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

def main(data):
    """Main function to process PDF file"""
    file = data.get('file')
    
    if not file:
        return {'success': False, 'error': 'No file provided'}
    
    # Check if file was selected
    if file.filename == '':
        return {'success': False, 'error': 'No file selected'}
    
    # Validate file type (more robust check)
    if not allowed_file(file.filename):
        return {'success': False, 'error': 'Only PDF files allowed'}
    
    # Read file content
    pdf_content = file.read()
    
    # Reset file pointer for potential re-reading
    file.seek(0)
    
    # Process PDF (example: extract text)
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
    except Exception as e:
        return {'success': False, 'error': f'Failed to process PDF: {str(e)}'}
    
    # Save file if needed
    try:
        # Create uploads directory if it doesn't exist
        upload_folder = 'uploads'
        os.makedirs(upload_folder, exist_ok=True)
        
        # Secure the filename
        filename = secure_filename(file.filename)
        filepath = os.path.join(upload_folder, filename)
        
        with open(filepath, "wb") as f:
            f.write(pdf_content)
    except Exception as e:
        return {'success': False, 'error': f'Failed to save file: {str(e)}'}
    
    return {
        'success': True,
        'data': {
            "filename": file.filename,
            "size": len(pdf_content),
            "text_preview": text[:500],  # First 500 chars
            "pages": len(pdf_reader.pages),
            "status": "success"
        }
    }
