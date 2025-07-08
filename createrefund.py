import xmlrpc.client
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

def main(data):
    """
    Create refund from HTTP request data
    
    Expected data format:
    {
        "refund_type": "customer" or "vendor",  # required
        "partner_id": 123,                      # required (or partner_name for new)
        "partner_name": "New Partner Name",     # optional, creates new partner
        "description": "Refund reason",         # required
        "amount": 150.75,                       # required
        "refund_date": "2025-01-15",           # optional, defaults to today
        "reference": "REF-001"                  # optional
    }
    """
    
    # Validate required fields
    if not data.get('refund_type'):
        return {
            'success': False,
            'error': 'refund_type is required (customer or vendor)'
        }
    
    if data['refund_type'] not in ['customer', 'vendor']:
        return {
            'success': False,
            'error': 'refund_type must be "customer" or "vendor"'
        }
    
    if not data.get('partner_id') and not data.get('partner_name'):
        return {
            'success': False,
            'error': 'Either partner_id or partner_name is required'
        }
    
    if not data.get('description'):
        return {
            'success': False,
            'error': 'description is required'
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
        
        # Determine move type
        move_type = 'out_refund' if data['refund_type'] == 'customer' else 'in_refund'
        
        # Handle partner
        if data.get('partner_id'):
            partner_id = data['partner_id']
            
            # Verify partner exists and has correct ranking
            rank_field = 'customer_rank' if data['refund_type'] == 'customer' else 'supplier_rank'
            partner_exists = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_count',
                [[('id', '=', partner_id), (rank_field, '>', 0)]]
            )
            
            if not partner_exists:
                return {
                    'success': False,
                    'error': f'Partner with ID {partner_id} not found or is not a {data["refund_type"]}'
                }
            
            # Get partner name
            partner_info = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [[partner_id]], 
                {'fields': ['name']}
            )[0]
            partner_name = partner_info['name']
            
        else:
            # Create new partner
            partner_data = {
                'name': data['partner_name'],
                'is_company': True,
            }
            
            if data['refund_type'] == 'customer':
                partner_data['customer_rank'] = 1
                partner_data['supplier_rank'] = 0
            else:
                partner_data['supplier_rank'] = 1
                partner_data['customer_rank'] = 0
            
            partner_id = models.execute_kw(
                db, uid, password,
                'res.partner', 'create',
                [partner_data]
            )
            
            if not partner_id:
                return {
                    'success': False,
                    'error': 'Failed to create new partner'
                }
            
            partner_name = data['partner_name']
        
        # Prepare refund data
        refund_date = data.get('refund_date', datetime.now().strftime('%Y-%m-%d'))
        
        # Validate date format
        try:
            datetime.strptime(refund_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'refund_date must be in YYYY-MM-DD format'
            }
        
        refund_data = {
            'move_type': move_type,
            'partner_id': partner_id,
            'invoice_date': refund_date,
            'invoice_line_ids': [(0, 0, {
                'name': data['description'],
                'quantity': 1.0,
                'price_unit': amount,
            })]
        }
        
        # Add reference if provided
        if data.get('reference'):
            refund_data['ref'] = data['reference']
        
        # Create refund
        refund_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [refund_data]
        )
        
        if not refund_id:
            return {
                'success': False,
                'error': 'Failed to create refund in Odoo'
            }
        
        # Get created refund information
        refund_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[refund_id]], 
            {'fields': ['name', 'amount_total', 'state']}
        )[0]
        
        return {
            'success': True,
            'refund_id': refund_id,
            'refund_number': refund_info.get('name'),
            'refund_type': data['refund_type'],
            'partner_name': partner_name,
            'partner_id': partner_id,
            'total_amount': refund_info.get('amount_total'),
            'state': refund_info.get('state'),
            'refund_date': refund_date,
            'description': data['description'],
            'message': f'{data["refund_type"].title()} refund created successfully'
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

def list_refunds():
    """Get list of refunds for reference"""
    
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
        
        refunds = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('move_type', 'in', ['out_refund', 'in_refund'])]], 
            {'fields': ['id', 'name', 'partner_id', 'move_type', 'amount_total', 'state', 'invoice_date'], 'limit': 20}
        )
        
        return {
            'success': True,
            'refunds': refunds,
            'count': len(refunds)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }