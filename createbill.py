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

def find_account_by_code(models, db, uid, password, account_code, company_id):
    """Find account by account code for specific company"""
    try:
        accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [[('code', '=', account_code), ('company_id', '=', company_id)]],
            {'fields': ['id', 'name', 'code'], 'limit': 1}
        )
        return accounts[0]['id'] if accounts else None
    except Exception as e:
        print(f"Error finding account {account_code}: {str(e)}")
        return None

def check_duplicate_bill(models, db, uid, password, vendor_id, invoice_date, total_amount, company_id, vendor_ref=None):
    """
    Check if a bill with the same vendor, date, total amount, and reference already exists in the specified company
    
    Returns:
        - None if no duplicate found
        - Bill data with exists=True if duplicate found
    """
    try:
        # Build search criteria for the specific company
        search_domain = [
            ('move_type', '=', 'in_invoice'),  # Vendor bills only
            ('partner_id', '=', vendor_id),
            ('invoice_date', '=', invoice_date),
            ('company_id', '=', company_id),   # Filter by company
            ('state', '!=', 'cancel'),  # Exclude cancelled bills
        ]
        
        # Add reference to search criteria if provided
        if vendor_ref:
            search_domain.append(('ref', '=', vendor_ref))
        
        # Search for existing bills
        existing_bills = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [search_domain],
            {'fields': ['id', 'name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'ref', 'partner_id']}
        )
        
        # Check if any bill matches the total amount (with small tolerance for rounding)
        for bill in existing_bills:
            if abs(float(bill['amount_total']) - float(total_amount)) < 0.01:
                # Get detailed bill information including line items
                line_items = models.execute_kw(
                    db, uid, password,
                    'account.move.line', 'search_read',
                    [[('move_id', '=', bill['id']), ('display_type', '=', False)]], 
                    {'fields': ['id', 'name', 'quantity', 'price_unit', 'price_total']}
                )
                
                # Get vendor name
                vendor_info = models.execute_kw(
                    db, uid, password,
                    'res.partner', 'read',
                    [[bill['partner_id'][0]]], 
                    {'fields': ['name']}
                )[0]
                
                return {
                    'success': True,
                    'exists': True,
                    'bill_id': bill['id'],
                    'bill_number': bill['name'],
                    'vendor_name': vendor_info['name'],
                    'total_amount': bill['amount_total'],
                    'subtotal': bill['amount_untaxed'],
                    'tax_amount': bill['amount_tax'],
                    'state': bill['state'],
                    'vendor_ref': bill.get('ref'),
                    'line_items': line_items,
                    'message': 'Bill already exists - no duplicate created'
                }
        
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
        "vendor_id": 123,                  # Optional - Vendor ID in Odoo
        "vendor_name": "ABC Supplies Ltd", # Optional - Vendor name (alternative to vendor_id)
        "company_id": 1,                   # MANDATORY - Company ID for bill creation
        "invoice_date": "2025-01-15",      # optional, defaults to today
        "due_date": "2025-02-15",          # optional, defaults to today if null/empty
        "vendor_ref": "INV-001",           # optional
        "description": "Office supplies",
        "amount": 1500.50,
        "accounting_assignment": {         # optional - for custom journal entries
            "debit_account": "6200",       # Account code for debit
            "debit_account_name": "Consultancy fees",
            "credit_account": "2100",      # Account code for credit
            "credit_account_name": "Accounts payable",
            "additional_entries": [        # Optional VAT entries
                {
                    "account_code": "2202",
                    "account_name": "Input VAT/Purchases", 
                    "debit_amount": 526.89,
                    "credit_amount": 0,
                    "description": "Reverse charge VAT on EU services"
                },
                {
                    "account_code": "2201",
                    "account_name": "Output VAT/Sales",
                    "debit_amount": 0,
                    "credit_amount": 526.89,
                    "description": "Reverse charge VAT on EU services"
                }
            ]
        }
    }
    
    Note: Either vendor_id OR vendor_name is required (not both)
    """
    
    # Validate required fields
    if not data.get('vendor_id') and not data.get('vendor_name'):
        return {
            'success': False,
            'error': 'Either vendor_id or vendor_name is required'
        }
    
    if not data.get('company_id'):
        return {
            'success': False,
            'error': 'company_id is required'
        }
    
    # Accept extra fields
    payment_reference = data.get('payment_reference')
    subtotal = data.get('subtotal')
    tax_amount = data.get('tax_amount')
    total_amount = data.get('total_amount')
    company_id = data['company_id']
    
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
        
        # Handle vendor lookup - accept either vendor_id or vendor_name
        vendor_id = data.get('vendor_id')
        vendor_name = data.get('vendor_name')
        
        if vendor_name and not vendor_id:
            # Look up vendor by name within the company
            vendor_search = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_read',
                [[('name', '=', vendor_name), ('supplier_rank', '>', 0)]],
                {'fields': ['id', 'name'], 'limit': 1}
            )
            
            if not vendor_search:
                # Try partial match if exact match fails
                vendor_search = models.execute_kw(
                    db, uid, password,
                    'res.partner', 'search_read',
                    [[('name', 'ilike', vendor_name), ('supplier_rank', '>', 0)]],
                    {'fields': ['id', 'name'], 'limit': 1}
                )
            
            if not vendor_search:
                return {
                    'success': False,
                    'error': f'Vendor with name "{vendor_name}" not found or is not a supplier'
                }
            
            vendor_id = vendor_search[0]['id']
            vendor_info = vendor_search[0]
        else:
            # Verify vendor exists by ID
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
        
        # Calculate expected total amount
        expected_total = calculate_total_amount(data)
        
        # Check for duplicate bill in the specific company
        vendor_ref = data.get('vendor_ref')
        existing_bill = check_duplicate_bill(
            models, db, uid, password, 
            vendor_id, invoice_date, expected_total, company_id, vendor_ref
        )
        
        if existing_bill:
            # Return existing bill details
            return existing_bill
        
        # Helper function to find tax by rate
        def find_tax_by_rate(tax_rate, company_id):
            """Find tax record by rate percentage for specific company"""
            try:
                domain = [('amount', '=', tax_rate), ('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]
                
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
            'invoice_date_due': due_date,
            'company_id': company_id,
        }
        
        # Add vendor reference if provided
        if data.get('vendor_ref'):
            bill_data['ref'] = data['vendor_ref']

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
                
                # Set account from accounting_assignment if provided
                accounting_assignment = data.get('accounting_assignment', {})
                if accounting_assignment.get('debit_account'):
                    account_id = find_account_by_code(models, db, uid, password, accounting_assignment['debit_account'], company_id)
                    if account_id:
                        line_item['account_id'] = account_id
                
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
            
            # Set account from accounting_assignment if provided
            accounting_assignment = data.get('accounting_assignment', {})
            if accounting_assignment.get('debit_account'):
                account_id = find_account_by_code(models, db, uid, password, accounting_assignment['debit_account'], company_id)
                if account_id:
                    line_item['account_id'] = account_id
            
            invoice_line_ids.append((0, 0, line_item))
        
        else:
            return {
                'success': False,
                'error': 'Either provide line_items array or description and amount'
            }
        
        bill_data['invoice_line_ids'] = invoice_line_ids
        
        # Create the bill
        context = {'allowed_company_ids': [company_id]}
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
        
        # Handle additional journal entries for VAT/reverse charge if provided
        accounting_assignment = data.get('accounting_assignment', {})
        if accounting_assignment.get('additional_entries'):
            try:
                # Get the created bill to access its journal entries
                bill_info = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[bill_id]], 
                    {'fields': ['line_ids']}
                )[0]
                
                # Prepare additional journal entries
                additional_lines = []
                for entry in accounting_assignment['additional_entries']:
                    account_id = find_account_by_code(models, db, uid, password, entry['account_code'], company_id)
                    if account_id:
                        line_data = {
                            'move_id': bill_id,
                            'account_id': account_id,
                            'name': entry.get('description', entry.get('account_name', '')),
                            'debit': float(entry.get('debit_amount', 0.0)),
                            'credit': float(entry.get('credit_amount', 0.0)),
                            'partner_id': vendor_id,
                        }
                        additional_lines.append((0, 0, line_data))
                    else:
                        print(f"Warning: Account {entry['account_code']} not found, skipping additional entry")
                
                # Add additional lines to the bill
                if additional_lines:
                    models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[bill_id], {'line_ids': additional_lines}]
                    )
                    
            except Exception as e:
                print(f"Warning: Could not add additional journal entries: {str(e)}")
        
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
        
        # Get final bill information after posting including line items
        bill_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[bill_id]], 
            {'fields': ['name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'invoice_date_due']}
        )[0]
        
        # Get line items
        line_items = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', bill_id), ('display_type', '=', False)]], 
            {'fields': ['id', 'name', 'quantity', 'price_unit', 'price_total']}
        )
        
        return {
            'success': True,
            'exists': False,
            'bill_id': bill_id,
            'bill_number': bill_info.get('name'),
            'vendor_name': vendor_info['name'],
            'total_amount': bill_info.get('amount_total'),
            'subtotal': bill_info.get('amount_untaxed'),
            'tax_amount': bill_info.get('amount_tax'),
            'state': bill_info.get('state'),
            'invoice_date': invoice_date,
            'due_date': due_date,
            'payment_reference': payment_reference if payment_reference != 'none' else None,
            'line_items': line_items,
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

def get_bill_details(bill_id, company_id=None):
    """Get detailed bill information including line items for a specific company"""
    
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
        
        # Build search domain
        domain = [('id', '=', bill_id), ('move_type', '=', 'in_invoice')]
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        # Get bill info
        bill = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'company_id']}
        )
        
        if not bill:
            return {'success': False, 'error': 'Bill not found or does not belong to specified company'}
        
        # Get line items
        line_items = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', bill_id), ('display_type', '=', False)]], 
            {'fields': ['id', 'name', 'quantity', 'price_unit', 'price_total', 'account_id', 'tax_ids']}
        )
        
        return {
            'success': True,
            'bill': bill[0],
            'line_items': line_items
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Helper function to list vendors for specific company
def list_vendors(company_id=None):
    """Get list of vendors for reference, optionally filtered by company"""
    
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
        
        domain = [('supplier_rank', '>', 0)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'email', 'company_id']}
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

# Helper function to search vendors by name
def search_vendors_by_name(vendor_name, company_id=None):
    """Search for vendors by name, optionally within a specific company"""
    
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
        
        # Search for exact match first
        domain = [('name', '=', vendor_name), ('supplier_rank', '>', 0)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'email', 'company_id']}
        )
        
        # If no exact match, try partial match
        if not vendors:
            domain = [('name', 'ilike', vendor_name), ('supplier_rank', '>', 0)]
            if company_id:
                domain.append(('company_id', '=', company_id))
            
            vendors = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_read',
                [domain], 
                {'fields': ['id', 'name', 'email', 'company_id']}
            )
        
        return {
            'success': True,
            'vendors': vendors,
            'count': len(vendors),
            'search_term': vendor_name
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }