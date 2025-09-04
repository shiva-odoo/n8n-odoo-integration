import boto3
import bcrypt
import jwt
import json
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
import os

# JWT Configuration
JWT_SECRET = os.getenv('JWT_SECRET', 'your-super-secret-jwt-key-change-this-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_MINUTES = 30

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='eu-north-1')  # Change region as needed
users_table = dynamodb.Table('users')

def hash_password(password):
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password, hashed):
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def generate_jwt(user_data):
    """Generate JWT token for authenticated user"""
    payload = {
        'user_id': user_data['username'],
        'username': user_data['username'],
        'role': user_data['role'],
        'company_id': user_data.get('company_id', ''),
        'company_name': user_data['company_name'],
        'email': user_data['email'],
        'exp': datetime.utcnow() + timedelta(minutes=JWT_EXPIRY_MINUTES),
        'iat': datetime.utcnow()
    }
    
    # Add metadata if exists
    if 'metadata' in user_data:
        payload['metadata'] = user_data['metadata']
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token

def verify_jwt(token):
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"valid": True, "payload": payload}
    except jwt.ExpiredSignatureError:
        return {"valid": False, "error": "Token has expired"}
    except jwt.InvalidTokenError:
        return {"valid": False, "error": "Invalid token"}

def authenticate_user(username, password):
    """Authenticate user credentials against DynamoDB"""
    try:
        # Get user from DynamoDB
        response = users_table.get_item(
            Key={'username': username}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "Invalid username or password"
            }
        
        user = response['Item']
        
        # Check if user account is active
        if user.get('status', 'active') != 'active':
            return {
                "success": False,
                "error": "Account is suspended or inactive"
            }
        
        # Verify password
        if not verify_password(password, user['password_hash']):
            return {
                "success": False,
                "error": "Invalid username or password"
            }
        
        # Update last login
        users_table.update_item(
            Key={'username': username},
            UpdateExpression='SET last_login = :timestamp',
            ExpressionAttributeValues={
                ':timestamp': datetime.utcnow().isoformat()
            }
        )
        
        # Generate JWT
        token = generate_jwt(user)
        
        # Prepare user data (exclude password_hash)
        user_data = {
            'username': user['username'],
            'email': user['email'],
            'role': user['role'],
            'company_name': user['company_name'],
            'company_id': user.get('company_id', ''),
            'metadata': user.get('metadata', {})
        }
        
        print(f"✅ User {username} authenticated successfully")
        
        return {
            "success": True,
            "token": token,
            "user": user_data,
            "expires_in": JWT_EXPIRY_MINUTES * 60  # seconds
        }
        
    except ClientError as e:
        print(f"❌ DynamoDB error: {e}")
        return {
            "success": False,
            "error": "Database error occurred"
        }
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return {
            "success": False,
            "error": "Authentication failed"
        }

def create_user_account(user_data):
    """Create a new user account in DynamoDB (used by n8n after approval)"""
    try:
        # Hash the password
        hashed_password = hash_password(user_data['password'])
        
        # Prepare user item
        user_item = {
            'username': user_data['username'],
            'password_hash': hashed_password,
            'role': user_data.get('role', 'user'),
            'email': user_data['email'],
            'company_name': user_data['company_name'],
            'company_id': user_data.get('company_id', ''),
            'status': 'active',
            'created_at': datetime.utcnow().isoformat(),
            'metadata': user_data.get('metadata', {})
        }
        
        # Save to DynamoDB
        users_table.put_item(Item=user_item)
        
        print(f"✅ User account created: {user_data['username']}")
        
        return {
            "success": True,
            "message": "User account created successfully"
        }
        
    except ClientError as e:
        print(f"❌ DynamoDB error creating user: {e}")
        return {
            "success": False,
            "error": "Failed to create user account"
        }
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        return {
            "success": False,
            "error": "User creation failed"
        }

def refresh_token(current_token):
    """Refresh JWT token if valid"""
    verification = verify_jwt(current_token)
    
    if not verification["valid"]:
        return {
            "success": False,
            "error": verification["error"]
        }
    
    try:
        # Get updated user data from database
        username = verification["payload"]["username"]
        response = users_table.get_item(
            Key={'username': username}
        )
        
        if 'Item' not in response:
            return {
                "success": False,
                "error": "User not found"
            }
        
        user = response['Item']
        
        # Generate new token
        new_token = generate_jwt(user)
        
        return {
            "success": True,
            "token": new_token,
            "expires_in": JWT_EXPIRY_MINUTES * 60
        }
        
    except Exception as e:
        print(f"❌ Token refresh error: {e}")
        return {
            "success": False,
            "error": "Token refresh failed"
        }