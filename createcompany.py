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
    
    Expected data format (based on Odoo documentation):
    {
        "name": "Company Name",                    # required - Company Name
        
        # Address fields
        "street": "123 Main St",                  # optional - Address
        "street2": "Suite 100",                   # optional - Address line 2
        "city": "City Name",                      # optional - Address
        "zip": "12345",                           # optional - Address
        "state": "State/Province",                # optional - Address
        "country_code": "US",                     # optional - Address (ISO country code)
        
        # Tax and Legal fields
        "vat": "VAT123456",                       # optional - Tax ID
        "lei": "LEI123456789",                    # optional - Legal Entity Identifier
        "company_registry": "REG123456",          # optional - Company ID (registry number)
        
        # Currency
        "currency_code": "USD",                   # optional - Currency (ISO currency code)
        
        # Contact fields
        "phone": "+1234567890",                   # optional - Phone
        "mobile": "+1234567890",                  # optional - Mobile
        "email": "contact@company.com",           # optional - Email
        
        # Web fields
        "website": "https://website.com",         # optional - Website
        "email_domain": "company.com",            # optional - Email Domain
        
        # Visual
        "color": 1                                # optional - Color (integer 0-11)
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
        
        # Prepare company data
        company_data = {
            'name': data['name'],
        }
        
        # Add optional fields based on Odoo documentation
        # Address fields
        address_fields = ['street', 'street2', 'city', 'zip', 'state']
        for field in address_fields:
            if data.get(field):
                company_data[field] = data[field]
        
        # Tax and Legal fields
        tax_legal_fields = ['vat', 'lei', 'company_registry']
        for field in tax_legal_fields:
            if data.get(field):
                company_data[field] = data[field]
        
        # Contact fields
        contact_fields = ['phone', 'mobile', 'email']
        for field in contact_fields:
            if data.get(field):
                company_data[field] = data[field]
        
        # Web fields
        web_fields = ['website', 'email_domain']
        for field in web_fields:
            if data.get(field):
                company_data[field] = data[field]
        
        # Visual fields
        if data.get('color') is not None:
            # Validate color is integer between 0-11
            try:
                color = int(data['color'])
                if 0 <= color <= 11:
                    company_data['color'] = color
                else:
                    return {
                        'success': False,
                        'error': 'color must be an integer between 0 and 11'
                    }
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'color must be an integer between 0 and 11'
                }
        
        # Handle country (Address)
        if data.get('country_code'):
            country_id = get_country_id(models, db, uid, password, data['country_code'])
            if country_id:
                company_data['country_id'] = country_id
            else:
                return {
                    'success': False,
                    'error': f'Country code "{data["country_code"]}" not found'
                }
        
        # Handle currency
        if data.get('currency_code'):
            currency_id = get_currency_id(models, db, uid, password, data['currency_code'])
            if currency_id:
                company_data['currency_id'] = currency_id
            else:
                return {
                    'success': False,
                    'error': f'Currency code "{data["currency_code"]}" not found'
                }
        
        # Handle state (if country is provided)
        if data.get('state') and company_data.get('country_id'):
            state_id = get_state_id(models, db, uid, password, data['state'], company_data['country_id'])
            if state_id:
                company_data['state_id'] = state_id
            # Note: Not returning error if state not found, keeping as text field
        
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
            {'fields': [
                'name', 'email', 'phone', 'mobile', 'website', 'vat', 'lei', 
                'company_registry', 'currency_id', 'country_id', 'email_domain', 'color'
            ]}
        )[0]
        
        return {
            'success': True,
            'company_id': company_id,
            'company_name': company_info['name'],
            'email': company_info.get('email'),
            'phone': company_info.get('phone'),
            'mobile': company_info.get('mobile'),
            'website': company_info.get('website'),
            'vat': company_info.get('vat'),                    # Tax ID
            'lei': company_info.get('lei'),                    # Legal Entity Identifier
            'company_registry': company_info.get('company_registry'),  # Company ID
            'currency': company_info.get('currency_id', [None, 'N/A'])[1],
            'country': company_info.get('country_id', [None, 'N/A'])[1],
            'email_domain': company_info.get('email_domain'),
            'color': company_info.get('color'),
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
        
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], 
            {'fields': [
                'id', 'name', 'email', 'phone', 'mobile', 'website', 'vat', 'lei',
                'company_registry', 'currency_id', 'country_id', 'email_domain', 'color'
            ], 'order': 'name'}
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