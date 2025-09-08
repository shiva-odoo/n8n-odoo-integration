import boto3
from datetime import datetime
from botocore.exceptions import ClientError
import os

# Configuration from environment variables
AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')

# AWS clients with consistent region configuration
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
batch_table = dynamodb.Table('batch_processing')

def update_batch_status(batch_id, status_data):
    """Update batch processing status - specifically for n8n workflow updates"""
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
        
        # Validate that batch exists
        response = batch_table.get_item(
            Key={'batch_id': batch_id}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Batch not found"
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