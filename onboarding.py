import requests
import json

def main(form_data, files):
    """
    Process onboarding form data and files, then forward to n8n webhook
    
    Args:
        form_data: Flask request.form object containing form fields
        files: List of uploaded files from request.files.getlist()
    
    Returns:
        dict: Response with status and message
    """
    
    webhook_url = "https://kyrasteldeveloper.app.n8n.cloud/webhook-test/company-onboarding"
    
    try:
        # Prepare form data for n8n
        payload = {
            'companyName': form_data.get('companyName', ''),
            'registrationNo': form_data.get('registrationNo', ''),
            'vatNo': form_data.get('vatNo', ''),
            'repName': form_data.get('repName', ''),
            'repEmail': form_data.get('repEmail', ''),
        }
        
        # Prepare files for upload
        files_to_send = []
        for file in files:
            if file and file.filename:
                files_to_send.append(
                    ('files', (file.filename, file.stream, file.content_type))
                )
        
        print(f"📤 Sending onboarding data to n8n webhook...")
        print(f"📋 Company: {payload['companyName']}")
        print(f"📋 Registration: {payload['registrationNo']}")
        print(f"📋 Representative: {payload['repName']} ({payload['repEmail']})")
        print(f"📎 Files: {len(files_to_send)} files attached")
        
        # Send to n8n webhook
        response = requests.post(
            webhook_url,
            data=payload,
            files=files_to_send,
            timeout=30  # 30 second timeout
        )
        
        print(f"📨 n8n Response Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                n8n_response = response.json()
                print(f"✅ n8n Response: {n8n_response}")
            except json.JSONDecodeError:
                n8n_response = {"message": "Success", "raw_response": response.text}
                
            return {
                "status": "success",
                "message": "Onboarding submitted successfully. Login credentials will be emailed to you after approval.",
                "n8n_response": n8n_response
            }
        else:
            print(f"❌ n8n Error: {response.status_code} - {response.text}")
            return {
                "status": "error",
                "message": f"Failed to submit onboarding. n8n returned status {response.status_code}",
                "details": response.text
            }
            
    except requests.exceptions.Timeout:
        print("⏰ Request to n8n webhook timed out")
        return {
            "status": "error",
            "message": "Request timed out. Please try again.",
            "error_type": "timeout"
        }
        
    except requests.exceptions.ConnectionError:
        print("🔌 Connection error to n8n webhook")
        return {
            "status": "error", 
            "message": "Unable to connect to processing service. Please try again later.",
            "error_type": "connection_error"
        }
        
    except Exception as e:
        print(f"💥 Unexpected error: {str(e)}")
        return {
            "status": "error",
            "message": "An unexpected error occurred during onboarding submission.",
            "error": str(e)
        }