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

def normalize_date(date_value):
    """
    Normalize date values - if null, "null", "none", empty string, or None, return today's date
    Otherwise return the date value as-is
    """
    if (date_value is None or 
        date_value == "" or 
        str(date_value).lower() in ["null", "none"]):
        return datetime.now().strftime('%Y-%m-%d')
    return date_value

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
    elif 'amount' in data:
        return float(data['amount'])
    else:
        return 0.0

def create_combined_description(line_items):
    """
    Create a combined description from multiple line items
    """
    if not line_items or len(line_items) == 0:
        return "Various services"
    
    if len(line_items) == 1:
        return line_items[0].get('description', 'Service')
    
    # For multiple items, create a summary
    descriptions = []
    for item in line_items[:3]:  # Show first 3 items
        desc = item.get('description', 'Service')
        if len(desc) > 50:  # Truncate long descriptions
            desc = desc[:47] + "..."
        descriptions.append(desc)
    
    result = "; ".join(descriptions)
    if len(line_items) > 3:
        result += f" (and {len(line_items) - 3} more)"
    
    return result

def main(data):
    """
    Create vendor bill from HTTP request data with consolidated line items
    
    Expected data format:
    {
        "vendor_id": 123,
        "invoice_date": "2025-01-15",
        "due_date": "2025-02-15",
        "vendor_ref": "INV-001",
        "subtotal": 121.26,
        "tax_amount": 23.17,
        "total_amount": 144.43,
        "line_items": [...]  # Will be consolidated into single description
    }
    """
    
    # Validate required fields
    if not data.get('vendor_id'):
        return {
            'success': False,
            'error': 'vendor_id is required'
        }
    
    # Validate required amounts
    if data.get('subtotal') is None or data.get('total_amount') is None:
        return {
            'success': False,
            'error': 'subtotal and total_amount are required'
        }
    
    # Accept extra fields
    payment_reference = data.get('payment_reference')
    subtotal = float(data.get('subtotal'))
    tax_amount = float(data.get('tax_amount', 0))
    total_amount = float(data.get('total_amount'))
    
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
        
        # Normalize and prepare dates
        invoice_date = normalize_date(data.get('invoice_date'))
        due_date = normalize_date(data.get('due_date'))
        
        # Validate date formats
        try:
            datetime.strptime(invoice_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'invoice_date must be in YYYY-MM-DD format'
            }
        
        try:
            datetime.strptime(due_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'due_date must be in YYYY-MM-DD format'
            }
        
        # Check for duplicate bill
        vendor_ref = data.get('vendor_ref')
        existing_bill = check_duplicate_bill(
            models, db, uid, password, 
            vendor_id, invoice_date, total_amount, vendor_ref
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
        
        # Prepare bill data
        bill_data = {
            'move_type': 'in_invoice',
            'partner_id': vendor_id,
            'invoice_date': invoice_date,
            'invoice_date_due': due_date,
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

        # Create single consolidated line item
        # Use line_items to create description, or fallback to generic description
        if data.get('line_items'):
            description = create_combined_description(data['line_items'])
        elif data.get('description'):
            description = data['description']
        else:
            description = "Telecommunications services"
        
        # Create single line item with the subtotal as price_unit
        line_item = {
            'name': description,
            'quantity': 1.0,
            'price_unit': subtotal,  # Use subtotal (tax-excluded amount)
        }
        
        bill_data['invoice_line_ids'] = [(0, 0, line_item)]
        
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
        
        # Set the exact amounts - do this before posting
        try:
            models.execute_kw(
                db, uid, password,
                'account.move', 'write',
                [[bill_id], {
                    'amount_untaxed': subtotal,
                    'amount_tax': tax_amount,
                    'amount_total': total_amount
                }]
            )
        except Exception as e:
            print(f"Warning: Could not set explicit amounts before posting: {str(e)}")
        
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
        
        # Try to update amounts after posting if needed (some Odoo versions allow this)
        try:
            models.execute_kw(
                db, uid, password,
                'account.move', 'write',
                [[bill_id], {
                    'amount_untaxed': subtotal,
                    'amount_tax': tax_amount,
                    'amount_total': total_amount
                }]
            )
        except Exception as e:
            # This might fail in some Odoo configurations after posting, which is expected
            pass
        
        # Get final bill information after posting
        bill_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[bill_id]], 
            {'fields': ['name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'invoice_date_due']}
        )[0]
        
        return {
            'success': True,
            'bill_id': bill_id,
            'bill_number': bill_info.get('name'),
            'vendor_name': vendor_info['name'],
            'total_amount': bill_info.get('amount_total', total_amount),
            'subtotal': bill_info.get('amount_untaxed', subtotal),
            'tax_amount': bill_info.get('amount_tax', tax_amount),
            'state': bill_info.get('state'),
            'invoice_date': invoice_date,
            'due_date': due_date,
            'payment_reference': payment_reference if payment_reference != 'none' else None,
            'description': description,
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