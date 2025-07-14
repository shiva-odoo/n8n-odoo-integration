import xmlrpc.client
from datetime import datetime
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
    Create vendor payment from HTTP request data
    
    Expected data format:
    {
        "vendor_id": 123,                       # required
        "amount": 500.75,                       # required
        "payment_date": "2025-01-15",          # optional, defaults to today
        "reference": "Payment reference"        # optional
    }
    """
    
    # Validate required fields
    if not data.get('vendor_id'):
        return {
            'success': False,
            'error': 'vendor_id is required'
        }
    
    if not data.get('amount'):
        return {
            'success': False,
            'error': 'amount is required'
        }
    
    try:
        amount = float(data['amount'])
        if amount <= 0:
            return {
                'success': False,
                'error': 'amount must be positive'
            }
    except (ValueError, TypeError):
        return {
            'success': False,
            'error': 'amount must be a valid number'
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
        
        vendor_id = data['vendor_id']
        
        # Verify vendor exists and is a supplier
        vendor_exists = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_count',
            [[('id', '=', vendor_id), ('supplier_rank', '>', 0)]]
        )
        
        if not vendor_exists:
            return {
                'success': False,
                'error': f'Vendor with ID {vendor_id} not found or is not a supplier'
            }
        
        # Get vendor info
        vendor_info = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[vendor_id]], 
            {'fields': ['name']}
        )[0]
        
        # Prepare payment data
        payment_date = data.get('payment_date', datetime.now().strftime('%Y-%m-%d'))
        
        # Validate date format
        try:
            datetime.strptime(payment_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'payment_date must be in YYYY-MM-DD format'
            }
        
        # Create vendor payment (outbound payment to supplier)
        payment_data = {
            'payment_type': 'outbound',      # Money going OUT to vendor
            'partner_type': 'supplier',      # Partner is a SUPPLIER  
            'partner_id': vendor_id,
            'amount': amount,
            'date': payment_date,
        }
        
        # Add reference if provided
        if data.get('reference'):
            payment_data['ref'] = data['reference']
        
        # Try creating the payment with multiple approaches
        payment_id = None
        error_messages = []
        
        # Method 1: Full payment data with partner_type
        try:
            payment_id = models.execute_kw(
                db, uid, password,
                'account.payment', 'create',
                [payment_data]
            )
        except Exception as e1:
            error_messages.append(f"Method 1 failed: {str(e1)}")
            
            # Method 2: Without partner_type field
            try:
                simplified_data = {
                    'payment_type': 'outbound',
                    'partner_id': vendor_id,
                    'amount': amount,
                    'date': payment_date,
                }
                
                if data.get('reference'):
                    simplified_data['ref'] = data['reference']
                
                payment_id = models.execute_kw(
                    db, uid, password,
                    'account.payment', 'create',
                    [simplified_data]
                )
            except Exception as e2:
                error_messages.append(f"Method 2 failed: {str(e2)}")
        
        if not payment_id:
            return {
                'success': False,
                'error': f'Failed to create vendor payment. Errors: {"; ".join(error_messages)}'
            }
        
        # Get created payment information
        payment_info = models.execute_kw(
            db, uid, password,
            'account.payment', 'read',
            [[payment_id]], 
            {'fields': ['name', 'amount', 'state', 'payment_type', 'partner_type']}
        )[0]
        
        return {
            'success': True,
            'payment_id': payment_id,
            'payment_number': payment_info.get('name'),
            'vendor_name': vendor_info['name'],
            'vendor_id': vendor_id,
            'amount': payment_info.get('amount'),
            'payment_type': 'vendor_payment',
            'state': payment_info.get('state'),
            'payment_date': payment_date,
            'message': 'Vendor payment created successfully'
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

def list_vendor_payments():
    """Get list of vendor payments for reference"""
    
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
        
        # Get outbound payments (vendor payments)
        payments = models.execute_kw(
            db, uid, password,
            'account.payment', 'search_read',
            [[('payment_type', '=', 'outbound')]], 
            {'fields': ['id', 'name', 'partner_id', 'amount', 'state', 'date'], 'limit': 20}
        )
        
        return {
            'success': True,
            'vendor_payments': payments,
            'count': len(payments)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }