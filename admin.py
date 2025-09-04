import boto3
import json
from datetime import datetime
from botocore.exceptions import ClientError
from auth import create_user_account
import requests
import secrets
import string

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='eu-north-1')  # Change region as needed
onboarding_table = dynamodb.Table('onboarding_submissions')

def get_all_companies():
    """Get all onboarding submissions for admin dashboard"""
    try:
        # Scan the onboarding_submissions table
        response = onboarding_table.scan()
        companies = response.get('Items', [])
        
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

def generate_username_password(company_name):
    """Generate username and password for approved company"""
    # Create username from company name
    username = company_name.lower().replace(' ', '_').replace('-', '_')
    username = ''.join(c for c in username if c.isalnum() or c == '_')
    username = username[:20]  # Limit length
    
    # Add random suffix to ensure uniqueness
    suffix = ''.join(secrets.choice(string.digits) for _ in range(4))
    username = f"{username}_{suffix}"
    
    # Generate secure password
    password = ''.join(secrets.choice(string.ascii_letters + string.digits + '!@#$%') for _ in range(12))
    
    return username, password

def approve_company(submission_id, approved_by_username):
    """Approve a company and create user account"""
    try:
        # Get company details
        company_result = get_company_details(submission_id)
        if not company_result["success"]:
            return company_result
        
        company = company_result["company"]
        
        # Check if already approved
        if company['status'] in ['manual_approved', 'ai_approved']:
            return {
                "success": False,
                "error": "Company is already approved"
            }
        
        # Generate username and password
        username, password = generate_username_password(company['company_name'])
        
        # Create user account
        user_data = {
            'username': username,
            'password': password,
            'email': company['rep_email'],
            'company_name': company['company_name'],
            'company_id': f"cmp_{submission_id}",
            'role': 'user',
            'metadata': {
                'registration_no': company.get('registration_no', ''),
                'vat_no': company.get('vat_no', ''),
                'rep_name': company.get('rep_name', '')
            }
        }
        
        # Create user account
        user_creation = create_user_account(user_data)
        if not user_creation["success"]:
            return {
                "success": False,
                "error": "Failed to create user account"
            }
        
        # Update onboarding submission status
        onboarding_table.update_item(
            Key={'submission_id': submission_id},
            UpdateExpression='SET #status = :status, approved_at = :approved_at, approved_by = :approved_by, username = :username',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'manual_approved',
                ':approved_at': datetime.utcnow().isoformat(),
                ':approved_by': approved_by_username,
                ':username': username
            }
        )
        
        # TODO: Send email with credentials via n8n
        # You can trigger an n8n webhook here to send the email
        send_credentials_email(company['rep_email'], company['company_name'], username, password)
        
        print(f"✅ Company {company['company_name']} approved by {approved_by_username}")
        
        return {
            "success": True,
            "message": "Company approved successfully",
            "username": username,
            "email_sent": True
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
        
        # TODO: Send rejection email via n8n
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