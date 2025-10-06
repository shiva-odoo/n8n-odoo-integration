import requests
import boto3
from datetime import datetime
from botocore.exceptions import ClientError
from decimal import Decimal
import os
import uuid
import json

# DynamoDB setup
AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
batch_table = dynamodb.Table('batch_processing')
users_table = dynamodb.Table('users')

# Replace with your actual webhook URL
N8N_WEBHOOK_URL = "https://kyrasteldeveloper.app.n8n.cloud/webhook/financial-upload"

# ============================================
# REQUIRED FIELDS CONFIGURATION
# ============================================

REQUIRED_FIELDS = {
    "tax_information": {
        "vat_period_category": ["category_a", "category_b", "category_c", "not_applicable"],
        "vat_rates": ["19", "9", "5", "mixed"]
    },
    "payroll_information": {
        "num_employees": "integer",
        "payroll_frequency": ["monthly", "bi_weekly", "weekly", "no_employees"],
        "uses_ghs": "boolean",
        "social_insurance": ["employee_employer", "employer_only", "not_applicable"]
    },
    "banking_information": {
        "primary_bank": "string",
        "primary_currency": ["EUR", "USD", "GBP", "other"]
    },
    "business_operations": {
        "seasonal_business": "boolean",
        "multi_location": "boolean",
        "international": "boolean",
        "inventory_management": ["physical", "digital", "none"]
    }
}

# ============================================
# UTILITY FUNCTIONS
# ============================================

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


def sanitize_for_dynamodb(data):
    """
    Sanitize data for DynamoDB storage - remove empty strings and UI-only fields
    DynamoDB doesn't accept empty strings as values
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Skip UI-only fields that shouldn't be stored
            if key in ['secondary_bank_input', 'currency_input']:
                continue
            
            if isinstance(value, str):
                # Only include non-empty strings
                if value.strip():
                    sanitized[key] = value.strip()
            elif isinstance(value, (dict, list)):
                # Recursively sanitize nested structures
                sanitized_value = sanitize_for_dynamodb(value)
                if sanitized_value:  # Only include if not empty
                    sanitized[key] = sanitized_value
            elif value is not None:
                # Include all other non-None values (booleans, numbers, etc.)
                sanitized[key] = value
        return sanitized
    elif isinstance(data, list):
        return [sanitize_for_dynamodb(item) for item in data if item]
    else:
        return data

# ============================================
# FINANCIAL PROFILE FUNCTIONS
# ============================================

def get_financial_profile(username):
    """Retrieve user's financial profile"""
    try:
        response = users_table.get_item(Key={'username': username})
        
        if 'Item' not in response:
            return {
                "exists": False,
                "upload_ready": False,
                "is_vat_registered": False
            }
        
        user = response['Item']
        user = convert_decimal(user)
        
        # Get VAT registration status
        is_vat_registered = user.get('is_vat_registered')
        # Handle both string ('yes'/'no') and boolean formats
        if isinstance(is_vat_registered, str):
            is_vat_registered = is_vat_registered.lower() == 'yes'
        elif is_vat_registered is None:
            is_vat_registered = False
        
        return {
            "exists": True,
            "upload_ready": user.get('upload_ready', False),
            "is_vat_registered": is_vat_registered,
            "profile_completed_at": user.get('profile_completed_at'),
            "profile_last_updated": user.get('profile_last_updated'),
            "tax_information": user.get('tax_information', {}),
            "payroll_information": user.get('payroll_information', {}),
            "banking_information": user.get('banking_information', {}),
            "business_operations": user.get('business_operations', {}),
            "special_circumstances": user.get('special_circumstances', {})
        }
        
    except Exception as e:
        print(f"Error getting financial profile: {e}")
        raise


def validate_financial_data(data):
    """Validate financial profile data"""
    errors = []
    
    # Get VAT registration status from data (passed from frontend or fetched separately)
    is_vat_registered = data.get('is_vat_registered', False)
    
    # Validate tax_information based on VAT registration status
    tax_info = data.get('tax_information', {})
    
    if is_vat_registered:
        # Full VAT validation for registered users
        if not tax_info.get('vat_period_category'):
            errors.append("VAT period category is required")
        elif tax_info['vat_period_category'] not in REQUIRED_FIELDS['tax_information']['vat_period_category']:
            errors.append("Invalid VAT period category")
        
        if not tax_info.get('vat_rates') or len(tax_info['vat_rates']) == 0:
            errors.append("At least one VAT rate must be selected")
    else:
        # Simplified validation for non-VAT registered users
        if not tax_info.get('reverse_charge') or len(tax_info['reverse_charge']) == 0:
            errors.append("At least one reverse charge scenario must be selected")
        
        # If 'other' is selected, ensure the text field is filled
        if 'other' in tax_info.get('reverse_charge', []) and not tax_info.get('reverse_charge_other', '').strip():
            errors.append("Please specify the other reverse charge category")
    
    # Validate payroll_information
    payroll_info = data.get('payroll_information', {})
    if 'num_employees' not in payroll_info:
        errors.append("Number of employees is required")
    elif not isinstance(payroll_info['num_employees'], int) or payroll_info['num_employees'] < 0:
        errors.append("Number of employees must be a non-negative integer")
    
    if not payroll_info.get('payroll_frequency'):
        errors.append("Payroll frequency is required")
    elif payroll_info['payroll_frequency'] not in REQUIRED_FIELDS['payroll_information']['payroll_frequency']:
        errors.append("Invalid payroll frequency")
    
    if 'uses_ghs' not in payroll_info:
        errors.append("GHS usage must be specified")
    elif not isinstance(payroll_info['uses_ghs'], bool):
        errors.append("GHS usage must be true or false")
    
    if not payroll_info.get('social_insurance'):
        errors.append("Social insurance type is required")
    elif payroll_info['social_insurance'] not in REQUIRED_FIELDS['payroll_information']['social_insurance']:
        errors.append("Invalid social insurance type")
    
    # Validate banking_information
    banking_info = data.get('banking_information', {})
    if not banking_info.get('primary_bank', '').strip():
        errors.append("Primary bank is required")
    
    if not banking_info.get('primary_currency'):
        errors.append("Primary currency is required")
    elif banking_info['primary_currency'] not in REQUIRED_FIELDS['banking_information']['primary_currency']:
        errors.append("Invalid primary currency")
    
    # Validate multi-currency conditional
    if banking_info.get('multi_currency') and not banking_info.get('currencies_list'):
        errors.append("Currency list required when multi-currency is enabled")
    
    # Validate business_operations
    ops_info = data.get('business_operations', {})
    if 'seasonal_business' not in ops_info:
        errors.append("Seasonal business status is required")
    elif not isinstance(ops_info['seasonal_business'], bool):
        errors.append("Seasonal business must be true or false")
    
    if 'multi_location' not in ops_info:
        errors.append("Multi-location status is required")
    elif not isinstance(ops_info['multi_location'], bool):
        errors.append("Multi-location must be true or false")
    
    if 'international' not in ops_info:
        errors.append("International operations status is required")
    elif not isinstance(ops_info['international'], bool):
        errors.append("International operations must be true or false")
    
    if not ops_info.get('inventory_management'):
        errors.append("Inventory management type is required")
    elif ops_info['inventory_management'] not in REQUIRED_FIELDS['business_operations']['inventory_management']:
        errors.append("Invalid inventory management type")
    
    # Validate conditional fields
    if ops_info.get('seasonal_business') and not ops_info.get('peak_seasons', '').strip():
        errors.append("Peak seasons required when seasonal business is enabled")
    
    if ops_info.get('multi_location') and not ops_info.get('num_locations'):
        errors.append("Number of locations required when multi-location is enabled")
    
    if ops_info.get('international') and not ops_info.get('international_countries', '').strip():
        errors.append("Countries required when international operations are enabled")
    
    # Validate special_circumstances (optional but validate structure if provided)
    special = data.get('special_circumstances', {})
    
    # Construction validation
    construction = special.get('construction', {})
    if construction.get('enabled') is True:
        if not construction.get('project_duration', '').strip():
            errors.append("Project duration required when construction is enabled")
    
    # Professional services validation
    prof_services = special.get('professional_services', {})
    if prof_services.get('enabled') is True:
        if not prof_services.get('service_type', '').strip():
            errors.append("Service type required when professional services is enabled")
    
    # Retail/E-commerce validation
    retail = special.get('retail_ecommerce', {})
    if retail.get('enabled') is True:
        if not retail.get('platform_type', '').strip():
            errors.append("Platform type required when retail/e-commerce is enabled")
    
    # Manufacturing validation
    manufacturing = special.get('manufacturing', {})
    if manufacturing.get('enabled') is True:
        if not manufacturing.get('product_type', '').strip():
            errors.append("Product type required when manufacturing is enabled")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def update_financial_profile(username, data):
    """Update user's financial profile in DynamoDB"""
    try:
        # First get the user's VAT registration status
        user_response = users_table.get_item(Key={'username': username})
        if 'Item' not in user_response:
            return {
                "success": False,
                "error": "User not found"
            }
        
        user = user_response['Item']
        is_vat_registered = user.get('is_vat_registered')
        
        # Convert string to boolean if needed
        if isinstance(is_vat_registered, str):
            is_vat_registered = is_vat_registered.lower() == 'yes'
        
        # Add VAT status to data for validation
        data['is_vat_registered'] = is_vat_registered
        
        # Sanitize data before validation (removes empty strings and UI fields)
        sanitized_data = sanitize_for_dynamodb(data)
        
        # Validate
        validation = validate_financial_data(sanitized_data)
        if not validation["valid"]:
            return {
                "success": False,
                "error": "Validation failed",
                "details": validation["errors"]
            }
        
        now = datetime.utcnow().isoformat()
        
        # Check if this is first-time completion
        existing_profile = get_financial_profile(username)
        is_first_time = not existing_profile.get('upload_ready', False)
        
        # Build update expression
        update_parts = []
        expression_values = {}
        expression_names = {}
        
        # Tax information - sanitized (no empty strings)
        if 'tax_information' in sanitized_data:
            update_parts.append("#tax_info = :tax_info")
            expression_names['#tax_info'] = 'tax_information'
            expression_values[':tax_info'] = sanitized_data['tax_information']
        
        # Payroll information - sanitized
        if 'payroll_information' in sanitized_data:
            update_parts.append("#payroll_info = :payroll_info")
            expression_names['#payroll_info'] = 'payroll_information'
            expression_values[':payroll_info'] = sanitized_data['payroll_information']
        
        # Banking information - sanitized (excludes UI-only fields)
        if 'banking_information' in sanitized_data:
            update_parts.append("#banking_info = :banking_info")
            expression_names['#banking_info'] = 'banking_information'
            expression_values[':banking_info'] = sanitized_data['banking_information']
        
        # Business operations - sanitized
        if 'business_operations' in sanitized_data:
            update_parts.append("#ops_info = :ops_info")
            expression_names['#ops_info'] = 'business_operations'
            expression_values[':ops_info'] = sanitized_data['business_operations']
        
        # Special circumstances - sanitized (only stores if enabled=true with data)
        if 'special_circumstances' in sanitized_data:
            # Only store special circumstances that are actually enabled
            cleaned_special = {}
            for key, value in sanitized_data['special_circumstances'].items():
                if isinstance(value, dict) and value.get('enabled') is True:
                    cleaned_special[key] = value
            
            if cleaned_special:  # Only update if there are enabled special circumstances
                update_parts.append("#special = :special")
                expression_names['#special'] = 'special_circumstances'
                expression_values[':special'] = cleaned_special
            else:
                # Remove special circumstances if all are disabled
                update_parts.append("#special = :empty_map")
                expression_names['#special'] = 'special_circumstances'
                expression_values[':empty_map'] = {}
        
        # Set upload_ready to true
        update_parts.append("upload_ready = :upload_ready")
        expression_values[':upload_ready'] = True
        
        # Update timestamps
        update_parts.append("profile_last_updated = :updated")
        expression_values[':updated'] = now
        
        if is_first_time:
            update_parts.append("profile_completed_at = :completed")
            expression_values[':completed'] = now
        
        update_expression = "SET " + ", ".join(update_parts)
        
        # Execute update
        users_table.update_item(
            Key={'username': username},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ExpressionAttributeNames=expression_names if expression_names else None
        )
        
        print(f"Financial profile updated for user: {username}")
        print(f"Stored data structure:")
        print(f"   - Tax Info: {bool(sanitized_data.get('tax_information'))}")
        print(f"   - Payroll Info: {bool(sanitized_data.get('payroll_information'))}")
        print(f"   - Banking Info: {bool(sanitized_data.get('banking_information'))}")
        print(f"   - Business Ops: {bool(sanitized_data.get('business_operations'))}")
        if 'cleaned_special' in locals() and cleaned_special:
            print(f"   - Special Circumstances: {list(cleaned_special.keys())}")
        else:
            print(f"   - Special Circumstances: None")
        
        return {
            "success": True,
            "upload_ready": True,
            "is_first_time": is_first_time
        }
        
    except Exception as e:
        print(f"Error updating financial profile: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


def check_upload_ready(username):
    """Check if user has completed financial profile and can upload"""
    try:
        response = users_table.get_item(Key={'username': username})
        
        if 'Item' not in response:
            return {
                "upload_ready": False,
                "missing_fields": ["User not found"]
            }
        
        user = response['Item']
        upload_ready = user.get('upload_ready', False)
        
        if upload_ready:
            return {
                "upload_ready": True,
                "missing_fields": []
            }
        
        # Check what's missing
        missing = []
        
        if not user.get('tax_information'):
            missing.append("Tax information")
        if not user.get('payroll_information'):
            missing.append("Payroll information")
        if not user.get('banking_information'):
            missing.append("Banking information")
        if not user.get('business_operations'):
            missing.append("Business operations")
        
        return {
            "upload_ready": False,
            "missing_fields": missing
        }
        
    except Exception as e:
        print(f"Error checking upload ready: {e}")
        raise


# ============================================
# BATCH PROCESSING FUNCTIONS
# ============================================

def create_batch(username, company_name, email, files_list):
    """Create a new batch record in DynamoDB with collision-safe batch_id"""
    try:
        # Create collision-safe batch_id: batch_username_timestamp
        timestamp = int(datetime.utcnow().timestamp() * 1000)
        batch_id = f"batch_{username}_{timestamp}"
        
        # Create files data with unique file_id for each file
        files_data = []
        for f in files_list:
            file_id = str(uuid.uuid4())  # Generate unique file ID
            files_data.append({
                'file_id': file_id,
                'filename': f.filename,
                'status': 'uploaded',
                'document_type': 'unknown',  # Will be updated later by AI processing
                'content_type': getattr(f, 'content_type', 'application/octet-stream'),
                'size': getattr(f, 'content_length', 0) or len(f.read()) if hasattr(f, 'read') else 0
            })
            # Reset file pointer if we read it for size
            if hasattr(f, 'seek'):
                f.seek(0)
        
        batch_data = {
            'batch_id': batch_id,
            'username': username,
            'company_name': company_name,
            'email': email,
            'processing_stage': 'uploaded',
            'total_documents': len(files_list),
            'completed_documents': 0,
            'failed_documents': 0,
            'files': files_data,  # Now includes file_id and additional metadata
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        batch_table.put_item(Item=batch_data)
        
        print(f"Batch created: {batch_id} with {len(files_list)} files")
        
        return {
            "success": True,
            "batch_id": batch_id,
            "batch_data": batch_data
        }
        
    except Exception as e:
        print(f"Error creating batch: {e}")
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
        
        print(f"Batch {batch_id} status updated to: {status}")
        return {"success": True}
        
    except Exception as e:
        print(f"Error updating batch status: {e}")
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
        print(f"Error getting user batches: {e}")
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
        print(f"Error getting incomplete batches: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ============================================
# MAIN UPLOAD FUNCTION
# ============================================

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

    # Check if user has completed financial profile
    ready_check = check_upload_ready(username)
    
    if not ready_check["upload_ready"]:
        return {
            "status": "error",
            "message": "Please complete your financial profile before uploading documents",
            "missing_fields": ready_check["missing_fields"],
            "error_code": "PROFILE_INCOMPLETE"
        }

    received_files = [file.filename for file in files]
    print(f"Files received from user {username}: {received_files}")

    # Step 1: Create batch record
    batch_result = create_batch(username, company_name, email, files)
    
    if not batch_result["success"]:
        return {
            "status": "error",
            "message": "Failed to create batch record",
            "error": batch_result["error"]
        }
    
    batch_id = batch_result["batch_id"]
    files_data = batch_result["batch_data"]["files"]  # Get the files data with file_ids

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
        # Step 3: Send to n8n webhook with batch context and files metadata
        response = requests.post(
            N8N_WEBHOOK_URL,
            files=files_payload,
            data={
                "company_name": company_name,
                "email": email,
                "username": username,
                "company_id": company_id,
                "batch_id": batch_id,
                "files_data": json.dumps(files_data)  # Send files metadata as JSON string
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