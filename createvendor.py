def check_vendor_exists(models, db, uid, password, vat=None, name=None, email=None, company_id=None):
    """Check if vendor already exists - now considers company context"""
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

def main(data):
    """
    Create vendor from HTTP request data - Updated to pass company_id to vendor check
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
        
        # FIXED: Check if vendor already exists WITH company context
        existing_vendor = check_vendor_exists(
            models, db, uid, password,
            vat=data.get('vat'),
            name=data.get('name'),
            email=data.get('email'),
            company_id=data.get('company_id')  # Now passes company_id
        )
        
        if existing_vendor:
            vendor_info = get_vendor_info(models, db, uid, password, existing_vendor)
            return {
                'success': True,
                'vendor_id': existing_vendor,
                'vendor_name': vendor_info.get('name') if vendor_info else data['name'],
                'company_id': data.get('company_id'),
                'message': 'Vendor already exists',
                'existing': True,
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
        
        # Create vendor
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