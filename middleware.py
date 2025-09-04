from functools import wraps
from flask import request, jsonify, g
from auth import verify_jwt

def jwt_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        
        # Check for token in Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                # Extract token from "Bearer <token>"
                token = auth_header.split(' ')[1]
            except IndexError:
                return jsonify({'error': 'Invalid Authorization header format'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        # Verify token
        verification = verify_jwt(token)
        
        if not verification['valid']:
            return jsonify({'error': verification['error']}), 401
        
        # Store user info in Flask's g object for access in route functions
        g.current_user = verification['payload']
        
        return f(*args, **kwargs)
    
    return decorated_function

def admin_required(f):
    """Decorator to require admin role (use after jwt_required)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_user'):
            return jsonify({'error': 'Authentication required'}), 401
        
        if g.current_user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    
    return decorated_function

def get_current_user():
    """Helper function to get current authenticated user"""
    return getattr(g, 'current_user', None)