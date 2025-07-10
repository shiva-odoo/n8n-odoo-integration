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
    Create vendor bill with company selection from HTTP request data
    
    Expected data format:
    {
        "company_id": 1,
        "vendor_id": 123,
        "invoice_date": "2025-01-15",  # optional, defaults to today
        "vendor_ref": "INV-001",       # optional
        "description": "Office supplies",
        "amount": 1500.50
    }
    
    Or with multiple line items:
    {
        "company_id": 1,
        "vendor_id": 123,
        "invoice_date": "2025-01-15",
        "vendor_ref": "INV-001",
        "line_items": [
            {
                "description": "Office supplies",
                "quantity": 2,
                "price_unit": 750.25
            }
        ]
    }
    """
    
    # Validate required fields
    if not data.get('company_id'):
        return {
            'success': False,
            'error': 'company_id is required'
        }
    
    if not data.get('vendor_id'):
        return {
            'success': False,
            'error': 'vendor_id is required'
        }
    
    # Odoo connection details
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
        
        company_id = data['company_id']
        vendor_id = data['vendor_id']
        
        # Verify company exists
        company_exists = models.execute_kw(
            db, uid, password,
            'res.company', 'search_count',
            [[('id', '=', company_id)]]
        )
        
        if not company_exists:
            return {
                'success': False,
                'error': f'Company with ID {company_id} not found'
            }
        
        # Get company info
        company_info = models.execute_kw(
            db, uid, password,
            'res.company', 'read',
            [[company_id]], 
            {'fields': ['name', 'currency_id']}
        )[0]
        
        # Verify vendor exists and is available to company
        vendor_exists = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_count',
            [[
                ('id', '=', vendor_id), 
                ('supplier_rank', '>', 0),
                '|', 
                ('company_id', '=', company_id), 
                ('company_id', '=', False)
            ]]
        )
        
        if not vendor_exists:
            return {
                'success': False,
                'error': f'Vendor with ID {vendor_id} not found or not available to company {company_id}'
            }
        
        # Get vendor info
        vendor_info = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[vendor_id]], 
            {'fields': ['name']}
        )[0]
        
        # Prepare bill data
        invoice_date = data.get('invoice_date', datetime.now().strftime('%Y-%m-%d'))
        
        # Validate date format
        try:
            datetime.strptime(invoice_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'invoice_date must be in YYYY-MM-DD format'
            }
        
        bill_data = {
            'move_type': 'in_invoice',
            'partner_id': vendor_id,
            'company_id': company_id,
            'invoice_date': invoice_date,
        }
        
        # Add vendor reference if provided
        if data.get('vendor_ref'):
            bill_data['ref'] = data['vendor_ref']
        
        # Handle line items
        invoice_line_ids = []
        
        if 'line_items' in data and data['line_items']:
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
                    'company_id': company_id,
                }
                
                invoice_line_ids.append((0, 0, line_item))
        
        elif data.get('description') and data.get('amount'):
            # Single line item (backward compatibility)
            try:
                amount = float(data['amount'])
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'amount must be a valid number'
                }
            
            line_item = {
                'name': data['description'],
                'quantity': 1.0,
                'price_unit': amount,
                'company_id': company_id,
            }
            
            invoice_line_ids.append((0, 0, line_item))
        
        else:
            return {
                'success': False,
                'error': 'Either provide line_items array or description and amount'
            }
        
        bill_data['invoice_line_ids'] = invoice_line_ids
        
        # Create the bill with company context
        bill_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [bill_data],
            {'context': {'default_company_id': company_id}}
        )
        
        if not bill_id:
            return {
                'success': False,
                'error': 'Failed to create bill in Odoo'
            }
        
        # Get created bill information
        bill_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[bill_id]], 
            {'fields': ['name', 'amount_total', 'state', 'company_id']},
            {'context': {'company_id': company_id}}
        )[0]
        
        return {
            'success': True,
            'bill_id': bill_id,
            'bill_number': bill_info.get('name'),
            'company_name': company_info['name'],
            'vendor_name': vendor_info['name'],
            'total_amount': bill_info.get('amount_total'),
            'state': bill_info.get('state'),
            'invoice_date': invoice_date,
            'message': f'Vendor bill created successfully for {company_info["name"]}'
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

def list_companies():
    """Get list of companies for reference"""
    
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
        
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'currency_id', 'country_id'], 'order': 'name'}
        )
        
        return {
            'success': True,
            'companies': companies,
            'count': len(companies)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def list_vendors_by_company(company_id):
    """Get vendors available to a specific company"""
    
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
        
        # Get vendors available to this company (company-specific + global)
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[
                ('supplier_rank', '>', 0),
                '|', 
                ('company_id', '=', company_id), 
                ('company_id', '=', False)
            ]], 
            {'fields': ['id', 'name', 'email', 'company_id'], 'order': 'name'}
        )
        
        return {
            'success': True,
            'vendors': vendors,
            'count': len(vendors),
            'company_id': company_id
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }