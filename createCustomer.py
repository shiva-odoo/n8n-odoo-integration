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
    Create customer from HTTP request data
    
    Expected data format:
    {
        "name": "Customer Name",                 # required
        "is_company": true,                      # optional, defaults to true
        "email": "contact@customer.com",         # optional
        "phone": "+1234567890",                  # optional
        "website": "https://website.com",        # optional
        "street": "123 Main St",                 # optional
        "city": "City Name",                     # optional
        "zip": "12345",                          # optional
        "country_code": "US",                    # optional, ISO country code
        "company_id": 1                          # optional, for multi-company setup
    }
    """
    
    # Validate required fields
    if not data.get('name'):
        return {
            'success': False,
            'error': 'name is required'
        }
    
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
        
        # Check if customer already exists
        existing_customer = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_count',
            [[('name', '=', data['name']), ('customer_rank', '>', 0)]]
        )
        
        if existing_customer:
            # Get existing customer info
            customer_info = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_read',
                [[('name', '=', data['name']), ('customer_rank', '>', 0)]], 
                {'fields': ['id', 'name', 'email', 'phone'], 'limit': 1}
            )[0]
            
            return {
                'success': True,
                'customer_id': customer_info['id'],
                'customer_name': customer_info['name'],
                'company_id': data.get('company_id'),
                'email': customer_info.get('email'),
                'phone': customer_info.get('phone'),
                'message': 'Customer already exists',
                'existing': True,
                "invoice_date": data.get('invoice_date'),
                "due_date": data.get('due_date'),
                "reference": data.get('reference'),
                "subtotal": data.get('subtotal', 0.0),
                "tax_amount": data.get('tax_amount', 0.0),
                "total_amount": data.get('total_amount', 0.0),
                "currency": data.get('currency_code', 'USD'),
                "line_items": data.get('line_items', [])
            }
        
        # Prepare customer data
        customer_data = {
            'name': data['name'],
            'is_company': data.get('is_company', True),
            'customer_rank': 1,  # Mark as customer
            'supplier_rank': 0,  # Not a supplier
        }
        
        # Add company_id if provided (for multi-company setup)
        if data.get('company_id'):
            customer_data['company_id'] = data['company_id']
        
        # Add optional fields
        optional_fields = ['email', 'phone', 'website', 'street', 'city', 'zip']
        for field in optional_fields:
            if data.get(field):
                customer_data[field] = data[field]
        
        # Handle country
        if data.get('country_code'):
            country_id = get_country_id(models, db, uid, password, data['country_code'])
            if country_id:
                customer_data['country_id'] = country_id
            else:
                return {
                    'success': False,
                    'error': f'Country code "{data["country_code"]}" not found'
                }
        
        # Create customer
        customer_id = models.execute_kw(
            db, uid, password,
            'res.partner', 'create',
            [customer_data]
        )
        
        if not customer_id:
            return {
                'success': False,
                'error': 'Failed to create customer in Odoo'
            }
        
        # Get created customer information
        customer_info = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[customer_id]], 
            {'fields': ['name', 'email', 'phone', 'street', 'city', 'country_id', 'is_company']}
        )[0]
        
        return {
            'success': True,
            'customer_id': customer_id,
            'customer_name': customer_info['name'],
            'company_id': data.get('company_id'),
            'email': customer_info.get('email'),
            'phone': customer_info.get('phone'),
            'street': customer_info.get('street'),
            'city': customer_info.get('city'),
            'country': customer_info.get('country_id', [None, 'N/A'])[1],
            'is_company': customer_info.get('is_company'),
            'message': 'Customer created successfully',
            'existing': False,
            'customer_details': customer_info,
            "invoice_date": data.get('invoice_date'),
            "due_date": data.get('due_date'),
            "reference": data.get('reference'),
            "subtotal": data.get('subtotal', 0.0),
            "tax_amount": data.get('tax_amount', 0.0),
            "total_amount": data.get('total_amount', 0.0),
            "currency": data.get('currency_code', 'USD'),
            "line_items": data.get('line_items', [])
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

def list_customers():
    """Get list of customers for reference"""
    
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
        
        customers = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('customer_rank', '>', 0)]], 
            {'fields': ['id', 'name', 'email', 'phone', 'city', 'country_id', 'is_company'], 'limit': 20}
        )
        
        return {
            'success': True,
            'customers': customers,
            'count': len(customers)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }