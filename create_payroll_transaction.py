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

def parse_period_to_date(period_string, year=None):
    """
    Parse period string to date
    Examples: "202506 - JUNE" -> "2025-06-30", "June 2025" -> "2025-06-30"
    Returns last day of the month
    """
    try:
        if not period_string:
            return normalize_date(None)
        
        period_lower = str(period_string).lower()
        
        # Extract year if provided in parameter
        if not year:
            # Try to extract year from period string
            import re
            year_match = re.search(r'(20\d{2})', period_string)
            if year_match:
                year = year_match.group(1)
            else:
                year = datetime.now().year
        
        year = int(year)
        
        # Month mapping
        month_map = {
            'january': 1, 'jan': 1,
            'february': 2, 'feb': 2,
            'march': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'may': 5,
            'june': 6, 'jun': 6,
            'july': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'october': 10, 'oct': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12
        }
        
        # Find month in string
        month = None
        for month_name, month_num in month_map.items():
            if month_name in period_lower:
                month = month_num
                break
        
        if not month:
            # Try to extract numeric month (e.g., "202506")
            month_match = re.search(r'\d{4}(\d{2})', period_string)
            if month_match:
                month = int(month_match.group(1))
        
        if not month or month < 1 or month > 12:
            return normalize_date(None)
        
        # Get last day of month
        if month == 12:
            last_day = 31
        else:
            from calendar import monthrange
            last_day = monthrange(year, month)[1]
        
        return f"{year}-{month:02d}-{last_day:02d}"
        
    except Exception as e:
        print(f"Error parsing period '{period_string}': {e}")
        return normalize_date(None)

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
        
        # Build domain filter for accounts
        domain = [('active', '=', True)]
        
        # Try different approaches based on available fields
        company_filter_applied = False
        
        if 'company_id' in available_fields:
            domain.append(('company_id', '=', company_id))
            company_filter_applied = True
        elif 'company_ids' in available_fields:
            domain.append(('company_ids', 'in', [company_id]))
            company_filter_applied = True
        
        # Get accounts using the available filters
        try:
            accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [domain], 
                {'fields': ['id', 'code', 'name', 'account_type']}
            )
        except Exception as search_error:
            print(f"Direct search failed: {str(search_error)}")
            accounts = []
        
        # If direct filtering didn't work, try alternative approach
        if not accounts or not company_filter_applied:
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
                    
                    # Get account IDs used by this company
                    account_moves = models.execute_kw(
                        db, uid, password,
                        'account.move.line', 'search_read',
                        [[('journal_id', 'in', journal_ids)]], 
                        {'fields': ['account_id'], 'limit': 2000}
                    )
                    
                    if account_moves:
                        account_ids = list(set([move['account_id'][0] for move in account_moves if move.get('account_id')]))
                        
                        if account_ids:
                            accounts = models.execute_kw(
                                db, uid, password,
                                'account.account', 'search_read',
                                [[('id', 'in', account_ids), ('active', '=', True)]], 
                                {'fields': ['id', 'code', 'name', 'account_type']}
                            )
                        
                        if not accounts:
                            accounts = models.execute_kw(
                                db, uid, password,
                                'account.account', 'search_read',
                                [[('active', '=', True)]], 
                                {'fields': ['id', 'code', 'name', 'account_type'], 'limit': 1000}
                            )
                            
            except Exception as alt_error:
                print(f"Alternative approach failed: {str(alt_error)}")
                try:
                    accounts = models.execute_kw(
                        db, uid, password,
                        'account.account', 'search_read',
                        [[('active', '=', True)]], 
                        {'fields': ['id', 'code', 'name', 'account_type'], 'limit': 1000}
                    )
                except Exception as final_error:
                    print(f"Final fallback failed: {str(final_error)}")
                    return None
        
        if not accounts:
            print(f"No accounts found for company {company_name}")
            return None
        
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
                print(f"Found partial name match: {account}")
                return account['id']
        
        # Priority 5: Common payroll account variations
        payroll_variations = {
            'Gross wages': ['Wages', 'Salaries', 'Gross Salaries', 'Employee Salaries'],
            'Staff bonus': ['Bonuses', 'Employee Bonuses', 'Staff Bonuses'],
            'Employers n.i.': ['Employer NI', 'Employer National Insurance', 'Employer Social Insurance', 'Social Insurance - Employer'],
            'PAYE/NIC': ['PAYE', 'NIC', 'Social Insurance Payable', 'Payroll Taxes Payable'],
            'Net wages': ['Wages Payable', 'Salaries Payable', 'Net Salaries Payable'],
            'Income Tax': ['Income Tax Payable', 'PAYE Payable', 'Tax Payable'],
            'Traveling': ['Travel', 'Travel Allowance', 'Travelling Allowance']
        }
        
        if account_name in payroll_variations:
            for variation in payroll_variations[account_name]:
                for account in accounts:
                    if account['name'].lower() == variation.lower():
                        print(f"Found payroll variation match: {account} (variation: '{variation}')")
                        return account['id']
        
        # Priority 6: Keyword matching
        keywords = account_name_lower.split()
        for keyword in keywords:
            if len(keyword) > 3:
                for account in accounts:
                    if keyword in account['name'].lower():
                        print(f"Found keyword match: {account} (keyword: '{keyword}')")
                        return account['id']
        
        print(f"No account found for name='{account_name}' or code='{account_code}' in company {company_name}")
        return None
        
    except Exception as e:
        print(f"Error finding account '{account_name}': {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def find_account_by_code(models, db, uid, password, account_code, company_id):
    """Find account by account code"""
    try:
        # Try with company_id
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
            pass
        
        # Fallback: search by code only
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

def check_duplicate_payroll_entry(models, db, uid, password, transaction_date, company_id, period=None, journal_id=None):
    """
    Check if a payroll entry for the same period already exists
    
    Returns:
        - None if no duplicate found
        - Entry data with exists=True if duplicate found
    """
    try:
        # Build search criteria
        search_domain = [
            ('move_type', '=', 'entry'),
            ('company_id', '=', company_id),
            ('date', '=', transaction_date),
            ('state', '!=', 'cancel'),
        ]
        
        # Add journal filter if provided
        if journal_id:
            search_domain.append(('journal_id', '=', journal_id))
        
        # Search for existing entries
        existing_entries = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [search_domain],
            {'fields': ['id', 'name', 'date', 'state', 'ref', 'journal_id']}
        )
        
        # Check if any entry matches payroll pattern
        for entry in existing_entries:
            ref = entry.get('ref', '').lower() if entry.get('ref') else ''
            
            # Check if it's a payroll entry
            payroll_keywords = ['payroll', 'salary', 'salaries', 'wages']
            if period:
                payroll_keywords.append(period.lower())
            
            is_payroll = any(keyword in ref for keyword in payroll_keywords)
            
            if is_payroll:
                # Get line items
                line_items = models.execute_kw(
                    db, uid, password,
                    'account.move.line', 'search_read',
                    [[('move_id', '=', entry['id'])]], 
                    {'fields': ['id', 'name', 'debit', 'credit', 'account_id']}
                )
                
                return {
                    'success': True,
                    'exists': True,
                    'entry_id': entry['id'],
                    'entry_number': entry['name'],
                    'date': entry['date'],
                    'state': entry['state'],
                    'ref': entry.get('ref'),
                    'line_items': line_items,
                    'message': 'Payroll entry for this period already exists - no duplicate created'
                }
        
        return None
        
    except Exception as e:
        print(f"Error checking for duplicate payroll entries: {str(e)}")
        return None

def main(data):
    """
    Create payroll journal entry from processed payroll data
    
    Expected data format:
    {
        "payroll_data": {
            "period": "202506 - JUNE",
            "year": "2025",
            "month": "June",
            "pay_date": "2025-06-30" or null,
            "currency_code": "EUR",
            "description": "Payroll for June 2025...",
            "journal_entry_lines": [
                {
                    "account_code": "7000",
                    "account_name": "Gross wages",
                    "description": "Total gross salaries",
                    "debit_amount": 1050.00,
                    "credit_amount": 0
                },
                ...
            ]
        },
        "matched_company": {
            "id": 124,
            "name": "ENAMI Limited"
        },
        "journal_id": 801
    }
    """
    
    # Handle array input (extract first element if array)
    if isinstance(data, list):
        if not data:
            return {
                'success': False,
                'error': 'Empty data array provided'
            }
        data = data[0]
    
    # Validate required fields
    if not data.get('matched_company'):
        return {
            'success': False,
            'error': 'matched_company is required'
        }
    
    if not data.get('journal_id'):
        return {
            'success': False,
            'error': 'journal_id is required'
        }
    
    if not data.get('payroll_data'):
        return {
            'success': False,
            'error': 'payroll_data is required'
        }
    
    # Extract data
    payroll_data = data['payroll_data']
    company_id = data['matched_company']['id']
    company_name = data['matched_company'].get('name', 'Unknown')
    journal_id = data['journal_id']
    
    # Validate journal entry lines
    journal_entry_lines = payroll_data.get('journal_entry_lines', [])
    if not journal_entry_lines:
        return {
            'success': False,
            'error': 'No journal entry lines found in payroll data'
        }
    
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
        
        # Verify journal exists and belongs to company
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
        
        # Determine transaction date
        pay_date = payroll_data.get('pay_date')
        if pay_date and pay_date not in [None, '', 'null', 'none']:
            transaction_date = normalize_date(pay_date)
        else:
            # Parse from period
            period = payroll_data.get('period', '')
            year = payroll_data.get('year')
            transaction_date = parse_period_to_date(period, year)
        
        # Validate date format
        try:
            datetime.strptime(transaction_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': f'Invalid date format: {transaction_date}. Expected YYYY-MM-DD'
            }
        
        # Check for duplicate payroll entry
        period = payroll_data.get('period', '')
        existing_entry = check_duplicate_payroll_entry(
            models, db, uid, password,
            transaction_date, company_id, period, journal_id
        )
        
        if existing_entry:
            return existing_entry
        
        # Prepare journal entry data
        move_data = {
            'move_type': 'entry',
            'date': transaction_date,
            'journal_id': journal_id,
            'company_id': company_id,
        }
        
        # Add reference
        period_display = payroll_data.get('period', payroll_data.get('month', 'Unknown'))
        year_display = payroll_data.get('year', '')
        ref = f"Payroll - {period_display} {year_display}".strip()
        move_data['ref'] = ref
        
        # Add description/narration if provided
        description = payroll_data.get('description', '')
        if description:
            move_data['narration'] = description
        
        # Process journal entry lines
        move_line_ids = []
        total_debits = 0
        total_credits = 0
        missing_accounts = []
        
        for line in journal_entry_lines:
            account_code = line.get('account_code', '')
            account_name = line.get('account_name', '')
            line_description = line.get('description', '')
            debit_amount = float(line.get('debit_amount', 0))
            credit_amount = float(line.get('credit_amount', 0))
            
            # Skip zero lines
            if debit_amount == 0 and credit_amount == 0:
                continue
            
            # Find account
            account_id = None
            if account_name:
                account_id = find_account_by_name(
                    models, db, uid, password,
                    account_name, company_id, account_code
                )
            elif account_code:
                account_id = find_account_by_code(
                    models, db, uid, password,
                    account_code, company_id
                )
            
            if not account_id:
                account_identifier = account_name or account_code or 'Unknown'
                missing_accounts.append(account_identifier)
                print(f"Warning: Account '{account_identifier}' not found, skipping line")
                continue
            
            # Create journal line
            journal_line = {
                'account_id': account_id,
                'name': line_description or account_name or f"Payroll - {account_code}",
                'debit': debit_amount,
                'credit': credit_amount,
            }
            
            move_line_ids.append((0, 0, journal_line))
            total_debits += debit_amount
            total_credits += credit_amount
        
        # Check if we have any valid lines
        if not move_line_ids:
            return {
                'success': False,
                'error': 'No valid journal entry lines could be created. All accounts were not found.',
                'missing_accounts': missing_accounts
            }
        
        # Calculate balance for informational purposes
        balance_difference = abs(total_debits - total_credits)
        is_balanced = balance_difference < 0.01
        
        # Log balance information (but don't fail if unbalanced)
        if is_balanced:
            print(f"✓ Journal entry is balanced: Debits {total_debits:.2f} = Credits {total_credits:.2f}")
        else:
            print(f"⚠️  Journal entry has balance difference: Debits {total_debits:.2f}, Credits {total_credits:.2f}, Difference: {balance_difference:.2f}")
            print(f"   Note: Entry will be created as-is. Odoo may automatically balance or accountant can adjust.")
        
        # Warn about missing accounts
        if missing_accounts:
            print(f"⚠️  Warning: Some accounts were not found and lines were skipped: {missing_accounts}")
        
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
                'error': 'Failed to create payroll journal entry in Odoo'
            }
        
        # POST THE JOURNAL ENTRY
        try:
            post_result = models.execute_kw(
                db, uid, password,
                'account.move', 'action_post',
                [[move_id]]
            )
            
            # Verify posted
            move_state = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[move_id]], 
                {'fields': ['state']}
            )[0]['state']
            
            if move_state != 'posted':
                return {
                    'success': False,
                    'error': f'Payroll entry was created but failed to post. Current state: {move_state}'
                }
                
        except xmlrpc.client.Fault as e:
            return {
                'success': False,
                'error': f'Payroll entry created but failed to post: {str(e)}'
            }
        
        # Get final entry information
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
            'entry_id': move_id,
            'entry_number': move_info.get('name'),
            'company_name': company_name,
            'period': period_display,
            'year': year_display,
            'transaction_date': transaction_date,
            'state': move_info.get('state'),
            'journal_name': journal_info['name'],
            'journal_code': journal_info['code'],
            'total_debits': total_debits,
            'total_credits': total_credits,
            'balance_difference': balance_difference,
            'is_balanced': is_balanced,
            'line_items': line_items,
            'line_count': len(line_items),
            'missing_accounts': missing_accounts if missing_accounts else None,
            'message': 'Payroll journal entry created and posted successfully'
        }
        
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

def create_payroll_entry(data):
    """Alias for main function"""
    return main(data)

def create(data):
    """Another alias for main function"""
    return main(data)

# Helper functions

def get_payroll_entry_details(entry_id, company_id=None):
    """Get detailed payroll entry information including line items"""
    
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
        domain = [('id', '=', entry_id), ('move_type', '=', 'entry')]
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        # Get entry info
        entry = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'date', 'ref', 'state', 'company_id', 'journal_id']}
        )
        
        if not entry:
            return {'success': False, 'error': 'Payroll entry not found'}
        
        # Get line items
        line_items = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', entry_id)]], 
            {'fields': ['id', 'name', 'debit', 'credit', 'account_id']}
        )
        
        return {
            'success': True,
            'entry': entry[0],
            'line_items': line_items
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def list_payroll_entries(company_id, journal_id=None, limit=50):
    """List payroll entries for a company"""
    
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
        domain = [
            ('move_type', '=', 'entry'),
            ('company_id', '=', company_id),
            ('state', '=', 'posted')
        ]
        
        if journal_id:
            domain.append(('journal_id', '=', journal_id))
        
        # Get entries
        entries = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [domain], 
            {'fields': ['id', 'name', 'date', 'ref', 'journal_id'], 'limit': limit * 2, 'order': 'date desc'}
        )
        
        # Filter for payroll entries
        payroll_entries = []
        for entry in entries:
            ref = entry.get('ref', '').lower() if entry.get('ref') else ''
            if any(keyword in ref for keyword in ['payroll', 'salary', 'salaries', 'wages']):
                payroll_entries.append(entry)
                if len(payroll_entries) >= limit:
                    break
        
        return {
            'success': True,
            'company_id': company_id,
            'entries': payroll_entries,
            'count': len(payroll_entries)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Export main functions
__all__ = ['main', 'create_payroll_entry', 'create', 'get_payroll_entry_details', 'list_payroll_entries']