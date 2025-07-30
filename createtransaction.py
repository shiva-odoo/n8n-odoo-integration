import os
import xmlrpc.client
from datetime import datetime

# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def main(data):
    """
    Create bank transaction entry in Odoo for specific company
    
    Expected data format:
    {
        "bank_name": "Bank of Cyprus",
        "company_name": "KYRASTEL ENTERPRISES LTD",
        "entry_type": "transaction",
        "description": "Registrar of companies fee reimbursement",
        "amount": 20,
        "currency": "EUR",
        "id": "20250721_BOC_143022",
        "date": "2025-07-21"
    }
    """
    
    # Validate required fields
    required_fields = [
        'bank_name', 'company_name', 'entry_type', 'description', 
        'amount', 'currency', 'id', 'date'
    ]
    
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        return {
            'success': False,
            'error': f'Missing required fields: {", ".join(missing_fields)}'
        }

    # Validate entry type
    if data['entry_type'] != 'transaction':
        return {
            'success': False,
            'error': 'entry_type must be "transaction"'
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
        print(f"=== PROCESSING TRANSACTION ===")
        print(f"Company: {data['company_name']}")
        print(f"Description: {data['description']}")
        print(f"Amount: {data['amount']} {data['currency']}")
        print(f"Date: {data['date']}")
        
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
        
        # Step 1: Find and switch to correct company
        company_id = find_company(models, db, uid, password, data)
        if not company_id:
            return {
                'success': False,
                'error': f'Company not found: {data["company_name"]}'
            }
        
        print(f"✅ Found Company ID: {company_id}")
        
        # Update context to work with specific company
        context = {'allowed_company_ids': [company_id]}
        
        # Step 2: Get default bank and expense accounts
        bank_account_id = get_default_bank_account(models, db, uid, password, context)
        expense_account_id = get_default_expense_account(models, db, uid, password, context)
        
        if not bank_account_id or not expense_account_id:
            return {
                'success': False,
                'error': 'Could not find default bank or expense accounts'
            }
        
        print(f"✅ Using Bank Account ID: {bank_account_id}")
        print(f"✅ Using Expense Account ID: {expense_account_id}")
        
        # Step 3: Get default bank journal (with bank name)
        journal_id = get_or_create_bank_journal(models, db, uid, password, data, context)
        
        if not journal_id:
            return {
                'success': False,
                'error': 'Could not find default bank journal'
            }
        
        print(f"✅ Using Journal ID: {journal_id}")
        
        # Step 4: Create Journal Entry
        journal_entry_id = create_journal_entry(
            models, db, uid, password,
            journal_id,
            bank_account_id,
            expense_account_id,
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
            'company_id': company_id,
            'transaction_id': data['id'],
            'amount': data['amount'],
            'currency': data['currency'],
            'message': 'Bank transaction entry created successfully'
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

def find_company(models, db, uid, password, data):
    """Find company in Odoo using company_name with fuzzy matching"""
    try:
        print(f"🔍 Searching for company: {data['company_name']}")
        
        # Get all companies first for better matching
        all_companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], {'fields': ['id', 'name']}
        )
        
        print(f"📋 Available companies: {[c['name'] for c in all_companies]}")
        
        search_name = data['company_name']
        
        # Try exact match first
        for company in all_companies:
            if company['name'] == search_name:
                print(f"✅ Found company by exact match: {company['name']}")
                return company['id']
        
        # Try case-insensitive match
        for company in all_companies:
            if company['name'].upper() == search_name.upper():
                print(f"✅ Found company by case-insensitive match: {company['name']}")
                return company['id']
        
        # Try fuzzy matching - remove common suffixes and variations
        def normalize_company_name(name):
            name = name.upper()
            # Replace common variations
            name = name.replace('LIMITED', 'LTD')
            name = name.replace('ENTERPRISES', 'ENT')
            name = name.replace('COMPANY', 'CO')
            name = name.replace('CORPORATION', 'CORP')
            # Remove common punctuation and extra spaces
            name = name.replace('.', '').replace(',', '').replace('-', ' ')
            name = ' '.join(name.split())  # Remove extra spaces
            return name
        
        normalized_search = normalize_company_name(search_name)
        print(f"🔍 Normalized search name: {normalized_search}")
        
        for company in all_companies:
            normalized_company = normalize_company_name(company['name'])
            print(f"   Comparing with: {normalized_company}")
            
            if normalized_company == normalized_search:
                print(f"✅ Found company by normalized match: {company['name']}")
                return company['id']
        
        # Try partial matching - check if key words match
        search_words = set(normalized_search.split())
        for company in all_companies:
            company_words = set(normalize_company_name(company['name']).split())
            
            # If most words match (at least 70% overlap)
            if len(search_words & company_words) >= len(search_words) * 0.7:
                print(f"✅ Found company by partial word match: {company['name']}")
                return company['id']
        
        # Try contains matching
        for company in all_companies:
            if (normalized_search in normalize_company_name(company['name']) or 
                normalize_company_name(company['name']) in normalized_search):
                print(f"✅ Found company by contains match: {company['name']}")
                return company['id']
        
        print(f"❌ Company not found: {data['company_name']}")
        print(f"   Tried normalized: {normalized_search}")
        return None
        
    except Exception as e:
        print(f"❌ Error finding company: {e}")
        return None

def get_default_bank_account(models, db, uid, password, context):
    """Get the default bank account"""
    try:
        # Look for any bank-type account
        account_ids = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('account_type', '=', 'asset_cash')]], 
            {'limit': 1, 'context': context}
        )
        
        if account_ids:
            return account_ids[0]
        
        # If no cash account, look for any asset account
        account_ids = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('account_type', 'like', 'asset')]], 
            {'limit': 1, 'context': context}
        )
        
        return account_ids[0] if account_ids else None
        
    except Exception as e:
        print(f"❌ Error finding bank account: {e}")
        return None

def get_default_expense_account(models, db, uid, password, context):
    """Get the default expense account"""
    try:
        # Look for expense account
        account_ids = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('account_type', '=', 'expense')]], 
            {'limit': 1, 'context': context}
        )
        
        return account_ids[0] if account_ids else None
        
    except Exception as e:
        print(f"❌ Error finding expense account: {e}")
        return None

def get_or_create_bank_journal(models, db, uid, password, data, context):
    """Get or create bank journal with bank name"""
    try:
        journal_name = data['bank_name']
        journal_code = data['bank_name'][:10].upper().replace(' ', '')  # Short code from bank name
        
        print(f"📋 Looking for journal: {journal_name}")
        
        # Look for journal with this bank name
        journal_ids = models.execute_kw(
            db, uid, password,
            'account.journal', 'search',
            [[('name', '=', journal_name), ('type', '=', 'bank')]], 
            {'limit': 1, 'context': context}
        )
        
        if journal_ids:
            print(f"✅ Found existing journal: {journal_name}")
            return journal_ids[0]
        
        # If not found, get any bank journal and update it, or create new one
        existing_journal_ids = models.execute_kw(
            db, uid, password,
            'account.journal', 'search',
            [[('type', '=', 'bank')]], 
            {'limit': 1, 'context': context}
        )
        
        if existing_journal_ids:
            # Update existing journal with bank name
            models.execute_kw(
                db, uid, password,
                'account.journal', 'write',
                [existing_journal_ids, {'name': journal_name}],
                {'context': context}
            )
            print(f"✅ Updated existing journal to: {journal_name}")
            return existing_journal_ids[0]
        
        # Create new journal if none exists
        bank_account_id = get_default_bank_account(models, db, uid, password, context)
        if not bank_account_id:
            return None
            
        journal_data = {
            'name': journal_name,
            'code': journal_code,
            'type': 'bank',
            'default_account_id': bank_account_id,
        }
        
        journal_id = models.execute_kw(
            db, uid, password,
            'account.journal', 'create',
            [journal_data], {'context': context}
        )
        
        print(f"✅ Created new journal: {journal_name}")
        return journal_id
        
    except Exception as e:
        print(f"❌ Error with bank journal: {e}")
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

def create_journal_entry(models, db, uid, password, journal_id, bank_account_id, expense_account_id, data, context):
    """Create the actual journal entry"""
    try:
        print(f"📝 Creating journal entry...")
        
        amount = float(data['amount'])
        
        print(f"   Amount: {amount} {data['currency']}")
        
        # Most bank transactions are expenses (money going out)
        # Bank account gets credited (money out), expense account gets debited
        line_ids = []
        
        # Bank account line (credit - money going out)
        bank_line = {
            'account_id': bank_account_id,
            'name': data['description'],
            'debit': 0.0,
            'credit': amount,
        }
        
        line_ids.append((0, 0, bank_line))
        
        # Expense account line (debit - expense incurred)
        expense_line = {
            'account_id': expense_account_id,
            'name': data['description'],
            'debit': amount,
            'credit': 0.0,
        }
        
        line_ids.append((0, 0, expense_line))
        
        # Create journal entry
        move_data = {
            'journal_id': journal_id,
            'date': data['date'],
            'ref': data['description'],  # Use description as reference
            'line_ids': line_ids,
        }
        
        print(f"📝 Creating move with reference: {data['description']}")
        
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

def create(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

# Example usage
if __name__ == "__main__":
    sample_data = {
        "bank_name": "Bank of Cyprus",
        "company_name": "KYRASTEL ENTERPRISES LTD",
        "entry_type": "transaction",
        "description": "Registrar of companies fee reimbursement",
        "amount": 20,
        "currency": "EUR",
        "id": "20250721_BOC_143022",
        "date": "2025-07-21"
    }
    
    result = main(sample_data)
    print(result)