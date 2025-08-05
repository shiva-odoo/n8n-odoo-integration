import os
import xmlrpc.client
from datetime import datetime
import hashlib

# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def main(data):
    """
    Create bank transaction entry in Odoo using flexible line items structure
    
    Expected data format:
    {
        "company_id": 13,
        "date": "2025-07-16",
        "ref": "BOC Transfer 255492965",
        "narration": "New Share Capital of Kyrastel Investments Ltd - Bank Credit Advice",
        "line_items": [
            {
                "name": "Bank of Cyprus",
                "debit": 15000.00,
                "credit": 0.00,
                "partner_id": null
            },
            {
                "name": "Share Capital",
                "debit": 0.00,
                "credit": 15000.00,
                "partner_id": null
            }
        ]
    }
    """
    
    # Validate required fields ( important )
    required_fields = ['company_id', 'date', 'ref', 'narration', 'line_items']
    
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        return {
            'success': False,
            'error': f'Missing required fields: {", ".join(missing_fields)}'
        }

    # Validate line_items
    if not isinstance(data['line_items'], list) or len(data['line_items']) < 2:
        return {
            'success': False,
            'error': 'line_items must be a list with at least 2 entries'
        }

    # Validate each line item
    for i, line in enumerate(data['line_items']):
        required_line_fields = ['name', 'debit', 'credit']
        missing_line_fields = [field for field in required_line_fields if field not in line]
        if missing_line_fields:
            return {
                'success': False,
                'error': f'Line item {i+1} missing fields: {", ".join(missing_line_fields)}'
            }
        
        # Validate debit/credit are numbers
        try:
            float(line['debit'])
            float(line['credit'])
        except (ValueError, TypeError):
            return {
                'success': False,
                'error': f'Line item {i+1} debit/credit must be valid numbers'
            }

    # Validate company_id is a number
    try:
        company_id = int(data['company_id'])
    except (ValueError, TypeError):
        return {
            'success': False,
            'error': 'company_id must be a valid integer'
        }

    # Validate that debits equal credits
    total_debits = sum(float(line['debit']) for line in data['line_items'])
    total_credits = sum(float(line['credit']) for line in data['line_items'])
    
    if abs(total_debits - total_credits) > 0.01:  # Allow for small rounding differences
        return {
            'success': False,
            'error': f'Debits ({total_debits}) must equal credits ({total_credits})'
        }

    # Fix future dates
    data['date'] = validate_and_fix_date(data['date'])

    # Connection details
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    if not all([url, db, username, password]):
        return {
            'success': False,
            'error': 'Missing Odoo connection environment variables'
        }
    
    try:
        print(f"=== PROCESSING FLEXIBLE TRANSACTION ===")
        print(f"Company ID: {company_id}")
        print(f"Date: {data['date']}")
        print(f"Reference: {data['ref']}")
        print(f"Narration: {data['narration']}")
        print(f"Line Items: {len(data['line_items'])}")
        
        # Initialize connection
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Authenticate
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {
                'success': False,
                'error': 'Odoo authentication failed'
            }
        
        print("✅ Odoo authentication successful")
        
        # Step 1: Verify company exists and get its details
        company_details = verify_company_exists(models, db, uid, password, company_id)
        if not company_details:
            return {
                'success': False,
                'error': f'Company with ID {company_id} not found'
            }
        
        print(f"✅ Found Company: {company_details['name']}")
        
        # Update context to work with specific company
        context = {'allowed_company_ids': [company_id]}
        
        # Step 2: Check for duplicate transaction by reference
        duplicate_check = check_for_duplicate_by_ref(
            models, db, uid, password, data['ref'], company_id, context
        )
        
        if duplicate_check['is_duplicate']:
            # Get journal and partner info from existing entry for consistent response
            existing_entry = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [duplicate_check['existing_entry_id']],
                {'fields': ['journal_id', 'line_ids', 'partner_id']}
            )
            
            journal_code = None
            if existing_entry[0]['journal_id']:
                journal_details = models.execute_kw(
                    db, uid, password,
                    'account.journal', 'read',
                    [existing_entry[0]['journal_id'][0]],
                    {'fields': ['code']}
                )
                journal_code = journal_details[0]['code'] if journal_details else None
            
            partner_ids = []
            
            # Get partner info from line items
            if existing_entry[0]['line_ids']:
                line_details = models.execute_kw(
                    db, uid, password,
                    'account.move.line', 'read',
                    existing_entry[0]['line_ids'],
                    {'fields': ['partner_id']}
                )
                partner_ids = [line['partner_id'][0] for line in line_details if line['partner_id']]
            
            return {
                'success': False,
                'error': 'Duplicate transaction',
                'message': f'Transaction with reference "{data["ref"]}" already exists',
                'existing_entry_id': duplicate_check['existing_entry_id'],
                'date': data['date'],
                'ref': data['ref'],
                'journal_code': journal_code,
                'company_id': company_id,
                'company_name': company_details['name'],
                'total_amount': total_debits,
                'partner_ids': partner_ids,
                'duplicate_details': duplicate_check
            }
        
        print("✅ No duplicate found, proceeding with transaction creation")
        
        # Step 3: Resolve account IDs for all line items
        resolved_line_items = []
        partner_ids = []
        
        for i, line_item in enumerate(data['line_items']):
            account_id = find_account_by_name(models, db, uid, password, line_item['name'], context)
            
            if not account_id:
                return {
                    'success': False,
                    'error': f'Could not find account for: "{line_item["name"]}"'
                }
            
            resolved_line = {
                'account_id': account_id,
                'name': data['narration'],  # Use narration as line description
                'debit': float(line_item['debit']),
                'credit': float(line_item['credit']),
            }
            
            # Add partner_id if specified and collect partner IDs
            if line_item.get('partner_id'):
                resolved_line['partner_id'] = line_item['partner_id']
                if line_item['partner_id'] not in partner_ids:
                    partner_ids.append(line_item['partner_id'])
            
            resolved_line_items.append(resolved_line)
            print(f"✅ Line {i+1}: {line_item['name']} -> Account ID {account_id}")
        
        # Step 4: Get default journal (or determine from line items)
        journal_id = get_default_journal_for_transaction(models, db, uid, password, data, context)
        
        if not journal_id:
            return {
                'success': False,
                'error': 'Could not find appropriate journal'
            }
        
        print(f"✅ Using Journal ID: {journal_id}")
        
        # Get journal code for return response
        journal_code = None
        if journal_id:
            journal_details = models.execute_kw(
                db, uid, password,
                'account.journal', 'read',
                [journal_id],
                {'fields': ['code']}
            )
            journal_code = journal_details[0]['code'] if journal_details else None
        
        # Step 5: Create Journal Entry
        journal_entry_id = create_journal_entry_flexible(
            models, db, uid, password,
            journal_id,
            resolved_line_items,
            data,
            context
        )
        
        if not journal_entry_id:
            return {
                'success': False,
                'error': 'Failed to create journal entry'
            }
        
        print(f"✅ Journal Entry ID: {journal_entry_id}")
        print(f"✅ Transaction completed successfully")
        
        return {
            'success': True,
            'journal_entry_id': journal_entry_id,
            'date': data['date'],
            'ref': data['ref'],
            'journal_code': journal_code,
            'company_id': company_id,
            'company_name': company_details['name'],
            'total_amount': total_debits,
            'partner_ids': partner_ids,
            'description': data['narration'],
            'line_count': len(data['line_items']),
            'message': 'Flexible bank transaction entry created successfully'
        }
        
    except xmlrpc.client.Fault as e:
        error_msg = f'Odoo API error: {str(e)}'
        print(f"❌ {error_msg}")
        return {
            'success': False,
            'error': error_msg
        }
    except Exception as e:
        error_msg = f'Unexpected error: {str(e)}'
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': error_msg
        }

def find_account_by_name(models, db, uid, password, account_name, context):
    """
    Find account ID by searching for account name or code
    Searches both name and code fields for flexible matching
    """
    try:
        print(f"🔍 Looking for account: '{account_name}'")
        
        # First try exact match on name
        account_ids = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('name', '=', account_name)]], 
            {'limit': 1, 'context': context}
        )
        
        if account_ids:
            account_details = models.execute_kw(
                db, uid, password,
                'account.account', 'read',
                [account_ids, ['name', 'code']], 
                {'context': context}
            )
            print(f"✅ Exact name match: {account_details[0]['name']} ({account_details[0]['code']})")
            return account_ids[0]
        
        # Try exact match on code
        account_ids = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('code', '=', account_name)]], 
            {'limit': 1, 'context': context}
        )
        
        if account_ids:
            account_details = models.execute_kw(
                db, uid, password,
                'account.account', 'read',
                [account_ids, ['name', 'code']], 
                {'context': context}
            )
            print(f"✅ Exact code match: {account_details[0]['name']} ({account_details[0]['code']})")
            return account_ids[0]
        
        # Try partial match on name (case insensitive)
        account_ids = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('name', 'ilike', account_name)]], 
            {'limit': 1, 'context': context}
        )
        
        if account_ids:
            account_details = models.execute_kw(
                db, uid, password,
                'account.account', 'read',
                [account_ids, ['name', 'code']], 
                {'context': context}
            )
            print(f"✅ Partial name match: {account_details[0]['name']} ({account_details[0]['code']})")
            return account_ids[0]
        
        # Try to find by keywords for common account types
        account_keywords = {
            'bank': ['bank', 'cash', 'current account'],
            'share capital': ['share capital', 'capital', 'equity'],
            'revenue': ['revenue', 'income', 'sales'],
            'expense': ['expense', 'cost'],
            'accounts receivable': ['receivable', 'debtors'],
            'accounts payable': ['payable', 'creditors']
        }
        
        account_name_lower = account_name.lower()
        
        for account_type, keywords in account_keywords.items():
            for keyword in keywords:
                if keyword in account_name_lower:
                    print(f"🔍 Searching by keyword '{keyword}' for account type '{account_type}'")
                    
                    # Search for accounts containing this keyword
                    account_ids = models.execute_kw(
                        db, uid, password,
                        'account.account', 'search',
                        [[('name', 'ilike', keyword)]], 
                        {'limit': 1, 'context': context}
                    )
                    
                    if account_ids:
                        account_details = models.execute_kw(
                            db, uid, password,
                            'account.account', 'read',
                            [account_ids, ['name', 'code']], 
                            {'context': context}
                        )
                        print(f"✅ Keyword match: {account_details[0]['name']} ({account_details[0]['code']})")
                        return account_ids[0]
        
        print(f"❌ No account found for: '{account_name}'")
        return None
        
    except Exception as e:
        print(f"❌ Error finding account '{account_name}': {e}")
        return None

def check_for_duplicate_by_ref(models, db, uid, password, ref, company_id, context):
    """
    Check if a duplicate transaction exists by reference
    """
    try:
        print(f"🔍 Checking for duplicate by reference: {ref}")
        
        existing_moves = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[
                ('company_id', '=', company_id),
                ('ref', '=', ref)
            ]], 
            {'fields': ['id', 'ref', 'date', 'state', 'amount_total'], 'limit': 1, 'context': context}
        )
        
        if existing_moves:
            move = existing_moves[0]
            print(f"❌ Duplicate found by reference:")
            print(f"   Existing: Move ID {move['id']}, Ref: {move['ref']}")
            print(f"   Date: {move['date']}, Amount: {move['amount_total']}")
            return {
                'is_duplicate': True,
                'existing_entry_id': move['id'],
                'method': 'exact_reference_match',
                'existing_ref': move['ref'],
                'existing_amount': move['amount_total'],
                'existing_date': move['date']
            }
        
        print("✅ No duplicate reference found")
        return {
            'is_duplicate': False,
            'existing_entry_id': None,
            'method': None
        }
        
    except Exception as e:
        print(f"❌ Error checking for duplicates: {e}")
        import traceback
        traceback.print_exc()
        return {
            'is_duplicate': True,
            'existing_entry_id': None,
            'method': 'error_safe_mode',
            'error': str(e)
        }

def verify_company_exists(models, db, uid, password, company_id):
    """Verify that the company exists and return its details"""
    try:
        print(f"🔍 Verifying company with ID: {company_id}")
        
        company_data = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[('id', '=', company_id)]], 
            {'fields': ['id', 'name', 'country_id', 'currency_id'], 'limit': 1}
        )
        
        if not company_data:
            print(f"❌ Company with ID {company_id} not found")
            return None
        
        company = company_data[0]
        print(f"✅ Company verified: {company['name']}")
        print(f"   Country: {company.get('country_id', 'Not set')}")
        print(f"   Currency: {company.get('currency_id', 'Not set')}")
        
        return company
        
    except Exception as e:
        print(f"❌ Error verifying company: {e}")
        return None

def get_default_journal_for_transaction(models, db, uid, password, data, context):
    """
    Determine appropriate journal for the transaction
    Looks for bank journals or miscellaneous journals
    """
    try:
        # First, try to find a bank journal
        journal_ids = models.execute_kw(
            db, uid, password,
            'account.journal', 'search',
            [[('type', '=', 'bank')]], 
            {'limit': 1, 'context': context}
        )
        
        if journal_ids:
            journal_details = models.execute_kw(
                db, uid, password,
                'account.journal', 'read',
                [journal_ids, ['name', 'code', 'type']], 
                {'context': context}
            )
            print(f"✅ Using bank journal: {journal_details[0]['name']} ({journal_details[0]['code']})")
            return journal_ids[0]
        
        # If no bank journal, look for miscellaneous journal
        journal_ids = models.execute_kw(
            db, uid, password,
            'account.journal', 'search',
            [[('type', '=', 'general')]], 
            {'limit': 1, 'context': context}
        )
        
        if journal_ids:
            journal_details = models.execute_kw(
                db, uid, password,
                'account.journal', 'read',
                [journal_ids, ['name', 'code', 'type']], 
                {'context': context}
            )
            print(f"✅ Using general journal: {journal_details[0]['name']} ({journal_details[0]['code']})")
            return journal_ids[0]
        
        # If no specific journal found, get any available journal
        journal_ids = models.execute_kw(
            db, uid, password,
            'account.journal', 'search',
            [[]], 
            {'limit': 1, 'context': context}
        )
        
        if journal_ids:
            journal_details = models.execute_kw(
                db, uid, password,
                'account.journal', 'read',
                [journal_ids, ['name', 'code', 'type']], 
                {'context': context}
            )
            print(f"✅ Using default journal: {journal_details[0]['name']} ({journal_details[0]['code']})")
            return journal_ids[0]
        
        return None
        
    except Exception as e:
        print(f"❌ Error finding journal: {e}")
        return None

def validate_and_fix_date(date_str):
    """Ensure date is not in the future and is valid"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        today = datetime.now()
        
        # If date is in the future, use today's date
        if date_obj > today:
            corrected_date = today.strftime('%Y-%m-%d')
            print(f"⚠️  Future date {date_str} corrected to {corrected_date}")
            return corrected_date
        
        return date_str
    except ValueError:
        # If invalid format, use today
        corrected_date = datetime.now().strftime('%Y-%m-%d')
        print(f"⚠️  Invalid date format {date_str} corrected to {corrected_date}")
        return corrected_date

def create_journal_entry_flexible(models, db, uid, password, journal_id, line_items, data, context):
    """Create journal entry using flexible line items"""
    try:
        print(f"📝 Creating flexible journal entry...")
        
        # Prepare line_ids for Odoo (using (0, 0, values) format)
        line_ids = []
        for line_item in line_items:
            line_ids.append((0, 0, line_item))
        
        # Create journal entry
        move_data = {
            'journal_id': journal_id,
            'date': data['date'],
            'ref': data['ref'],
            'narration': data['narration'],
            'line_ids': line_ids,
        }
        
        print(f"📝 Creating move with reference: {data['ref']}")
        print(f"📝 Narration: {data['narration']}")
        
        move_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [move_data], {'context': context}
        )
        
        if not move_id:
            raise Exception("Failed to create account move")
        
        print(f"✅ Move created with ID: {move_id}")
        
        # Post the journal entry
        print(f"📝 Posting journal entry...")
        models.execute_kw(
            db, uid, password,
            'account.move', 'action_post',
            [[move_id]], {'context': context}
        )
        
        print(f"✅ Journal entry posted successfully")
        return move_id
        
    except Exception as e:
        print(f"❌ Error creating journal entry: {e}")
        import traceback
        traceback.print_exc()
        return None

def list_available_accounts(models, db, uid, password, context, account_type=None):
    """
    Helper function to list available accounts (useful for debugging)
    """
    try:
        search_domain = []
        if account_type:
            search_domain.append(('account_type', '=', account_type))
        
        accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [search_domain], 
            {'fields': ['id', 'name', 'code', 'account_type'], 'limit': 50, 'context': context}
        )
        
        print(f"📊 Available accounts ({len(accounts)}):")
        for account in accounts:
            print(f"   ID: {account['id']}, Code: {account['code']}, Name: {account['name']}, Type: {account['account_type']}")
        
        return accounts
        
    except Exception as e:
        print(f"❌ Error listing accounts: {e}")
        return []

def create(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

# Example usage
if __name__ == "__main__":
    sample_data = {
        "company_id": 13,
        "date": "2025-07-16",
        "ref": "BOC Transfer 255492965",
        "narration": "New Share Capital of Kyrastel Investments Ltd - Bank Credit Advice",
        "line_items": [
            {
                "name": "Bank of Cyprus",
                "debit": 15000.00,
                "credit": 0.00,
                "partner_id": None
            },
            {
                "name": "Share Capital",
                "debit": 0.00,
                "credit": 15000.00,
                "partner_id": None
            }
        ]
    }
    
    result = main(sample_data)
    print("\n" + "="*50)
    print("FINAL RESULT:")
    print(result)