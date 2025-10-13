# dashboard.py
import boto3
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from decimal import Decimal
import os

# Configuration
AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
batches_table = dynamodb.Table('processing_batches')
users_table = dynamodb.Table('users')

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

def get_dashboard_metrics(company_id, username):
    """Get dashboard metrics for a specific company"""
    try:
        # Get company's processing batches
        response = batches_table.scan(
            FilterExpression='company_id = :company_id',
            ExpressionAttributeValues={
                ':company_id': company_id
            }
        )
        
        batches = convert_decimal(response.get('Items', []))
        
        # Calculate metrics
        total_documents = 0
        completed_documents = 0
        pending_items = 0
        
        for batch in batches:
            files = batch.get('files', [])
            total_documents += len(files)
            
            for file in files:
                if file.get('status') == 'complete':
                    completed_documents += 1
                elif file.get('status') in ['uploaded', 'processing', 'pending']:
                    pending_items += 1
        
        # Calculate compliance status (percentage of completed documents)
        compliance_status = "0%"
        if total_documents > 0:
            compliance_percentage = (completed_documents / total_documents) * 100
            compliance_status = f"{compliance_percentage:.0f}%"
        
        # Mock monthly revenue (you can replace this with actual accounting data)
        monthly_revenue = "0"
        
        return {
            "success": True,
            "data": {
                "documents_processed": completed_documents,
                "total_documents": total_documents,
                "monthly_revenue": monthly_revenue,
                "compliance_status": compliance_status,
                "pending_items": pending_items
            }
        }
        
    except ClientError as e:
        print(f"DynamoDB error getting dashboard metrics: {e}")
        return {
            "success": False,
            "error": "Failed to retrieve dashboard metrics"
        }
    except Exception as e:
        print(f"Error getting dashboard metrics: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def get_recent_documents(company_id, limit=10):
    """Get recent documents for a specific company"""
    try:
        # Get company's processing batches
        response = batches_table.scan(
            FilterExpression='company_id = :company_id',
            ExpressionAttributeValues={
                ':company_id': company_id
            }
        )
        
        batches = convert_decimal(response.get('Items', []))
        
        # Extract all files from batches
        all_documents = []
        for batch in batches:
            batch_id = batch.get('batch_id')
            batch_created_at = batch.get('created_at', '')
            
            files = batch.get('files', [])
            for file in files:
                all_documents.append({
                    'batch_id': batch_id,
                    'filename': file.get('filename', 'Unknown'),
                    'document_type': file.get('document_type', 'unknown'),
                    'status': file.get('status', 'uploaded'),
                    'processed_at': file.get('processed_at') or batch_created_at,
                    'uploaded_at': batch_created_at
                })
        
        # Sort by processed_at (most recent first)
        all_documents.sort(key=lambda x: x.get('processed_at', ''), reverse=True)
        
        # Limit results
        recent_documents = all_documents[:limit]
        
        return {
            "success": True,
            "documents": recent_documents,
            "total_count": len(all_documents)
        }
        
    except ClientError as e:
        print(f"DynamoDB error getting recent documents: {e}")
        return {
            "success": False,
            "error": "Failed to retrieve recent documents"
        }
    except Exception as e:
        print(f"Error getting recent documents: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def get_compliance_items(company_id):
    """Get compliance items/tasks for a specific company"""
    try:
        # Get pending/incomplete documents
        response = batches_table.scan(
            FilterExpression='company_id = :company_id',
            ExpressionAttributeValues={
                ':company_id': company_id
            }
        )
        
        batches = convert_decimal(response.get('Items', []))
        
        compliance_items = []
        
        for batch in batches:
            files = batch.get('files', [])
            
            for file in files:
                status = file.get('status', 'uploaded')
                
                # Create compliance items for documents that need action
                if status in ['uploaded', 'processing', 'pending', 'error']:
                    item_status = 'pending' if status in ['uploaded', 'processing', 'pending'] else 'overdue'
                    
                    compliance_items.append({
                        'id': f"{batch.get('batch_id')}_{file.get('filename')}",
                        'title': f"Process {file.get('document_type', 'document')}: {file.get('filename')}",
                        'description': f"Complete processing of {file.get('filename')}",
                        'status': item_status,
                        'due_date': batch.get('created_at', ''),
                        'priority': 'high' if status == 'error' else 'medium',
                        'category': 'document_processing'
                    })
        
        # Sort by priority and status
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        compliance_items.sort(key=lambda x: (priority_order.get(x['priority'], 3), x['status']))
        
        return {
            "success": True,
            "items": compliance_items,
            "total_count": len(compliance_items)
        }
        
    except ClientError as e:
        print(f"DynamoDB error getting compliance items: {e}")
        return {
            "success": False,
            "error": "Failed to retrieve compliance items"
        }
    except Exception as e:
        print(f"Error getting compliance items: {e}")
        return {
            "success": False,
            "error": str(e)
        }

