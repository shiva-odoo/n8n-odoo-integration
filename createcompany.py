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
    Create company from HTTP request data following Odoo documentation
    
    Expected data format (based on your form):
    {
        "name": "Company Name",                    # required - Company Name
        "email": "contact@company.com",           # optional - Email
        "phone": "+1234567890",                   # optional - Phone
        "website": "https://website.com",         # optional - Website
        "vat": "VAT123456",                       # optional - Tax ID
        "company_registry": "REG123456",          # optional - Company ID (registry number)
        "street": "123 Main St",                  # optional - Address
        "city": "City Name",                      # optional - City
        "zip": "12345",                           # optional - ZIP
        "state": "State Name",                    # optional - State
        "country_code": "IN",                     # optional - Country (ISO code)
        "currency_code": "INR"                    # optional - Currency (ISO code)
    }
    """
    
    # Validate required fields
    if not data.get('name'):
        return {
            'success': False,
            'error': 'name is required'
        }
    
    # Odoo connection details
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
        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Authenticate
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {
                'success': False,
                'error': 'Odoo authentication failed'
            }
        
        # Check if company already exists
        existing_company = models.execute_kw(
            db, uid, password,
            'res.company', 'search_count',
            [[('name', '=', data['name'])]]
        )
        
        if existing_company:
            return {
                'success': False,
                'error': f'Company with name "{data["name"]}" already exists'
            }
        
        # Get available fields for res.company model to avoid field errors
        available_fields = get_available_company_fields(models, db, uid, password)
        
        # Prepare company data with only available fields
        company_data = {
            'name': data['name'],
        }
        
        # Add optional fields only if they exist in this Odoo version
        field_mapping = {
            'email': data.get('email'),
            'phone': data.get('phone'),
            'website': data.get('website'),
            'vat': data.get('vat'),                    # Tax ID
            'company_registry': data.get('company_registry'),  # Company ID
            'street': data.get('street'),
            'city': data.get('city'),
            'zip': data.get('zip'),
            'state': data.get('state')
        }
        
        # Only add fields that exist and have values
        for field, value in field_mapping.items():
            if value and field in available_fields:
                company_data[field] = value
        
        # Handle country (if country_code provided and country_id field exists)
        if data.get('country_code') and 'country_id' in available_fields:
            country_id = get_country_id(models, db, uid, password, data['country_code'])
            if country_id:
                company_data['country_id'] = country_id
            else:
                return {
                    'success': False,
                    'error': f'Country code "{data["country_code"]}" not found'
                }
        
        # Handle currency (if currency_code provided and currency_id field exists)
        if data.get('currency_code') and 'currency_id' in available_fields:
            currency_id = get_currency_id(models, db, uid, password, data['currency_code'])
            if currency_id:
                company_data['currency_id'] = currency_id
            else:
                return {
                    'success': False,
                    'error': f'Currency code "{data["currency_code"]}" not found'
                }
        
        # Handle state (if state provided and state_id field exists)
        if data.get('state') and company_data.get('country_id') and 'state_id' in available_fields:
            state_id = get_state_id(models, db, uid, password, data['state'], company_data['country_id'])
            if state_id:
                company_data['state_id'] = state_id
                # Remove the text state field if we have state_id
                company_data.pop('state', None)
        
        # Create company
        company_id = models.execute_kw(
            db, uid, password,
            'res.company', 'create',
            [company_data]
        )
        
        if not company_id:
            return {
                'success': False,
                'error': 'Failed to create company in Odoo'
            }
        
        # Get created company information using only safe/available fields
        safe_read_fields = [
            'name', 'email', 'phone', 'website', 'vat', 'company_registry',
            'currency_id', 'country_id', 'street', 'city', 'zip'
        ]
        # Filter to only fields that actually exist
        read_fields = [field for field in safe_read_fields if field in available_fields]
        
        company_info = models.execute_kw(
            db, uid, password,
            'res.company', 'read',
            [[company_id]], 
            {'fields': read_fields}
        )[0]
        
        # Prepare response with safe field access
        response = {
            'success': True,
            'company_id': company_id,
            'company_name': company_info['name'],
            'message': 'Company created successfully'
        }
        
        # Add optional fields to response if they exist
        optional_response_fields = {
            'email': 'email',
            'phone': 'phone', 
            'website': 'website',
            'vat': 'vat',
            'company_registry': 'company_registry',
            'street': 'street',
            'city': 'city',
            'zip': 'zip'
        }
        
        for response_key, odoo_field in optional_response_fields.items():
            if odoo_field in company_info:
                response[response_key] = company_info.get(odoo_field)
        
        # Handle relational fields safely
        if 'currency_id' in company_info and company_info['currency_id']:
            response['currency'] = company_info['currency_id'][1] if isinstance(company_info['currency_id'], list) else 'N/A'
        
        if 'country_id' in company_info and company_info['country_id']:
            response['country'] = company_info['country_id'][1] if isinstance(company_info['country_id'], list) else 'N/A'
        
        return response
        
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

def get_available_company_fields(models, db, uid, password):
    """Get list of available fields for res.company model"""
    try:
        fields_info = models.execute_kw(
            db, uid, password,
            'res.company', 'fields_get',
            [[]], {'attributes': ['string', 'type']}
        )
        return list(fields_info.keys())
    except Exception as e:
        print(f"Error getting fields: {e}")
        # Return basic fields that should exist in most Odoo versions
        return ['name', 'email', 'phone', 'website', 'vat', 'street', 'city', 'zip', 'country_id', 'currency_id']

def create(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

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

def get_currency_id(models, db, uid, password, currency_code):
    """Get currency ID from currency code"""
    try:
        currency_ids = models.execute_kw(
            db, uid, password,
            'res.currency', 'search',
            [[('name', '=', currency_code.upper())]], {'limit': 1}
        )
        return currency_ids[0] if currency_ids else None
    except Exception:
        return None

def get_state_id(models, db, uid, password, state_name, country_id):
    """Get state ID from state name and country"""
    try:
        state_ids = models.execute_kw(
            db, uid, password,
            'res.country.state', 'search',
            [[('name', '=', state_name), ('country_id', '=', country_id)]], {'limit': 1}
        )
        return state_ids[0] if state_ids else None
    except Exception:
        return None

def list_companies():
    """Get list of all companies for reference"""
    
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
        
        # Get available fields first
        available_fields = get_available_company_fields(models, db, uid, password)
        safe_fields = [field for field in ['id', 'name', 'email', 'phone', 'currency_id', 'country_id', 'vat', 'website'] if field in available_fields]
        
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], 
            {'fields': safe_fields, 'order': 'name'}
        )
        
        return {
            'success': True,
            'companies': companies,
            'count': len(companies)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }