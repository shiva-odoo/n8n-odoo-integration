import requests

# Replace with your actual webhook URL
N8N_WEBHOOK_URL = "https://kyrasteldeveloper.app.n8n.cloud/webhook/financial-upload"

def main(form, files):
    """
    Accepts metadata and multiple files, then forwards everything
    in ONE request to the n8n webhook.

    Expected input:
        form: dict with "company_name" and "email"
        files: list of FileStorage objects (Flask's request.files.getlist)

    Returns: dict with success/error status
    """
    company_name = form.get("company_name")
    email = form.get("email")

    if not files:
        return {"status": "error", "message": "No files uploaded"}

    # ✅ Immediate confirmation
    received_files = [file.filename for file in files]
    print(f"✅ Files received: {received_files}")

    # Prepare payload for n8n
    files_payload = []
    for file in files:
        file_bytes = file.read()
        files_payload.append(
            ("files", (file.filename, file_bytes, file.content_type))
        )

    try:
        # ✅ Send to n8n webhook
        response = requests.post(
            N8N_WEBHOOK_URL,
            files=files_payload,
            data={"company_name": company_name, "email": email},
            timeout=60,
        )

        if response.status_code == 200:
            try:
                return {
                    "status": "success",
                    "message": "Files received successfully and sent to webhook",
                    "received_files": received_files,
                    "n8n_response": response.json(),
                }
            except Exception:
                return {
                    "status": "success",
                    "message": "Files received successfully and sent to webhook",
                    "received_files": received_files,
                    "n8n_response": response.text,
                }
        else:
            return {
                "status": "partial",
                "message": "Files received successfully but webhook returned error",
                "received_files": received_files,
                "n8n_status": response.status_code,
                "n8n_response": response.text,
            }

    except Exception as e:
        return {
            "status": "error",
            "message": "Files received successfully but failed to send to webhook",
            "received_files": received_files,
            "error": str(e),
        }
