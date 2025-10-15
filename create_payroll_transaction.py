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
    
def find_suspense_account(models, db, uid, password, company_id):
    """
    Find suspense account code 1260 "Suspense account" for the specific company
    
    CRITICAL: Must belong to same company to avoid Odoo cross-company errors
    
    Returns: account_id if found, None if not found
    """
    try:
        print(f"\n{'='*80}")
        print(f"🔍 SEARCHING FOR SUSPENSE ACCOUNT")
        print(f"{'='*80}")
        print(f"Target: Code 1260, Name 'Suspense account'")
        print(f"Company ID: {company_id}")
        
        # Get company name
        try:
            company_data = models.execute_kw(
                db, uid, password,
                'res.company', 'search_read',
                [[('id', '=', company_id)]], 
                {'fields': ['name'], 'limit': 1}
            )
            company_name = company_data[0]['name'] if company_data else f"Company ID {company_id}"
        except:
            company_name = f"Company ID {company_id}"
        
        print(f"Company Name: {company_name}")
        print(f"{'-'*80}")
        
        # ATTEMPT 1: Direct search by code 1260 with company_id
        print(f"\n📌 ATTEMPT 1: Search by code='1260' with company_id={company_id}")
        try:
            result = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('code', '=', '1260'), ('company_id', '=', company_id), ('active', '=', True)]],
                {'fields': ['id', 'name', 'code', 'company_id']}
            )
            
            if result:
                account = result[0]
                print(f"✅ SUCCESS! Found account:")
                print(f"   ID: {account['id']}")
                print(f"   Name: {account['name']}")
                print(f"   Code: {account['code']}")
                print(f"   Company: {account.get('company_id')}")
                print(f"{'='*80}\n")
                return account['id']
            else:
                print(f"❌ No results")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
        
        # ATTEMPT 2: Search by exact name with company_id
        print(f"\n📌 ATTEMPT 2: Search by name='Suspense account' with company_id={company_id}")
        try:
            result = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('name', '=', 'Suspense account'), ('company_id', '=', company_id), ('active', '=', True)]],
                {'fields': ['id', 'name', 'code', 'company_id']}
            )
            
            if result:
                account = result[0]
                print(f"✅ SUCCESS! Found account:")
                print(f"   ID: {account['id']}")
                print(f"   Name: {account['name']}")
                print(f"   Code: {account.get('code')}")
                print(f"   Company: {account.get('company_id')}")
                print(f"{'='*80}\n")
                return account['id']
            else:
                print(f"❌ No results")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
        
        # ATTEMPT 3: Search without company_id filter, then filter results
        print(f"\n📌 ATTEMPT 3: Search by code='1260' without company filter, then filter")
        try:
            result = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('code', '=', '1260'), ('active', '=', True)]],
                {'fields': ['id', 'name', 'code', 'company_id']}
            )
            
            if result:
                print(f"Found {len(result)} account(s) with code 1260:")
                for acc in result:
                    acc_company_id = acc['company_id'][0] if isinstance(acc['company_id'], list) else acc['company_id']
                    matches = acc_company_id == company_id
                    status = "✅ MATCH" if matches else "❌ WRONG COMPANY"
                    print(f"   {status} - ID: {acc['id']}, Name: {acc['name']}, Company ID: {acc_company_id}")
                    
                    if matches:
                        print(f"\n✅ SUCCESS! Using account ID: {acc['id']}")
                        print(f"{'='*80}\n")
                        return acc['id']
                
                print(f"❌ No accounts match company_id {company_id}")
            else:
                print(f"❌ No accounts with code 1260 found in any company")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
        
        # ATTEMPT 4: Indirect method via journals
        print(f"\n📌 ATTEMPT 4: Indirect search via company's journals")
        try:
            journals = models.execute_kw(
                db, uid, password,
                'account.journal', 'search_read',
                [[('company_id', '=', company_id)]],
                {'fields': ['id']}
            )
            
            if journals:
                journal_ids = [j['id'] for j in journals]
                print(f"Found {len(journal_ids)} journals for company")
                
                # Get accounts used by these journals
                moves = models.execute_kw(
                    db, uid, password,
                    'account.move.line', 'search_read',
                    [[('journal_id', 'in', journal_ids)]],
                    {'fields': ['account_id'], 'limit': 3000}
                )
                
                if moves:
                    account_ids = list(set([
                        m['account_id'][0] if isinstance(m['account_id'], list) else m['account_id']
                        for m in moves if m.get('account_id')
                    ]))
                    print(f"Found {len(account_ids)} unique accounts used by company")
                    
                    # Get details for these accounts
                    accounts = models.execute_kw(
                        db, uid, password,
                        'account.account', 'search_read',
                        [[('id', 'in', account_ids), ('active', '=', True)]],
                        {'fields': ['id', 'name', 'code']}
                    )
                    
                    # Look for code 1260
                    for acc in accounts:
                        if acc.get('code') == '1260':
                            print(f"✅ SUCCESS! Found via journals:")
                            print(f"   ID: {acc['id']}")
                            print(f"   Name: {acc['name']}")
                            print(f"   Code: {acc['code']}")
                            print(f"{'='*80}\n")
                            return acc['id']
                    
                    # Look for exact name
                    for acc in accounts:
                        if acc.get('name') == 'Suspense account':
                            print(f"✅ SUCCESS! Found via journals by name:")
                            print(f"   ID: {acc['id']}")
                            print(f"   Name: {acc['name']}")
                            print(f"   Code: {acc.get('code')}")
                            print(f"{'='*80}\n")
                            return acc['id']
                    
                    print(f"❌ Code 1260 or 'Suspense account' not found in company's used accounts")
                else:
                    print(f"❌ No account moves found for company journals")
            else:
                print(f"❌ No journals found for company")
        except Exception as e:
            print(f"❌ Error in indirect search: {str(e)}")
        
        # NOT FOUND - Provide detailed diagnostic
        print(f"\n{'='*80}")
        print(f"❌ SUSPENSE ACCOUNT NOT FOUND")
        print(f"{'='*80}")
        print(f"Searched for:")
        print(f"  - Code: 1260")
        print(f"  - Name: Suspense account")
        print(f"  - Company: {company_name} (ID: {company_id})")
        print(f"\n💡 SOLUTION:")
        print(f"  1. Verify in Odoo: Accounting > Configuration > Chart of Accounts")
        print(f"  2. Check if account 1260 exists for company '{company_name}'")
        print(f"  3. Check if account is active (not archived)")
        print(f"  4. Check account is assigned to correct company")
        print(f"\n  If account doesn't exist, create it:")
        print(f"     Code: 1260")
        print(f"     Name: Suspense account")
        print(f"     Type: Current Assets")
        print(f"     Company: {company_name}")
        print(f"{'='*80}\n")
        
        return None
        
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ CRITICAL ERROR IN find_suspense_account()")
        print(f"{'='*80}")
        print(f"Error: {str(e)}")
        print(f"{'='*80}\n")
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
        
        # Calculate balance
        balance_difference = abs(total_debits - total_credits)
        is_balanced = balance_difference < 0.01
        auto_balanced = False
        
        # CRITICAL: Auto-balance if unbalanced
        if not is_balanced:
            print(f"⚠️  Entry unbalanced by €{balance_difference:.2f}")
            print(f"   Total Debits: €{total_debits:.2f}")
            print(f"   Total Credits: €{total_credits:.2f}")
            
            # Try to find a suspense/rounding account
            suspense_account_id = find_suspense_account(models, db, uid, password, company_id)
            
            if suspense_account_id:
                # Add balancing line
                if total_debits > total_credits:
                    # Need more credits
                    balance_line = {
                        'account_id': suspense_account_id,
                        'name': f'Auto-balancing adjustment (Difference: €{balance_difference:.2f}) - REVIEW AND ADJUST',
                        'debit': 0,
                        'credit': balance_difference,
                    }
                else:
                    # Need more debits
                    balance_line = {
                        'account_id': suspense_account_id,
                        'name': f'Auto-balancing adjustment (Difference: €{balance_difference:.2f}) - REVIEW AND ADJUST',
                        'debit': balance_difference,
                        'credit': 0,
                    }
                
                move_line_ids.append((0, 0, balance_line))
                
                # Recalculate totals after balancing
                if total_debits > total_credits:
                    total_credits += balance_difference
                else:
                    total_debits += balance_difference
                
                is_balanced = True
                auto_balanced = True
                
                print(f"✓ Added auto-balancing line to suspense account")
                print(f"⚠️  IMPORTANT: Manual review required to correct the balancing entry")
            else:
                # Cannot auto-balance - return detailed error
                return {
                    'success': False,
                    'error': 'Entry is unbalanced and no suspense account found for auto-balancing',
                    'total_debits': total_debits,
                    'total_credits': total_credits,
                    'balance_difference': balance_difference,
                    'line_items_attempted': len(move_line_ids),
                    'missing_accounts': missing_accounts if missing_accounts else None,
                    'suggestion': 'Please verify the payroll document processing or create a suspense account (code: 1260)',
                    'debug_info': {
                        'journal_lines_provided': len(journal_entry_lines),
                        'journal_lines_processed': len(move_line_ids),
                        'debit_lines': [
                            {'account': line[2].get('name'), 'amount': line[2].get('debit')} 
                            for line in move_line_ids if line[2].get('debit', 0) > 0
                        ],
                        'credit_lines': [
                            {'account': line[2].get('name'), 'amount': line[2].get('credit')} 
                            for line in move_line_ids if line[2].get('credit', 0) > 0
                        ]
                    }
                }
        
        # Log balance information
        if is_balanced and not auto_balanced:
            print(f"✓ Journal entry is naturally balanced: Debits €{total_debits:.2f} = Credits €{total_credits:.2f}")
        elif is_balanced and auto_balanced:
            print(f"✓ Journal entry is auto-balanced: Debits €{total_debits:.2f} = Credits €{total_credits:.2f}")
        
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
                    'error': f'Payroll entry was created but failed to post. Current state: {move_state}',
                    'entry_id': move_id,
                    'auto_balanced': auto_balanced
                }
                
        except xmlrpc.client.Fault as e:
            return {
                'success': False,
                'error': f'Payroll entry created but failed to post: {str(e)}',
                'entry_id': move_id,
                'auto_balanced': auto_balanced
            }
        
        # ### START: COMPREHENSIVE OUTPUT RETRIEVAL (matching share script) ###

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
                'entry_id': move_id
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

        # Build warnings array
        warnings = []
        if auto_balanced:
            warnings.append('Entry was auto-balanced using suspense account - MANUAL REVIEW REQUIRED')
            warnings.append('Verify all amounts match the source payroll document')
            warnings.append('Adjust or remove the suspense account line after verification')
        if missing_accounts:
            warnings.append(f'Some accounts were not found: {", ".join(missing_accounts)}')

        # Construct the comprehensive success response (matching share script format)
        return {
            'success': True,
            'exists': False,
            'message': 'Payroll journal entry created and posted successfully' + 
                      (' (AUTO-BALANCED - Manual review required)' if auto_balanced else ''),
            
            # Entry header information
            'entry_id': move_id,
            'entry_number': entry_info.get('name'),
            'state': entry_info.get('state'),
            'move_type': entry_info.get('move_type'),
            
            # Dates
            'transaction_date': transaction_date,
            'date': entry_info.get('date'),
            
            # Payroll specific info
            'company_name': company_name,
            'period': period_display,
            'year': year_display,
            
            # References
            'reference': entry_info.get('ref'),
            'ref': entry_info.get('ref'),
            'narration': entry_info.get('narration'),
            
            # Amounts
            'total_debits': total_debits,
            'total_credits': total_credits,
            'balance_difference': 0 if auto_balanced else balance_difference,
            'is_balanced': is_balanced,
            'auto_balanced': auto_balanced,
            'requires_review': auto_balanced or len(missing_accounts) > 0,
            'amount_total': entry_info.get('amount_total', total_debits),
            'currency': entry_info.get('currency_id'),
            
            # Partner information (if exists - usually not for payroll)
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
            'journal_name': journal_details['name'],
            'journal_code': journal_details['code'],
            
            # Detailed line items (matching share script format)
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
            
            # Additional info
            'missing_accounts': missing_accounts if missing_accounts else None,
            'warnings': warnings if warnings else None,
            
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