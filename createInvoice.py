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

def check_duplicate_invoice(models, db, uid, password, customer_id, invoice_date, total_amount, company_id, customer_ref=None):
    """
    Check if an invoice with the same customer, date, total amount, and reference already exists in the specified company
    
    Returns:
        - None if no duplicate found
        - Invoice data with exists=True if duplicate found
    """
    try:
        # Build search criteria for the specific company
        search_domain = [
            ('move_type', '=', 'out_invoice'),  # Customer invoices only
            ('partner_id', '=', customer_id),
            ('invoice_date', '=', invoice_date),
            ('company_id', '=', company_id),   # Filter by company
            ('state', '!=', 'cancel'),  # Exclude cancelled invoices
        ]
        
        # Add reference to search criteria if provided
        if customer_ref:
            search_domain.append(('ref', '=', customer_ref))
        
        # Search for existing invoices
        existing_invoices = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [search_domain],
            {'fields': ['id', 'name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'ref', 'partner_id']}
        )
        
        # Check if any invoice matches the total amount (with small tolerance for rounding)
        for invoice in existing_invoices:
            if abs(float(invoice['amount_total']) - float(total_amount)) < 0.01:
                # Get detailed invoice information including line items
                line_items = models.execute_kw(
                    db, uid, password,
                    'account.move.line', 'search_read',
                    [[('move_id', '=', invoice['id']), ('display_type', '=', False)]], 
                    {'fields': ['id', 'name', 'quantity', 'price_unit', 'price_total']}
                )
                
                # Get customer name
                customer_info = models.execute_kw(
                    db, uid, password,
                    'res.partner', 'read',
                    [[invoice['partner_id'][0]]], 
                    {'fields': ['name']}
                )[0]
                
                return {
                    'success': True,
                    'exists': True,
                    'invoice_id': invoice['id'],
                    'invoice_number': invoice['name'],
                    'customer_name': customer_info['name'],
                    'total_amount': invoice['amount_total'],
                    'subtotal': invoice['amount_untaxed'],
                    'tax_amount': invoice['amount_tax'],
                    'state': invoice['state'],
                    'customer_ref': invoice.get('ref'),
                    'line_items': line_items,
                    'message': 'Invoice already exists - no duplicate created'
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
    Create customer invoice from HTTP request data
    
    Expected data format:
    {
        "customer_id": 123,                  # Optional - Customer ID in Odoo
        "customer_name": "ABC Company Ltd",  # Optional - Customer name (alternative to customer_id)
        "company_id": 1,                     # MANDATORY - Company ID for invoice creation
        "invoice_date": "2025-01-15",        # optional, defaults to today
        "due_date": "2025-02-15",            # optional, defaults to today if null/empty
        "customer_ref": "PO-001",            # optional
        "description": "Consulting services",
        "amount": 1500.50,
        "accounting_assignment": {           # optional - for custom journal entries
            "credit_account": "4000",        # Account code for credit (revenue)
            "credit_account_name": "Sales Revenue",
            "debit_account": "1200",         # Account code for debit (receivables)
            "debit_account_name": "Accounts receivable",
            "additional_entries": [          # Optional VAT entries
                {
                    "account_code": "2201",
                    "account_name": "Output VAT/Sales", 
                    "debit_amount": 0,
                    "credit_amount": 285.10,
                    "description": "VAT on sales"
                }
            ]
        }
    }
    
    Note: Either customer_id OR customer_name is required (not both)
    """
    
    # Validate required fields
    if not data.get('customer_id') and not data.get('customer_name'):
        return {
            'success': False,
            'error': 'Either customer_id or customer_name is required'
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
        
        # Handle customer lookup - accept either customer_id or customer_name
        customer_id = data.get('customer_id')
        customer_name = data.get('customer_name')
        
        if customer_name and not customer_id:
            # Look up customer by name within the company
            customer_search = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_read',
                [[('name', '=', customer_name), ('customer_rank', '>', 0)]],
                {'fields': ['id', 'name'], 'limit': 1}
            )
            
            if not customer_search:
                # Try partial match if exact match fails
                customer_search = models.execute_kw(
                    db, uid, password,
                    'res.partner', 'search_read',
                    [[('name', 'ilike', customer_name), ('customer_rank', '>', 0)]],
                    {'fields': ['id', 'name'], 'limit': 1}
                )
            
            if not customer_search:
                return {
                    'success': False,
                    'error': f'Customer with name "{customer_name}" not found or is not a customer'
                }
            
            customer_id = customer_search[0]['id']
            customer_info = customer_search[0]
        else:
            # Verify customer exists by ID
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
            
            # Get customer name for response
            customer_info = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [[customer_id]], 
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
        
        # Check for duplicate invoice in the specific company
        customer_ref = data.get('customer_ref')
        existing_invoice = check_duplicate_invoice(
            models, db, uid, password, 
            customer_id, invoice_date, expected_total, company_id, customer_ref
        )
        
        if existing_invoice:
            # Return existing invoice details
            return existing_invoice
        
        # Helper function to find tax by rate
        def find_tax_by_rate(tax_rate, company_id):
            """Find tax record by rate percentage for specific company"""
            try:
                domain = [('amount', '=', tax_rate), ('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]
                
                tax_ids = models.execute_kw(
                    db, uid, password,
                    'account.tax', 'search',
                    [domain],
                    {'limit': 1}
                )
                return tax_ids[0] if tax_ids else None
            except:
                return None
        
        # Prepare invoice data
        invoice_data = {
            'move_type': 'out_invoice',
            'partner_id': customer_id,
            'invoice_date': invoice_date,
            'invoice_date_due': due_date,
            'company_id': company_id,
        }
        
        # Add customer reference if provided
        if data.get('customer_ref'):
            invoice_data['ref'] = data['customer_ref']

        # Add payment_reference if provided
        if payment_reference and payment_reference != 'none':
            invoice_data['payment_reference'] = payment_reference

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
                if accounting_assignment.get('credit_account'):
                    account_id = find_account_by_code(models, db, uid, password, accounting_assignment['credit_account'], company_id)
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
            if accounting_assignment.get('credit_account'):
                account_id = find_account_by_code(models, db, uid, password, accounting_assignment['credit_account'], company_id)
                if account_id:
                    line_item['account_id'] = account_id
            
            invoice_line_ids.append((0, 0, line_item))
        
        else:
            return {
                'success': False,
                'error': 'Either provide line_items array or description and amount'
            }
        
        invoice_data['invoice_line_ids'] = invoice_line_ids
        
        # Create the invoice
        context = {'allowed_company_ids': [company_id]}
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
        
        # Handle additional journal entries for VAT if provided
        accounting_assignment = data.get('accounting_assignment', {})
        if accounting_assignment.get('additional_entries'):
            try:
                # Get the created invoice to access its journal entries
                invoice_info = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[invoice_id]], 
                    {'fields': ['line_ids']}
                )[0]
                
                # Prepare additional journal entries
                additional_lines = []
                for entry in accounting_assignment['additional_entries']:
                    account_id = find_account_by_code(models, db, uid, password, entry['account_code'], company_id)
                    if account_id:
                        line_data = {
                            'move_id': invoice_id,
                            'account_id': account_id,
                            'name': entry.get('description', entry.get('account_name', '')),
                            'debit': float(entry.get('debit_amount', 0.0)),
                            'credit': float(entry.get('credit_amount', 0.0)),
                            'partner_id': customer_id,
                        }
                        additional_lines.append((0, 0, line_data))
                    else:
                        print(f"Warning: Account {entry['account_code']} not found, skipping additional entry")
                
                # Add additional lines to the invoice
                if additional_lines:
                    models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[invoice_id], {'line_ids': additional_lines}]
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
        
        # Get final invoice information after posting including line items
        invoice_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[invoice_id]], 
            {'fields': ['name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'invoice_date_due']}
        )[0]
        
        # Get line items
        line_items = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', invoice_id), ('display_type', '=', False)]], 
            {'fields': ['id', 'name', 'quantity', 'price_unit', 'price_total']}
        )
        
        return {
            'success': True,
            'exists': False,
            'invoice_id': invoice_id,
            'invoice_number': invoice_info.get('name'),
            'customer_name': customer_info['name'],
            'total_amount': invoice_info.get('amount_total'),
            'subtotal': invoice_info.get('amount_untaxed'),
            'tax_amount': invoice_info.get('amount_tax'),
            'state': invoice_info.get('state'),
            'invoice_date': invoice_date,
            'due_date': due_date,
            'payment_reference': payment_reference if payment_reference != 'none' else None,
            'line_items': line_items,
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

def get_invoice_details(invoice_id, company_id=None):
    """Get detailed invoice information including line items for a specific company"""
    
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
        domain = [('id', '=', invoice_id), ('move_type', '=', 'out_invoice')]
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        # Get invoice info
        invoice = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'company_id']}
        )
        
        if not invoice:
            return {'success': False, 'error': 'Invoice not found or does not belong to specified company'}
        
        # Get line items
        line_items = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', invoice_id), ('display_type', '=', False)]], 
            {'fields': ['id', 'name', 'quantity', 'price_unit', 'price_total', 'account_id', 'tax_ids']}
        )
        
        return {
            'success': True,
            'invoice': invoice[0],
            'line_items': line_items
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Helper function to list customers for specific company
def list_customers(company_id=None):
    """Get list of customers for reference, optionally filtered by company"""
    
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
        
        domain = [('customer_rank', '>', 0)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        customers = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'email', 'company_id']}
        )
        
        return {
            'success': True,
            'customers': customers,
            'count': len(customers)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Helper function to search customers by name
def search_customers_by_name(customer_name, company_id=None):
    """Search for customers by name, optionally within a specific company"""
    
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
        domain = [('name', '=', customer_name), ('customer_rank', '>', 0)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        customers = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'email', 'company_id']}
        )
        
        # If no exact match, try partial match
        if not customers:
            domain = [('name', 'ilike', customer_name), ('customer_rank', '>', 0)]
            if company_id:
                domain.append(('company_id', '=', company_id))
            
            customers = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_read',
                [domain], 
                {'fields': ['id', 'name', 'email', 'company_id']}
            )
        
        return {
            'success': True,
            'customers': customers,
            'count': len(customers),
            'search_term': customer_name
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }