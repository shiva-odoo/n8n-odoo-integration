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

def check_duplicate_bill(models, db, uid, password, vendor_id, invoice_date, total_amount, vendor_ref=None):
    """
    Check if a bill with the same vendor, date, total amount, and reference already exists
    
    Returns:
        - None if no duplicate found
        - Bill data if duplicate found
    """
    try:
        # Build search criteria
        search_domain = [
            ('move_type', '=', 'in_invoice'),  # Vendor bills only
            ('partner_id', '=', vendor_id),
            ('invoice_date', '=', invoice_date),
            ('state', '!=', 'cancel'),  # Exclude cancelled bills
        ]
        
        # Add reference to search criteria if provided
        if vendor_ref:
            search_domain.append(('ref', '=', vendor_ref))
        else:
            # If no reference provided, search for bills without reference
            search_domain.append(('ref', '=', False))
        
        # Search for existing bills
        existing_bills = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [search_domain],
            {'fields': ['id', 'name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'ref']}
        )
        
        # Check if any bill matches the total amount (with small tolerance for rounding)
        for bill in existing_bills:
            if abs(float(bill['amount_total']) - float(total_amount)) < 0.01:
                return bill
        
        return None
        
    except Exception as e:
        print(f"Error checking for duplicates: {str(e)}")
        return None

def calculate_total_amount(data):
    """
    Calculate the expected total amount from the data
    """
    if 'total_amount' in data:
        return float(data['total_amount'])
    elif 'line_items' in data and data['line_items']:
        # Calculate from line items
        total = 0.0
        for item in data['line_items']:
            quantity = float(item.get('quantity', 1.0))
            price_unit = float(item.get('price_unit', 0.0))
            tax_rate = float(item.get('tax_rate', 0.0)) if item.get('tax_rate') else 0.0
            
            line_subtotal = quantity * price_unit
            line_tax = line_subtotal * (tax_rate / 100.0)
            total += line_subtotal + line_tax
        
        return total
    elif 'amount' in data:
        return float(data['amount'])
    else:
        return 0.0

def main(data):
    """
    Create vendor bill from HTTP request data
    
    Expected data format:
    {
        "vendor_id": 123,
        "invoice_date": "2025-01-15",  # optional, defaults to today
        "vendor_ref": "INV-001",       # optional
        "description": "Office supplies",
        "amount": 1500.50
    }
    
    Or with multiple line items:
    {
        "vendor_id": 123,
        "invoice_date": "2025-01-15",
        "vendor_ref": "INV-001",
        "line_items": [
            {
                "description": "Office supplies",
                "quantity": 2,
                "price_unit": 750.25,
                "tax_rate": 19
            },
            {
                "description": "Software license",
                "quantity": 1,
                "price_unit": 500.00,
                "tax_rate": 19
            }
        ],
        "subtotal": 1250.50,
        "tax_amount": 237.60,
        "total_amount": 1488.10
    }
    """
    
    # Validate required fields
    if not data.get('vendor_id'):
        return {
            'success': False,
            'error': 'vendor_id is required'
        }
    # Accept extra fields
    payment_reference = data.get('payment_reference')
    subtotal = data.get('subtotal')
    tax_amount = data.get('tax_amount')
    total_amount = data.get('total_amount')
    
    # Odoo connection details  
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
        
        # Verify vendor exists
        vendor_id = data['vendor_id']
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
        
        # Get vendor name for response
        vendor_info = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[vendor_id]], 
            {'fields': ['name']}
        )[0]
        
        # Prepare invoice date
        invoice_date = data.get('invoice_date', datetime.now().strftime('%Y-%m-%d'))
        
        # Validate date format
        try:
            datetime.strptime(invoice_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'invoice_date must be in YYYY-MM-DD format'
            }
        
        # Calculate expected total amount
        expected_total = calculate_total_amount(data)
        
        # Check for duplicate bill
        vendor_ref = data.get('vendor_ref')
        existing_bill = check_duplicate_bill(
            models, db, uid, password, 
            vendor_id, invoice_date, expected_total, vendor_ref
        )
        
        if existing_bill:
            # Return existing bill details instead of creating a duplicate
            return {
                'success': True,
                'bill_id': existing_bill['id'],
                'bill_number': existing_bill['name'],
                'vendor_name': vendor_info['name'],
                'total_amount': existing_bill['amount_total'],
                'subtotal': existing_bill['amount_untaxed'],
                'tax_amount': existing_bill['amount_tax'],
                'state': existing_bill['state'],
                'invoice_date': invoice_date,
                'vendor_ref': existing_bill.get('ref'),
                'message': 'Bill already exists - no duplicate created'
            }
        
        # Helper function to find tax by rate
        def find_tax_by_rate(tax_rate, company_id=None):
            """Find tax record by rate percentage"""
            try:
                domain = [('amount', '=', tax_rate), ('type_tax_use', '=', 'purchase')]
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
        
        # Prepare bill data
        bill_data = {
            'move_type': 'in_invoice',
            'partner_id': vendor_id,
            'invoice_date': invoice_date,
        }
        
        # Add vendor reference if provided
        if data.get('vendor_ref'):
            bill_data['ref'] = data['vendor_ref']

        # Add company_id if provided (for multi-company setup)
        company_id = None
        if data.get('company_id'):
            company_id = data['company_id']
            bill_data['company_id'] = company_id

        # Add payment_reference if provided
        if payment_reference and payment_reference != 'none':
            bill_data['payment_reference'] = payment_reference

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
            }
            
            invoice_line_ids.append((0, 0, line_item))
        
        else:
            return {
                'success': False,
                'error': 'Either provide line_items array or description and amount'
            }
        
        bill_data['invoice_line_ids'] = invoice_line_ids
        
        # Create the bill
        context = {'allowed_company_ids': [company_id]} if company_id else {}
        bill_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [bill_data],
            {'context': context}
        )
        
        if not bill_id:
            return {
                'success': False,
                'error': 'Failed to create bill in Odoo'
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
        
        # Update the bill with explicit amounts if any were provided
        if update_data:
            try:
                models.execute_kw(
                    db, uid, password,
                    'account.move', 'write',
                    [[bill_id], update_data]
                )
            except Exception as e:
                # If we can't set the amounts directly, continue with posting
                print(f"Warning: Could not set explicit amounts: {str(e)}")
        
        # POST THE BILL - Move from draft to posted state
        try:
            post_result = models.execute_kw(
                db, uid, password,
                'account.move', 'action_post',
                [[bill_id]]
            )
            
            # Verify the bill was posted successfully
            bill_state = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[bill_id]], 
                {'fields': ['state']}
            )[0]['state']
            
            if bill_state != 'posted':
                return {
                    'success': False,
                    'error': f'Bill was created but failed to post. Current state: {bill_state}'
                }
                
        except xmlrpc.client.Fault as e:
            return {
                'success': False,
                'error': f'Bill created but failed to post: {str(e)}'
            }
        
        # If posting succeeded but we need to update amounts after posting, do it now
        if update_data:
            try:
                # Try to update amounts even after posting (some Odoo configurations allow this)
                models.execute_kw(
                    db, uid, password,
                    'account.move', 'write',
                    [[bill_id], update_data]
                )
            except Exception as e:
                # This is expected in some cases, amounts might be computed automatically
                pass
        
        # Get final bill information after posting
        bill_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[bill_id]], 
            {'fields': ['name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state']}
        )[0]
        
        return {
            'success': True,
            'bill_id': bill_id,
            'bill_number': bill_info.get('name'),
            'vendor_name': vendor_info['name'],
            'total_amount': bill_info.get('amount_total'),
            'subtotal': bill_info.get('amount_untaxed'),
            'tax_amount': bill_info.get('amount_tax'),
            'state': bill_info.get('state'),
            'invoice_date': invoice_date,
            'payment_reference': payment_reference if payment_reference != 'none' else None,
            'line_items': data.get('line_items'),
            'message': 'Vendor bill created and posted successfully'
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

# Helper function to list vendors (for reference)
def list_vendors():
    """Get list of vendors for reference"""
    
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
            {'fields': ['id', 'name', 'email']}
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