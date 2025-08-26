import xmlrpc.client
import os
# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def check_customer_exists_comprehensive(models, db, uid, password, data, company_id=None):
    """
    Comprehensive check if customer already exists using multiple criteria
    Returns customer_id if found, None otherwise
    """
    try:
        base_domain = [('customer_rank', '>', 0)]
        
        # Add company context to avoid cross-company matches
        if company_id:
            base_domain.extend(['|', ('company_id', '=', company_id), ('company_id', '=', False)])
        
        # Priority order for matching:
        # 1. Email + Name combination (most reliable for customers)
        # 2. Email only
        # 3. Exact name match
        
        search_criteria = []
        
        # 1. Check by email + name combination if both provided
        if data.get('email') and data.get('name'):
            email_name_domain = base_domain + [
                ('email', '=', data['email']),
                ('name', '=', data['name'])
            ]
            search_criteria.append(email_name_domain)
        
        # 2. Check by email only if provided (but no name match yet)
        elif data.get('email'):
            email_domain = base_domain + [('email', '=', data['email'])]
            search_criteria.append(email_domain)
        
        # 3. Check by exact name match as fallback
        if data.get('name'):
            name_domain = base_domain + [('name', '=', data['name'])]
            search_criteria.append(name_domain)
        
        # Search using each criteria in priority order
        for domain in search_criteria:
            customer_ids = models.execute_kw(
                db, uid, password,
                'res.partner', 'search',
                [domain], {'limit': 1}
            )
            
            if customer_ids:
                return customer_ids[0]
        
        return None
        
    except Exception as e:
        print(f"Error checking for customer duplicates: {str(e)}")
        return None

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
        
        # Check if customer already exists using comprehensive method
        existing_customer_id = check_customer_exists_comprehensive(
            models, db, uid, password, data, data.get('company_id')
        )
        
        if existing_customer_id:
            # Get existing customer info
            customer_info = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [[existing_customer_id]], 
                {'fields': ['id', 'name', 'email', 'phone', 'street', 'city', 'country_id', 'is_company']}
            )[0]
            
            return {
                'success': True,
                'customer_id': customer_info['id'],
                'customer_name': customer_info['name'],
                'company_id': data.get('company_id'),
                'email': customer_info.get('email'),
                'phone': customer_info.get('phone'),
                'street': customer_info.get('street'),
                'city': customer_info.get('city'),
                'country': customer_info.get('country_id', [None, 'N/A'])[1] if customer_info.get('country_id') else 'N/A',
                'is_company': customer_info.get('is_company'),
                'message': 'Customer already exists - no duplicate created',
                'existing': True,
                'customer_details': customer_info,
                # Pass through any additional fields that might be used for invoice creation
                "invoice_date": data.get('invoice_date'),
                "due_date": data.get('due_date'),
                "reference": data.get('reference'),
                "subtotal": data.get('subtotal', 0.0),
                "tax_amount": data.get('tax_amount', 0.0),
                "total_amount": data.get('total_amount', 0.0),
                "currency": data.get('currency_code', 'USD'),
                "line_items": data.get('line_items', [])
            }
        
        # Prepare customer data for creation
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
            'country': customer_info.get('country_id', [None, 'N/A'])[1] if customer_info.get('country_id') else 'N/A',
            'is_company': customer_info.get('is_company'),
            'message': 'Customer created successfully',
            'existing': False,
            'customer_details': customer_info,
            # Pass through any additional fields that might be used for invoice creation
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

def check_customer_exists(models, db, uid, password, name=None, email=None, company_id=None):
    """Legacy function - kept for backward compatibility"""
    try:
        domain = [('customer_rank', '>', 0)]
        
        # CRITICAL: Add company context to avoid cross-company matches
        if company_id:
            # In Odoo, company_id can be False for records available to all companies
            # So we need to check for both the specific company AND company_id=False
            domain.append('|')  # OR condition
            domain.append(('company_id', '=', company_id))
            domain.append(('company_id', '=', False))
        
        # Add the search criteria
        if name:
            domain.append(('name', '=', name))
        elif email:
            domain.append(('email', '=', email))
        else:
            return None
            
        customer_ids = models.execute_kw(
            db, uid, password,
            'res.partner', 'search',
            [domain], {'limit': 1}
        )
        
        return customer_ids[0] if customer_ids else None
        
    except Exception:
        return None

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