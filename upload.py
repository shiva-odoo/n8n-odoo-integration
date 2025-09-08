import requests
import boto3
from datetime import datetime
from botocore.exceptions import ClientError
from decimal import Decimal
import os

# DynamoDB setup (using your existing pattern)
AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
batch_table = dynamodb.Table('batch_processing')

# Replace with your actual webhook URL
N8N_WEBHOOK_URL = "https://kyrasteldeveloper.app.n8n.cloud/webhook/financial-upload"

def convert_decimal(obj):
    """Convert DynamoDB Decimal objects to regular Python numbers"""
    if isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal(v) for v in obj]
    elif isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    else:
        return obj

def create_batch(username, company_name, email, files_list):
    """Create a new batch record in DynamoDB with collision-safe batch_id"""
    try:
        # Create collision-safe batch_id: batch_username_timestamp
        timestamp = int(datetime.utcnow().timestamp() * 1000)
        batch_id = f"batch_{username}_{timestamp}"
        
        batch_data = {
            'batch_id': batch_id,
            'username': username,
            'company_name': company_name,
            'email': email,
            'processing_stage': 'uploaded',
            'total_documents': len(files_list),
            'completed_documents': 0,
            'failed_documents': 0,
            'files': [{'filename': f.filename, 'status': 'uploaded'} for f in files_list],
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        batch_table.put_item(Item=batch_data)
        
        print(f"✅ Batch created: {batch_id} with {len(files_list)} files")
        
        return {
            "success": True,
            "batch_id": batch_id,
            "batch_data": batch_data
        }
        
    except Exception as e:
        print(f"❌ Error creating batch: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def update_batch_status(batch_id, status, error_message=None):
    """Update batch status (for error handling)"""
    try:
        update_expression = 'SET processing_stage = :status, updated_at = :updated'
        expression_values = {
            ':status': status,
            ':updated': datetime.utcnow().isoformat()
        }
        
        if error_message:
            update_expression += ', error_message = :error'
            expression_values[':error'] = error_message
        
        batch_table.update_item(
            Key={'batch_id': batch_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        print(f"✅ Batch {batch_id} status updated to: {status}")
        return {"success": True}
        
    except Exception as e:
        print(f"❌ Error updating batch status: {e}")
        return {"success": False, "error": str(e)}

def get_user_batches(username):
    """Get all batches for a user"""
    try:
        response = batch_table.query(
            IndexName='username-index',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('username').eq(username)
        )
        
        batches = response.get('Items', [])
        batches = convert_decimal(batches)
        
        # Sort by created_at descending (newest first)
        batches.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return {
            "success": True,
            "batches": batches,
            "total_count": len(batches)
        }
        
    except Exception as e:
        print(f"❌ Error getting user batches: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def get_incomplete_batches(username):
    """Get only incomplete batches for smart polling"""
    try:
        all_batches_result = get_user_batches(username)
        
        if not all_batches_result["success"]:
            return all_batches_result
        
        incomplete_stages = ['uploaded', 'processing', 'ai_complete', 'data_extracted', 'posted_to_accounting']
        incomplete_batches = [
            batch for batch in all_batches_result["batches"] 
            if batch.get('processing_stage') in incomplete_stages
        ]
        
        return {
            "success": True,
            "batches": incomplete_batches,
            "total_count": len(incomplete_batches)
        }
        
    except Exception as e:
        print(f"❌ Error getting incomplete batches: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def main(form, files):
    """
    Main upload function - handles batch creation and n8n forwarding
    
    Expected input:
        form: dict with metadata + user info from JWT
        files: list of FileStorage objects
    
    Returns: dict with success/error status and batch_id
    """
    company_name = form.get("company_name")
    email = form.get("email")
    username = form.get("user_id")
    company_id = form.get("company_id")

    if not files:
        return {"status": "error", "message": "No files uploaded"}

    received_files = [file.filename for file in files]
    print(f"✅ Files received from user {username}: {received_files}")

    # Step 1: Create batch record
    batch_result = create_batch(username, company_name, email, files)
    
    if not batch_result["success"]:
        return {
            "status": "error",
            "message": "Failed to create batch record",
            "error": batch_result["error"]
        }
    
    batch_id = batch_result["batch_id"]

    # Step 2: Prepare files for n8n
    files_payload = []
    for file in files:
        # Reset file pointer to beginning
        file.seek(0)
        file_bytes = file.read()
        files_payload.append(
            ("files", (file.filename, file_bytes, file.content_type))
        )

    try:
        # Step 3: Send to n8n webhook with batch context
        response = requests.post(
            N8N_WEBHOOK_URL,
            files=files_payload,
            data={
                "company_name": company_name,
                "email": email,
                "username": username,
                "company_id": company_id,
                "batch_id": batch_id  # This is key for n8n to update the batch
            },
            timeout=60,
        )

        if response.status_code == 200:
            try:
                n8n_response = response.json()
            except:
                n8n_response = response.text

            return {
                "status": "success",
                "message": "Files uploaded and processing started",
                "batch_id": batch_id,
                "received_files": received_files,
                "n8n_response": n8n_response,
            }
        else:
            # Webhook failed - update batch to error
            error_msg = f"Webhook failed with status {response.status_code}"
            update_batch_status(batch_id, "error", error_msg)
            
            return {
                "status": "error",
                "message": "Failed to start processing",
                "batch_id": batch_id,
                "received_files": received_files,
                "n8n_status": response.status_code,
                "n8n_response": response.text,
            }

    except Exception as e:
        # Network/timeout error - update batch to error
        error_msg = f"Upload failed: {str(e)}"
        update_batch_status(batch_id, "error", error_msg)
        
        return {
            "status": "error",
            "message": "Failed to upload files",
            "batch_id": batch_id,
            "received_files": received_files,
            "error": str(e),
        }