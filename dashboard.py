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
batches_table = dynamodb.Table('batch_processing')
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
        # Get company's processing batches by username
        response = batches_table.scan(
            FilterExpression='username = :username',
            ExpressionAttributeValues={
                ':username': username
            }
        )
        
        batches = convert_decimal(response.get('Items', []))
        
        # Calculate metrics from batch data
        total_documents = 0
        completed_documents = 0
        failed_documents = 0
        pending_items = 0
        total_batches = len(batches)
        
        for batch in batches:
            # Use batch-level counters if available
            batch_total = batch.get('total_documents', 0)
            batch_completed = batch.get('completed_documents', 0)
            batch_failed = batch.get('failed_documents', 0)
            
            if batch_total > 0:
                total_documents += batch_total
                completed_documents += batch_completed
                failed_documents += batch_failed
            else:
                # Fallback: count from files array
                files = batch.get('files', [])
                total_documents += len(files)
                
                for file in files:
                    status = file.get('status', 'uploaded')
                    if status == 'complete':
                        completed_documents += 1
                    elif status == 'error':
                        failed_documents += 1
                    elif status in ['uploaded', 'processing', 'pending']:
                        pending_items += 1
        
        # Calculate compliance status (percentage of completed documents)
        compliance_status = "0%"
        if total_documents > 0:
            compliance_percentage = (completed_documents / total_documents) * 100
            compliance_status = f"{compliance_percentage:.0f}%"
        
        # Mock monthly revenue (replace with actual accounting data if available)
        monthly_revenue = "0"
        
        return {
            "success": True,
            "data": {
                "documents_processed": completed_documents,
                "total_documents": total_documents,
                "documents_failed": failed_documents,
                "pending_items": pending_items,
                "total_batches": total_batches,
                "monthly_revenue": monthly_revenue,
                "compliance_status": compliance_status
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

def get_recent_documents(company_id, username, limit=10):
    """Get recent documents for a specific company"""
    try:
        # Get company's processing batches by username
        response = batches_table.scan(
            FilterExpression='username = :username',
            ExpressionAttributeValues={
                ':username': username
            }
        )
        
        batches = convert_decimal(response.get('Items', []))
        
        # Extract all files from batches
        all_documents = []
        for batch in batches:
            batch_id = batch.get('batch_id')
            batch_created_at = batch.get('created_at', '')
            batch_stage = batch.get('processing_stage', 'uploaded')
            company_name = batch.get('company_name', '')
            
            files = batch.get('files', [])
            for file in files:
                all_documents.append({
                    'batch_id': batch_id,
                    'filename': file.get('filename', 'Unknown'),
                    'document_type': file.get('document_type', 'unknown'),
                    'status': file.get('status', 'uploaded'),
                    'file_size': file.get('size', 0),
                    'content_type': file.get('content_type', 'application/pdf'),
                    'processed_at': file.get('processed_at') or batch_created_at,
                    'uploaded_at': batch_created_at,
                    'batch_stage': batch_stage,
                    'company_name': company_name
                })
        
        # Sort by processed_at or uploaded_at (most recent first)
        all_documents.sort(key=lambda x: x.get('processed_at', x.get('uploaded_at', '')), reverse=True)
        
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

def get_compliance_items(company_id, username):
    """Get compliance items/tasks for a specific company"""
    try:
        # Get pending/incomplete batches by username
        response = batches_table.scan(
            FilterExpression='username = :username',
            ExpressionAttributeValues={
                ':username': username
            }
        )
        
        batches = convert_decimal(response.get('Items', []))
        
        compliance_items = []
        
        for batch in batches:
            batch_id = batch.get('batch_id')
            batch_stage = batch.get('processing_stage', 'uploaded')
            batch_created = batch.get('created_at', '')
            
            files = batch.get('files', [])
            
            for file in files:
                status = file.get('status', 'uploaded')
                filename = file.get('filename', 'Unknown')
                doc_type = file.get('document_type', 'document')
                
                # Create compliance items for documents that need action
                if status in ['uploaded', 'processing', 'pending', 'error']:
                    # Determine item status and priority
                    if status == 'error':
                        item_status = 'overdue'
                        priority = 'high'
                        title = f"⚠️ Fix error in {doc_type}"
                    elif status == 'pending':
                        item_status = 'pending'
                        priority = 'high'
                        title = f"Review pending {doc_type}"
                    else:
                        item_status = 'pending'
                        priority = 'medium'
                        title = f"Processing {doc_type}"
                    
                    compliance_items.append({
                        'id': f"{batch_id}_{filename}",
                        'title': title,
                        'description': f"{filename} - Status: {status}",
                        'status': item_status,
                        'due_date': batch_created,
                        'priority': priority,
                        'category': 'document_processing',
                        'batch_id': batch_id,
                        'document_type': doc_type,
                        'batch_stage': batch_stage
                    })
        
        # Sort by priority (high first) and status
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        status_order = {'overdue': 0, 'pending': 1, 'completed': 2}
        
        compliance_items.sort(key=lambda x: (
            priority_order.get(x['priority'], 3),
            status_order.get(x['status'], 3)
        ))
        
        return {
            "success": True,
            "items": compliance_items,
            "total_count": len(compliance_items),
            "high_priority_count": len([i for i in compliance_items if i['priority'] == 'high']),
            "overdue_count": len([i for i in compliance_items if i['status'] == 'overdue'])
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

