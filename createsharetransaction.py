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
            post_result = models.execute_kw(
                db, uid, password,
                'account.move', 'action_post',
                [[move_id]]
            )
            
            # Verify the entry was posted successfully
            move_state = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[move_id]], 
                {'fields': ['state']}
            )[0]['state']
            
            if move_state != 'posted':
                return {
                    'success': False,
                    'error': f'Share capital transaction was created but failed to post. Current state: {move_state}'
                }
                
        except xmlrpc.client.Fault as e:
            return {
                'success': False,
                'error': f'Share capital transaction created but failed to post: {str(e)}'
            }
        
        # Get final transaction information after posting including line items
        move_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[move_id]], 
            {'fields': ['name', 'state', 'date', 'ref', 'journal_id']}
        )[0]
        
        # Get line items
        line_items = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', move_id)]], 
            {'fields': ['id', 'name', 'debit', 'credit', 'account_id']}
        )
        
        return {
            'success': True,
            'exists': False,
            'transaction_id': move_id,
            'entry_number': move_info.get('name'),
            'partner_name': partner_info['name'] if partner_info else None,
            'transaction_amount': transaction_amount,
            'state': move_info.get('state'),
            'transaction_date': transaction_date,
            'journal_name': journal_info['name'],
            'journal_code': journal_info['code'],
            'payment_reference': payment_reference if payment_reference not in ['', 'none', None] else None,
            'line_items': line_items,
            'message': 'Share capital transaction created and posted successfully'
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