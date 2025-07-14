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
    Create customer invoice from HTTP request data
    
    Expected data format:
    {
        "customer_id": 123,                     # required (or customer_name for new)
        "customer_name": "New Customer Name",   # optional, creates new customer
        "customer_email": "contact@new.com",    # optional, for new customer
        "invoice_date": "2025-01-15",          # optional, defaults to today
        "due_date": "2025-02-15",              # optional
        "reference": "Customer reference",      # optional
        "line_items": [                         # required
            {
                "description": "Product/Service",
                "quantity": 2,
                "price_unit": 150.00
            }
        ]
    }
    
    Or with single line item:
    {
        "customer_id": 123,
        "description": "Service provided",
        "quantity": 1,
        "price_unit": 500.00,
        "invoice_date": "2025-01-15"
    }
    """
    
    # Validate required fields
    if not data.get('customer_id') and not data.get('customer_name'):
        return {
            'success': False,
            'error': 'Either customer_id or customer_name is required'
        }
    
    # Check for line items
    has_line_items = data.get('line_items') and len(data['line_items']) > 0
    has_single_item = data.get('description') and data.get('price_unit')
    
    if not has_line_items and not has_single_item:
        return {
            'success': False,
            'error': 'Either provide line_items array or description and price_unit'
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
        
        # Handle customer
        if data.get('customer_id'):
            customer_id = data['customer_id']
            
            # Verify customer exists
            customer_exists = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_count',
                [[('id', '=', customer_id), ('customer_rank', '>', 0)]]
            )
            
            if not customer_exists:
                return {
                    'success': False,
                    'error': f'Customer with ID {customer_id} not found or is not a customer'
                }
            
            # Get customer name
            customer_info = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [[customer_id]], 
                {'fields': ['name']}
            )[0]
            customer_name = customer_info['name']
            
        else:
            # Create new customer
            customer_data = {
                'name': data['customer_name'],
                'is_company': True,
                'customer_rank': 1,
                'supplier_rank': 0,
            }
            
            if data.get('customer_email'):
                customer_data['email'] = data['customer_email']
            
            customer_id = models.execute_kw(
                db, uid, password,
                'res.partner', 'create',
                [customer_data]
            )
            
            if not customer_id:
                return {
                    'success': False,
                    'error': 'Failed to create new customer'
                }
            
            customer_name = data['customer_name']
        
        # Prepare invoice data
        invoice_date = data.get('invoice_date', datetime.now().strftime('%Y-%m-%d'))
        
        # Validate date format
        try:
            datetime.strptime(invoice_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'invoice_date must be in YYYY-MM-DD format'
            }
        
        invoice_data = {
            'move_type': 'out_invoice',  # Customer invoice
            'partner_id': customer_id,
            'invoice_date': invoice_date,
        }
        
        # Add due date if provided
        if data.get('due_date'):
            try:
                datetime.strptime(data['due_date'], '%Y-%m-%d')
                invoice_data['invoice_date_due'] = data['due_date']
            except ValueError:
                return {
                    'success': False,
                    'error': 'due_date must be in YYYY-MM-DD format'
                }
        
        # Add reference if provided
        if data.get('reference'):
            invoice_data['ref'] = data['reference']
        
        # Handle line items
        invoice_line_ids = []
        
        if has_line_items:
            # Multiple line items
            for item in data['line_items']:
                if not item.get('description'):
                    return {
                        'success': False,
                        'error': 'Each line item must have a description'
                    }
                
                try:
                    quantity = float(item.get('quantity', 1.0))
                    price_unit = float(item.get('price_unit', 0.0))
                except (ValueError, TypeError):
                    return {
                        'success': False,
                        'error': 'quantity and price_unit must be valid numbers'
                    }
                
                line_item = {
                    'name': item['description'],
                    'quantity': quantity,
                    'price_unit': price_unit,
                }
                
                invoice_line_ids.append((0, 0, line_item))
        
        else:
            # Single line item
            try:
                quantity = float(data.get('quantity', 1.0))
                price_unit = float(data['price_unit'])
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'quantity and price_unit must be valid numbers'
                }
            
            line_item = {
                'name': data['description'],
                'quantity': quantity,
                'price_unit': price_unit,
            }
            
            invoice_line_ids.append((0, 0, line_item))
        
        invoice_data['invoice_line_ids'] = invoice_line_ids
        
        # Create invoice
        invoice_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [invoice_data]
        )
        
        if not invoice_id:
            return {
                'success': False,
                'error': 'Failed to create invoice in Odoo'
            }
        
        # Get created invoice information
        invoice_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[invoice_id]], 
            {'fields': ['name', 'amount_total', 'state', 'invoice_date_due']}
        )[0]
        
        return {
            'success': True,
            'invoice_id': invoice_id,
            'invoice_number': invoice_info.get('name'),
            'customer_name': customer_name,
            'customer_id': customer_id,
            'total_amount': invoice_info.get('amount_total'),
            'state': invoice_info.get('state'),
            'invoice_date': invoice_date,
            'due_date': invoice_info.get('invoice_date_due'),
            'line_items_count': len(invoice_line_ids),
            'message': 'Customer invoice created successfully'
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

def list_customer_invoices():
    """Get list of customer invoices for reference"""
    
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
        
        invoices = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('move_type', '=', 'out_invoice')]], 
            {'fields': ['id', 'name', 'partner_id', 'amount_total', 'state', 'invoice_date', 'invoice_date_due'], 'limit': 20}
        )
        
        return {
            'success': True,
            'invoices': invoices,
            'count': len(invoices)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }