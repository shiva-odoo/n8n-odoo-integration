# compliance.py
import boto3
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from decimal import Decimal
import os

# Configuration
AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
compliance_table = dynamodb.Table('compliance_items')

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

def get_compliance_items(company_id, status=None):
    """Get compliance items for a specific company"""
    try:
        # Build filter expression
        filter_expression = 'company_id = :company_id'
        expression_values = {':company_id': company_id}
        
        if status:
            filter_expression += ' AND #status = :status'
            expression_values[':status'] = status
        
        # Scan compliance items table
        if status:
            response = compliance_table.scan(
                FilterExpression=filter_expression,
                ExpressionAttributeValues=expression_values,
                ExpressionAttributeNames={'#status': 'status'}
            )
        else:
            response = compliance_table.scan(
                FilterExpression=filter_expression,
                ExpressionAttributeValues=expression_values
            )
        
        items = convert_decimal(response.get('Items', []))
        
        # Sort by priority and due date
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        items.sort(key=lambda x: (
            priority_order.get(x.get('priority', 'low'), 3),
            x.get('due_date', '')
        ))
        
        # Format items for frontend
        formatted_items = []
        for item in items:
            formatted_items.append({
                'compliance_id': item.get('compliance_id', ''),
                'title': item.get('title', ''),
                'description': item.get('description', ''),
                'category': item.get('category', 'general'),
                'status': item.get('status', 'pending'),
                'priority': item.get('priority', 'medium'),
                'due_date': item.get('due_date', ''),
                'created_at': item.get('created_at', ''),
                'completed_at': item.get('completed_at'),
                'assigned_to': item.get('assigned_to', ''),
                'notes': item.get('notes', '')
            })
        
        return {
            "success": True,
            "items": formatted_items,
            "total_count": len(formatted_items)
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

def create_compliance_item(company_id, item_data, created_by):
    """Create a new compliance item"""
    try:
        import uuid
        
        compliance_id = f"comp_{uuid.uuid4().hex[:12]}"
        
        item = {
            'compliance_id': compliance_id,
            'company_id': company_id,
            'title': item_data.get('title', ''),
            'description': item_data.get('description', ''),
            'category': item_data.get('category', 'general'),
            'status': item_data.get('status', 'pending'),
            'priority': item_data.get('priority', 'medium'),
            'due_date': item_data.get('due_date', ''),
            'created_at': datetime.utcnow().isoformat(),
            'created_by': created_by,
            'assigned_to': item_data.get('assigned_to', created_by),
            'notes': item_data.get('notes', '')
        }
        
        compliance_table.put_item(Item=item)
        
        print(f"Compliance item created: {compliance_id}")
        
        return {
            "success": True,
            "message": "Compliance item created successfully",
            "compliance_id": compliance_id,
            "item": convert_decimal(item)
        }
        
    except ClientError as e:
        print(f"DynamoDB error creating compliance item: {e}")
        return {
            "success": False,
            "error": "Failed to create compliance item"
        }
    except Exception as e:
        print(f"Error creating compliance item: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def update_compliance_item(compliance_id, company_id, update_data, updated_by):
    """Update a compliance item"""
    try:
        # Verify the item exists and belongs to the company
        response = compliance_table.get_item(
            Key={'compliance_id': compliance_id}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Compliance item not found"
            }
        
        item = convert_decimal(response['Item'])
        
        if item.get('company_id') != company_id:
            return {
                "success": False,
                "error": "Unauthorized to update this compliance item"
            }
        
        # Build update expression
        update_expressions = []
        expression_values = {}
        expression_names = {}
        
        updatable_fields = ['title', 'description', 'category', 'status', 'priority', 'due_date', 'notes', 'assigned_to']
        
        for field in updatable_fields:
            if field in update_data:
                placeholder = f"#{field}"
                value_placeholder = f":{field}"
                update_expressions.append(f"{placeholder} = {value_placeholder}")
                expression_values[value_placeholder] = update_data[field]
                expression_names[placeholder] = field
        
        # Add updated_at and updated_by
        update_expressions.append("#updated_at = :updated_at")
        update_expressions.append("#updated_by = :updated_by")
        expression_values[':updated_at'] = datetime.utcnow().isoformat()
        expression_values[':updated_by'] = updated_by
        expression_names['#updated_at'] = 'updated_at'
        expression_names['#updated_by'] = 'updated_by'
        
        # If status is being updated to 'completed', set completed_at
        if update_data.get('status') == 'completed':
            update_expressions.append("#completed_at = :completed_at")
            expression_values[':completed_at'] = datetime.utcnow().isoformat()
            expression_names['#completed_at'] = 'completed_at'
        
        if not update_expressions:
            return {
                "success": False,
                "error": "No valid fields to update"
            }
        
        update_expression = "SET " + ", ".join(update_expressions)
        
        compliance_table.update_item(
            Key={'compliance_id': compliance_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ExpressionAttributeNames=expression_names
        )
        
        print(f"Compliance item {compliance_id} updated by {updated_by}")
        
        return {
            "success": True,
            "message": "Compliance item updated successfully"
        }
        
    except ClientError as e:
        print(f"DynamoDB error updating compliance item: {e}")
        return {
            "success": False,
            "error": "Failed to update compliance item"
        }
    except Exception as e:
        print(f"Error updating compliance item: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def delete_compliance_item(compliance_id, company_id):
    """Delete a compliance item"""
    try:
        # Verify the item exists and belongs to the company
        response = compliance_table.get_item(
            Key={'compliance_id': compliance_id}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Compliance item not found"
            }
        
        item = convert_decimal(response['Item'])
        
        if item.get('company_id') != company_id:
            return {
                "success": False,
                "error": "Unauthorized to delete this compliance item"
            }
        
        compliance_table.delete_item(
            Key={'compliance_id': compliance_id}
        )
        
        print(f"Compliance item {compliance_id} deleted")
        
        return {
            "success": True,
            "message": "Compliance item deleted successfully"
        }
        
    except ClientError as e:
        print(f"DynamoDB error deleting compliance item: {e}")
        return {
            "success": False,
            "error": "Failed to delete compliance item"
        }
    except Exception as e:
        print(f"Error deleting compliance item: {e}")
        return {
            "success": False,
            "error": str(e)
        }

