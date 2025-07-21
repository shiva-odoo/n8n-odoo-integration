import xmlrpc.client
import os
# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def main(data):
    """
    Create bank in Odoo from HTTP request data
    
    Expected data format:
    {
        "name": "Bank Name",                    # required
        "bic": "SWIFT123456",                   # optional, SWIFT/BIC code
        "street": "123 Bank Street",            # optional
        "city": "City Name",                    # optional
        "zip": "12345",                         # optional
        "country_code": "US",                   # optional, ISO country code
        "state_code": "CA",                     # optional, state code
        "phone": "+1234567890",                 # optional
        "email": "info@bank.com",               # optional
        "website": "https://bank.com",          # optional
        "active": true                          # optional, default true
    }
    """
    
    # Validate required fields
    if not data.get('name'):
        return {
            'success': False,
            'error': 'name is required'
        }

    # Only allow valid fields for res.bank
    allowed_fields = {"name", "bic", "active", "street", "city", "zip", "phone", "email"}
    filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

    # Connection details
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    if not username or not password:
        return {
            'success': False,
            'error': 'ODOO_USERNAME and ODOO_API_KEY environment variables are required'
        }
    
    try:
        # Initialize connection
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Authenticate
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {
                'success': False,
                'error': 'Odoo authentication failed'
            }
        
        # Check if bank already exists
        existing_bank = check_bank_exists(
            models, db, uid, password,
            name=filtered_data.get('name'),
            bic=filtered_data.get('bic')
        )
        
        if existing_bank:
            bank_info = get_bank_info(models, db, uid, password, existing_bank)
            return {
                'success': True,
                'bank_id': existing_bank,
                'bank_name': bank_info.get('name') if bank_info else filtered_data['name'],
                'message': 'Bank already exists',
                'existing': True,
                'bank_details': bank_info
            }

        # Handle country
        if data.get('country_code'):
            country_id = get_country_id(models, db, uid, password, data['country_code'])
            if country_id:
                filtered_data['country'] = country_id

        # Handle state
        if data.get('state_code') and data.get('country_code'):
            state_id = get_state_id(models, db, uid, password, data['state_code'], data['country_code'])
            if state_id:
                filtered_data['state'] = state_id

        # Create bank
        bank_id = models.execute_kw(
            db, uid, password,
            'res.bank', 'create',
            [filtered_data]
        )

        if not bank_id:
            return {
                'success': False,
                'error': 'Failed to create bank in Odoo'
            }
        
        # Get created bank information
        bank_info = get_bank_info(models, db, uid, password, bank_id)
        
        return {
            'success': True,
            'bank_id': bank_id,
            'bank_name': bank_info.get('name') if bank_info else filtered_data['name'],
            'message': 'Bank created successfully',
            'existing': False,
            'bank_details': bank_info
        }
        
    except xmlrpc.client.Fault as e:
        return {
            'success': False,
            'error': f'Odoo API error: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }

def create(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

def check_bank_exists(models, db, uid, password, name=None, bic=None):
    """Check if bank already exists"""
    try:
        domain = []
        
        if bic:
            domain.append(('bic', '=', bic))
        elif name:
            domain.append(('name', '=', name))
        else:
            return None
            
        bank_ids = models.execute_kw(
            db, uid, password,
            'res.bank', 'search',
            [domain], {'limit': 1}
        )
        
        return bank_ids[0] if bank_ids else None
        
    except Exception:
        return None

def create_bank(models, db, uid, password, data):
    """Create a bank with provided information"""
    
    bank_data = {
        'name': data['name'],
        'active': data.get('active', True),
    }
    
    # Add optional fields
    optional_fields = ['bic', 'street', 'city', 'zip', 'phone', 'email', 'website']
    for field in optional_fields:
        if data.get(field):
            bank_data[field] = data[field]

    # Handle country
    if data.get('country_code'):
        country_id = get_country_id(models, db, uid, password, data['country_code'])
        if country_id:
            bank_data['country'] = country_id

    # Handle state
    if data.get('state_code') and data.get('country_code'):
        state_id = get_state_id(models, db, uid, password, data['state_code'], data['country_code'])
        if state_id:
            bank_data['state'] = state_id

    try:
        bank_id = models.execute_kw(
            db, uid, password,
            'res.bank', 'create',
            [bank_data]
        )
        return bank_id
        
    except Exception as e:
        raise Exception(f"Error creating bank: {e}")

def get_country_id(models, db, uid, password, country_code):
    """Get country ID from country code"""
    try:
        country_ids = models.execute_kw(
            db, uid, password,
            'res.country', 'search',
            [[('code', '=', country_code.upper())]], {'limit': 1}
        )
        return country_ids[0] if country_ids else None
    except Exception:
        return None

def get_state_id(models, db, uid, password, state_code, country_code):
    """Get state ID from state code and country"""
    try:
        country_id = get_country_id(models, db, uid, password, country_code)
        if not country_id:
            return None
            
        state_ids = models.execute_kw(
            db, uid, password,
            'res.country.state', 'search',
            [[('code', '=', state_code.upper()), ('country_id', '=', country_id)]], 
            {'limit': 1}
        )
        return state_ids[0] if state_ids else None
    except Exception:
        return None

def get_bank_info(models, db, uid, password, bank_id):
    """Get bank information by ID"""
    try:
        bank_data = models.execute_kw(
            db, uid, password,
            'res.bank', 'read',
            [[bank_id]], 
            {'fields': ['name', 'bic', 'street', 'city', 'zip', 'country', 'state', 'phone', 'email', 'website', 'active']}
        )
        return bank_data[0] if bank_data else None
    except Exception:
        return None

def list_banks():
    """Get list of all banks for reference"""
    
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {'success': False, 'error': 'Authentication failed'}
        
        banks = models.execute_kw(
            db, uid, password,
            'res.bank', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'bic', 'city', 'country', 'active'], 'order': 'name'}
        )
        
        return {
            'success': True,
            'banks': banks,
            'count': len(banks)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Example usage
if __name__ == "__main__":
    # Example: Create a new bank
    sample_bank_data = {
        "name": "Sample Bank Ltd",
        "bic": "SAMBUS33XXX",
        "street": "123 Banking Street",
        "city": "New York",
        "zip": "10001",
        "country_code": "US",
        "state_code": "NY",
        "phone": "+1-555-123-4567",
        "email": "info@samplebank.com",
        "website": "https://www.samplebank.com"
    }
    
    print("Creating bank...")
    result = main(sample_bank_data)
    print(f"Create Result: {result}")
    
    # List all banks
    print("\nListing all banks...")
    banks_result = list_banks()
    print(f"Banks: {banks_result}")