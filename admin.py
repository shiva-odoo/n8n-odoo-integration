#admin.py
import boto3
import json
from datetime import datetime
from botocore.exceptions import ClientError
from auth import create_user_account
import createcompany
import requests
import secrets
import string
from decimal import Decimal
import os

AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'company-documents-2025')

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='AWS_REGION')  # Change region as needed
onboarding_table = dynamodb.Table('onboarding_submissions')

# Update the existing S3 and DynamoDB setup lines
s3_client = boto3.client('s3', region_name=AWS_REGION)
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)

def generate_presigned_url(s3_key, expiration=3600):
    """Generate a presigned URL for S3 object"""
    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=expiration
        )
        return response
    except ClientError as e:
        print(f"❌ Error generating presigned URL for {s3_key}: {e}")
        return None

def get_company_documents(submission_id):
    """Get documents for a specific company submission with presigned URLs"""
    try:
        # Get company details
        response = onboarding_table.get_item(
            Key={'submission_id': submission_id}
        )
        
        if 'Item' not in response:
            return {"success": False, "error": "Submission not found"}
        
        company = response['Item']
        company = convert_decimal(company)
        
        # Get documents and generate presigned URLs
        documents = []
        files = company.get('files', [])
        
        for file_data in files:
            s3_key = file_data.get('s3_key')
            if s3_key:
                presigned_url = generate_presigned_url(s3_key)
                if presigned_url:
                    documents.append({
                        'filename': file_data.get('filename', s3_key.split('/')[-1]),
                        's3_key': s3_key,
                        'download_url': presigned_url,
                        'file_type': file_data.get('file_type', 'unknown'),
                        'bucket': file_data.get('bucket', S3_BUCKET_NAME),
                        'uploaded_at': file_data.get('uploaded_at', ''),
                        's3_location': file_data.get('s3_location', '')
                    })
        
        return {
            "success": True,
            "documents": documents,
            "total_count": len(documents)
        }
        
    except Exception as e:
        print(f"❌ Error getting company documents: {e}")
        return {"success": False, "error": "Failed to get documents"}

def convert_decimal(obj):
    """Convert DynamoDB Decimal objects to regular Python numbers"""
    if isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal(v) for v in obj]
    elif isinstance(obj, Decimal):
        # Convert to int if it's a whole number, otherwise float
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    else:
        return obj

def get_all_companies():
    """Get all onboarding submissions for admin dashboard"""
    try:
        # Scan the onboarding_submissions table
        response = onboarding_table.scan()
        companies = response.get('Items', [])
        
        # Convert Decimal objects
        companies = convert_decimal(companies)
        
        # Sort by submission date (newest first)
        companies.sort(key=lambda x: x.get('submitted_at', ''), reverse=True)
        
        # Format data for frontend
        formatted_companies = []
        for company in companies:
            formatted_companies.append({
                'submission_id': company['submission_id'],
                'company_name': company['company_name'],
                'rep_email': company['rep_email'],
                'rep_name': company.get('rep_name', ''),
                'registration_no': company.get('registration_no', ''),
                'vat_no': company.get('vat_no', ''),
                'status': company['status'],
                'submitted_at': company['submitted_at'],
                'approved_at': company.get('approved_at'),
                'approved_by': company.get('approved_by'),
                'files': company.get('files', []),
                'rejection_reason': company.get('rejection_reason')
            })
        
        print(f"📋 Retrieved {len(formatted_companies)} company submissions")
        
        return {
            "success": True,
            "companies": formatted_companies,
            "total_count": len(formatted_companies)
        }
        
    except ClientError as e:
        print(f"❌ DynamoDB error: {e}")
        return {
            "success": False,
            "error": "Failed to retrieve company data"
        }
    except Exception as e:
        print(f"❌ Error retrieving companies: {e}")
        return {
            "success": False,
            "error": "Failed to get companies"
        }

def get_company_details(submission_id):
    """Get detailed information for a specific company submission"""
    try:
        response = onboarding_table.get_item(
            Key={'submission_id': submission_id}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Company submission not found"
            }
        
        company = response['Item']
        
        # Convert Decimal objects
        company = convert_decimal(company)
        
        return {
            "success": True,
            "company": company
        }
        
    except ClientError as e:
        print(f"❌ DynamoDB error: {e}")
        return {
            "success": False,
            "error": "Failed to retrieve company details"
        }
    except Exception as e:
        print(f"❌ Error retrieving company details: {e}")
        return {
            "success": False,
            "error": "Failed to get company details"
        }

def generate_username_password(company_name, password_length=12):
    """Generate username (max 12 chars with 2-digit suffix) and secure password"""
    
    # Clean company name: only alphanumeric, lowercase
    base = ''.join(c for c in company_name.lower() if c.isalnum())
    
    if not base:
        base = "user"
    
    # Add random 2-digit suffix
    suffix = ''.join(secrets.choice(string.digits) for _ in range(2))
    
    # Ensure base length + 2 <= 12
    max_base_length = 12 - len(suffix)
    base = base[:max_base_length]
    
    username = base + suffix
    
    # Generate secure password
    all_chars = string.ascii_letters + string.digits + '!@#$%'
    password = ''.join(secrets.choice(all_chars) for _ in range(password_length))
    
    return username, password

def format_company_data_for_business_system(company):
    """Format onboarding company data for business system creation"""
    company_data = {
        "name": company.get('company_name'),  # required
        "email": company.get('rep_email'),    # optional - use rep email as company email
        "phone": None,                        # optional - not collected in onboarding
        "website": None,                      # optional - not collected in onboarding
        "vat": company.get('vat_no'),         # optional - VAT number
        "company_registry": company.get('registration_no'),  # optional - registration number
        "street": None,                       # optional - not collected in onboarding
        "city": None,                         # optional - not collected in onboarding
        "zip": None,                          # optional - not collected in onboarding
        "state": None,                        # optional - not collected in onboarding
        "country_code": "IN",                 # optional - default to India
        "currency_code": "INR"                # optional - default to Indian Rupee
    }
    
    return company_data

def send_admin_failure_notification(admin_email, company, error_message, submission_id):
    """Send failure notification to admin via n8n webhook"""
    try:
        webhook_url = "https://kyrasteldeveloper.app.n8n.cloud/webhook/admin-company-fail"
        
        payload = {
            'admin_email': admin_email,
            'error_details': error_message,
            'submission_id': submission_id,
            'company_name': company.get('company_name'),
            'rep_email': company.get('rep_email'),
            'registration_no': company.get('registration_no'),
            'failed_at': datetime.utcnow().isoformat(),
            'failure_type': 'odoo_company_creation'
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        print(f"📧 Admin failure notification sent: {response.status_code}")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"❌ Error sending admin failure notification: {e}")
        return False

def send_user_failure_notification(company, error_message):
    """Send failure notification to company via n8n webhook"""
    try:
        webhook_url = "https://kyrasteldeveloper.app.n8n.cloud/webhook/user-company-fail"
        
        payload = {
            'company_email': company.get('rep_email'),
            'company_name': company.get('company_name'),
            'rep_name': company.get('rep_name'),
            'registration_no': company.get('registration_no'),
            'vat_no': company.get('vat_no'),
            'submission_id': company.get('submission_id'),
            'error_summary': 'Company creation in our system failed',
            'technical_details': error_message,
            'failed_at': datetime.utcnow().isoformat(),
            'next_steps': 'Our team has been notified and will review your application'
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        print(f"📧 User failure notification sent to {company.get('rep_email')}: {response.status_code}")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"❌ Error sending user failure notification: {e}")
        return False

def approve_company(submission_id, approved_by_username, admin_email):
    """Approve a company - PRIORITY: Create Odoo company first, then proceed with other tasks"""
    original_status = None
    
    try:
        # Get company details
        company_result = get_company_details(submission_id)
        if not company_result["success"]:
            return company_result
        
        company = company_result["company"]
        original_status = company['status']  # Store original status for rollback
        
        # Check if already manually approved or rejected
        if company['status'] == 'manual_approved':
            return {
                "success": False,
                "error": "Company is already manually approved"
            }
        
        if company['status'] == 'rejected':
            return {
                "success": False,
                "error": "Cannot approve a rejected company"
            }
        
        # Allow approval for both 'pending' and 'ai_approved' statuses
        if company['status'] not in ['pending', 'ai_approved']:
            return {
                "success": False,
                "error": f"Cannot approve company with status: {company['status']}"
            }
        
        # PRIORITY STEP 1: Create company in Odoo FIRST
        business_company_data = format_company_data_for_business_system(company)
        
        print(f"🏢 PRIORITY: Creating company in Odoo first: {business_company_data}")
        
        try:
            business_company_result = createcompany.main(business_company_data)
            print(f"📊 Odoo company creation result: {business_company_result}")
            
            # Check if Odoo company creation failed
            if not business_company_result.get("success"):
                error_message = business_company_result.get("error", "Unknown Odoo creation error")
                print(f"❌ CRITICAL: Odoo company creation failed: {error_message}")
                
                # Revert status back to pending
                onboarding_table.update_item(
                    Key={'submission_id': submission_id},
                    UpdateExpression='SET #status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'pending'}
                )
                
                # Send failure notifications
                send_admin_failure_notification(admin_email, company, error_message, submission_id)
                send_user_failure_notification(company, error_message)
                
                return {
                    "success": False,
                    "error": f"Odoo company creation failed: {error_message}",
                    "odoo_error": True,
                    "notifications_sent": True
                }
                
        except Exception as odoo_error:
            error_message = str(odoo_error)
            print(f"❌ CRITICAL: Odoo company creation exception: {error_message}")
            
            # Revert status back to pending
            onboarding_table.update_item(
                Key={'submission_id': submission_id},
                UpdateExpression='SET #status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': 'pending'}
            )
            
            # Send failure notifications
            send_admin_failure_notification(admin_email, company, error_message, submission_id)
            send_user_failure_notification(company, error_message)
            
            return {
                "success": False,
                "error": f"Odoo company creation failed: {error_message}",
                "odoo_error": True,
                "notifications_sent": True
            }
        
        # If we get here, Odoo company creation was successful
        business_company_id = business_company_result.get("company_id")
        print(f"✅ SUCCESS: Odoo company created with ID: {business_company_id}")
        
        # Now proceed with the other 3 tasks since Odoo creation succeeded
        
        # Generate username and password
        username, password = generate_username_password(company['company_name'])
        
        # Step 2: Create user account in users table
        user_data = {
            'username': username,
            'password': password,
            'email': company['rep_email'],
            'company_name': company['company_name'],
            'company_id': f"cmp_{submission_id}",
            'business_company_id': business_company_id,  # Add Odoo company ID
            'role': 'user',
            'metadata': {
                'registration_no': company.get('registration_no', ''),
                'vat_no': company.get('vat_no', ''),
                'rep_name': company.get('rep_name', '')
            }
        }
        
        user_creation = create_user_account(user_data)
        if not user_creation["success"]:
            return {
                "success": False,
                "error": "Failed to create user account after Odoo creation"
            }
        
        # Step 3: Update onboarding submission status to manual_approved
        onboarding_table.update_item(
            Key={'submission_id': submission_id},
            UpdateExpression='SET #status = :status, approved_at = :approved_at, approved_by = :approved_by, username = :username, business_company_id = :business_company_id',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'manual_approved',
                ':approved_at': datetime.utcnow().isoformat(),
                ':approved_by': approved_by_username,
                ':username': username,
                ':business_company_id': business_company_id
            }
        )
        
        # Step 4: Send email with credentials via n8n
        send_credentials_email(company['rep_email'], company['company_name'], username, password)
        
        print(f"✅ Company {company['company_name']} fully approved by {approved_by_username}")
        
        return {
            "success": True,
            "message": "Company approved successfully",
            "username": username,
            "email_sent": True,
            "user_account_created": True,
            "business_company_created": True,
            "business_company_id": business_company_id
        }
        
    except ClientError as e:
        print(f"❌ DynamoDB error: {e}")
        return {
            "success": False,
            "error": "Failed to approve company"
        }
    except Exception as e:
        print(f"❌ Error approving company: {e}")
        return {
            "success": False,
            "error": "Approval process failed"
        }

def reject_company(submission_id, rejected_by_username, reason):
    """Reject a company submission"""
    try:
        # Get company details first
        company_result = get_company_details(submission_id)
        if not company_result["success"]:
            return company_result
        
        company = company_result["company"]
        
        # Check if already processed
        if company['status'] == 'rejected':
            return {
                "success": False,
                "error": "Company is already rejected"
            }
        
        if company['status'] == 'manual_approved':
            return {
                "success": False,
                "error": "Cannot reject an already approved company"
            }
        
        # Update submission status to rejected
        onboarding_table.update_item(
            Key={'submission_id': submission_id},
            UpdateExpression='SET #status = :status, rejected_at = :rejected_at, rejected_by = :rejected_by, rejection_reason = :reason',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'rejected',
                ':rejected_at': datetime.utcnow().isoformat(),
                ':rejected_by': rejected_by_username,
                ':reason': reason
            }
        )
        
        # Send rejection email via n8n
        send_rejection_email(company['rep_email'], company['company_name'], reason)
        
        print(f"✅ Company {company['company_name']} rejected by {rejected_by_username}")
        
        return {
            "success": True,
            "message": "Company rejected successfully"
        }
        
    except ClientError as e:
        print(f"❌ DynamoDB error: {e}")
        return {
            "success": False,
            "error": "Failed to reject company"
        }
    except Exception as e:
        print(f"❌ Error rejecting company: {e}")
        return {
            "success": False,
            "error": "Rejection process failed"
        }

def send_credentials_email(email, company_name, username, password):
    """Send login credentials via n8n webhook"""
    try:
        webhook_url = "https://kyrasteldeveloper.app.n8n.cloud/webhook/send-credentials"
        
        payload = {
            'email': email,
            'company_name': company_name,
            'username': username,
            'password': password,
            'portal_url': 'https://your-domain.com'  # Replace with your actual domain
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        print(f"📧 Credentials email sent to {email}: {response.status_code}")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"❌ Error sending credentials email: {e}")
        return False

def send_rejection_email(email, company_name, reason):
    """Send rejection notification via n8n webhook"""
    try:
        webhook_url = "https://kyrasteldeveloper.app.n8n.cloud/webhook/send-rejection"
        
        payload = {
            'email': email,
            'company_name': company_name,
            'rejection_reason': reason
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        print(f"📧 Rejection email sent to {email}: {response.status_code}")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"❌ Error sending rejection email: {e}")
        return False
    

def update_submission_files(submission_id, files_data):
    """Update the files field for a specific onboarding submission"""
    try:
        # Validate input
        if not submission_id:
            return {
                "success": False,
                "error": "submission_id is required"
            }
        
        if not files_data or not isinstance(files_data, list):
            return {
                "success": False,
                "error": "files_data must be a non-empty list"
            }
        
        # Validate that submission exists
        response = onboarding_table.get_item(
            Key={'submission_id': submission_id}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Submission not found"
            }
        
        # Update the files field
        onboarding_table.update_item(
            Key={'submission_id': submission_id},
            UpdateExpression='SET files = :files, updated_at = :updated_at',
            ExpressionAttributeValues={
                ':files': files_data,
                ':updated_at': datetime.utcnow().isoformat()
            }
        )
        
        print(f"✅ Updated files for submission {submission_id} with {len(files_data)} files")
        
        return {
            "success": True,
            "message": f"Successfully updated {len(files_data)} files for submission {submission_id}",
            "submission_id": submission_id,
            "files_count": len(files_data)
        }
        
    except ClientError as e:
        print(f"❌ DynamoDB error updating files: {e}")
        return {
            "success": False,
            "error": "Failed to update submission files"
        }
    except Exception as e:
        print(f"❌ Error updating submission files: {e}")
        return {
            "success": False,
            "error": "Update process failed"
        }