import xmlrpc.client
import logging
from typing import Dict, Optional, Union
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

def get_vendors_for_company(models, db, uid, password, company_id=None):
    """
    Fetch existing vendors for a specific company or all vendors if no company specified
    """
    try:
        # Base domain for vendors
        domain = [('is_company', '=', True), ('supplier_rank', '>', 0)]
        
        # Add company filter if specified
        if company_id:
            # In Odoo multi-company setup:
            # - Records with company_id = specific_company belong to that company
            # - Records with company_id = False are shared across all companies
            domain.extend(['|', ('company_id', '=', company_id), ('company_id', '=', False)])
        
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'email', 'vat', 'company_id']}
        )
        
        return vendors
        
    except Exception as e:
        print(f"Error fetching vendors: {str(e)}")
        return []

def check_vendor_exists_comprehensive(models, db, uid, password, data, company_id=None):
    """
    Comprehensive check if vendor already exists using multiple criteria including fuzzy matching
    Returns vendor_id if found, None otherwise
    """
    try:
        # First, get all existing vendors for the company
        existing_vendors = get_vendors_for_company(models, db, uid, password, company_id)
        
        if not existing_vendors:
            return None
        
        input_name = data.get('name', '').strip()
        input_email = data.get('email', '').strip().lower() if data.get('email') else None
        input_vat = data.get('vat', '').strip() if data.get('vat') else None
        
        # Priority order for matching:
        # 1. VAT number (exact match - most reliable)
        # 2. Email exact match
        # 3. Email + Name combination (exact)
        # 4. Fuzzy name matching (similarity > 85%)
        # 5. Exact name match (fallback)
        
        # 1. Check by VAT if provided (exact match)
        if input_vat:
            for vendor in existing_vendors:
                if vendor.get('vat') and vendor['vat'].strip().lower() == input_vat.lower():
                    print(f"Found vendor by VAT match: {vendor['name']}")
                    return vendor['id']
        
        # 2. Check by email exact match
        if input_email:
            for vendor in existing_vendors:
                vendor_email = vendor.get('email', '').strip().lower() if vendor.get('email') else ''
                if vendor_email and vendor_email == input_email:
                    print(f"Found vendor by email match: {vendor['name']}")
                    return vendor['id']
        
        # 3. Check by email + name combination (both exact)
        if input_email and input_name:
            for vendor in existing_vendors:
                vendor_email = vendor.get('email', '').strip().lower() if vendor.get('email') else ''
                vendor_name = vendor.get('name', '').strip()
                if (vendor_email == input_email and 
                    vendor_name.lower() == input_name.lower()):
                    print(f"Found vendor by email+name combination: {vendor['name']}")
                    return vendor['id']
        
        # 4. Fuzzy name matching (similarity > 85%)
        if input_name:
            normalized_input = normalize_string(input_name)
            best_match = None
            best_similarity = 0
            
            for vendor in existing_vendors:
                vendor_name = vendor.get('name', '').strip()
                if not vendor_name:
                    continue
                    
                normalized_vendor = normalize_string(vendor_name)
                
                # Calculate similarity
                sim_score = similarity(normalized_input, normalized_vendor)
                
                # Also check raw similarity without normalization
                raw_sim_score = similarity(input_name, vendor_name)
                
                # Take the higher of the two scores
                final_score = max(sim_score, raw_sim_score)
                
                if final_score > best_similarity:
                    best_similarity = final_score
                    best_match = vendor
            
            # If similarity is above threshold (85%), consider it a match
            if best_similarity > 0.85:
                print(f"Found vendor by fuzzy match (similarity: {best_similarity:.2%}): {best_match['name']}")
                return best_match['id']
        
        # 5. Exact name match (fallback)
        if input_name:
            for vendor in existing_vendors:
                vendor_name = vendor.get('name', '').strip()
                if vendor_name.lower() == input_name.lower():
                    print(f"Found vendor by exact name match: {vendor['name']}")
                    return vendor['id']
        
        return None
        
    except Exception as e:
        print(f"Error checking for vendor duplicates: {str(e)}")
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
    Create vendor from HTTP request data
    
    Expected data format:
    {
        "name": "Company Name",          # REQUIRED
        "company_id": 1,                 # REQUIRED - company ID for multi-company setup
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
        
        # Handle company_id conversion from string to int if needed
        try:
            company_id = int(data['company_id'])
            data['company_id'] = company_id  # Update the data dict for later use
        except (ValueError, TypeError):
            return {
                'success': False,
                'error': 'company_id must be a valid integer'
            }
        
        # Check if vendor already exists using comprehensive method (including fuzzy matching)
        existing_vendor = check_vendor_exists_comprehensive(
            models, db, uid, password, data, company_id
        )
        
        if existing_vendor:
            # Get vendor details
            vendor_info = get_vendor_info(models, db, uid, password, existing_vendor)
            
            return {
                'success': True,
                'vendor_id': existing_vendor,
                'vendor_name': vendor_info.get('name') if vendor_info else data['name'],
                'company_id': company_id,
                'message': 'Vendor already exists - no duplicate created',
                'exists': True,
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
            'company_id': company_id,
            'message': 'Vendor created successfully',
            'exists': False,
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
    return not any(is_valid_value(data.get(field)) for field in comprehensive_fields)

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
    
    # Add optional basic fields, but only if they have valid values
    if is_valid_value(data.get('email')):
        vendor_data['email'] = data['email']
    if is_valid_value(data.get('phone')):
        vendor_data['phone'] = data['phone']
    if is_valid_value(data.get('website')):
        vendor_data['website'] = data['website']

    # Add company_id (now required for multi-company setup)
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
    
    # Add optional fields, but only if they have valid values (not "none", "null", empty, etc.)
    optional_fields = ['vat', 'email', 'phone', 'website', 'street', 'city', 'zip']
    for field in optional_fields:
        if is_valid_value(data.get(field)):
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

def list_vendors(company_id=None):
    """Get list of vendors for reference, optionally filtered by company_id"""
    
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
        
        # Base domain for vendors
        domain = [('supplier_rank', '>', 0)]
        
        # Add company filter if specified
        if company_id:
            domain.extend(['|', ('company_id', '=', company_id), ('company_id', '=', False)])
        
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'email', 'vat', 'city', 'country_id', 'company_id'], 'order': 'name'}
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