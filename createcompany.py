import xmlrpc.client
import os
from dotenv import load_dotenv

load_dotenv()

def main(data):
    """
    Create company from HTTP request data
    
    Expected data format:
    {
        "name": "Company Name",
        "email": "contact@company.com",  # optional
        "phone": "+1234567890",          # optional
        "website": "https://website.com", # optional
        "vat": "VAT123456",              # optional
        "street": "123 Main St",         # optional
        "city": "City Name",             # optional
        "zip": "12345",                  # optional
        "country_code": "US"             # optional, ISO country code
    }
    """
    
    # Validate required fields
    if not data.get('name'):
        return {
            'success': False,
            'error': 'name is required'
        }
    
    # Odoo connection details
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
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
        
        # Prepare company data
        company_data = {
            'name': data['name'],
        }
        
        # Add optional fields
        optional_fields = ['email', 'phone', 'website', 'vat', 'street', 'city', 'zip']
        for field in optional_fields:
            if data.get(field):
                company_data[field] = data[field]
        
        # Handle country
        if data.get('country_code'):
            country_id = get_country_id(models, db, uid, password, data['country_code'])
            if country_id:
                company_data['country_id'] = country_id
            else:
                return {
                    'success': False,
                    'error': f'Country code "{data["country_code"]}" not found'
                }
        
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
        
        # Get created company information
        company_info = models.execute_kw(
            db, uid, password,
            'res.company', 'read',
            [[company_id]], 
            {'fields': ['name', 'email', 'phone', 'currency_id']}
        )[0]
        
        return {
            'success': True,
            'company_id': company_id,
            'company_name': company_info['name'],
            'email': company_info.get('email'),
            'phone': company_info.get('phone'),
            'currency': company_info.get('currency_id', [None, 'N/A'])[1],
            'message': 'Company created successfully'
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

def list_companies():
    """Get list of all companies for reference"""
    
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {'success': False, 'error': 'Authentication failed'}
        
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'email', 'phone', 'currency_id', 'country_id'], 'order': 'name'}
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