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
        
        # Step 1: Create/Get Bank
        bank_id = get_or_create_bank(models, db, uid, password, data)
        if not bank_id:
            return {
                'success': False,
                'error': 'Failed to create or find bank'
            }
        
        # Step 2: Create/Get Bank Account
        bank_account_id = get_or_create_account(
            models, db, uid, password,
            data['bank_account_code'],
            data['bank_account_name'],
            'asset_cash'  # Account type for bank accounts
        )
        
        # Step 3: Create/Get Counterpart Account  
        counterpart_account_id = get_or_create_account(
            models, db, uid, password,
            data['counterpart_account_code'],
            data['counterpart_account_name'],
            'income_other'  # Default account type
        )
        
        # Step 4: Create/Get Journal
        journal_id = get_or_create_journal(
            models, db, uid, password,
            data['journal_name'],
            data['journal_code'],
            bank_account_id,
            bank_id
        )
        
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
        
        # Get created entry details
        entry_details = get_journal_entry_details(models, db, uid, password, journal_entry_id)
        
        return {
            'success': True,
            'journal_entry_id': journal_entry_id,
            'bank_id': bank_id,
            'journal_id': journal_id,
            'reference': data.get('reference', ''),
            'amount': data['amount'],
            'message': 'Bank journal entry created successfully',
            'entry_details': entry_details
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
        
        return bank_id
        
    except Exception as e:
        print(f"Error creating bank: {e}")
        return None

def get_or_create_account(models, db, uid, password, account_code, account_name, account_type):
    """Create or get chart of account"""
    try:
        # Check if account exists
        account_ids = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('code', '=', account_code)]], {'limit': 1}
        )
        
        if account_ids:
            return account_ids[0]
        
        # Create new account
        account_data = {
            'code': account_code,
            'name': account_name,
            'account_type': account_type,
        }
        
        account_id = models.execute_kw(
            db, uid, password,
            'account.account', 'create',
            [account_data]
        )
        
        return account_id
        
    except Exception as e:
        print(f"Error creating account: {e}")
        return None

def get_or_create_journal(models, db, uid, password, journal_name, journal_code, bank_account_id, bank_id):
    """Create or get bank journal"""
    try:
        # Check if journal exists
        journal_ids = models.execute_kw(
            db, uid, password,
            'account.journal', 'search',
            [[('code', '=', journal_code)]], {'limit': 1}
        )
        
        if journal_ids:
            return journal_ids[0]
        
        # Create new journal
        journal_data = {
            'name': journal_name,
            'code': journal_code,
            'type': 'bank',
            'default_account_id': bank_account_id,
            'bank_id': bank_id,
        }
        
        journal_id = models.execute_kw(
            db, uid, password,
            'account.journal', 'create',
            [journal_data]
        )
        
        return journal_id
        
    except Exception as e:
        print(f"Error creating journal: {e}")
        return None

def create_journal_entry(models, db, uid, password, journal_id, bank_account_id, counterpart_account_id, data):
    """Create the actual journal entry without partner"""
    try:
        amount = float(data['amount'])
        is_deposit = data['transaction_type'] == 'deposit'
        
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
        
        # Create journal entry
        move_data = {
            'journal_id': journal_id,
            'date': data['date'],
            'ref': data.get('reference', data['description']),
            'line_ids': line_ids,
        }
        
        move_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [move_data]
        )
        
        # Post the journal entry
        models.execute_kw(
            db, uid, password,
            'account.move', 'action_post',
            [[move_id]]
        )
        
        return move_id
        
    except Exception as e:
        print(f"Error creating journal entry: {e}")
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