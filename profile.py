# profile.py
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
profiles_table = dynamodb.Table('company_profiles')

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
    """Get company profile information"""
    try:
        # Try to get from company_profiles table
        profile_response = profiles_table.get_item(
            Key={'company_id': company_id}
        )
        
        # Also get user data for basic info
        user_response = users_table.get_item(
            Key={'username': username}
        )
        
        if 'Item' not in user_response:
            return {
                "success": False,
                "error": "User not found"
            }
        
        user = convert_decimal(user_response['Item'])
        
        # If profile exists, merge with user data
        if 'Item' in profile_response:
            profile = convert_decimal(profile_response['Item'])
        else:
            # Create default profile from user data
            profile = {
                'company_id': company_id,
                'company_name': user.get('company_name', ''),
                'email': user.get('email', ''),
                'trading_name': user.get('trading_name', ''),
                'registration_no': user.get('registration_no', ''),
                'tax_registration_no': user.get('tax_registration_no', ''),
                'business_address': user.get('business_address', ''),
                'is_vat_registered': user.get('is_vat_registered', ''),
                'vat_no': user.get('vat_no', ''),
                'primary_industry': user.get('primary_industry', ''),
                'business_description': user.get('business_description', ''),
                'main_products': user.get('main_products', ''),
                'business_model': user.get('business_model', ''),
                'created_at': user.get('created_at', ''),
                'updated_at': datetime.utcnow().isoformat()
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
    """Update company profile information"""
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
        
        # Prepare profile item
        profile_item = {
            'company_id': company_id,
            'company_name': profile_data.get('company_name', user.get('company_name', '')),
            'trading_name': profile_data.get('trading_name', ''),
            'registration_no': profile_data.get('registration_no', ''),
            'tax_registration_no': profile_data.get('tax_registration_no', ''),
            'business_address': profile_data.get('business_address', ''),
            'phone': profile_data.get('phone', ''),
            'email': profile_data.get('email', user.get('email', '')),
            'website': profile_data.get('website', ''),
            'is_vat_registered': profile_data.get('is_vat_registered', ''),
            'vat_no': profile_data.get('vat_no', ''),
            'primary_industry': profile_data.get('primary_industry', ''),
            'business_description': profile_data.get('business_description', ''),
            'main_products': profile_data.get('main_products', ''),
            'business_model': profile_data.get('business_model', ''),
            'updated_at': datetime.utcnow().isoformat(),
            'updated_by': username
        }
        
        # If this is the first time creating the profile, set created_at
        existing_profile = profiles_table.get_item(Key={'company_id': company_id})
        if 'Item' not in existing_profile:
            profile_item['created_at'] = datetime.utcnow().isoformat()
        
        # Save to DynamoDB
        profiles_table.put_item(Item=profile_item)
        
        # Also update relevant fields in users table
        users_table.update_item(
            Key={'username': username},
            UpdateExpression='SET company_name = :company_name, trading_name = :trading_name, is_vat_registered = :is_vat_registered, vat_no = :vat_no',
            ExpressionAttributeValues={
                ':company_name': profile_data.get('company_name', user.get('company_name', '')),
                ':trading_name': profile_data.get('trading_name', ''),
                ':is_vat_registered': profile_data.get('is_vat_registered', ''),
                ':vat_no': profile_data.get('vat_no', '')
            }
        )
        
        print(f"Company profile updated for {company_id} by {username}")
        
        return {
            "success": True,
            "message": "Company profile updated successfully",
            "profile": convert_decimal(profile_item)
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

