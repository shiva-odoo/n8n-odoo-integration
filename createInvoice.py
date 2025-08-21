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
        "company_id": 1,                        # optional, for multi-company setup
        "invoice_date": "2025-01-15",          # optional, defaults to today
        "due_date": "2025-02-15",              # optional
        "reference": "Customer reference",      # optional
        "line_items": [                         # required
            {
                "description": "Product/Service",
                "quantity": 2,
                "price_unit": 150.00,
                "tax_rate": 19
            }
        ],
        "subtotal": 300.00,
        "tax_amount": 57.00,
        "total_amount": 357.00
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
    
    # Accept extra fields for amount handling
    payment_reference = data.get('payment_reference')
    subtotal = data.get('subtotal')
    tax_amount = data.get('tax_amount')
    total_amount = data.get('total_amount')
    
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
        
        # Helper function to find tax by rate
        def find_tax_by_rate(tax_rate, company_id=None):
            """Find tax record by rate percentage"""
            try:
                domain = [('amount', '=', tax_rate), ('type_tax_use', '=', 'sale')]
                if company_id:
                    domain.append(('company_id', '=', company_id))
                
                tax_ids = models.execute_kw(
                    db, uid, password,
                    'account.tax', 'search',
                    [domain],
                    {'limit': 1}
                )
                return tax_ids[0] if tax_ids else None
            except:
                return None
        
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
        
        # Add company_id if provided (for multi-company setup)
        company_id = None
        if data.get('company_id'):
            company_id = data['company_id']
            invoice_data['company_id'] = company_id
        
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
        
        # Add payment_reference if provided
        if payment_reference and payment_reference != 'none':
            invoice_data['payment_reference'] = payment_reference
        
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
                    tax_rate = float(item.get('tax_rate', 0.0)) if item.get('tax_rate') else None
                except (ValueError, TypeError):
                    return {
                        'success': False,
                        'error': 'quantity, price_unit, and tax_rate must be valid numbers'
                    }
                
                line_item = {
                    'name': item['description'],
                    'quantity': quantity,
                    'price_unit': price_unit,
                }
                
                # Apply tax if tax_rate is provided
                if tax_rate is not None and tax_rate > 0:
                    tax_id = find_tax_by_rate(tax_rate, company_id)
                    if tax_id:
                        line_item['tax_ids'] = [(6, 0, [tax_id])]
                    else:
                        # Log warning but continue - tax might be calculated differently
                        print(f"Warning: No tax found for rate {tax_rate}%, continuing without tax")
                
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
        context = {'allowed_company_ids': [company_id]} if company_id else {}
        invoice_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [invoice_data],
            {'context': context}
        )
        
        if not invoice_id:
            return {
                'success': False,
                'error': 'Failed to create invoice in Odoo'
            }
        
        # Update with explicit amounts if provided
        update_data = {}
        
        # Set explicit amounts if provided
        if subtotal is not None:
            try:
                update_data['amount_untaxed'] = float(subtotal)
            except (ValueError, TypeError):
                pass
        
        if tax_amount is not None:
            try:
                update_data['amount_tax'] = float(tax_amount)
            except (ValueError, TypeError):
                pass
        
        if total_amount is not None:
            try:
                update_data['amount_total'] = float(total_amount)
            except (ValueError, TypeError):
                pass
        
        # Update the invoice with explicit amounts if any were provided
        if update_data:
            try:
                models.execute_kw(
                    db, uid, password,
                    'account.move', 'write',
                    [[invoice_id], update_data]
                )
            except Exception as e:
                # If we can't set the amounts directly, continue with posting
                print(f"Warning: Could not set explicit amounts: {str(e)}")
        
        # POST THE INVOICE - Move from draft to posted state
        try:
            post_result = models.execute_kw(
                db, uid, password,
                'account.move', 'action_post',
                [[invoice_id]]
            )
            
            # Verify the invoice was posted successfully
            invoice_state = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[invoice_id]], 
                {'fields': ['state']}
            )[0]['state']
            
            if invoice_state != 'posted':
                return {
                    'success': False,
                    'error': f'Invoice was created but failed to post. Current state: {invoice_state}'
                }
                
        except xmlrpc.client.Fault as e:
            return {
                'success': False,
                'error': f'Invoice created but failed to post: {str(e)}'
            }
        
        # If posting succeeded but we need to update amounts after posting, do it now
        if update_data:
            try:
                # Try to update amounts even after posting (some Odoo configurations allow this)
                models.execute_kw(
                    db, uid, password,
                    'account.move', 'write',
                    [[invoice_id], update_data]
                )
            except Exception as e:
                # This is expected in some cases, amounts might be computed automatically
                pass
        
        # Get final invoice information after posting
        invoice_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[invoice_id]], 
            {'fields': ['name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'invoice_date_due']}
        )[0]
        
        return {
            'success': True,
            'invoice_id': invoice_id,
            'invoice_number': invoice_info.get('name'),
            'customer_name': customer_name,
            'customer_id': customer_id,
            'total_amount': invoice_info.get('amount_total'),
            'subtotal': invoice_info.get('amount_untaxed'),
            'tax_amount': invoice_info.get('amount_tax'),
            'state': invoice_info.get('state'),
            'invoice_date': invoice_date,
            'due_date': invoice_info.get('invoice_date_due'),
            'payment_reference': payment_reference if payment_reference != 'none' else None,
            'company_id': company_id,
            'line_items': data.get('line_items'),
            'line_items_count': len(invoice_line_ids),
            'message': 'Customer invoice created and posted successfully'
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