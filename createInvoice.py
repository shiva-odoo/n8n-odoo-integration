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

def find_account_by_name(models, db, uid, password, account_name, company_id, account_code=None):
    """Find account by matching name and/or code using improved company-aware approach"""
    try:
        print(f"Searching for account: name='{account_name}', code='{account_code}', company_id={company_id}")
        
        # Get company name first
        company_data = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[('id', '=', company_id)]], 
            {'fields': ['name'], 'limit': 1}
        )
        
        if not company_data:
            print(f"Company with ID {company_id} not found")
            return None
        
        company_name = company_data[0]['name']
        print(f"Found company: {company_name}")
        
        # Check what fields are available on account.account
        available_fields = models.execute_kw(
            db, uid, password,
            'account.account', 'fields_get',
            [], {'attributes': ['string', 'type']}
        )
        
        print(f"Available account fields: {list(available_fields.keys())}")
        
        # Build domain filter for accounts - start with basic filters
        domain = [('active', '=', True)]
        
        # Try different approaches based on available fields
        company_filter_applied = False
        
        if 'company_id' in available_fields:
            # Standard single-company approach
            domain.append(('company_id', '=', company_id))
            company_filter_applied = True
            print(f"Using company_id filter for company {company_name}")
        elif 'company_ids' in available_fields:
            # Multi-company field approach
            domain.append(('company_ids', 'in', [company_id]))
            company_filter_applied = True
            print(f"Using company_ids filter for company {company_name}")
        else:
            print(f"No direct company filter available on account.account model")
        
        # Get accounts using the available filters
        try:
            accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [domain], 
                {'fields': ['id', 'code', 'name', 'account_type']}
            )
            print(f"Found {len(accounts)} accounts using direct search")
        except Exception as search_error:
            print(f"Direct search failed: {str(search_error)}")
            accounts = []
        
        # If direct company filtering didn't work or returned no results, try alternative approach
        if not accounts or not company_filter_applied:
            print(f"Trying alternative approach - getting accounts from company journals...")
            try:
                # Get journals for this company
                company_journals = models.execute_kw(
                    db, uid, password,
                    'account.journal', 'search_read',
                    [[('company_id', '=', company_id)]], 
                    {'fields': ['id', 'name']}
                )
                
                if company_journals:
                    journal_ids = [j['id'] for j in company_journals]
                    print(f"Found {len(journal_ids)} journals for company {company_name}")
                    
                    # Get account move lines from these journals to find relevant accounts
                    account_moves = models.execute_kw(
                        db, uid, password,
                        'account.move.line', 'search_read',
                        [[('journal_id', 'in', journal_ids)]], 
                        {'fields': ['account_id'], 'limit': 2000}
                    )
                    
                    if account_moves:
                        # Get unique account IDs used by this company
                        account_ids = list(set([move['account_id'][0] for move in account_moves if move.get('account_id')]))
                        print(f"Found {len(account_ids)} unique accounts used by company")
                        
                        # Now get the actual account details
                        if account_ids:
                            accounts = models.execute_kw(
                                db, uid, password,
                                'account.account', 'search_read',
                                [[('id', 'in', account_ids), ('active', '=', True)]], 
                                {'fields': ['id', 'code', 'name', 'account_type']}
                            )
                            print(f"Retrieved {len(accounts)} account details")
                        
                        # If still no accounts, get ALL accounts (fallback for shared account models)
                        if not accounts:
                            print("Falling back to searching all accounts...")
                            accounts = models.execute_kw(
                                db, uid, password,
                                'account.account', 'search_read',
                                [[('active', '=', True)]], 
                                {'fields': ['id', 'code', 'name', 'account_type'], 'limit': 1000}
                            )
                            print(f"Retrieved {len(accounts)} accounts from fallback search")
                            
            except Exception as alt_error:
                print(f"Alternative approach failed: {str(alt_error)}")
                # Final fallback - get all accounts
                try:
                    print("Final fallback: searching all active accounts...")
                    accounts = models.execute_kw(
                        db, uid, password,
                        'account.account', 'search_read',
                        [[('active', '=', True)]], 
                        {'fields': ['id', 'code', 'name', 'account_type'], 'limit': 1000}
                    )
                    print(f"Final fallback retrieved {len(accounts)} accounts")
                except Exception as final_error:
                    print(f"Final fallback also failed: {str(final_error)}")
                    return None
        
        print(f"Total accounts available for search: {len(accounts)}")
        
        if not accounts:
            print(f"No accounts found for company {company_name}")
            return None
        
        # Show sample of available accounts for debugging
        print(f"Sample accounts available: {[{'id': acc['id'], 'name': acc['name'], 'code': acc['code']} for acc in accounts[:5]]}")
        
        # Now perform matching against retrieved accounts
        
        # Priority 1: Exact name match
        for account in accounts:
            if account['name'] == account_name:
                print(f"Found exact name match: {account}")
                return account['id']
        
        # Priority 2: Exact code match (if provided)
        if account_code:
            for account in accounts:
                if account.get('code') == account_code:
                    print(f"Found exact code match: {account}")
                    return account['id']
        
        # Priority 3: Case-insensitive name match
        account_name_lower = account_name.lower()
        for account in accounts:
            if account['name'].lower() == account_name_lower:
                print(f"Found case-insensitive name match: {account}")
                return account['id']
        
        # Priority 4: Name contains the search term (partial match)
        for account in accounts:
            if account_name_lower in account['name'].lower():
                print(f"Found partial name match: {account} (contains '{account_name}')")
                return account['id']
        
        # Priority 5: Name variations (sales/revenue variations for invoices)
        name_variations = [
            account_name.replace('Sales Revenue', 'Sales'),
            account_name.replace('Sales', 'Sales Revenue'),
            account_name.replace('Revenue', 'Sales'),
            account_name.replace('Sales', 'Revenue'),
            account_name.replace('Income', 'Revenue'),
            account_name.replace('Revenue', 'Income'),
            account_name.replace('Service Revenue', 'Services'),
            account_name.replace('Services', 'Service Revenue'),
            account_name.replace(' fees', ''),
            account_name.replace(' fee', ''),
            account_name.replace('fees', 'fee'),
            account_name.replace('fee', 'fees'),
        ]
        
        for variation in name_variations:
            if variation != account_name:  # Skip original name
                for account in accounts:
                    if account['name'].lower() == variation.lower():
                        print(f"Found name variation match: {account} (variation: '{variation}')")
                        return account['id']
        
        # Priority 6: Search term appears in name (broader search)
        keywords = account_name_lower.split()
        for keyword in keywords:
            if len(keyword) > 3:  # Only meaningful keywords
                for account in accounts:
                    if keyword in account['name'].lower():
                        print(f"Found keyword match: {account} (keyword: '{keyword}')")
                        return account['id']
        
        # Priority 7: Special handling for common revenue account patterns
        revenue_patterns = {
            'sales revenue': ['sales', 'revenue', 'income', 'service revenue', 'consulting revenue'],
            'sales': ['sales', 'revenue', 'income', 'service revenue'],
            'revenue': ['sales', 'revenue', 'income', 'service revenue'],
            'service revenue': ['sales', 'revenue', 'services', 'consulting', 'professional'],
            'consulting revenue': ['sales', 'revenue', 'consulting', 'professional', 'services'],
        }
        
        account_name_lower = account_name.lower()
        for pattern_key, patterns in revenue_patterns.items():
            if pattern_key in account_name_lower:
                for pattern in patterns:
                    for account in accounts:
                        if pattern in account['name'].lower():
                            print(f"Found revenue pattern match: {account} (pattern: '{pattern}')")
                            return account['id']
        
        # No match found - show debug info
        print(f"No account found for name='{account_name}' or code='{account_code}' in company {company_name}")
        
        # Show accounts containing similar terms for debugging
        similar_accounts = []
        search_terms = ['sales', 'revenue', 'income', 'service', 'consulting', 'professional']
        if account_code:
            search_terms.append(account_code[:2] if len(account_code) >= 2 else account_code)
        
        for term in search_terms:
            for account in accounts:
                account_name_lower = account['name'].lower()
                account_code_str = str(account.get('code', '')).lower()
                
                if (term.lower() in account_name_lower or term.lower() in account_code_str):
                    if account not in similar_accounts:
                        similar_accounts.append(account)
        
        if similar_accounts:
            print(f"Similar accounts found: {similar_accounts[:10]}")
        else:
            print(f"No similar accounts found. Sample available accounts: {accounts[:10]}")
        
        return None
        
    except Exception as e:
        print(f"Error finding account '{account_name}': {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def find_account_by_code(models, db, uid, password, account_code, company_id):
    """Find account by account code - improved version without company_id dependency"""
    try:
        # First try with company_id if the field exists
        try:
            accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('code', '=', account_code), ('company_id', '=', company_id)]],
                {'fields': ['id', 'name', 'code'], 'limit': 1}
            )
            if accounts:
                return accounts[0]['id']
        except:
            # company_id field doesn't exist, try without it
            pass
        
        # Fallback: search by code only (for shared account models)
        accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [[('code', '=', account_code), ('active', '=', True)]],
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
    
    Expected data format can be either:
    1. Single invoice object: {...}
    2. Array with single invoice: [{...}]
    
    Invoice object format:
    {
        "customer_id": 123,                  # Optional - Customer ID in Odoo
        "customer_name": "ABC Company Ltd",  # Optional - Customer name (alternative to customer_id)
        "company_id": 1,                     # MANDATORY - Company ID for invoice creation
        "invoice_date": "2025-01-15",        # optional, defaults to today
        "due_date": "2025-02-15",            # optional, defaults to today if null/empty
        "customer_ref": "PO-001",            # optional
        "description": "Consulting services",
        "amount": 1500.50,
        "line_items": [                      # Each line item can have its own account
            {
                "account_code": "4000",
                "account_name": "Sales Revenue",
                "description": "Consulting services",
                "line_total": 1500.50,
                "price_unit": 1500.50,
                "quantity": 1,
                "tax_rate": 19
            }
        ],
        "accounting_assignment": {           # optional - for additional journal entries
            "credit_account": "4000",        # Account code for credit (revenue) - fallback for backward compatibility
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
    
    # Handle both single object and array input
    if isinstance(data, list):
        if len(data) == 0:
            return {
                'success': False,
                'error': 'Empty array provided'
            }
        elif len(data) == 1:
            data = data[0]  # Extract the single invoice object
        else:
            return {
                'success': False,
                'error': 'Multiple invoices in array not supported. Please process one invoice at a time.'
            }
    
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
        
        # Determine VAT treatment type
        accounting_assignment = data.get('accounting_assignment', {})
        additional_entries = accounting_assignment.get('additional_entries', [])
        
        # Check for reverse charge: both input and output VAT present
        has_input_vat = any(
            'input' in entry.get('account_name', '').lower() and 
            ('vat' in entry.get('account_name', '').lower() or 'tax' in entry.get('account_name', '').lower())
            for entry in additional_entries
        )
        has_output_vat = any(
            'output' in entry.get('account_name', '').lower() and 
            ('vat' in entry.get('account_name', '').lower() or 'tax' in entry.get('account_name', '').lower())
            for entry in additional_entries
        )
        
        is_reverse_charge = has_input_vat and has_output_vat
        is_normal_vat_with_manual_entries = has_output_vat and not has_input_vat  # Output VAT only for invoices
        
        # Any manual VAT entries (either reverse charge or normal VAT)
        has_manual_vat = has_input_vat or has_output_vat
        
        print(f"VAT Treatment Analysis:")
        print(f"- Has Input VAT: {has_input_vat}")
        print(f"- Has Output VAT: {has_output_vat}")
        print(f"- Is Reverse Charge: {is_reverse_charge}")
        print(f"- Is Normal VAT with Manual Entries: {is_normal_vat_with_manual_entries}")
        print(f"- Has Manual VAT: {has_manual_vat}")
        
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

        # Handle line items - UPDATED SECTION
        invoice_line_ids = []
        
        if 'line_items' in data and data['line_items']:
            # Multiple line items - each with its own account
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
                
                # CHANGED: Use line item's own account instead of global credit account
                account_id = None
                
                # Try name-based lookup first for this line item
                if item.get('account_name'):
                    account_id = find_account_by_name(
                        models, db, uid, password, 
                        item['account_name'], 
                        company_id, 
                        item.get('account_code')  # fallback code
                    )
                    print(f"Name-based lookup result for '{item['account_name']}': {account_id}")
                
                # If name lookup failed, try code lookup for this line item
                if not account_id and item.get('account_code'):
                    account_id = find_account_by_code(models, db, uid, password, item['account_code'], company_id)
                    print(f"Code-based lookup result for '{item['account_code']}': {account_id}")
                
                # If line item account not found, fall back to global credit account (backward compatibility)
                if not account_id:
                    if accounting_assignment.get('credit_account_name'):
                        account_id = find_account_by_name(
                            models, db, uid, password, 
                            accounting_assignment['credit_account_name'], 
                            company_id, 
                            accounting_assignment.get('credit_account')  # fallback code
                        )
                        print(f"Fallback name-based lookup result for '{accounting_assignment['credit_account_name']}': {account_id}")
                    
                    if not account_id and accounting_assignment.get('credit_account'):
                        account_id = find_account_by_code(models, db, uid, password, accounting_assignment['credit_account'], company_id)
                        print(f"Fallback code-based lookup result for '{accounting_assignment['credit_account']}': {account_id}")
                
                # If we found an account, assign it
                if account_id:
                    line_item['account_id'] = account_id
                    print(f"Successfully assigned account_id {account_id} to line item")
                else:
                    # Return error instead of proceeding with wrong account
                    account_info = item.get('account_name', item.get('account_code', accounting_assignment.get('credit_account_name', 'Unknown')))
                    return {
                        'success': False,
                        'error': f'Could not find revenue account "{account_info}" for line item "{item["description"]}" in company {company_id}. Please check the account name or code.'
                    }
                
                # Apply tax logic based on VAT treatment
                if tax_rate is not None and tax_rate > 0:
                    if is_reverse_charge:
                        # Reverse charge: no automatic tax on line items
                        print(f"Reverse charge detected - skipping automatic tax calculation")
                    elif is_normal_vat_with_manual_entries:
                        # Normal VAT with manual entries: no automatic tax (handled in additional_entries)
                        print(f"Normal VAT with manual entries - skipping automatic tax calculation")
                    elif not has_manual_vat:
                        # Standard automatic tax calculation
                        tax_id = find_tax_by_rate(tax_rate, company_id)
                        if tax_id:
                            line_item['tax_ids'] = [(6, 0, [tax_id])]
                            print(f"Applied automatic tax calculation: {tax_rate}%")
                        else:
                            print(f"Warning: No tax found for rate {tax_rate}%, continuing without automatic tax")
                elif tax_rate is None or tax_rate == 0:
                    print(f"No tax rate provided or tax rate is 0%, skipping tax calculation")
                
                invoice_line_ids.append((0, 0, line_item))
        
        elif data.get('description') and data.get('amount'):
            # Single line item (backward compatibility) - use global credit account
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
            
            # Use global accounting assignment for backward compatibility
            account_id = None
            
            # Try name-based lookup first
            if accounting_assignment.get('credit_account_name'):
                account_id = find_account_by_name(
                    models, db, uid, password, 
                    accounting_assignment['credit_account_name'], 
                    company_id, 
                    accounting_assignment.get('credit_account')  # fallback code
                )
                print(f"Name-based lookup result for '{accounting_assignment['credit_account_name']}': {account_id}")
            
            # If name lookup failed, try code lookup
            if not account_id and accounting_assignment.get('credit_account'):
                account_id = find_account_by_code(models, db, uid, password, accounting_assignment['credit_account'], company_id)
                print(f"Code-based lookup result for '{accounting_assignment['credit_account']}': {account_id}")
            
            # If we found an account, assign it
            if account_id:
                line_item['account_id'] = account_id
                print(f"Successfully assigned account_id {account_id} to line item")
            else:
                # Return error instead of proceeding with wrong account
                account_info = accounting_assignment.get('credit_account_name', accounting_assignment.get('credit_account', 'Unknown'))
                return {
                    'success': False,
                    'error': f'Could not find credit account "{account_info}" in company {company_id}. Please check the account name or code.'
                }
            
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
        
        # Handle additional journal entries for VAT based on treatment type
        if additional_entries:
            try:
                # Prepare additional journal entries
                additional_lines = []
                output_vat_amount = 0.0
                
                for entry in additional_entries:
                    # Try to find account by name first, then by code
                    account_id = None
                    if entry.get('account_name'):
                        account_id = find_account_by_name(
                            models, db, uid, password, 
                            entry['account_name'], 
                            company_id, 
                            entry.get('account_code')  # fallback code
                        )
                    elif entry.get('account_code'):
                        account_id = find_account_by_code(models, db, uid, password, entry['account_code'], company_id)
                    
                    if account_id:
                        debit_amount = float(entry.get('debit_amount', 0.0))
                        credit_amount = float(entry.get('credit_amount', 0.0))
                        
                        line_data = {
                            'move_id': invoice_id,
                            'account_id': account_id,
                            'name': entry.get('description', entry.get('account_name', '')),
                            'debit': debit_amount,
                            'credit': credit_amount,
                            'partner_id': customer_id,
                        }
                        additional_lines.append((0, 0, line_data))
                        
                        # Track output VAT amount for normal VAT treatment
                        if ('output' in entry.get('account_name', '').lower() and 
                            ('vat' in entry.get('account_name', '').lower() or 'tax' in entry.get('account_name', '').lower())):
                            output_vat_amount += credit_amount
                        
                        print(f"Added journal entry: {entry.get('account_name')} - Debit: {debit_amount}, Credit: {credit_amount}")
                    else:
                        account_identifier = entry.get('account_name', entry.get('account_code', 'Unknown'))
                        print(f"Warning: Account '{account_identifier}' not found, skipping additional entry")
                
                # Add additional lines to the invoice
                if additional_lines:
                    models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[invoice_id], {'line_ids': additional_lines}]
                    )
                
                # For normal VAT with manual entries, adjust accounts receivable
                if is_normal_vat_with_manual_entries and output_vat_amount > 0:
                    print(f"Normal VAT detected - adjusting accounts receivable to include VAT amount: {output_vat_amount}")
                    
                    # Get the current invoice line items to find the accounts receivable line
                    current_lines = models.execute_kw(
                        db, uid, password,
                        'account.move.line', 'search_read',
                        [[('move_id', '=', invoice_id)]], 
                        {'fields': ['id', 'account_id', 'credit', 'debit', 'name']}
                    )
                    
                    # Find the accounts receivable line (debit > 0, typically the largest debit amount)
                    receivable_lines = [line for line in current_lines if line['debit'] > 0 and line['debit'] > line['credit']]
                    
                    if receivable_lines:
                        # Sort by debit amount descending and take the largest (should be accounts receivable)
                        receivable_line = max(receivable_lines, key=lambda x: x['debit'])
                        
                        # Update the accounts receivable line to include the VAT amount
                        new_debit_amount = receivable_line['debit'] + output_vat_amount
                        
                        models.execute_kw(
                            db, uid, password,
                            'account.move.line', 'write',
                            [[receivable_line['id']], {'debit': new_debit_amount}]
                        )
                        
                        print(f"Updated accounts receivable from {receivable_line['debit']} to {new_debit_amount}")
                    else:
                        print("Warning: Could not find accounts receivable line to adjust")
                        
            except Exception as e:
                print(f"Warning: Could not add additional journal entries: {str(e)}")
                import traceback
                traceback.print_exc()
        
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

# Helper function to search and list accounts by name pattern
def search_accounts_by_pattern(company_id, pattern="sales", limit=20):
    """Search for accounts matching a pattern in a specific company"""
    
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
        
        # Search for accounts containing the pattern
        try:
            accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('name', 'ilike', pattern), ('company_id', '=', company_id)]],
                {'fields': ['id', 'name', 'code', 'account_type'], 'limit': limit}
            )
        except:
            # Fallback for shared account models
            accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('name', 'ilike', pattern), ('active', '=', True)]],
                {'fields': ['id', 'name', 'code', 'account_type'], 'limit': limit}
            )
        
        return {
            'success': True,
            'pattern': pattern,
            'company_id': company_id,
            'accounts': accounts,
            'count': len(accounts)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Helper function to list all income/revenue accounts 
def list_revenue_accounts(company_id, limit=50):
    """List all income/revenue-type accounts in a specific company"""
    
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
        
        # Get income accounts (account_type = 'income')
        try:
            accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('account_type', '=', 'income'), ('company_id', '=', company_id)]],
                {'fields': ['id', 'name', 'code', 'account_type'], 'limit': limit, 'order': 'code'}
            )
        except:
            # Fallback for shared account models
            accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('account_type', '=', 'income'), ('active', '=', True)]],
                {'fields': ['id', 'name', 'code', 'account_type'], 'limit': limit, 'order': 'code'}
            )
        
        return {
            'success': True,
            'company_id': company_id,
            'accounts': accounts,
            'count': len(accounts),
            'account_type': 'income'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }