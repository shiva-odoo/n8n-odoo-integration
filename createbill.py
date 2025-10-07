import xmlrpc.client
from datetime import datetime
import os
import time  # Added for a small delay

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

def find_tax_tag_by_name(models, db, uid, password, tag_name, company_id):
    """
    Find tax tag (report line) by name or code
    Tax tags are used to map transactions to tax report grids
    
    Args:
        tag_name: The tax grid identifier (e.g., "+7", "+4", "-1")
    
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
        
        # Priority 5: Name variations (consulting vs consultancy, fees variations)
        name_variations = [
            account_name.replace('Consultancy', 'Consulting'),
            account_name.replace('Consulting', 'Consultancy'),
            account_name.replace(' fees', ''),
            account_name.replace(' fee', ''),
            account_name.replace('fees', 'fee'),
            account_name.replace('fee', 'fees'),
            account_name.replace('Consultancy fees', 'Consulting'),
            account_name.replace('Consulting fees', 'Consultancy'),
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
        
        # Priority 7: Special handling for common expense account patterns
        expense_patterns = {
            'consultancy fees': ['consulting', 'consultancy', 'professional fees', 'service fees'],
            'consulting fees': ['consulting', 'consultancy', 'professional fees', 'service fees'],
            'professional fees': ['consulting', 'consultancy', 'professional', 'service'],
        }
        
        account_name_lower = account_name.lower()
        if account_name_lower in expense_patterns:
            for pattern in expense_patterns[account_name_lower]:
                for account in accounts:
                    if pattern in account['name'].lower():
                        print(f"Found expense pattern match: {account} (pattern: '{pattern}')")
                        return account['id']
        
        # No match found - show debug info
        print(f"No account found for name='{account_name}' or code='{account_code}' in company {company_name}")
        
        # Show accounts containing similar terms for debugging
        similar_accounts = []
        search_terms = ['consult', 'fee', 'expense', 'service', 'professional']
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
    
    Expected data format can be either:
    1. Single bill object: {...}
    2. Array with single bill: [{...}]
    
    Bill object format with new 'tax_grid' field:
    {
        "vendor_id": 123,
        "vendor_name": "ABC Supplies Ltd",
        "company_id": 1,
        "invoice_date": "2025-01-15",
        "line_items": [
            {
                "account_code": "7503",
                "account_name": "Internet",
                "description": "Internet services",
                "price_unit": 6.85,
                "quantity": 1,
                "tax_rate": 19,
                "tax_grid": "+7"  // <-- NEW FIELD
            }
        ],
        "accounting_assignment": {
            "additional_entries": [
                {
                    "account_code": "2202",
                    "account_name": "Input VAT/Purchases", 
                    "debit_amount": 526.89,
                    "description": "...",
                    "tax_grid": "+4"  // <-- NEW FIELD
                }
            ]
        }
    }
    
    Note: Either vendor_id OR vendor_name is required (not both)
    """
    
    # Handle both single object and array input
    if isinstance(data, list):
        if len(data) == 0:
            return {
                'success': False,
                'error': 'Empty array provided'
            }
        elif len(data) == 1:
            data = data[0]  # Extract the single bill object
        else:
            return {
                'success': False,
                'error': 'Multiple bills in array not supported. Please process one bill at a time.'
            }
    
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
        is_normal_vat_with_manual_entries = has_input_vat and not has_output_vat
        
        # Any manual VAT entries (either reverse charge or normal VAT)
        has_manual_vat = has_input_vat or has_output_vat
        
        print(f"VAT Treatment Analysis:")
        print(f"- Has Input VAT: {has_input_vat}")
        print(f"- Has Output VAT: {has_output_vat}")
        print(f"- Is Reverse Charge: {is_reverse_charge}")
        print(f"- Is Normal VAT with Manual Entries: {is_normal_vat_with_manual_entries}")
        print(f"- Has Manual VAT: {has_manual_vat}")

        # Handle line items
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
                
                # Use line item's own account instead of global debit account
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
                        'error': f'Could not find expense account "{account_info}" for line item "{item["description"]}" in company {company_id}. Please check the account name or code.'
                    }
                
                # Apply tax logic based on VAT treatment
                if tax_rate is not None and tax_rate > 0:
                    if is_reverse_charge:
                        print(f"Reverse charge detected - skipping automatic tax calculation")
                        line_item['tax_ids'] = [(6, 0, [])]
                    elif is_normal_vat_with_manual_entries:
                        print(f"Normal VAT with manual entries - skipping automatic tax calculation")
                        line_item['tax_ids'] = [(6, 0, [])]
                    elif not has_manual_vat:
                        tax_id = find_tax_by_rate(tax_rate, company_id)
                        if tax_id:
                            line_item['tax_ids'] = [(6, 0, [tax_id])]
                            print(f"Applied automatic tax calculation: {tax_rate}%")
                        else:
                            print(f"Warning: No tax found for rate {tax_rate}%, continuing without automatic tax")
                elif tax_rate is None or tax_rate == 0:
                    print(f"No tax rate provided or tax rate is 0%, skipping tax calculation")
                
                # --- START: ADDED TAX GRID LOGIC ---
                if item.get('tax_grid'):
                    tax_tag_id = find_tax_tag_by_name(models, db, uid, password, item['tax_grid'], company_id)
                    if tax_tag_id:
                        line_item['tax_tag_ids'] = [(6, 0, [tax_tag_id])]
                        print(f"Applied tax tag '{item['tax_grid']}' (ID: {tax_tag_id}) to line item")
                    else:
                        print(f"Warning: Tax tag '{item['tax_grid']}' not found")
                # --- END: ADDED TAX GRID LOGIC ---
                
                invoice_line_ids.append((0, 0, line_item))
        
        elif data.get('description') and data.get('amount'):
            # Single line item (backward compatibility) - use global debit account
            try:
                amount = float(data['amount'])
            except (ValueError, TypeError):
                return { 'success': False, 'error': 'amount must be a valid number' }
            
            line_item = {
                'name': data['description'],
                'quantity': 1.0,
                'price_unit': amount,
            }
            
            # Use global accounting assignment for backward compatibility
            accounting_assignment = data.get('accounting_assignment', {})
            account_id = None
            
            # Try name-based lookup first
            if accounting_assignment.get('debit_account_name'):
                account_id = find_account_by_name(
                    models, db, uid, password, 
                    accounting_assignment['debit_account_name'], 
                    company_id, 
                    accounting_assignment.get('debit_account')  # fallback code
                )
                print(f"Name-based lookup result for '{accounting_assignment['debit_account_name']}': {account_id}")
            
            # If name lookup failed, try code lookup
            if not account_id and accounting_assignment.get('debit_account'):
                account_id = find_account_by_code(models, db, uid, password, accounting_assignment['debit_account'], company_id)
                print(f"Code-based lookup result for '{accounting_assignment['debit_account']}': {account_id}")
            
            # If we found an account, assign it
            if account_id:
                line_item['account_id'] = account_id
                print(f"Successfully assigned account_id {account_id} to line item")
            else:
                # Return error instead of proceeding with wrong account
                account_info = accounting_assignment.get('debit_account_name', accounting_assignment.get('debit_account', 'Unknown'))
                return {
                    'success': False,
                    'error': f'Could not find debit account "{account_info}" in company {company_id}. Please check the account name or code.'
                }
            
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
        
        # Handle additional journal entries for VAT based on treatment type
        if additional_entries:
            try:
                # Prepare additional journal entries
                additional_lines = []
                input_vat_amount = 0.0
                
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
                            'move_id': bill_id,
                            'account_id': account_id,
                            'name': entry.get('description', entry.get('account_name', '')),
                            'debit': debit_amount,
                            'credit': credit_amount,
                            'partner_id': vendor_id,
                        }

                        # --- START: ADDED TAX GRID LOGIC ---
                        # Add tax tags/grid for additional entries
                        if entry.get('tax_grid'):
                            tax_tag_id = find_tax_tag_by_name(models, db, uid, password, entry['tax_grid'], company_id)
                            if tax_tag_id:
                                line_data['tax_tag_ids'] = [(6, 0, [tax_tag_id])]
                                print(f"Applied tax tag '{entry['tax_grid']}' (ID: {tax_tag_id}) to additional entry")
                            else:
                                print(f"Warning: Tax tag '{entry['tax_grid']}' not found")
                        # --- END: ADDED TAX GRID LOGIC ---

                        additional_lines.append((0, 0, line_data))
                        
                        # Track input VAT amount for normal VAT treatment
                        if ('input' in entry.get('account_name', '').lower() and 
                            ('vat' in entry.get('account_name', '').lower() or 'tax' in entry.get('account_name', '').lower())):
                            input_vat_amount += debit_amount
                        
                        print(f"Added journal entry: {entry.get('account_name')} - Debit: {debit_amount}, Credit: {credit_amount}")
                    else:
                        account_identifier = entry.get('account_name', entry.get('account_code', 'Unknown'))
                        print(f"Warning: Account '{account_identifier}' not found, skipping additional entry")
                
                # Add additional lines to the bill
                if additional_lines:
                    models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[bill_id], {'line_ids': additional_lines}]
                    )
                
                # For normal VAT with manual entries, adjust accounts payable
                if is_normal_vat_with_manual_entries and input_vat_amount > 0:
                    print(f"Normal VAT detected - adjusting accounts payable to include VAT amount: {input_vat_amount}")
                    
                    # Get the current bill line items to find the accounts payable line
                    current_lines = models.execute_kw(
                        db, uid, password,
                        'account.move.line', 'search_read',
                        [[('move_id', '=', bill_id)]], 
                        {'fields': ['id', 'account_id', 'credit', 'debit', 'name']}
                    )
                    
                    # Find the accounts payable line (credit > 0, typically the largest credit amount)
                    payable_lines = [line for line in current_lines if line['credit'] > 0 and line['credit'] > line['debit']]
                    
                    if payable_lines:
                        # Sort by credit amount descending and take the largest (should be accounts payable)
                        payable_line = max(payable_lines, key=lambda x: x['credit'])
                        
                        # Update the accounts payable line to include the VAT amount
                        new_credit_amount = payable_line['credit'] + input_vat_amount
                        
                        models.execute_kw(
                            db, uid, password,
                            'account.move.line', 'write',
                            [[payable_line['id']], {'credit': new_credit_amount}]
                        )
                        
                        print(f"Updated accounts payable from {payable_line['credit']} to {new_credit_amount}")
                    else:
                        print("Warning: Could not find accounts payable line to adjust")
                        
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
        
        # ### START: ROBUST FIX FOR LINE ITEM RETRIEVAL ###
        
        # Add a short delay to ensure the database transaction is complete after posting.
        # This helps prevent a race condition where we query for lines before they are fully available.
        print("Waiting for 1 second for database commit after posting...")
        time.sleep(1)

        # Step 1: Read the entire posted move again to get the definitive list of its line IDs.
        # This is more reliable than searching for them separately.
        posted_bill_data = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[bill_id]],
            {
                'fields': [
                    'name', 'amount_total', 'amount_untaxed', 'amount_tax', 
                    'state', 'invoice_date_due', 'line_ids'  # Crucially, fetch the line IDs
                ],
                'context': context
            }
        )

        if not posted_bill_data:
            return {
                'success': False,
                'error': f'Could not read back the created bill (ID: {bill_id}) after posting.',
                'bill_id': bill_id
            }

        bill_info = posted_bill_data[0]
        line_ids = bill_info.get('line_ids', [])

        detailed_line_items = []
        if line_ids:
            # Step 2: Now that we have the exact IDs, read the details of those lines.
            detailed_line_items = models.execute_kw(
                db, uid, password,
                'account.move.line', 'read',
                [line_ids],  # Use the list of IDs directly
                {
                    'fields': [
                        'id', 'name', 'account_id', 'debit', 'credit', 
                        'quantity', 'price_unit', 'tax_tag_ids', 'display_type'
                    ],
                    'context': context
                }
            )
            # Filter out lines that are just for display (like section headers)
            if detailed_line_items:
                detailed_line_items = [line for line in detailed_line_items if not line.get('display_type')]


        # Construct the new, more detailed success response
        return {
            'success': True,
            'exists': False,
            'bill_id': bill_id,
            'bill_number': bill_info.get('name'),
            'vendor_name': vendor_info['name'],
            'invoice_date': invoice_date,
            'due_date': bill_info.get('invoice_date_due'),
            'payment_reference': payment_reference if payment_reference != 'none' else None,
            'state': bill_info.get('state'),
            'bill_amount': bill_info.get('amount_untaxed'),
            'tax_amount': bill_info.get('amount_tax'),
            'total_amount': bill_info.get('amount_total'),
            'line_items': detailed_line_items,
            'message': 'Vendor bill created and posted successfully'
        }
        # ### END: ROBUST FIX FOR LINE ITEM RETRIEVAL ###
        
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

# Helper function to search and list accounts by name pattern
def search_accounts_by_pattern(company_id, pattern="consult", limit=20):
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
        accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [[('name', 'ilike', pattern), ('company_id', '=', company_id)]],
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

# Helper function to list all expense accounts 
def list_expense_accounts(company_id, limit=50):
    """List all expense-type accounts in a specific company"""
    
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
        
        # Get expense accounts (account_type = 'expense')
        accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [[('account_type', '=', 'expense'), ('company_id', '=', company_id)]],
            {'fields': ['id', 'name', 'code', 'account_type'], 'limit': limit, 'order': 'code'}
        )
        
        return {
            'success': True,
            'company_id': company_id,
            'accounts': accounts,
            'count': len(accounts),
            'account_type': 'expense'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def search_vendor_by_name(vendor_name, company_id=None):
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