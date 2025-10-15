# company profile
import boto3
from datetime import datetime
from botocore.exceptions import ClientError
from decimal import Decimal
import os

# Configuration
AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
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

def get_company_profile(company_id, username):
    """Get company profile information from users table"""
    try:
        # Get user data which contains all company profile information
        user_response = users_table.get_item(
            Key={'username': username}
        )
        
        if 'Item' not in user_response:
            return {
                "success": False,
                "error": "User not found"
            }
        
        user = convert_decimal(user_response['Item'])
        
        # Build profile from user data (users table has all the fields)
        profile = {
            'company_id': user.get('company_id', company_id),
            'company_name': user.get('company_name', ''),
            'trading_name': user.get('trading_name', ''),
            'registration_no': user.get('registration_no', ''),
            'tax_registration_no': user.get('tax_registration_no', ''),
            'business_address': user.get('business_address', ''),
            'phone': user.get('phone', ''),
            'email': user.get('email', ''),
            'website': user.get('website', ''),
            'is_vat_registered': user.get('is_vat_registered', ''),
            'vat_no': user.get('vat_no', ''),
            'primary_industry': user.get('primary_industry', ''),
            'business_description': user.get('business_description', ''),
            'main_products': user.get('main_products', ''),
            'business_model': user.get('business_model', ''),
            'business_company_id': user.get('business_company_id', ''),
            'banking_information': user.get('banking_information', {}),
            'payroll_information': user.get('payroll_information', {}),
            'business_operations': user.get('business_operations', {}),
            'tax_information': user.get('tax_information', {}),
            'special_circumstances': user.get('special_circumstances', {}),
            'created_at': user.get('created_at', ''),
            'last_login': user.get('last_login', ''),
            'profile_completed_at': user.get('profile_completed_at'),
            'profile_last_updated': user.get('profile_last_updated')
        }
        
        return {
            "success": True,
            "profile": profile
        }
        
    except ClientError as e:
        print(f"DynamoDB error getting company profile: {e}")
        return {
            "success": False,
            "error": "Failed to retrieve company profile"
        }
    except Exception as e:
        print(f"Error getting company profile: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def update_company_profile(company_id, username, profile_data):
    """Update company profile information in users table"""
    try:
        # Validate that user has permission to update this company
        user_response = users_table.get_item(
            Key={'username': username}
        )
        
        if 'Item' not in user_response:
            return {
                "success": False,
                "error": "User not found"
            }
        
        user = convert_decimal(user_response['Item'])
        
        # Check if user's company_id matches the profile being updated
        if user.get('company_id') != company_id and user.get('role') != 'admin':
            return {
                "success": False,
                "error": "Unauthorized to update this profile"
            }
        
        # Build update expression dynamically based on provided fields
        update_expressions = []
        expression_values = {}
        
        # Map of profile fields to update
        field_mapping = {
            'company_name': 'company_name',
            'trading_name': 'trading_name',
            'registration_no': 'registration_no',
            'tax_registration_no': 'tax_registration_no',
            'business_address': 'business_address',
            'phone': 'phone',
            'website': 'website',
            'is_vat_registered': 'is_vat_registered',
            'vat_no': 'vat_no',
            'primary_industry': 'primary_industry',
            'business_description': 'business_description',
            'main_products': 'main_products',
            'business_model': 'business_model',
            'banking_information': 'banking_information',
            'payroll_information': 'payroll_information',
            'business_operations': 'business_operations',
            'tax_information': 'tax_information',
            'special_circumstances': 'special_circumstances'
        }
        
        # Build update expression for provided fields
        for field, attr_name in field_mapping.items():
            if field in profile_data:
                update_expressions.append(f"{attr_name} = :{attr_name}")
                expression_values[f":{attr_name}"] = profile_data[field]
        
        # Always update profile_last_updated
        update_expressions.append("profile_last_updated = :profile_last_updated")
        expression_values[':profile_last_updated'] = datetime.utcnow().isoformat()
        
        if not update_expressions:
            return {
                "success": False,
                "error": "No fields to update"
            }
        
        # Update users table
        update_expression = "SET " + ", ".join(update_expressions)
        
        users_table.update_item(
            Key={'username': username},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        print(f"✅ Company profile updated for {company_id} by {username}")
        
        # Get updated profile
        updated_result = get_company_profile(company_id, username)
        
        return {
            "success": True,
            "message": "Company profile updated successfully",
            "profile": updated_result.get('profile', {})
        }
        
    except ClientError as e:
        print(f"DynamoDB error updating company profile: {e}")
        return {
            "success": False,
            "error": "Failed to update company profile"
        }
    except Exception as e:
        print(f"Error updating company profile: {e}")
        return {
            "success": False,
            "error": str(e)
        }

