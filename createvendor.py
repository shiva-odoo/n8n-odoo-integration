import xmlrpc.client
import logging
from typing import Dict, Optional, Union
import os
# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def check_vendor_exists_comprehensive(models, db, uid, password, data, company_id=None):
    """
    Comprehensive check if vendor already exists using multiple criteria
    Returns vendor_id if found, None otherwise
    """
    try:
        base_domain = [('is_company', '=', True), ('supplier_rank', '>', 0)]
        
        # Add company context to avoid cross-company matches
        if company_id:
            base_domain.extend(['|', ('company_id', '=', company_id), ('company_id', '=', False)])
        
        # Priority order for matching:
        # 1. VAT number (most reliable)
        # 2. Email + Name combination
        # 3. Exact name match
        
        search_criteria = []
        
        # 1. Check by VAT if provided
        if data.get('vat'):
            vat_domain = base_domain + [('vat', '=', data['vat'])]
            search_criteria.append(vat_domain)
        
        # 2. Check by email + name combination if both provided
        if data.get('email') and data.get('name'):
            email_name_domain = base_domain + [
                ('email', '=', data['email']),
                ('name', '=', data['name'])
            ]
            search_criteria.append(email_name_domain)
        
        # 3. Check by email only if provided (but no name match)
        elif data.get('email'):
            email_domain = base_domain + [('email', '=', data['email'])]
            search_criteria.append(email_domain)
        
        # 4. Check by exact name match as fallback
        if data.get('name'):
            name_domain = base_domain + [('name', '=', data['name'])]
            search_criteria.append(name_domain)
        
        # Search using each criteria in priority order
        for domain in search_criteria:
            vendor_ids = models.execute_kw(
                db, uid, password,
                'res.partner', 'search',
                [domain], {'limit': 1}
            )
            
            if vendor_ids:
                return vendor_ids[0]
        
        return None
        
    except Exception as e:
        print(f"Error checking for vendor duplicates: {str(e)}")
        return None

def main(data):
    """
    Create vendor from HTTP request data
    
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
        "country_code": "US",            # optional, ISO country code
        "state_code": "CA",              # optional, state code
        "payment_terms": 30,             # optional, payment terms in days
        "currency_code": "USD"           # optional, currency code
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
        
        # Check if vendor already exists using comprehensive method
        existing_vendor = check_vendor_exists_comprehensive(
            models, db, uid, password, data, data.get('company_id')
        )
        
        if existing_vendor:
            # Get vendor details
            vendor_info = get_vendor_info(models, db, uid, password, existing_vendor)
            
            return {
                'success': True,
                'vendor_id': existing_vendor,
                'vendor_name': vendor_info.get('name') if vendor_info else data['name'],
                'company_id': data.get('company_id'),
                'message': 'Vendor already exists - no duplicate created',
                'existing': True,
                'vendor_details': vendor_info,
                # Pass through any additional fields that might be used for bill creation
                "invoice_date": data.get('invoice_date'),
                "due_date": data.get('due_date'),
                "payment_reference": data.get('payment_reference'),
                "subtotal": data.get('subtotal', 0.0),
                "tax_amount": data.get('tax_amount', 0.0),
                "total_amount": data.get('total_amount', 0.0),
                "currency": data.get('currency_code', 'USD'),
                "vendor_ref": data.get('vendor_ref'),
                "line_items": data.get('line_items', [])
            }
        
        # Create vendor if no duplicate found
        if is_basic_vendor(data):
            vendor_id = create_vendor_basic(models, db, uid, password, data)
        else:
            vendor_id = create_vendor_comprehensive(models, db, uid, password, data)
        
        if not vendor_id:
            return {
                'success': False,
                'error': 'Failed to create vendor in Odoo'
            }
        
        # Get created vendor information
        vendor_info = get_vendor_info(models, db, uid, password, vendor_id)
        
        return {
            'success': True,
            'vendor_id': vendor_id,
            'vendor_name': vendor_info.get('name') if vendor_info else data['name'],
            'company_id': data.get('company_id'),
            'message': 'Vendor created successfully',
            'existing': False,
            'vendor_details': vendor_info,
            # Pass through any additional fields that might be used for bill creation
            "invoice_date": data.get('invoice_date'),
            "due_date": data.get('due_date'),
            "payment_reference": data.get('payment_reference'),
            "subtotal": data.get('subtotal', 0.0),
            "tax_amount": data.get('tax_amount', 0.0),
            "total_amount": data.get('total_amount', 0.0),
            "currency": data.get('currency_code', 'USD'),
            "vendor_ref": data.get('vendor_ref'),
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

def is_basic_vendor(data):
    """Determine if this should be a basic or comprehensive vendor"""
    comprehensive_fields = ['vat', 'street', 'city', 'country_code', 'payment_terms', 'currency_code']
    return not any(data.get(field) for field in comprehensive_fields)

def check_vendor_exists(models, db, uid, password, vat=None, name=None, email=None, company_id=None):
    """Legacy function - kept for backward compatibility"""
    try:
        domain = [('is_company', '=', True), ('supplier_rank', '>', 0)]
        
        # CRITICAL: Add company context to avoid cross-company matches
        if company_id:
            # In Odoo, company_id can be False for records available to all companies
            # So we need to check for both the specific company AND company_id=False
            domain.append('|')  # OR condition
            domain.append(('company_id', '=', company_id))
            domain.append(('company_id', '=', False))
        
        # Add the search criteria
        if vat:
            domain.append(('vat', '=', vat))
        elif email:
            domain.append(('email', '=', email))
        elif name:
            domain.append(('name', '=', name))
        else:
            return None
            
        vendor_ids = models.execute_kw(
            db, uid, password,
            'res.partner', 'search',
            [domain], {'limit': 1}
        )
        
        return vendor_ids[0] if vendor_ids else None
        
    except Exception:
        return None

def create_vendor_basic(models, db, uid, password, data):
    """Create a basic vendor with minimal information"""
    
    vendor_data = {
        'name': data['name'],
        'is_company': True,
        'supplier_rank': 1,
        'customer_rank': 0,
    }
    
    # Add optional basic fields
    if data.get('email'):
        vendor_data['email'] = data['email']
    if data.get('phone'):
        vendor_data['phone'] = data['phone']
    if data.get('website'):
        vendor_data['website'] = data['website']

    # Add company_id if provided (for multi-company setup)
    if data.get('company_id'):
        vendor_data['company_id'] = data['company_id']
        
    try:
        vendor_id = models.execute_kw(
            db, uid, password,
            'res.partner', 'create',
            [vendor_data]
        )
        return vendor_id
        
    except Exception as e:
        raise Exception(f"Error creating basic vendor: {e}")

def create_vendor_comprehensive(models, db, uid, password, data):
    """Create a comprehensive vendor with full details"""
    
    vendor_data = {
        'name': data['name'],
        'is_company': True,
        'supplier_rank': 1,
        'customer_rank': 0,
    }
    
    # Add optional fields
    optional_fields = ['vat', 'email', 'phone', 'website', 'street', 'city', 'zip']
    for field in optional_fields:
        if data.get(field):
            vendor_data[field] = data[field]

    # Add company_id if provided (for multi-company setup)
    if data.get('company_id'):
        vendor_data['company_id'] = data['company_id']

    # Handle country
    if data.get('country_code'):
        country_id = get_country_id(models, db, uid, password, data['country_code'])
        if country_id:
            vendor_data['country_id'] = country_id

    # Handle state
    if data.get('state_code') and data.get('country_code'):
        state_id = get_state_id(models, db, uid, password, data['state_code'], data['country_code'])
        if state_id:
            vendor_data['state_id'] = state_id

    # Handle payment terms
    if data.get('payment_terms'):
        payment_term_id = get_payment_term_id(models, db, uid, password, data['payment_terms'])
        if payment_term_id:
            vendor_data['property_supplier_payment_term_id'] = payment_term_id

    # Handle currency
    if data.get('currency_code'):
        currency_id = get_currency_id(models, db, uid, password, data['currency_code'])
        if currency_id:
            vendor_data['property_purchase_currency_id'] = currency_id

    try:
        vendor_id = models.execute_kw(
            db, uid, password,
            'res.partner', 'create',
            [vendor_data]
        )
        return vendor_id
        
    except Exception as e:
        raise Exception(f"Error creating comprehensive vendor: {e}")

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

def get_payment_term_id(models, db, uid, password, days):
    """Get or create payment term for specified days"""
    try:
        # Search for existing payment term
        term_ids = models.execute_kw(
            db, uid, password,
            'account.payment.term', 'search',
            [[('name', 'ilike', f'{days} days')]], {'limit': 1}
        )
        
        if term_ids:
            return term_ids[0]
        
        # Create new payment term if not found
        term_data = {
            'name': f'{days} Days',
            'line_ids': [(0, 0, {
                'value': 'balance',
                'days': days
            })]
        }
        
        term_id = models.execute_kw(
            db, uid, password,
            'account.payment.term', 'create',
            [term_data]
        )
        return term_id
        
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

def get_vendor_info(models, db, uid, password, vendor_id):
    """Get vendor information by ID"""
    try:
        vendor_data = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[vendor_id]], 
            {'fields': ['name', 'vat', 'email', 'phone', 'street', 'city', 'country_id', 'supplier_rank']}
        )
        return vendor_data[0] if vendor_data else None
    except Exception:
        return None

def list_vendors():
    """Get list of all vendors for reference"""
    
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
        
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('supplier_rank', '>', 0)]], 
            {'fields': ['id', 'name', 'email', 'vat', 'city', 'country_id'], 'order': 'name'}
        )
        
        return {
            'success': True,
            'vendors': vendors,
            'count': len(vendors)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }