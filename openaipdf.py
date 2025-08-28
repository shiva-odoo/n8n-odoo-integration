from flask import request, jsonify
import io
import PyPDF2
import os
from werkzeug.utils import secure_filename

def main(data):
    """Main function to process PDF binary data"""
    pdf_content = data.get('pdf_content')
    filename = data.get('filename', 'uploaded.pdf')
    
    if not pdf_content:
        return {'success': False, 'error': 'No file data provided'}
    
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
        safe_filename = secure_filename(filename)
        filepath = os.path.join(upload_folder, safe_filename)
        
        with open(filepath, "wb") as f:
            f.write(pdf_content)
    except Exception as e:
        return {'success': False, 'error': f'Failed to save file: {str(e)}'}
    
    return {
        'success': True,
        'data': {
            "filename": filename,
            "size": len(pdf_content),
            "text_preview": text[:500],  # First 500 chars
            "pages": len(pdf_reader.pages),
            "status": "success"
        }
    }