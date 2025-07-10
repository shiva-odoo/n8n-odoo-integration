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
    Modify vendor from HTTP request data
    
    Expected data format:
    {
        "vendor_id": 123,                      # required
        "name": "Updated Vendor Name",         # optional
        "email": "new@email.com",              # optional
        "phone": "+1-555-987-6543",           # optional
        "website": "https://newsite.com",      # optional
        "vat": "NEW-VAT-123",                  # optional
        "street": "456 New Street",            # optional
        "city": "New City",                    # optional
        "zip": "54321",                        # optional
        "country_code": "CA"                   # optional
    }
    """
    
    # Validate required fields
    if not data.get('vendor_id'):
        return {
            'success': False,
            'error': 'vendor_id is required'
        }
    
    try:
        vendor_id = int(data['vendor_id'])
    except (ValueError, TypeError):
        return {
            'success': False,
            'error': 'vendor_id must be a valid number'
        }
    
    # Connection details
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
        
        # Check if vendor exists
        vendor_exists = models.execute_kw(
            db, uid, password,
            'res.partner', 'search',
            [[('id', '=', vendor_id)]], {'limit': 1}
        )
        
        if not vendor_exists:
            return {
                'success': False,
                'error': f'Vendor with ID {vendor_id} not found'
            }
        
        # Get current vendor info
        current_vendor = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[vendor_id]], 
            {'fields': ['name', 'email', 'phone', 'vat', 'website', 'street', 'city', 'zip', 'country_id']}
        )[0]
        
        # Collect updates from request data
        updates = {}
        changes_made = []
        
        # Basic contact fields
        basic_fields = ['name', 'email', 'phone', 'vat', 'website', 'street', 'city', 'zip']
        for field in basic_fields:
            if data.get(field) is not None:
                new_value = data[field].strip() if isinstance(data[field], str) else data[field]
                if new_value != current_vendor.get(field):
                    updates[field] = new_value
                    old_value = current_vendor.get(field, 'N/A')
                    changes_made.append(f"{field}: '{old_value}' → '{new_value}'")
        
        # Handle country
        if data.get('country_code'):
            country_id = get_country_id(models, db, uid, password, data['country_code'])
            if country_id:
                current_country_id = current_vendor['country_id'][0] if current_vendor.get('country_id') else None
                if country_id != current_country_id:
                    updates['country_id'] = country_id
                    current_country_name = current_vendor['country_id'][1] if current_vendor.get('country_id') else 'N/A'
                    changes_made.append(f"country: '{current_country_name}' → '{data['country_code']}'")
            else:
                return {
                    'success': False,
                    'error': f'Country code "{data["country_code"]}" not found'
                }
        
        # Check if any updates were provided
        if not updates:
            return {
                'success': True,
                'vendor_id': vendor_id,
                'vendor_name': current_vendor['name'],
                'message': 'No changes detected - vendor information is already up to date',
                'current_info': current_vendor
            }
        
        # Apply updates
        try:
            result = models.execute_kw(
                db, uid, password,
                'res.partner', 'write',
                [[vendor_id], updates]
            )
            
            if not result:
                return {
                    'success': False,
                    'error': 'Failed to update vendor - write operation returned false'
                }
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to update vendor: {str(e)}'
            }
        
        # Get updated vendor info
        try:
            updated_vendor = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [[vendor_id]], 
                {'fields': ['name', 'email', 'phone', 'vat', 'website', 'street', 'city', 'zip', 'country_id']}
            )[0]
        except Exception:
            updated_vendor = current_vendor  # Fallback if read fails
        
        return {
            'success': True,
            'vendor_id': vendor_id,
            'vendor_name': updated_vendor['name'],
            'changes_made': changes_made,
            'updated_fields': list(updates.keys()),
            'message': f'Vendor updated successfully. {len(changes_made)} changes applied.',
            'updated_info': {
                'name': updated_vendor.get('name'),
                'email': updated_vendor.get('email'),
                'phone': updated_vendor.get('phone'),
                'vat': updated_vendor.get('vat'),
                'website': updated_vendor.get('website'),
                'street': updated_vendor.get('street'),
                'city': updated_vendor.get('city'),
                'zip': updated_vendor.get('zip'),
                'country': updated_vendor['country_id'][1] if updated_vendor.get('country_id') else None
            }
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

def modify(data):
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

def get_vendor_details(vendor_id):
    """Get detailed vendor information"""
    
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
        
        vendor = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('id', '=', vendor_id), ('supplier_rank', '>', 0)]], 
            {'fields': ['id', 'name', 'email', 'phone', 'vat', 'website', 'street', 'city', 'zip', 'country_id', 'active']}
        )
        
        if not vendor:
            return {'success': False, 'error': 'Vendor not found'}
        
        return {
            'success': True,
            'vendor': vendor[0]
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }