import xmlrpc.client
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

def main(data):
    """
    Create payment from HTTP request data
    
    Expected data format:
    {
        "payment_type": "received" or "sent",  # required
        "partner_id": 123,                     # required
        "amount": 500.75,                      # required
        "payment_date": "2025-01-15",         # optional, defaults to today
        "reference": "Payment reference"       # optional
    }
    """
    
    # Validate required fields
    if not data.get('payment_type'):
        return {
            'success': False,
            'error': 'payment_type is required (received or sent)'
        }
    
    if data['payment_type'] not in ['received', 'sent']:
        return {
            'success': False,
            'error': 'payment_type must be "received" or "sent"'
        }
    
    if not data.get('partner_id'):
        return {
            'success': False,
            'error': 'partner_id is required'
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
        
        # Determine payment type and validate partner
        odoo_payment_type = 'inbound' if data['payment_type'] == 'received' else 'outbound'
        partner_id = data['partner_id']
        
        # Verify partner exists and has correct ranking
        if data['payment_type'] == 'received':
            # Money received from customer
            rank_field = 'customer_rank'
            partner_type = 'customer'
        else:
            # Money sent to vendor
            rank_field = 'supplier_rank'
            partner_type = 'vendor'
        
        partner_exists = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_count',
            [[('id', '=', partner_id), (rank_field, '>', 0)]]
        )
        
        if not partner_exists:
            return {
                'success': False,
                'error': f'Partner with ID {partner_id} not found or is not a {partner_type}'
            }
        
        # Get partner info
        partner_info = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[partner_id]], 
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
        
        payment_data = {
            'payment_type': odoo_payment_type,
            'partner_id': partner_id,
            'amount': amount,
            'date': payment_date,
        }
        
        # Add reference if provided
        if data.get('reference'):
            payment_data['ref'] = data['reference']
        
        # Create payment
        payment_id = models.execute_kw(
            db, uid, password,
            'account.payment', 'create',
            [payment_data]
        )
        
        if not payment_id:
            return {
                'success': False,
                'error': 'Failed to create payment in Odoo'
            }
        
        # Get created payment information
        payment_info = models.execute_kw(
            db, uid, password,
            'account.payment', 'read',
            [[payment_id]], 
            {'fields': ['name', 'amount', 'state', 'payment_type']}
        )[0]
        
        return {
            'success': True,
            'payment_id': payment_id,
            'payment_number': payment_info.get('name'),
            'payment_type': data['payment_type'],
            'partner_name': partner_info['name'],
            'partner_id': partner_id,
            'amount': payment_info.get('amount'),
            'state': payment_info.get('state'),
            'payment_date': payment_date,
            'message': f'Payment {data["payment_type"]} created successfully'
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

def list_payments():
    """Get list of payments for reference"""
    
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
        
        payments = models.execute_kw(
            db, uid, password,
            'account.payment', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'partner_id', 'amount', 'payment_type', 'state', 'date'], 'limit': 20}
        )
        
        return {
            'success': True,
            'payments': payments,
            'count': len(payments)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }