import xmlrpc.client
from datetime import datetime
import os
import time
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
    
    Invoice object format with tax_name and tax_grid fields:
    {
        "customer_id": 123,                  # Optional - Customer ID in Odoo
        "customer_name": "ABC Company Ltd",  # Optional - Customer name (alternative to customer_id)
        "company_id": 1,                     # MANDATORY - Company ID for invoice creation
        "invoice_date": "2025-01-15",
        "due_date": "2025-02-15",
        "customer_ref": "PO-001",
        "payment_reference": "REF-123",
        "subtotal": 3000,
        "tax_amount": 570,
        "total_amount": 3570,
        "line_items": [
            {
                "account_code": "4000",
                "account_name": "Sales",
                "description": "Consulting services",
                "price_unit": 3000,
                "quantity": 1,
                "tax_rate": 19,
                "tax_name": "19% S",
                "tax_grid": "+6"
            }
        ],
        "accounting_assignment": {
            "credit_account": "4000",
            "credit_account_name": "Sales",
            "debit_account": "1100",
            "debit_account_name": "Accounts Receivable",
            "vat_treatment": "Standard VAT",
            "requires_reverse_charge": false,
            "additional_entries": [
                {
                    "account_code": "2201",
                    "account_name": "Output VAT (Sales)",
                    "debit_amount": 0,
                    "credit_amount": 570,
                    "description": "Output VAT on sales",
                    "tax_name": "19% S",
                    "tax_grid": "+1"
                }
            ]
        }
    }
    
    Note: Either customer_id OR customer_name is required (not both)
    """
    
    # Handle both single object and array input
    if isinstance(data, list):
        if len(data) == 0:
            return {'success': False, 'error': 'Empty array provided'}
        elif len(data) == 1:
            data = data[0]  # Extract the single invoice object
        else:
            return {
                'success': False,
                'error': 'Multiple invoices in array not supported. Please process one invoice at a time.'
            }
    
    # Validate required fields
    if not data.get('customer_id') and not data.get('customer_name'):
        return {'success': False, 'error': 'Either customer_id or customer_name is required'}
    
    if not data.get('company_id'):
        return {'success': False, 'error': 'company_id is required'}
    
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
            return {'success': False, 'error': 'Odoo authentication failed'}
        
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
            return {'success': False, 'error': f'Company with ID {company_id} not found'}
        
        # Normalize and prepare dates
        invoice_date = normalize_date(data.get('invoice_date'))
        due_date = normalize_date(data.get('due_date'))
        
        # Validate date formats
        try:
            datetime.strptime(invoice_date, '%Y-%m-%d')
        except ValueError:
            return {'success': False, 'error': 'invoice_date must be in YYYY-MM-DD format'}
        
        try:
            datetime.strptime(due_date, '%Y-%m-%d')
        except ValueError:
            return {'success': False, 'error': 'due_date must be in YYYY-MM-DD format'}
        
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
            # Multiple line items - each with its own account
            for item in data['line_items']:
                if not item.get('description'):
                    return {'success': False, 'error': 'Each line item must have a description'}
                
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
                
                # Use line item's own account instead of global credit account
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
                
                # If we found an account, assign it
                if account_id:
                    line_item['account_id'] = account_id
                    print(f"Successfully assigned account_id {account_id} to line item")
                else:
                    # Return error instead of proceeding with wrong account
                    account_info = item.get('account_name', item.get('account_code', 'Unknown'))
                    return {
                        'success': False,
                        'error': f'Could not find revenue account "{account_info}" for line item "{item["description"]}" in company {company_id}. Please check the account name or code.'
                    }
                
                # --- START: NEW TAX LOGIC using tax_name ---
                if item.get('tax_name'):
                    tax_id = find_tax_by_name(models, db, uid, password, item['tax_name'], company_id, tax_type='sale')
                    if tax_id:
                        line_item['tax_ids'] = [(6, 0, [tax_id])]
                        print(f"Applied tax '{item['tax_name']}' (ID: {tax_id}) using name lookup.")
                    else:
                        print(f"Warning: Tax with name '{item['tax_name']}' not found. No tax will be applied to this line.")
                # --- END: NEW TAX LOGIC ---

                # --- START: TAX GRID LOGIC ---
                if item.get('tax_grid'):
                    tax_tag_id = find_tax_tag_by_name(models, db, uid, password, item['tax_grid'], company_id)
                    if tax_tag_id:
                        line_item['tax_tag_ids'] = [(6, 0, [tax_tag_id])]
                        print(f"Applied tax tag '{item['tax_grid']}' (ID: {tax_tag_id}) to line item")
                    else:
                        print(f"Warning: Tax tag '{item['tax_grid']}' not found")
                # --- END: TAX GRID LOGIC ---
                
                invoice_line_ids.append((0, 0, line_item))
        
        elif data.get('description') and data.get('amount'):
            # Single line item (backward compatibility) - use global credit account
            try:
                amount = float(data['amount'])
            except (ValueError, TypeError):
                return {'success': False, 'error': 'amount must be a valid number'}
            
            line_item = {
                'name': data['description'],
                'quantity': 1.0,
                'price_unit': amount,
            }
            
            # Use global accounting assignment for backward compatibility
            accounting_assignment = data.get('accounting_assignment', {})
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
            return {'success': False, 'error': 'Failed to create invoice in Odoo'}
        
        # Determine VAT treatment type
        accounting_assignment = data.get('accounting_assignment', {})
        additional_entries = accounting_assignment.get('additional_entries', [])

        # --- UPDATED LOGIC START ---
        # Check if tax_name is being used on line items
        has_tax_name_on_items = any(item.get('tax_name') for item in data.get('line_items', []))
        
        # Only process additional_entries as journal entries when necessary
        if additional_entries:
            if accounting_assignment.get('requires_reverse_charge') is True:
                # Always skip for reverse charge - customer handles VAT
                print(f"ℹ️  Skipping {len(additional_entries)} additional journal entries - Reverse charge: customer accounts for VAT.")
            elif has_tax_name_on_items:
                # Skip if using tax_name - Odoo handles VAT automatically
                print(f"ℹ️  Skipping {len(additional_entries)} additional journal entries - tax_name provided: Odoo handles VAT automatically.")
                print("   Note: When tax_name is provided on line items, Odoo creates all necessary VAT entries.")
            else:
                # Process additional_entries for backward compatibility (when tax_name not provided)
                print(f"⚙️  Processing {len(additional_entries)} additional journal entries - Legacy mode (no tax_name provided).")
                try:
                    # Prepare additional journal entries
                    additional_lines = []
                    output_vat_amount = 0.0

                    has_output_vat = any('output' in entry.get('account_name', '').lower() for entry in additional_entries)
                    is_normal_vat_with_manual_entries = has_output_vat and accounting_assignment.get('requires_reverse_charge') is not True
                    
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

                            # --- START: TAX GRID LOGIC ---
                            if entry.get('tax_grid'):
                                tax_tag_id = find_tax_tag_by_name(models, db, uid, password, entry['tax_grid'], company_id)
                                if tax_tag_id:
                                    line_data['tax_tag_ids'] = [(6, 0, [tax_tag_id])]
                                    print(f"Applied tax tag '{entry['tax_grid']}' (ID: {tax_tag_id}) to additional entry")
                                else:
                                    print(f"Warning: Tax tag '{entry['tax_grid']}' not found")
                            # --- END: TAX GRID LOGIC ---

                            additional_lines.append((0, 0, line_data))
                            
                            # Track output VAT amount for normal VAT treatment
                            if ('output' in entry.get('account_name', '').lower()):
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
        # --- UPDATED LOGIC END ---

        # Update with explicit amounts if provided
        update_data = {}
        
        if subtotal is not None:
            try: update_data['amount_untaxed'] = float(subtotal)
            except (ValueError, TypeError): pass
        
        if tax_amount is not None:
            try: update_data['amount_tax'] = float(tax_amount)
            except (ValueError, TypeError): pass
        
        if total_amount is not None:
            try: update_data['amount_total'] = float(total_amount)
            except (ValueError, TypeError): pass
        
        # Update the invoice with explicit amounts if any were provided
        if update_data:
            try:
                models.execute_kw(
                    db, uid, password,
                    'account.move', 'write',
                    [[invoice_id], update_data]
                )
            except Exception as e:
                print(f"Warning: Could not set explicit amounts: {str(e)}")
        
        # POST THE INVOICE - Move from draft to posted state
        try:
            models.execute_kw(
                db, uid, password,
                'account.move', 'action_post',
                [[invoice_id]]
            )
            
            invoice_state_data = models.execute_kw(
                db, uid, password, 'account.move', 'read',
                [[invoice_id]], {'fields': ['state']}
            )
            
            if not invoice_state_data or invoice_state_data[0]['state'] != 'posted':
                state = invoice_state_data[0]['state'] if invoice_state_data else 'unknown'
                return {
                    'success': False,
                    'error': f'Invoice was created but failed to post. Current state: {state}'
                }
                
        except xmlrpc.client.Fault as e:
            return {
                'success': False,
                'error': f'Invoice created but failed to post: {str(e)}'
            }

        # ### START: COMPREHENSIVE OUTPUT RETRIEVAL ###

        print("Waiting for 2 seconds for database commit after posting...")
        time.sleep(2)

        # Step 1: DIRECTLY search for all move lines belonging to this invoice
        print(f"Searching for all lines with move_id = {invoice_id}")
        all_move_lines = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', invoice_id)]],
            {
                'fields': [
                    'id', 'move_id', 'name', 'account_id', 'partner_id',
                    'debit', 'credit', 'balance',
                    'quantity', 'price_unit', 'price_subtotal', 'price_total',
                    'tax_ids', 'tax_tag_ids', 'tax_line_id',
                    'display_type', 'sequence',
                    'date', 'date_maturity',
                    'currency_id', 'amount_currency'
                ],
                'context': context
            }
        )

        print(f"Found {len(all_move_lines)} total lines for move_id {invoice_id}")

        # Debug: print all lines found
        for idx, line in enumerate(all_move_lines):
            print(f"Line {idx + 1}: ID={line['id']}, Name={line.get('name')}, Debit={line.get('debit')}, Credit={line.get('credit')}, Display Type={line.get('display_type')}")

        # Step 2: Read the invoice header information
        posted_invoices = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', invoice_id)]],
            {
                'fields': [
                    'name', 'state', 'move_type', 'partner_id', 'company_id',
                    'invoice_date', 'invoice_date_due', 'ref', 'payment_reference',
                    'amount_untaxed', 'amount_tax', 'amount_total',
                    'currency_id', 'journal_id'
                ],
                'context': context,
                'limit': 1
            }
        )

        if not posted_invoices:
            return {
                'success': False,
                'error': f'Could not read back the created invoice (ID: {invoice_id}) after posting.',
                'invoice_id': invoice_id
            }

        invoice_info = posted_invoices[0]
        print(f"Invoice info retrieved: {invoice_info.get('name')}")

        # Step 3: Get detailed customer information
        customer_id_value = invoice_info['partner_id'][0] if isinstance(invoice_info['partner_id'], list) else invoice_info['partner_id']
        customer_details = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[customer_id_value]],
            {'fields': ['id', 'name', 'email', 'phone', 'vat', 'street', 'city', 'country_id']}
        )[0]

        # Step 4: Get company information
        company_id_from_invoice = invoice_info['company_id'][0] if isinstance(invoice_info['company_id'], list) else invoice_info['company_id']
        company_details = models.execute_kw(
            db, uid, password,
            'res.company', 'read',
            [[company_id_from_invoice]],
            {'fields': ['id', 'name', 'currency_id', 'country_id']}
        )[0]

        # Step 5: Get journal information
        journal_info = None
        if invoice_info.get('journal_id'):
            journal_id_value = invoice_info['journal_id'][0] if isinstance(invoice_info['journal_id'], list) else invoice_info['journal_id']
            journal_info = models.execute_kw(
                db, uid, password,
                'account.journal', 'read',
                [[journal_id_value]],
                {'fields': ['id', 'name', 'code', 'type']}
            )[0]

        # Step 6: Process and enrich the lines we found
        detailed_line_items = []

        print(f"\n=== Processing {len(all_move_lines)} lines ===")

        for line in all_move_lines:
            # FIXED: For invoices/bills, we want to INCLUDE product and tax lines
            # Only skip payment_term, line_section, line_note, etc.
            display_type = line.get('display_type')
            
            if display_type in ['payment_term', 'line_section', 'line_note']:
                print(f"⏭️  Skipping non-journal line: {line.get('name')} (type: {display_type})")
                continue
            
            # Include all other lines (product, tax, or no display_type)
            print(f"✅ Processing line: {line.get('name')} - Debit: {line.get('debit')}, Credit: {line.get('credit')}, Type: {display_type}")
            
            # Build enriched line
            enriched_line = {
                'id': line['id'],
                'name': line.get('name'),
                'display_type': display_type,
                'debit': line.get('debit', 0.0),
                'credit': line.get('credit', 0.0),
                'balance': line.get('balance', 0.0),
                'quantity': line.get('quantity'),
                'price_unit': line.get('price_unit'),
                'price_subtotal': line.get('price_subtotal'),
                'price_total': line.get('price_total'),
            }
            
            # Get account details
            if line.get('account_id'):
                account_id_value = line['account_id'][0] if isinstance(line['account_id'], list) else line['account_id']
                try:
                    account_details = models.execute_kw(
                        db, uid, password,
                        'account.account', 'read',
                        [[account_id_value]],
                        {'fields': ['id', 'code', 'name', 'account_type']}
                    )[0]
                    enriched_line['account'] = {
                        'id': account_details['id'],
                        'code': account_details['code'],
                        'name': account_details['name'],
                        'type': account_details['account_type']
                    }
                    print(f"   Account: {account_details.get('code')} - {account_details['name']}")
                except Exception as e:
                    print(f"   ⚠️  Could not fetch account details: {e}")
            
            # Get partner details for this line if exists
            if line.get('partner_id'):
                partner_id_value = line['partner_id'][0] if isinstance(line['partner_id'], list) else line['partner_id']
                try:
                    partner_details = models.execute_kw(
                        db, uid, password,
                        'res.partner', 'read',
                        [[partner_id_value]],
                        {'fields': ['id', 'name']}
                    )[0]
                    enriched_line['partner'] = {
                        'id': partner_details['id'],
                        'name': partner_details['name']
                    }
                    print(f"   Partner: {partner_details['name']}")
                except Exception as e:
                    print(f"   ⚠️  Could not fetch partner details: {e}")
            
            # Get tax details if taxes are applied
            if line.get('tax_ids'):
                tax_ids_list = line['tax_ids'] if isinstance(line['tax_ids'], list) else [line['tax_ids']]
                if tax_ids_list:
                    try:
                        tax_details = models.execute_kw(
                            db, uid, password,
                            'account.tax', 'read',
                            [tax_ids_list],
                            {'fields': ['id', 'name', 'amount', 'amount_type', 'type_tax_use']}
                        )
                        enriched_line['taxes'] = tax_details
                        print(f"   Taxes: {[t['name'] for t in tax_details]}")
                    except Exception as e:
                        print(f"   ⚠️  Could not fetch tax details: {e}")
            
            # Get tax tag details if tax tags are applied
            if line.get('tax_tag_ids'):
                tax_tag_ids_list = line['tax_tag_ids'] if isinstance(line['tax_tag_ids'], list) else [line['tax_tag_ids']]
                if tax_tag_ids_list:
                    try:
                        tax_tag_details = models.execute_kw(
                            db, uid, password,
                            'account.account.tag', 'read',
                            [tax_tag_ids_list],
                            {'fields': ['id', 'name', 'applicability', 'country_id']}
                        )
                        enriched_line['tax_tags'] = tax_tag_details
                        print(f"   Tax Tags: {[t['name'] for t in tax_tag_details]}")
                    except Exception as e:
                        print(f"   ⚠️  Could not fetch tax tag details: {e}")
            
            # Check if this is a tax line
            if line.get('tax_line_id'):
                enriched_line['is_tax_line'] = True
                tax_id_value = line['tax_line_id'][0] if isinstance(line['tax_line_id'], list) else line['tax_line_id']
                try:
                    tax_info = models.execute_kw(
                        db, uid, password,
                        'account.tax', 'read',
                        [[tax_id_value]],
                        {'fields': ['id', 'name', 'amount']}
                    )[0]
                    enriched_line['tax_line_info'] = tax_info
                    print(f"   Tax Line: {tax_info['name']}")
                except Exception as e:
                    print(f"   ⚠️  Could not fetch tax line info: {e}")
            else:
                enriched_line['is_tax_line'] = False
            
            detailed_line_items.append(enriched_line)

        print(f"\n=== Final Result: {len(detailed_line_items)} line items after filtering ===")

        # Construct the comprehensive success response
        return {
            'success': True,
            'exists': False,
            'message': 'Customer invoice created and posted successfully',
            
            # Invoice header information
            'invoice_id': invoice_id,
            'invoice_number': invoice_info.get('name'),
            'state': invoice_info.get('state'),
            'move_type': invoice_info.get('move_type'),
            
            # Dates
            'invoice_date': invoice_info.get('invoice_date'),
            'due_date': invoice_info.get('invoice_date_due'),
            
            # References
            'customer_reference': invoice_info.get('ref'),
            'payment_reference': invoice_info.get('payment_reference'),
            
            # Amounts
            'subtotal': invoice_info.get('amount_untaxed'),
            'tax_amount': invoice_info.get('amount_tax'),
            'total_amount': invoice_info.get('amount_total'),
            'currency': invoice_info.get('currency_id'),
            
            # Customer information
            'customer': {
                'id': customer_details['id'],
                'name': customer_details['name'],
                'email': customer_details.get('email'),
                'phone': customer_details.get('phone'),
                'vat': customer_details.get('vat'),
                'address': {
                    'street': customer_details.get('street'),
                    'city': customer_details.get('city'),
                    'country': customer_details.get('country_id')
                }
            },
            
            # Company information
            'company': {
                'id': company_details['id'],
                'name': company_details['name'],
                'currency': company_details.get('currency_id'),
                'country': company_details.get('country_id')
            },
            
            # Journal information
            'journal': journal_info,
            
            # Detailed line items (matching your transaction script format)
            'line_items': [
                {
                    'id': line['id'],
                    'label': line['name'],
                    'display_type': line.get('display_type'),
                    'account_code': line['account']['code'] if line.get('account') else None,
                    'account_name': line['account']['name'] if line.get('account') else None,
                    'account_type': line['account']['type'] if line.get('account') else None,
                    'partner': line['partner']['name'] if line.get('partner') else None,
                    'debit': line['debit'],
                    'credit': line['credit'],
                    'balance': line['balance'],
                    'quantity': line.get('quantity'),
                    'price_unit': line.get('price_unit'),
                    'price_subtotal': line.get('price_subtotal'),
                    'price_total': line.get('price_total'),
                    'taxes': line.get('taxes'),
                    'tax_tags': line.get('tax_tags'),
                    'is_tax_line': line.get('is_tax_line', False)
                }
                for line in detailed_line_items
            ],
            'line_count': len(detailed_line_items),
            
            # Keep the detailed journal entries for comprehensive info
            'journal_entries_detailed': detailed_line_items
        }

        # ### END: COMPREHENSIVE OUTPUT RETRIEVAL ###
        
    except xmlrpc.client.Fault as e:
        return {
            'success': False,
            'error': f'Odoo API error: {str(e)}'
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
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
    
def find_tax_tag_by_name(models, db, uid, password, tag_name, company_id):
    """
    Find tax tag (report line) by name or code
    Tax tags are used to map transactions to tax report grids
    
    Args:
        tag_name: The tax grid identifier (e.g., "+6", "+1", "-1")
    
    Returns:
        Tax tag ID if found, None otherwise
    """
    try:
        # Clean the tag name (remove spaces, ensure proper format)
        tag_name = tag_name.strip()
        
        print(f"Searching for tax tag: '{tag_name}' in company {company_id}")
        
        # Try exact name match first
        tax_tags = models.execute_kw(
            db, uid, password,
            'account.account.tag', 'search_read',
            [[('name', '=', tag_name), ('applicability', '=', 'taxes')]],
            {'fields': ['id', 'name', 'country_id'], 'limit': 1}
        )
        
        if tax_tags:
            print(f"Found tax tag by exact name: {tax_tags[0]}")
            return tax_tags[0]['id']
        
        # Try with country-specific search (Cyprus tax tags often include country prefix)
        # Get company's country
        company_data = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[('id', '=', company_id)]],
            {'fields': ['country_id'], 'limit': 1}
        )
        
        if company_data and company_data[0].get('country_id'):
            country_id = company_data[0]['country_id'][0]
            
            # Search for tags with this country
            tax_tags = models.execute_kw(
                db, uid, password,
                'account.account.tag', 'search_read',
                [[('name', 'ilike', tag_name), ('country_id', '=', country_id), ('applicability', '=', 'taxes')]],
                {'fields': ['id', 'name', 'country_id'], 'limit': 5}
            )
            
            if tax_tags:
                print(f"Found {len(tax_tags)} tax tags with country filter: {tax_tags}")
                # Return the first match
                return tax_tags[0]['id']
        
        # Try partial match without country filter
        tax_tags = models.execute_kw(
            db, uid, password,
            'account.account.tag', 'search_read',
            [[('name', 'ilike', tag_name), ('applicability', '=', 'taxes')]],
            {'fields': ['id', 'name', 'country_id'], 'limit': 5}
        )
        
        if tax_tags:
            print(f"Found {len(tax_tags)} tax tags with partial match: {tax_tags}")
            return tax_tags[0]['id']
        
        print(f"No tax tag found for '{tag_name}'")
        return None
        
    except Exception as e:
        print(f"Error finding tax tag '{tag_name}': {str(e)}")
        return None


def find_tax_by_name(models, db, uid, password, tax_name, company_id, tax_type='sale'):
    """
    Find tax record by its name for a specific company.
    """
    try:
        print(f"Searching for tax with name: '{tax_name}' in company {company_id}")
        
        # First, try an exact match
        domain = [
            ('name', '=', tax_name),
            ('company_id', '=', company_id),
            ('type_tax_use', '=', tax_type)
        ]
        tax_ids = models.execute_kw(
            db, uid, password,
            'account.tax', 'search',
            [domain],
            {'limit': 1}
        )
        
        if tax_ids:
            print(f"Found tax '{tax_name}' by exact match with ID: {tax_ids[0]}")
            return tax_ids[0]

        # If no exact match, try a case-insensitive match
        domain_ilike = [
            ('name', 'ilike', tax_name),
            ('company_id', '=', company_id),
            ('type_tax_use', '=', tax_type)
        ]
        tax_ids_ilike = models.execute_kw(
            db, uid, password,
            'account.tax', 'search',
            [domain_ilike],
            {'limit': 1}
        )
        
        if tax_ids_ilike:
            print(f"Found tax '{tax_name}' by case-insensitive match with ID: {tax_ids_ilike[0]}")
            return tax_ids_ilike[0]
        
        print(f"Warning: No tax found for name '{tax_name}' in company {company_id}")
        return None
        
    except Exception as e:
        print(f"Error finding tax '{tax_name}': {str(e)}")
        return None


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