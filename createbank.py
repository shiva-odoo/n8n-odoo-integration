# import os
# import xmlrpc.client
# from datetime import datetime

# # Load .env only in development (when .env file exists)
# if os.path.exists('.env'):
#     try:
#         from dotenv import load_dotenv
#         load_dotenv()
#     except ImportError:
#         pass  # dotenv not installed, use system env vars

# def main(data):
#     """
#     Create bank journal entry in Odoo, creating bank and journal if needed
    
#     Expected data format:
#     {
#         # Bank Information (creates if not exists)
#         "bank_name": "Sample Bank Ltd",           # required
#         "bank_bic": "SAMBUS33XXX",               # optional
#         "bank_details": {                        # optional bank details
#             "street": "123 Banking Street",
#             "city": "New York", 
#             "zip": "10001",
#             "country_code": "US",
#             "phone": "+1-555-123-4567"
#         },
        
#         # Journal Entry Information
#         "journal_name": "Bank - Sample Bank",     # required - journal name
#         "journal_code": "BNK1",                  # required - journal code
#         "bank_account_code": "101200",           # required - bank account code
#         "bank_account_name": "Sample Bank Account", # required
        
#         # Transaction Details
#         "date": "2024-01-15",                    # required - YYYY-MM-DD format
#         "reference": "TXN001",                   # optional - transaction reference
#         "description": "Bank deposit",           # required - transaction description
#         "amount": 1000.00,                       # required - transaction amount
#         "transaction_type": "deposit",           # required - "deposit" or "withdrawal"
        
#         # Counterpart Account
#         "counterpart_account_code": "400000",    # required - other account code
#         "counterpart_account_name": "Income Account", # required if account doesn't exist
        
#         # Optional Details
#         "currency_code": "USD"                   # optional - defaults to company currency
#     }
#     """
    
#     # Validate required fields
#     required_fields = [
#         'bank_name', 'journal_name', 'journal_code', 'bank_account_code', 
#         'bank_account_name', 'date', 'description', 'amount', 'transaction_type',
#         'counterpart_account_code', 'counterpart_account_name'
#     ]
    
#     missing_fields = [field for field in required_fields if not data.get(field)]
#     if missing_fields:
#         return {
#             'success': False,
#             'error': f'Missing required fields: {", ".join(missing_fields)}'
#         }

#     # Validate transaction type
#     if data['transaction_type'] not in ['deposit', 'withdrawal']:
#         return {
#             'success': False,
#             'error': 'transaction_type must be either "deposit" or "withdrawal"'
#         }

#     # Connection details
#     url = os.getenv("ODOO_URL")
#     db = os.getenv("ODOO_DB")
#     username = os.getenv("ODOO_USERNAME")
#     password = os.getenv("ODOO_API_KEY")
    
#     if not all([url, db, username, password]):
#         return {
#             'success': False,
#             'error': 'Missing Odoo connection environment variables'
#         }
    
#     try:
#         # Initialize connection
#         common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
#         models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
#         # Authenticate
#         uid = common.authenticate(db, username, password, {})
#         if not uid:
#             return {
#                 'success': False,
#                 'error': 'Odoo authentication failed'
#             }
        
#         # Step 1: Create/Get Bank
#         bank_id = get_or_create_bank(models, db, uid, password, data)
#         if not bank_id:
#             return {
#                 'success': False,
#                 'error': 'Failed to create or find bank'
#             }
        
#         # Step 2: Create/Get Bank Account
#         bank_account_id = get_or_create_account(
#             models, db, uid, password,
#             data['bank_account_code'],
#             data['bank_account_name'],
#             'asset_cash'  # Account type for bank accounts
#         )
        
#         # Step 3: Create/Get Counterpart Account  
#         counterpart_account_id = get_or_create_account(
#             models, db, uid, password,
#             data['counterpart_account_code'],
#             data['counterpart_account_name'],
#             'income_other'  # Default account type
#         )
        
#         # Step 4: Create/Get Journal
#         journal_id = get_or_create_journal(
#             models, db, uid, password,
#             data['journal_name'],
#             data['journal_code'],
#             bank_account_id,
#             bank_id
#         )
        
#         # Step 5: Create Journal Entry
#         journal_entry_id = create_journal_entry(
#             models, db, uid, password,
#             journal_id,
#             bank_account_id,
#             counterpart_account_id,
#             data
#         )
        
#         if not journal_entry_id:
#             return {
#                 'success': False,
#                 'error': 'Failed to create journal entry'
#             }
        
#         # Get created entry details
#         entry_details = get_journal_entry_details(models, db, uid, password, journal_entry_id)
        
#         return {
#             'success': True,
#             'journal_entry_id': journal_entry_id,
#             'bank_id': bank_id,
#             'journal_id': journal_id,
#             'reference': data.get('reference', ''),
#             'amount': data['amount'],
#             'message': 'Bank journal entry created successfully',
#             'entry_details': entry_details
#         }
        
#     except xmlrpc.client.Fault as e:
#         return {
#             'success': False,
#             'error': f'Odoo API error: {str(e)}'
#         }
#     except Exception as e:
#         return {
#             'success': False,
#             'error': f'Unexpected error: {str(e)}'
#         }

# def get_or_create_bank(models, db, uid, password, data):
#     """Create or get existing bank"""
#     try:
#         # Check if bank exists
#         domain = [('name', '=', data['bank_name'])]
#         if data.get('bank_bic'):
#             domain = [('bic', '=', data['bank_bic'])]
            
#         bank_ids = models.execute_kw(
#             db, uid, password,
#             'res.bank', 'search',
#             [domain], {'limit': 1}
#         )
        
#         if bank_ids:
#             return bank_ids[0]
        
#         # Create new bank
#         bank_data = {
#             'name': data['bank_name'],
#             'active': True
#         }
        
#         if data.get('bank_bic'):
#             bank_data['bic'] = data['bank_bic']
            
#         # Add bank details if provided
#         bank_details = data.get('bank_details', {})
#         for field in ['street', 'city', 'zip', 'phone', 'email']:
#             if bank_details.get(field):
#                 bank_data[field] = bank_details[field]
        
#         # Handle country
#         if bank_details.get('country_code'):
#             country_id = get_country_id(models, db, uid, password, bank_details['country_code'])
#             if country_id:
#                 bank_data['country'] = country_id

#         # Handle state
#         if bank_details.get('state_code') and bank_details.get('country_code'):
#             state_id = get_state_id(models, db, uid, password, bank_details['state_code'], bank_details['country_code'])
#             if state_id:
#                 bank_data['state'] = state_id
        
#         bank_id = models.execute_kw(
#             db, uid, password,
#             'res.bank', 'create',
#             [bank_data]
#         )
        
#         return bank_id
        
#     except Exception as e:
#         print(f"Error creating bank: {e}")
#         return None

# def get_or_create_account(models, db, uid, password, account_code, account_name, account_type):
#     """Create or get chart of account"""
#     try:
#         # Check if account exists
#         account_ids = models.execute_kw(
#             db, uid, password,
#             'account.account', 'search',
#             [[('code', '=', account_code)]], {'limit': 1}
#         )
        
#         if account_ids:
#             return account_ids[0]
        
#         # Create new account
#         account_data = {
#             'code': account_code,
#             'name': account_name,
#             'account_type': account_type,
#         }
        
#         account_id = models.execute_kw(
#             db, uid, password,
#             'account.account', 'create',
#             [account_data]
#         )
        
#         return account_id
        
#     except Exception as e:
#         print(f"Error creating account: {e}")
#         return None

# def get_or_create_journal(models, db, uid, password, journal_name, journal_code, bank_account_id, bank_id):
#     """Create or get bank journal"""
#     try:
#         # Check if journal exists
#         journal_ids = models.execute_kw(
#             db, uid, password,
#             'account.journal', 'search',
#             [[('code', '=', journal_code)]], {'limit': 1}
#         )
        
#         if journal_ids:
#             return journal_ids[0]
        
#         # Create new journal
#         journal_data = {
#             'name': journal_name,
#             'code': journal_code,
#             'type': 'bank',
#             'default_account_id': bank_account_id,
#             'bank_id': bank_id,
#         }
        
#         journal_id = models.execute_kw(
#             db, uid, password,
#             'account.journal', 'create',
#             [journal_data]
#         )
        
#         return journal_id
        
#     except Exception as e:
#         print(f"Error creating journal: {e}")
#         return None

# def create_journal_entry(models, db, uid, password, journal_id, bank_account_id, counterpart_account_id, data):
#     """Create the actual journal entry without partner"""
#     try:
#         amount = float(data['amount'])
#         is_deposit = data['transaction_type'] == 'deposit'
        
#         # Prepare move lines
#         line_ids = []
        
#         # Bank account line
#         bank_line = {
#             'account_id': bank_account_id,
#             'name': data['description'],
#             'debit': amount if is_deposit else 0.0,
#             'credit': 0.0 if is_deposit else amount,
#         }
        
#         line_ids.append((0, 0, bank_line))
        
#         # Counterpart account line
#         counterpart_line = {
#             'account_id': counterpart_account_id,
#             'name': data['description'],
#             'debit': 0.0 if is_deposit else amount,
#             'credit': amount if is_deposit else 0.0,
#         }
        
#         line_ids.append((0, 0, counterpart_line))
        
#         # Create journal entry
#         move_data = {
#             'journal_id': journal_id,
#             'date': data['date'],
#             'ref': data.get('reference', data['description']),
#             'line_ids': line_ids,
#         }
        
#         move_id = models.execute_kw(
#             db, uid, password,
#             'account.move', 'create',
#             [move_data]
#         )
        
#         # Post the journal entry
#         models.execute_kw(
#             db, uid, password,
#             'account.move', 'action_post',
#             [[move_id]]
#         )
        
#         return move_id
        
#     except Exception as e:
#         print(f"Error creating journal entry: {e}")
#         return None

# def get_country_id(models, db, uid, password, country_code):
#     """Get country ID from country code"""
#     try:
#         country_ids = models.execute_kw(
#             db, uid, password,
#             'res.country', 'search',
#             [[('code', '=', country_code.upper())]], {'limit': 1}
#         )
#         return country_ids[0] if country_ids else None
#     except Exception:
#         return None

# def get_state_id(models, db, uid, password, state_code, country_code):
#     """Get state ID from state code and country"""
#     try:
#         country_id = get_country_id(models, db, uid, password, country_code)
#         if not country_id:
#             return None
            
#         state_ids = models.execute_kw(
#             db, uid, password,
#             'res.country.state', 'search',
#             [[('code', '=', state_code.upper()), ('country_id', '=', country_id)]], 
#             {'limit': 1}
#         )
#         return state_ids[0] if state_ids else None
#     except Exception:
#         return None

# def get_journal_entry_details(models, db, uid, password, move_id):
#     """Get details of created journal entry"""
#     try:
#         move_data = models.execute_kw(
#             db, uid, password,
#             'account.move', 'read',
#             [[move_id]], 
#             {'fields': ['name', 'date', 'ref', 'journal_id', 'state', 'amount_total']}
#         )
        
#         return move_data[0] if move_data else None
        
#     except Exception:
#         return None

# def create(data):
#     """Alias for main function to maintain compatibility"""
#     return main(data)

# # Example usage
# if __name__ == "__main__":
#     sample_data = {
#         "bank_name": "Sample Bank Ltd",
#         "bank_bic": "SAMBUS33XXX",
#         "bank_details": {
#             "street": "123 Banking Street",
#             "city": "New York",
#             "zip": "10001",
#             "country_code": "US",
#             "phone": "+1-555-123-4567"
#         },
#         "journal_name": "Bank - Sample Bank",
#         "journal_code": "BNK1",
#         "bank_account_code": "101200",
#         "bank_account_name": "Sample Bank Account",
#         "date": "2024-01-15",
#         "reference": "TXN001",
#         "description": "Customer deposit",
#         "amount": 1000.00,
#         "transaction_type": "deposit",
#         "counterpart_account_code": "400000",
#         "counterpart_account_name": "Sales Revenue"
#     }
    
#     result = main(sample_data)
#     print(result)


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
    Create bank journal entry in Odoo, creating bank and journal if needed
    
    Expected data format:
    {
        # Bank Information (creates if not exists)
        "bank_name": "Sample Bank Ltd",           # required
        "bank_bic": "SAMBUS33XXX",               # optional
        "bank_details": {                        # optional bank details
            "street": "123 Banking Street",
            "city": "New York", 
            "zip": "10001",
            "country_code": "US",
            "phone": "+1-555-123-4567"
        },
        
        # Journal Entry Information
        "journal_name": "Bank - Sample Bank",     # required - journal name
        "journal_code": "BNK1",                  # required - journal code
        "bank_account_code": "101200",           # required - bank account code
        "bank_account_name": "Sample Bank Account", # required
        
        # Transaction Details
        "date": "2024-01-15",                    # required - YYYY-MM-DD format
        "reference": "TXN001",                   # optional - transaction reference
        "description": "Bank deposit",           # required - transaction description
        "amount": 1000.00,                       # required - transaction amount
        "transaction_type": "deposit",           # required - "deposit" or "withdrawal"
        
        # Counterpart Account
        "counterpart_account_code": "400000",    # required - other account code
        "counterpart_account_name": "Income Account", # required if account doesn't exist
        
        # Optional Details
        "currency_code": "USD"                   # optional - defaults to company currency
    }
    """
    
    # Validate required fields
    required_fields = [
        'bank_name', 'journal_name', 'journal_code', 'bank_account_code', 
        'bank_account_name', 'date', 'description', 'amount', 'transaction_type',
        'counterpart_account_code', 'counterpart_account_name'
    ]
    
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        return {
            'success': False,
            'error': f'Missing required fields: {", ".join(missing_fields)}'
        }

    # Validate transaction type
    if data['transaction_type'] not in ['deposit', 'withdrawal']:
        return {
            'success': False,
            'error': 'transaction_type must be either "deposit" or "withdrawal"'
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
        print(f"Description: {data['description']}")
        print(f"Amount: {data['amount']}")
        print(f"Type: {data['transaction_type']}")
        print(f"Date: {data['date']}")
        print(f"Bank Account Code: {data['bank_account_code']}")
        print(f"Counterpart Code: {data['counterpart_account_code']}")
        
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
        
        # Step 1: Create/Get Bank
        bank_id = get_or_create_bank(models, db, uid, password, data)
        if not bank_id:
            return {
                'success': False,
                'error': 'Failed to create or find bank'
            }
        
        print(f"✅ Bank ID: {bank_id}")
        
        # Step 2: Create/Get Bank Account
        bank_account_id = get_or_create_account(
            models, db, uid, password,
            data['bank_account_code'],
            data['bank_account_name'],
            'asset_cash'  # Account type for bank accounts
        )
        
        if not bank_account_id:
            return {
                'success': False,
                'error': f'Failed to create bank account {data["bank_account_code"]}'
            }
        
        print(f"✅ Bank Account ID: {bank_account_id}")
        
        # Step 3: Create/Get Counterpart Account with smart type detection
        counterpart_account_type = get_smart_account_type(
            data['counterpart_account_code'], 
            data['transaction_type']
        )
        
        print(f"📋 Counterpart account type detected: {counterpart_account_type}")
        
        counterpart_account_id = get_or_create_account(
            models, db, uid, password,
            data['counterpart_account_code'],
            data['counterpart_account_name'],
            counterpart_account_type  # Use smart type detection
        )
        
        if not counterpart_account_id:
            return {
                'success': False,
                'error': f'Failed to create counterpart account {data["counterpart_account_code"]}'
            }
        
        print(f"✅ Counterpart Account ID: {counterpart_account_id}")
        
        # Step 4: Create/Get Journal
        journal_id = get_or_create_journal(
            models, db, uid, password,
            data['journal_name'],
            data['journal_code'],
            bank_account_id,
            bank_id
        )
        
        if not journal_id:
            return {
                'success': False,
                'error': f'Failed to create journal {data["journal_code"]}'
            }
        
        print(f"✅ Journal ID: {journal_id}")
        
        # Step 5: Create Journal Entry
        journal_entry_id = create_journal_entry(
            models, db, uid, password,
            journal_id,
            bank_account_id,
            counterpart_account_id,
            data
        )
        
        if not journal_entry_id:
            return {
                'success': False,
                'error': 'Failed to create journal entry'
            }
        
        print(f"✅ Journal Entry ID: {journal_entry_id}")
        
        # Get created entry details
        entry_details = get_journal_entry_details(models, db, uid, password, journal_entry_id)
        
        print(f"✅ Transaction completed successfully")
        
        return {
            'success': True,
            'journal_entry_id': journal_entry_id,
            'bank_id': bank_id,
            'journal_id': journal_id,
            'reference': data.get('reference', ''),
            'amount': data['amount'],
            'message': 'Bank journal entry created successfully',
            'entry_details': entry_details,
            'debug_info': {
                'bank_account_id': bank_account_id,
                'counterpart_account_id': counterpart_account_id,
                'counterpart_account_type': counterpart_account_type,
                'original_date': data.get('original_date'),
                'corrected_date': data['date']
            }
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

def get_smart_account_type(account_code, transaction_type):
    """Determine correct account type based on code and transaction type"""
    
    # Smart detection based on account code ranges
    if account_code.startswith('1'):      # 100000-199999 = Assets
        if account_code.startswith('101') or account_code.startswith('102'):
            return 'asset_cash'  # Bank and cash accounts
        else:
            return 'asset_current'  # Other current assets
    elif account_code.startswith('2'):    # 200000-299999 = Liabilities
        if account_code.startswith('201'):
            return 'liability_payable'  # Accounts payable
        else:
            return 'liability_current'  # Other current liabilities
    elif account_code.startswith('3'):    # 300000-399999 = Equity
        return 'equity'
    elif account_code.startswith('4'):    # 400000-499999 = Income
        return 'income_other'
    elif account_code.startswith('5'):    # 500000-599999 = Income (alternative)
        return 'income'
    elif account_code.startswith('6'):    # 600000-699999 = Expenses
        return 'expense'
    elif account_code.startswith('7'):    # 700000-799999 = Expenses (alternative)
        return 'expense'
    else:
        # Fallback based on transaction type
        print(f"⚠️  Unknown account code pattern {account_code}, using fallback logic")
        return 'income_other' if transaction_type == 'deposit' else 'expense'

def get_or_create_bank(models, db, uid, password, data):
    """Create or get existing bank"""
    try:
        # Check if bank exists
        domain = [('name', '=', data['bank_name'])]
        if data.get('bank_bic'):
            domain = [('bic', '=', data['bank_bic'])]
            
        bank_ids = models.execute_kw(
            db, uid, password,
            'res.bank', 'search',
            [domain], {'limit': 1}
        )
        
        if bank_ids:
            print(f"📋 Found existing bank: {data['bank_name']}")
            return bank_ids[0]
        
        # Create new bank
        bank_data = {
            'name': data['bank_name'],
            'active': True
        }
        
        if data.get('bank_bic'):
            bank_data['bic'] = data['bank_bic']
            
        # Add bank details if provided
        bank_details = data.get('bank_details', {})
        for field in ['street', 'city', 'zip', 'phone', 'email']:
            if bank_details.get(field):
                bank_data[field] = bank_details[field]
        
        # Handle country
        if bank_details.get('country_code'):
            country_id = get_country_id(models, db, uid, password, bank_details['country_code'])
            if country_id:
                bank_data['country'] = country_id

        # Handle state
        if bank_details.get('state_code') and bank_details.get('country_code'):
            state_id = get_state_id(models, db, uid, password, bank_details['state_code'], bank_details['country_code'])
            if state_id:
                bank_data['state'] = state_id
        
        bank_id = models.execute_kw(
            db, uid, password,
            'res.bank', 'create',
            [bank_data]
        )
        
        print(f"✅ Created new bank: {data['bank_name']}")
        return bank_id
        
    except Exception as e:
        print(f"❌ Error creating bank: {e}")
        return None

def get_or_create_account(models, db, uid, password, account_code, account_name, account_type):
    """Create or get chart of account with enhanced error handling"""
    try:
        print(f"📋 Looking for account: {account_code} ({account_name})")
        
        # Check if account exists
        account_ids = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('code', '=', account_code)]], {'limit': 1}
        )
        
        if account_ids:
            print(f"✅ Found existing account: {account_code}")
            return account_ids[0]
        
        # Create new account
        account_data = {
            'code': account_code,
            'name': account_name,
            'account_type': account_type,
        }
        
        print(f"📝 Creating account: {account_code} with type: {account_type}")
        
        account_id = models.execute_kw(
            db, uid, password,
            'account.account', 'create',
            [account_data]
        )
        
        print(f"✅ Created new account: {account_code}")
        return account_id
        
    except xmlrpc.client.Fault as e:
        print(f"❌ Odoo error creating account {account_code}: {e}")
        return None
    except Exception as e:
        print(f"❌ Error creating account {account_code}: {e}")
        return None

def get_or_create_journal(models, db, uid, password, journal_name, journal_code, bank_account_id, bank_id):
    """Create or get bank journal with enhanced error handling"""
    try:
        print(f"📋 Looking for journal: {journal_code}")
        
        # Check if journal exists
        journal_ids = models.execute_kw(
            db, uid, password,
            'account.journal', 'search',
            [[('code', '=', journal_code)]], {'limit': 1}
        )
        
        if journal_ids:
            print(f"✅ Found existing journal: {journal_code}")
            return journal_ids[0]
        
        # Create new journal
        journal_data = {
            'name': journal_name,
            'code': journal_code,
            'type': 'bank',
            'default_account_id': bank_account_id,
            'bank_id': bank_id,
        }
        
        print(f"📝 Creating journal: {journal_code}")
        
        journal_id = models.execute_kw(
            db, uid, password,
            'account.journal', 'create',
            [journal_data]
        )
        
        print(f"✅ Created new journal: {journal_code}")
        return journal_id
        
    except xmlrpc.client.Fault as e:
        print(f"❌ Odoo error creating journal {journal_code}: {e}")
        return None
    except Exception as e:
        print(f"❌ Error creating journal {journal_code}: {e}")
        return None

def create_journal_entry(models, db, uid, password, journal_id, bank_account_id, counterpart_account_id, data):
    """Create the actual journal entry with enhanced validation and logging"""
    try:
        print(f"📝 Creating journal entry...")
        print(f"   Journal ID: {journal_id}")
        print(f"   Bank Account ID: {bank_account_id}")
        print(f"   Counterpart Account ID: {counterpart_account_id}")
        
        amount = float(data['amount'])
        is_deposit = data['transaction_type'] == 'deposit'
        
        print(f"   Amount: {amount}")
        print(f"   Is Deposit: {is_deposit}")
        
        # Validate accounts exist before creating entry
        for account_id, name in [(bank_account_id, 'bank'), (counterpart_account_id, 'counterpart')]:
            if not account_id:
                raise Exception(f"Missing {name} account ID")
                
            account_exists = models.execute_kw(
                db, uid, password,
                'account.account', 'search_count',
                [[('id', '=', account_id)]]
            )
            if not account_exists:
                raise Exception(f"{name.title()} account ID {account_id} does not exist")
        
        # Prepare move lines
        line_ids = []
        
        # Bank account line
        bank_line = {
            'account_id': bank_account_id,
            'name': data['description'],
            'debit': amount if is_deposit else 0.0,
            'credit': 0.0 if is_deposit else amount,
        }
        
        line_ids.append((0, 0, bank_line))
        
        # Counterpart account line
        counterpart_line = {
            'account_id': counterpart_account_id,
            'name': data['description'],
            'debit': 0.0 if is_deposit else amount,
            'credit': amount if is_deposit else 0.0,
        }
        
        line_ids.append((0, 0, counterpart_line))
        
        print(f"   Debit/Credit lines prepared:")
        print(f"     Bank: Debit={bank_line['debit']}, Credit={bank_line['credit']}")
        print(f"     Counterpart: Debit={counterpart_line['debit']}, Credit={counterpart_line['credit']}")
        
        # Create journal entry
        move_data = {
            'journal_id': journal_id,
            'date': data['date'],
            'ref': data.get('reference', data['description']),
            'line_ids': line_ids,
        }
        
        print(f"📝 Creating move with data: {move_data}")
        
        move_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [move_data]
        )
        
        if not move_id:
            raise Exception("Failed to create account move")
        
        print(f"✅ Move created with ID: {move_id}")
        
        # Post the journal entry
        print(f"📝 Posting journal entry...")
        models.execute_kw(
            db, uid, password,
            'account.move', 'action_post',
            [[move_id]]
        )
        
        print(f"✅ Journal entry posted successfully")
        return move_id
        
    except xmlrpc.client.Fault as e:
        print(f"❌ Odoo error creating journal entry: {e}")
        return None
    except Exception as e:
        print(f"❌ Error creating journal entry: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_country_id(models, db, uid, password, country_code):
    """Get country ID from country code"""
    try:
        country_ids = models.execute_kw(
            db, uid, password,
            'res.country', 'search',
            [[('code', '=', country_code.upper())]], {'limit': 1}
        )
        return country_ids[0] if country_ids else None
    except Exception:
        return None

def get_state_id(models, db, uid, password, state_code, country_code):
    """Get state ID from state code and country"""
    try:
        country_id = get_country_id(models, db, uid, password, country_code)
        if not country_id:
            return None
            
        state_ids = models.execute_kw(
            db, uid, password,
            'res.country.state', 'search',
            [[('code', '=', state_code.upper()), ('country_id', '=', country_id)]], 
            {'limit': 1}
        )
        return state_ids[0] if state_ids else None
    except Exception:
        return None

def get_journal_entry_details(models, db, uid, password, move_id):
    """Get details of created journal entry"""
    try:
        move_data = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[move_id]], 
            {'fields': ['name', 'date', 'ref', 'journal_id', 'state', 'amount_total']}
        )
        
        return move_data[0] if move_data else None
        
    except Exception:
        return None

def create(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

# Example usage
if __name__ == "__main__":
    sample_data = {
        "bank_name": "Sample Bank Ltd",
        "bank_bic": "SAMBUS33XXX",
        "bank_details": {
            "street": "123 Banking Street",
            "city": "New York",
            "zip": "10001",
            "country_code": "US",
            "phone": "+1-555-123-4567"
        },
        "journal_name": "Bank - Sample Bank",
        "journal_code": "BNK1",
        "bank_account_code": "101200",
        "bank_account_name": "Sample Bank Account",
        "date": "2024-01-15",
        "reference": "TXN001",
        "description": "Customer deposit",
        "amount": 1000.00,
        "transaction_type": "deposit",
        "counterpart_account_code": "400000",
        "counterpart_account_name": "Sales Revenue"
    }
    
    result = main(sample_data)
    print(result)