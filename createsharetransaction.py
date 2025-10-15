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
        
        # Priority 5: Equity/Share account variations for share capital
        equity_variations = [
            account_name.replace('Share Capital', 'Capital'),
            account_name.replace('Capital', 'Share Capital'),
            account_name.replace('Share Capital', 'Equity'),
            account_name.replace('Equity', 'Share Capital'),
            account_name.replace('Share Capital', 'Shares'),
            account_name.replace('Shares', 'Share Capital'),
            account_name.replace('Ordinary Shares', 'Share Capital'),
            account_name.replace('Share Capital', 'Ordinary Shares'),
        ]
        
        for variation in equity_variations:
            if variation != account_name:  # Skip original name
                for account in accounts:
                    if account['name'].lower() == variation.lower():
                        print(f"Found equity variation match: {account} (variation: '{variation}')")
                        return account['id']
        
        # Priority 6: Search term appears in name (broader search)
        keywords = account_name_lower.split()
        for keyword in keywords:
            if len(keyword) > 3:  # Only meaningful keywords
                for account in accounts:
                    if keyword in account['name'].lower():
                        print(f"Found keyword match: {account} (keyword: '{keyword}')")
                        return account['id']
        
        # No match found - show debug info
        print(f"No account found for name='{account_name}' or code='{account_code}' in company {company_name}")
        
        # Show accounts containing similar terms for debugging
        similar_accounts = []
        search_terms = ['share', 'capital', 'equity', 'bank', 'cash']
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

def check_duplicate_share_transaction(models, db, uid, password, partner_id, transaction_date, total_amount, company_id, customer_ref=None):
    """
    Check if a share capital transaction with the same partner, date, total amount, and reference already exists in the specified company
    
    Returns:
        - None if no duplicate found
        - Transaction data with exists=True if duplicate found
    """
    try:
        # Build search criteria for the specific company
        search_domain = [
            ('move_type', '=', 'entry'),  # Journal entries
            ('company_id', '=', company_id),   # Filter by company
            ('date', '=', transaction_date),
            ('state', '!=', 'cancel'),  # Exclude cancelled entries
        ]
        
        # Add partner if provided (partner might be optional for share capital)
        if partner_id:
            search_domain.append(('partner_id', '=', partner_id))
        
        # Add reference to search criteria if provided
        if customer_ref:
            search_domain.append(('ref', '=', customer_ref))
        
        # Search for existing transactions
        existing_transactions = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [search_domain],
            {'fields': ['id', 'name', 'amount_total', 'state', 'ref', 'partner_id', 'date']}
        )
        
        # Check if any transaction matches the total amount (with small tolerance for rounding)
        for transaction in existing_transactions:
            if abs(float(transaction.get('amount_total', 0)) - float(total_amount)) < 0.01:
                # Get detailed transaction information including line items
                line_items = models.execute_kw(
                    db, uid, password,
                    'account.move.line', 'search_read',
                    [[('move_id', '=', transaction['id'])]], 
                    {'fields': ['id', 'name', 'debit', 'credit', 'account_id']}
                )
                
                # Get partner name if exists
                partner_name = None
                if transaction.get('partner_id'):
                    partner_info = models.execute_kw(
                        db, uid, password,
                        'res.partner', 'read',
                        [[transaction['partner_id'][0]]], 
                        {'fields': ['name']}
                    )[0]
                    partner_name = partner_info['name']
                
                return {
                    'success': True,
                    'exists': True,
                    'transaction_id': transaction['id'],
                    'entry_number': transaction['name'],
                    'partner_name': partner_name,
                    'total_amount': transaction.get('amount_total', 0),
                    'state': transaction['state'],
                    'customer_ref': transaction.get('ref'),
                    'date': transaction['date'],
                    'line_items': line_items,
                    'message': 'Share capital transaction already exists - no duplicate created'
                }
        
        return None
        
    except Exception as e:
        print(f"Error checking for duplicate share transactions: {str(e)}")
        return None

def main(data):
    """
    Create share capital transaction from HTTP request data (updated for new input format)
    
    Expected data format (flattened from N8N transformation):
    {
        "customer_name": "STELIOS KYRANIDES",    # Partner name (can be None for company transactions)
        "company_id": 60,                        # MANDATORY - Company ID for transaction
        "journal_id": 419,                       # MANDATORY - Journal ID for the transaction
        "invoice_date": "2025-07-15",            # Transaction date
        "due_date": "2025-07-15",                # Due date (optional, defaults to invoice_date)
        "customer_ref": "Director's Resolution dated 15/07/2025",  # Transaction reference
        "payment_reference": "",                 # Payment reference (optional)
        "subtotal": 15000.0,
        "tax_amount": 0.0,
        "total_amount": 15000.0,
        "line_items": [                          # Line items for the transaction
            {
                "description": "15,000 ordinary shares of nominal value €1 each",
                "quantity": 15000,
                "price_unit": 1.0,
                "tax_rate": 0
            }
        ],
        "accounting_assignment": {               # Accounting assignment for journal entries
            "debit_account": "1100",
            "debit_account_name": "Accounts receivable",
            "credit_account": "3000",
            "credit_account_name": "Share Capital",
            "additional_entries": []             # Optional additional journal entries
        }
    }
    """
    
    # Validate required fields
    if not data.get('company_id'):
        return {
            'success': False,
            'error': 'company_id is required'
        }
    
    if not data.get('journal_id'):
        return {
            'success': False,
            'error': 'journal_id is required'
        }
    
    # Extract data from flattened structure
    customer_name = data.get('customer_name')
    company_id = data['company_id']
    journal_id = data['journal_id']
    customer_ref = data.get('customer_ref')
    payment_reference = data.get('payment_reference')
    subtotal = data.get('subtotal', 0.0)
    tax_amount = data.get('tax_amount', 0.0)
    total_amount = data.get('total_amount', 0.0)
    
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
        
        # Handle partner lookup - partner is optional for share capital transactions
        partner_id = None
        partner_info = None
        
        if customer_name:
            # Look up partner by name
            partner_search = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_read',
                [[('name', '=', customer_name)]],
                {'fields': ['id', 'name'], 'limit': 1}
            )
            
            if not partner_search:
                # Try partial match if exact match fails
                partner_search = models.execute_kw(
                    db, uid, password,
                    'res.partner', 'search_read',
                    [[('name', 'ilike', customer_name)]],
                    {'fields': ['id', 'name'], 'limit': 1}
                )
            
            if partner_search:
                partner_id = partner_search[0]['id']
                partner_info = partner_search[0]
            else:
                print(f"Warning: Partner '{customer_name}' not found, creating transaction without partner")
        
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
        
        # Verify journal exists and belongs to the company
        journal_info = models.execute_kw(
            db, uid, password,
            'account.journal', 'search_read',
            [[('id', '=', journal_id), ('company_id', '=', company_id)]],
            {'fields': ['id', 'name', 'code', 'type'], 'limit': 1}
        )
        
        if not journal_info:
            return {
                'success': False,
                'error': f'Journal with ID {journal_id} not found or does not belong to company {company_id}'
            }
        
        journal_info = journal_info[0]
        
        # Normalize and prepare dates
        transaction_date = normalize_date(data.get('invoice_date'))
        
        # Validate date format
        try:
            datetime.strptime(transaction_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'invoice_date must be in YYYY-MM-DD format'
            }
        
        # Calculate expected total amount
        expected_total = float(total_amount) if total_amount else 0.0
        
        # Check for duplicate transaction in the specific company
        existing_transaction = check_duplicate_share_transaction(
            models, db, uid, password, 
            partner_id, transaction_date, expected_total, company_id, customer_ref
        )
        
        if existing_transaction:
            # Return existing transaction details
            return existing_transaction
        
        # Prepare journal entry data
        move_data = {
            'move_type': 'entry',  # Journal entry (not invoice)
            'date': transaction_date,
            'journal_id': journal_id,
            'company_id': company_id,
        }
        
        # Add partner if provided
        if partner_id:
            move_data['partner_id'] = partner_id
        
        # Add customer reference if provided
        if customer_ref:
            move_data['ref'] = customer_ref
        
        # Add payment_reference if provided
        if payment_reference and payment_reference not in ['', 'none', None]:
            move_data['narration'] = f"Payment Reference: {payment_reference}"
        
        # Handle journal entry lines
        move_line_ids = []
        accounting_assignment = data.get('accounting_assignment', {})
        
        if not accounting_assignment:
            return {
                'success': False,
                'error': 'accounting_assignment is required for share capital transactions'
            }
        
        # Get debit and credit accounts
        debit_account_id = None
        credit_account_id = None
        
        # Find debit account (usually Bank or Accounts Receivable)
        if accounting_assignment.get('debit_account_name'):
            debit_account_id = find_account_by_name(
                models, db, uid, password, 
                accounting_assignment['debit_account_name'], 
                company_id, 
                accounting_assignment.get('debit_account')
            )
        elif accounting_assignment.get('debit_account'):
            debit_account_id = find_account_by_code(
                models, db, uid, password, 
                accounting_assignment['debit_account'], 
                company_id
            )
        
        if not debit_account_id:
            debit_info = accounting_assignment.get('debit_account_name', accounting_assignment.get('debit_account', 'Unknown'))
            return {
                'success': False,
                'error': f'Could not find debit account "{debit_info}" in company {company_id}'
            }
        
        # Find credit account (usually Share Capital)
        if accounting_assignment.get('credit_account_name'):
            credit_account_id = find_account_by_name(
                models, db, uid, password, 
                accounting_assignment['credit_account_name'], 
                company_id, 
                accounting_assignment.get('credit_account')
            )
        elif accounting_assignment.get('credit_account'):
            credit_account_id = find_account_by_code(
                models, db, uid, password, 
                accounting_assignment['credit_account'], 
                company_id
            )
        
        if not credit_account_id:
            credit_info = accounting_assignment.get('credit_account_name', accounting_assignment.get('credit_account', 'Unknown'))
            return {
                'success': False,
                'error': f'Could not find credit account "{credit_info}" in company {company_id}'
            }
        
        # Calculate transaction amount from line items
        transaction_amount = 0.0
        line_descriptions = []
        
        if 'line_items' in data and data['line_items']:
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
                
                line_amount = quantity * price_unit
                transaction_amount += line_amount
                line_descriptions.append(f"{item['description']} (Qty: {quantity:,.0f} @ {price_unit:,.2f})")
        
        # Use total_amount if provided, otherwise use calculated amount
        if total_amount:
            transaction_amount = float(total_amount)
        
        if transaction_amount <= 0:
            return {
                'success': False,
                'error': 'Transaction amount must be greater than zero'
            }
        
        # Create journal entry lines
        combined_description = "; ".join(line_descriptions) if line_descriptions else "Share Capital Transaction"
        
        # Debit line (Accounts Receivable - money to be received)
        debit_line = {
            'account_id': debit_account_id,
            'name': combined_description,
            'debit': transaction_amount,
            'credit': 0.0,
        }
        
        if partner_id:
            debit_line['partner_id'] = partner_id
        
        # Credit line (Share Capital account)
        credit_line = {
            'account_id': credit_account_id,
            'name': combined_description,
            'debit': 0.0,
            'credit': transaction_amount,
        }
        
        if partner_id:
            credit_line['partner_id'] = partner_id
        
        move_line_ids.append((0, 0, debit_line))
        move_line_ids.append((0, 0, credit_line))
        
        # Handle additional journal entries if provided
        if accounting_assignment.get('additional_entries'):
            for entry in accounting_assignment['additional_entries']:
                # Find account by name first, then by code
                account_id = None
                if entry.get('account_name'):
                    account_id = find_account_by_name(
                        models, db, uid, password, 
                        entry['account_name'], 
                        company_id, 
                        entry.get('account_code')
                    )
                elif entry.get('account_code'):
                    account_id = find_account_by_code(
                        models, db, uid, password, 
                        entry['account_code'], 
                        company_id
                    )
                
                if account_id:
                    additional_line = {
                        'account_id': account_id,
                        'name': entry.get('description', entry.get('account_name', '')),
                        'debit': float(entry.get('debit_amount', 0.0)),
                        'credit': float(entry.get('credit_amount', 0.0)),
                    }
                    
                    if partner_id:
                        additional_line['partner_id'] = partner_id
                    
                    move_line_ids.append((0, 0, additional_line))
                else:
                    account_identifier = entry.get('account_name', entry.get('account_code', 'Unknown'))
                    print(f"Warning: Account '{account_identifier}' not found, skipping additional entry")
        
        move_data['line_ids'] = move_line_ids
        
        # Create the journal entry
        context = {'allowed_company_ids': [company_id]}
        move_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [move_data],
            {'context': context}
        )
        
        if not move_id:
            return {
                'success': False,
                'error': 'Failed to create share capital transaction in Odoo'
            }
        
        # POST THE JOURNAL ENTRY - Move from draft to posted state
        try:
            models.execute_kw(
                db, uid, password,
                'account.move', 'action_post',
                [[move_id]]
            )
            
            # Verify the entry was posted successfully
            move_state_data = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[move_id]], 
                {'fields': ['state']}
            )
            
            if not move_state_data or move_state_data[0]['state'] != 'posted':
                state = move_state_data[0]['state'] if move_state_data else 'unknown'
                return {
                    'success': False,
                    'error': f'Share capital transaction was created but failed to post. Current state: {state}'
                }
                
        except xmlrpc.client.Fault as e:
            return {
                'success': False,
                'error': f'Share capital transaction created but failed to post: {str(e)}'
            }
        
        # ### START: COMPREHENSIVE OUTPUT RETRIEVAL (matching createbill.py) ###

        print("Waiting for 2 seconds for database commit after posting...")
        time.sleep(2)

        # Step 1: DIRECTLY search for all move lines belonging to this journal entry
        print(f"Searching for all lines with move_id = {move_id}")
        all_move_lines = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', move_id)]],
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

        print(f"Found {len(all_move_lines)} total lines for move_id {move_id}")

        # Debug: print all lines found
        for idx, line in enumerate(all_move_lines):
            print(f"Line {idx + 1}: ID={line['id']}, Name={line.get('name')}, Debit={line.get('debit')}, Credit={line.get('credit')}, Display Type={line.get('display_type')}")

        # Step 2: Read the journal entry header information
        posted_entries = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', move_id)]],
            {
                'fields': [
                    'name', 'state', 'move_type', 'partner_id', 'company_id',
                    'date', 'ref', 'narration',
                    'amount_total', 'currency_id', 'journal_id'
                ],
                'context': context,
                'limit': 1
            }
        )

        if not posted_entries:
            return {
                'success': False,
                'error': f'Could not read back the created journal entry (ID: {move_id}) after posting.',
                'transaction_id': move_id
            }

        entry_info = posted_entries[0]
        print(f"Journal entry info retrieved: {entry_info.get('name')}")

        # Step 3: Get detailed partner information (if exists)
        partner_details = None
        if entry_info.get('partner_id'):
            partner_id_value = entry_info['partner_id'][0] if isinstance(entry_info['partner_id'], list) else entry_info['partner_id']
            partner_details = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [[partner_id_value]],
                {'fields': ['id', 'name', 'email', 'phone', 'vat', 'street', 'city', 'country_id']}
            )[0]

        # Step 4: Get company information
        company_id_from_entry = entry_info['company_id'][0] if isinstance(entry_info['company_id'], list) else entry_info['company_id']
        company_details = models.execute_kw(
            db, uid, password,
            'res.company', 'read',
            [[company_id_from_entry]],
            {'fields': ['id', 'name', 'currency_id', 'country_id']}
        )[0]

        # Step 5: Get journal information (already have it, but get full details)
        journal_id_value = entry_info['journal_id'][0] if isinstance(entry_info['journal_id'], list) else entry_info['journal_id']
        journal_details = models.execute_kw(
            db, uid, password,
            'account.journal', 'read',
            [[journal_id_value]],
            {'fields': ['id', 'name', 'code', 'type']}
        )[0]

        # Step 6: Process and enrich the lines we found
        detailed_line_items = []

        print(f"\n=== Processing {len(all_move_lines)} lines ===")

        for line in all_move_lines:
            # For journal entries, include all lines except display-only types
            display_type = line.get('display_type')
            
            if display_type in ['payment_term', 'line_section', 'line_note']:
                print(f"⏭️  Skipping non-journal line: {line.get('name')} (type: {display_type})")
                continue
            
            # Include all other lines (standard journal entry lines)
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
                    partner_line_details = models.execute_kw(
                        db, uid, password,
                        'res.partner', 'read',
                        [[partner_id_value]],
                        {'fields': ['id', 'name']}
                    )[0]
                    enriched_line['partner'] = {
                        'id': partner_line_details['id'],
                        'name': partner_line_details['name']
                    }
                    print(f"   Partner: {partner_line_details['name']}")
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

        # Construct the comprehensive success response (matching createbill.py format)
        return {
            'success': True,
            'exists': False,
            'message': 'Share capital transaction created and posted successfully',
            
            # Transaction header information
            'transaction_id': move_id,
            'entry_number': entry_info.get('name'),
            'state': entry_info.get('state'),
            'move_type': entry_info.get('move_type'),
            
            # Dates
            'transaction_date': entry_info.get('date'),
            'date': entry_info.get('date'),
            
            # References
            'customer_ref': entry_info.get('ref'),
            'reference': entry_info.get('ref'),
            'narration': entry_info.get('narration'),
            
            # Amounts
            'transaction_amount': transaction_amount,
            'total_amount': entry_info.get('amount_total', transaction_amount),
            'currency': entry_info.get('currency_id'),
            
            # Partner information (if exists)
            'partner': {
                'id': partner_details['id'],
                'name': partner_details['name'],
                'email': partner_details.get('email'),
                'phone': partner_details.get('phone'),
                'vat': partner_details.get('vat'),
                'address': {
                    'street': partner_details.get('street'),
                    'city': partner_details.get('city'),
                    'country': partner_details.get('country_id')
                }
            } if partner_details else None,
            
            # Company information
            'company': {
                'id': company_details['id'],
                'name': company_details['name'],
                'currency': company_details.get('currency_id'),
                'country': company_details.get('country_id')
            },
            
            # Journal information
            'journal': {
                'id': journal_details['id'],
                'name': journal_details['name'],
                'code': journal_details['code'],
                'type': journal_details['type']
            },
            
            # Detailed line items (matching createbill.py transaction script format)
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

def create_share_capital(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

def create(data):
    """Another alias for main function to maintain compatibility with invoice pattern"""
    return main(data)

# Helper functions for share capital transactions

def get_share_transaction_details(transaction_id, company_id=None):
    """Get detailed share capital transaction information including line items for a specific company"""
    
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
        domain = [('id', '=', transaction_id), ('move_type', '=', 'entry')]
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        # Get transaction info
        transaction = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'partner_id', 'date', 'ref', 'state', 'company_id', 'journal_id']}
        )
        
        if not transaction:
            return {'success': False, 'error': 'Share capital transaction not found or does not belong to specified company'}
        
        # Get line items
        line_items = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', transaction_id)]], 
            {'fields': ['id', 'name', 'debit', 'credit', 'account_id', 'partner_id']}
        )
        
        return {
            'success': True,
            'transaction': transaction[0],
            'line_items': line_items
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def list_share_transactions(company_id, limit=50):
    """List all share capital transactions for a specific company"""
    
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
        
        # Get transactions that contain "share" in the reference or line descriptions
        # First get all journal entries for the company
        transactions = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('move_type', '=', 'entry'), ('company_id', '=', company_id), ('state', '=', 'posted')]], 
            {'fields': ['id', 'name', 'partner_id', 'date', 'ref', 'journal_id'], 'limit': limit * 2, 'order': 'date desc'}
        )
        
        # Filter for share-related transactions
        share_transactions = []
        for transaction in transactions:
            ref = transaction.get('ref', '').lower()
            if any(keyword in ref for keyword in ['share', 'capital', 'allotment', 'equity']):
                share_transactions.append(transaction)
                if len(share_transactions) >= limit:
                    break
        
        return {
            'success': True,
            'company_id': company_id,
            'transactions': share_transactions,
            'count': len(share_transactions)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def search_equity_accounts(company_id, limit=20):
    """Search for equity-type accounts in a specific company"""
    
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
        
        # Search for equity accounts
        try:
            accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('account_type', '=', 'equity'), ('company_id', '=', company_id)]],
                {'fields': ['id', 'name', 'code', 'account_type'], 'limit': limit, 'order': 'code'}
            )
        except:
            # Fallback for shared account models or different account type names
            accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('active', '=', True)]],
                {'fields': ['id', 'name', 'code', 'account_type'], 'limit': 200}
            )
            # Filter for equity-related accounts
            equity_keywords = ['capital', 'share', 'equity', 'retained', 'earnings']
            accounts = [acc for acc in accounts if any(keyword in acc['name'].lower() for keyword in equity_keywords)][:limit]
        
        return {
            'success': True,
            'company_id': company_id,
            'accounts': accounts,
            'count': len(accounts),
            'account_type': 'equity'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Export the main functions for external use
__all__ = ['main', 'create_share_capital', 'create', 'get_share_transaction_details', 'list_share_transactions', 'search_equity_accounts']