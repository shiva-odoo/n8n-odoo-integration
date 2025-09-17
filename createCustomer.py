import xmlrpc.client
import os
from difflib import SequenceMatcher

# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def similarity(a, b):
    """Calculate similarity between two strings using SequenceMatcher"""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

def normalize_string(s):
    """Normalize string for better comparison"""
    if not s:
        return ""
    # Remove common suffixes and prefixes, extra spaces, punctuation
    s = s.lower().strip()
    # Remove common company suffixes
    suffixes = [' inc', ' inc.', ' ltd', ' ltd.', ' llc', ' corp', ' corp.', ' co.', ' co', ' limited']
    for suffix in suffixes:
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
    # Remove extra punctuation and spaces
    s = ''.join(c for c in s if c.isalnum() or c.isspace())
    s = ' '.join(s.split())  # normalize whitespace
    return s

def get_customers_for_company(models, db, uid, password, company_id=None):
    """
    Fetch existing customers for a specific company or all customers if no company specified
    """
    try:
        # Base domain for customers
        domain = [('customer_rank', '>', 0)]
        
        # Add company filter if specified
        if company_id:
            # In Odoo multi-company setup:
            # - Records with company_id = specific_company belong to that company
            # - Records with company_id = False are shared across all companies
            domain.extend(['|', ('company_id', '=', company_id), ('company_id', '=', False)])
        
        customers = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'email', 'phone', 'company_id']}
        )
        
        return customers
        
    except Exception as e:
        print(f"Error fetching customers: {str(e)}")
        return []

def check_customer_exists_comprehensive(models, db, uid, password, data, company_id=None):
    """
    Comprehensive check if customer already exists using multiple criteria including fuzzy matching
    Returns customer_id if found, None otherwise
    """
    try:
        # First, get all existing customers for the company
        existing_customers = get_customers_for_company(models, db, uid, password, company_id)
        
        if not existing_customers:
            return None
        
        input_name = data.get('name', '').strip()
        input_email = data.get('email', '').strip().lower() if data.get('email') else None
        input_phone = data.get('phone', '').strip() if data.get('phone') else None
        
        # Priority order for matching:
        # 1. Email exact match (most reliable for customers)
        # 2. Phone exact match
        # 3. Email + Name combination (exact)
        # 4. Fuzzy name matching (similarity > 85%)
        # 5. Exact name match (fallback)
        
        # 1. Check by email exact match
        if input_email:
            for customer in existing_customers:
                customer_email = customer.get('email', '').strip().lower() if customer.get('email') else ''
                if customer_email and customer_email == input_email:
                    print(f"Found customer by email match: {customer['name']}")
                    return customer['id']
        
        # 2. Check by phone exact match
        if input_phone:
            # Normalize phone numbers by removing common separators
            normalized_input_phone = ''.join(c for c in input_phone if c.isdigit())
            for customer in existing_customers:
                customer_phone = customer.get('phone', '').strip() if customer.get('phone') else ''
                if customer_phone:
                    normalized_customer_phone = ''.join(c for c in customer_phone if c.isdigit())
                    if normalized_customer_phone and normalized_customer_phone == normalized_input_phone:
                        print(f"Found customer by phone match: {customer['name']}")
                        return customer['id']
        
        # 3. Check by email + name combination (both exact)
        if input_email and input_name:
            for customer in existing_customers:
                customer_email = customer.get('email', '').strip().lower() if customer.get('email') else ''
                customer_name = customer.get('name', '').strip()
                if (customer_email == input_email and 
                    customer_name.lower() == input_name.lower()):
                    print(f"Found customer by email+name combination: {customer['name']}")
                    return customer['id']
        
        # 4. Fuzzy name matching (similarity > 85%)
        if input_name:
            normalized_input = normalize_string(input_name)
            best_match = None
            best_similarity = 0
            
            for customer in existing_customers:
                customer_name = customer.get('name', '').strip()
                if not customer_name:
                    continue
                    
                normalized_customer = normalize_string(customer_name)
                
                # Calculate similarity
                sim_score = similarity(normalized_input, normalized_customer)
                
                # Also check raw similarity without normalization
                raw_sim_score = similarity(input_name, customer_name)
                
                # Take the higher of the two scores
                final_score = max(sim_score, raw_sim_score)
                
                if final_score > best_similarity:
                    best_similarity = final_score
                    best_match = customer
            
            # If similarity is above threshold (85%), consider it a match
            if best_similarity > 0.85:
                print(f"Found customer by fuzzy match (similarity: {best_similarity:.2%}): {best_match['name']}")
                return best_match['id']
        
        # 5. Exact name match (fallback)
        if input_name:
            for customer in existing_customers:
                customer_name = customer.get('name', '').strip()
                if customer_name.lower() == input_name.lower():
                    print(f"Found customer by exact name match: {customer['name']}")
                    return customer['id']
        
        return None
        
    except Exception as e:
        print(f"Error checking for customer duplicates: {str(e)}")
        return None

def is_valid_value(value):
    """
    Check if a value is valid (not None, not empty string, not "none", not "null")
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value.lower() not in ['none', 'null', '']
    return bool(value)

def main(data):
    """
    Create customer from HTTP request data
    
    Expected data format:
    {
        "name": "Customer Name",                 # REQUIRED
        "company_id": 1,                         # REQUIRED - company ID for multi-company setup
        "is_company": true,                      # optional, defaults to true
        "email": "contact@customer.com",         # optional
        "phone": "+1234567890",                  # optional
        "website": "https://website.com",        # optional
        "street": "123 Main St",                 # optional
        "city": "City Name",                     # optional
        "zip": "12345",                          # optional
        "country_code": "US"                     # optional, ISO country code
    }
    """
    
    # Validate required fields
    if not data.get('name'):
        return {
            'success': False,
            'error': 'name is required'
        }
    
    if not data.get('company_id'):
        return {
            'success': False,
            'error': 'company_id is required'
        }
    
    # Connection details
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    if not url or not db or not username or not password:
        return {
            'success': False,
            'error': 'Required Odoo environment variables are missing (ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY)'
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
        
        # Handle company_id conversion from string to int if needed
        try:
            company_id = int(data['company_id'])
            data['company_id'] = company_id  # Update the data dict for later use
        except (ValueError, TypeError):
            return {
                'success': False,
                'error': 'company_id must be a valid integer'
            }
        
        # Check if customer already exists using comprehensive method (including fuzzy matching)
        existing_customer_id = check_customer_exists_comprehensive(
            models, db, uid, password, data, company_id
        )
        
        if existing_customer_id:
            # Get existing customer info
            customer_info = get_customer_info(models, db, uid, password, existing_customer_id)
            
            return {
                'success': True,
                'customer_id': existing_customer_id,
                'customer_name': customer_info.get('name') if customer_info else data['name'],
                'company_id': company_id,
                'email': customer_info.get('email') if customer_info else None,
                'phone': customer_info.get('phone') if customer_info else None,
                'street': customer_info.get('street') if customer_info else None,
                'city': customer_info.get('city') if customer_info else None,
                'country': customer_info.get('country_id', [None, 'N/A'])[1] if customer_info and customer_info.get('country_id') else 'N/A',
                'is_company': customer_info.get('is_company') if customer_info else None,
                'message': 'Customer already exists - no duplicate created',
                'exists': True,
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
            'company_id': company_id  # Now required for multi-company setup
        }
        
        # Add optional fields, but only if they have valid values (not "none", "null", empty, etc.)
        optional_fields = ['email', 'phone', 'website', 'street', 'city', 'zip']
        for field in optional_fields:
            if is_valid_value(data.get(field)):
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
        customer_info = get_customer_info(models, db, uid, password, customer_id)
        
        return {
            'success': True,
            'customer_id': customer_id,
            'customer_name': customer_info.get('name') if customer_info else data['name'],
            'company_id': company_id,
            'email': customer_info.get('email') if customer_info else None,
            'phone': customer_info.get('phone') if customer_info else None,
            'street': customer_info.get('street') if customer_info else None,
            'city': customer_info.get('city') if customer_info else None,
            'country': customer_info.get('country_id', [None, 'N/A'])[1] if customer_info and customer_info.get('country_id') else 'N/A',
            'is_company': customer_info.get('is_company') if customer_info else None,
            'message': 'Customer created successfully',
            'exists': False,
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

def get_customer_info(models, db, uid, password, customer_id):
    """Get customer information by ID"""
    try:
        customer_data = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[customer_id]], 
            {'fields': ['name', 'email', 'phone', 'street', 'city', 'country_id', 'is_company', 'customer_rank']}
        )
        return customer_data[0] if customer_data else None
    except Exception:
        return None

def list_customers(company_id=None):
    """Get list of customers for reference, optionally filtered by company_id"""
    
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
        
        # Base domain for customers
        domain = [('customer_rank', '>', 0)]
        
        # Add company filter if specified
        if company_id:
            domain.extend(['|', ('company_id', '=', company_id), ('company_id', '=', False)])
        
        customers = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'email', 'phone', 'city', 'country_id', 'is_company', 'company_id'], 'order': 'name'}
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