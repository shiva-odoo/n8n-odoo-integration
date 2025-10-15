import boto3
from datetime import datetime
from botocore.exceptions import ClientError
import os

# Configuration from environment variables
AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')

# AWS clients with consistent region configuration
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
batch_table = dynamodb.Table('batch_processing')

def update_batch_status(batch_id, status_data, username=None, company_name=None):
    """Update batch processing status - specifically for n8n workflow updates
    
    Args:
        batch_id: The batch ID to update
        status_data: Dictionary with status updates
        username: Optional - verify batch belongs to this user
        company_name: Optional - verify batch belongs to this company
    """
    try:
        # Validate input
        if not batch_id:
            return {
                "success": False,
                "error": "batch_id is required"
            }
        
        if not status_data or not isinstance(status_data, dict):
            return {
                "success": False,
                "error": "status_data must be a non-empty dictionary"
            }
        
        # Validate that batch exists and belongs to the correct company/user
        response = batch_table.get_item(
            Key={'batch_id': batch_id}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Batch not found"
            }
        
        # Verify company/user ownership if provided
        batch_item = response['Item']
        if username and batch_item.get('username') != username:
            return {
                "success": False,
                "error": "Batch does not belong to this user"
            }
        
        if company_name and batch_item.get('company_name') != company_name:
            return {
                "success": False,
                "error": "Batch does not belong to this company"
            }
        
        # Build update expression dynamically based on provided fields
        update_expression_parts = []
        expression_values = {
            ':updated_at': datetime.utcnow().isoformat()
        }
        
        # Always update the timestamp
        update_expression_parts.append('updated_at = :updated_at')
        
        # Handle processing_stage
        if 'processing_stage' in status_data:
            update_expression_parts.append('processing_stage = :stage')
            expression_values[':stage'] = status_data['processing_stage']
        
        # Handle completed_documents
        if 'completed_documents' in status_data:
            update_expression_parts.append('completed_documents = :completed')
            expression_values[':completed'] = status_data['completed_documents']
        
        # Handle failed_documents
        if 'failed_documents' in status_data:
            update_expression_parts.append('failed_documents = :failed')
            expression_values[':failed'] = status_data['failed_documents']
        
        # Handle error_message
        if 'error_message' in status_data:
            update_expression_parts.append('error_message = :error_msg')
            expression_values[':error_msg'] = status_data['error_message']
        
        # Construct the update expression
        update_expression = 'SET ' + ', '.join(update_expression_parts)
        
        # Update the batch
        batch_table.update_item(
            Key={'batch_id': batch_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        print(f"✅ Updated batch {batch_id} with status: {status_data.get('processing_stage', 'N/A')}")
        
        return {
            "success": True,
            "message": f"Successfully updated batch {batch_id}",
            "batch_id": batch_id,
            "updated_fields": list(status_data.keys())
        }
        
    except ClientError as e:
        print(f"❌ DynamoDB error updating batch: {e}")
        return {
            "success": False,
            "error": "Failed to update batch status"
        }
    except Exception as e:
        print(f"❌ Error updating batch status: {e}")
        return {
            "success": False,
            "error": "Batch update process failed"
        }
    
def update_file_status(batch_id, file_id, file_status_data, username=None, company_name=None):
    """Update individual file status within a batch
    
    Args:
        batch_id: The batch ID to update
        file_id: The file ID within the batch to update
        file_status_data: Dictionary with file status updates
        username: Optional - verify batch belongs to this user
        company_name: Optional - verify batch belongs to this company
    """
    try:
        # Validate input
        if not batch_id:
            return {
                "success": False,
                "error": "batch_id is required"
            }
        
        if not file_id:
            return {
                "success": False,
                "error": "file_id is required"
            }
        
        if not file_status_data or not isinstance(file_status_data, dict):
            return {
                "success": False,
                "error": "file_status_data must be a non-empty dictionary"
            }
        
        # Get the current batch
        response = batch_table.get_item(
            Key={'batch_id': batch_id}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Batch not found"
            }
        
        batch_item = response['Item']
        
        # Verify company/user ownership if provided
        if username and batch_item.get('username') != username:
            return {
                "success": False,
                "error": "Batch does not belong to this user"
            }
        
        if company_name and batch_item.get('company_name') != company_name:
            return {
                "success": False,
                "error": "Batch does not belong to this company"
            }
        files_list = batch_item.get('files', [])
        
        # Find the file to update
        file_found = False
        updated_files = []
        
        for file_item in files_list:
            if file_item.get('file_id') == file_id:
                file_found = True
                # Update the file with new status data
                updated_file = dict(file_item)  # Create a copy
                
                # Update allowed fields
                if 'status' in file_status_data:
                    updated_file['status'] = file_status_data['status']
                
                if 'document_type' in file_status_data:
                    updated_file['document_type'] = file_status_data['document_type']
                
                # Add processing timestamp for this file
                updated_file['processed_at'] = datetime.utcnow().isoformat()
                
                updated_files.append(updated_file)
            else:
                updated_files.append(file_item)
        
        if not file_found:
            return {
                "success": False,
                "error": f"File with file_id {file_id} not found in batch"
            }
        
        # Calculate progress based on file statuses
        completed_files = len([f for f in updated_files if f.get('status') == 'complete'])
        pending_files = len([f for f in updated_files if f.get('status') == 'pending'])
        
        # Determine batch processing stage based on file statuses
        batch_stage = batch_item.get('processing_stage', 'uploaded')
        
        # If all files are complete, mark batch as ready for next stage
        if completed_files == len(updated_files):
            # You can customize this logic based on your workflow
            if batch_stage in ['uploaded', 'processing', 'ai_complete']:
                batch_stage = 'ai_complete'  # Files processed, ready for data extraction
        
        # Update the batch with new files list and progress
        update_expression = '''
            SET files = :files, 
                completed_documents = :completed, 
                updated_at = :updated_at,
                processing_stage = :stage
        '''
        
        expression_values = {
            ':files': updated_files,
            ':completed': completed_files,
            ':updated_at': datetime.utcnow().isoformat(),
            ':stage': batch_stage
        }
        
        batch_table.update_item(
            Key={'batch_id': batch_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        print(f"✅ Updated file {file_id} in batch {batch_id}")
        print(f"   Status: {file_status_data.get('status', 'N/A')}")
        print(f"   Document Type: {file_status_data.get('document_type', 'N/A')}")
        print(f"   Batch Progress: {completed_files}/{len(updated_files)} files completed")
        
        return {
            "success": True,
            "message": f"Successfully updated file {file_id}",
            "batch_id": batch_id,
            "file_id": file_id,
            "updated_fields": list(file_status_data.keys()),
            "batch_progress": {
                "completed_files": completed_files,
                "total_files": len(updated_files),
                "pending_files": pending_files
            }
        }
        
    except ClientError as e:
        print(f"❌ DynamoDB error updating file: {e}")
        return {
            "success": False,
            "error": "Failed to update file status"
        }
    except Exception as e:
        print(f"❌ Error updating file status: {e}")
        return {
            "success": False,
            "error": "File update process failed"
        }
