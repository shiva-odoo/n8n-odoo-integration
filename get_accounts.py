import xmlrpc.client
import os
import json

# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def get_accounts():
    """Get list of all chart of accounts"""
    
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
            return {'success': False, 'error': 'Authentication failed'}
        
        # Get accounts - only active ones
        accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [[('deprecated', '=', False)]], 
            {
                'fields': ['id', 'code', 'name', 'account_type', 'company_id', 'currency_id'],
                'order': 'code'
            }
        )
        
        return {
            'success': True,
            'accounts': accounts,
            'count': len(accounts)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def get_journals():
    """Get list of all journals"""
    
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
            return {'success': False, 'error': 'Authentication failed'}
        
        # Get journals
        journals = models.execute_kw(
            db, uid, password,
            'account.journal', 'search_read',
            [[]], 
            {
                'fields': ['id', 'name', 'code', 'type', 'company_id'],
                'order': 'name'
            }
        )
        
        return {
            'success': True,
            'journals': journals,
            'count': len(journals)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def find_common_accounts():
    """Find commonly used account types for journal entries"""
    
    accounts_result = get_accounts()
    if not accounts_result['success']:
        return accounts_result
    
    accounts = accounts_result['accounts']
    
    # Common account types for journal entries
    common_types = {
        'expense': [],
        'asset_cash': [],
        'asset_current': [],
        'liability_current': [],
        'equity': [],
        'income': []
    }
    
    for account in accounts:
        account_type = account.get('account_type', '').lower()
        
        if 'expense' in account_type:
            common_types['expense'].append(account)
        elif 'asset' in account_type and ('cash' in account_type or 'bank' in account_type):
            common_types['asset_cash'].append(account)
        elif 'asset' in account_type and 'current' in account_type:
            common_types['asset_current'].append(account)
        elif 'liability' in account_type and 'current' in account_type:
            common_types['liability_current'].append(account)
        elif 'equity' in account_type:
            common_types['equity'].append(account)
        elif 'income' in account_type:
            common_types['income'].append(account)
    
    return {
        'success': True,
        'common_accounts': common_types,
        'total_accounts': len(accounts),
        'suggested_for_journal_entry': {
            'description': 'For a typical journal entry (like rent payment):',
            'debit_accounts': 'Use expense accounts for costs/expenses',
            'credit_accounts': 'Use cash/bank accounts for payments'
        }
    }

# Main execution
if __name__ == "__main__":
    print("=== ODOO ACCOUNTS FINDER ===\n")
    
    print("1. Getting all accounts...")
    accounts_result = get_accounts()
    
    if accounts_result['success']:
        print(f"✅ Found {accounts_result['count']} accounts")
        
        # Show first few accounts as example
        print("\n📋 Sample accounts:")
        for account in accounts_result['accounts'][:10]:
            company_name = account['company_id'][1] if account['company_id'] else 'No Company'
            print(f"ID: {account['id']:4} | Code: {account['code']:10} | {account['name']:30} | Type: {account['account_type']:15} | Company: {company_name}")
        
        if len(accounts_result['accounts']) > 10:
            print(f"... and {len(accounts_result['accounts']) - 10} more accounts")
    else:
        print(f"❌ Failed to get accounts: {accounts_result['error']}")
        exit(1)
    
    print("\n" + "="*80)
    print("2. Getting journals...")
    journals_result = get_journals()
    
    if journals_result['success']:
        print(f"✅ Found {journals_result['count']} journals")
        print("\n📋 Available journals:")
        for journal in journals_result['journals']:
            company_name = journal['company_id'][1] if journal['company_id'] else 'No Company'
            print(f"ID: {journal['id']:3} | Code: {journal['code']:6} | Type: {journal['type']:12} | {journal['name']:25} | Company: {company_name}")
    else:
        print(f"❌ Failed to get journals: {journals_result['error']}")
    
    print("\n" + "="*80)
    print("3. Finding common account types...")
    common_result = find_common_accounts()
    
    if common_result['success']:
        print("✅ Account categorization complete")
        
        print("\n💡 SUGGESTED ACCOUNTS FOR JOURNAL ENTRIES:")
        print("\nFor EXPENSE (Debit side - things you pay for):")
        for account in common_result['common_accounts']['expense'][:5]:
            print(f"   ID: {account['id']:4} | {account['code']:10} | {account['name']}")
        
        print("\nFor CASH/BANK (Credit side - where money comes from):")
        for account in common_result['common_accounts']['asset_cash'][:5]:
            print(f"   ID: {account['id']:4} | {account['code']:10} | {account['name']}")
        
        if not common_result['common_accounts']['asset_cash']:
            print("   (Looking in current assets...)")
            for account in common_result['common_accounts']['asset_current'][:3]:
                if 'cash' in account['name'].lower() or 'bank' in account['name'].lower():
                    print(f"   ID: {account['id']:4} | {account['code']:10} | {account['name']}")
        
        print(f"\n📊 Summary:")
        print(f"   Total accounts: {common_result['total_accounts']}")
        print(f"   Expense accounts: {len(common_result['common_accounts']['expense'])}")
        print(f"   Cash/Bank accounts: {len(common_result['common_accounts']['asset_cash'])}")
        print(f"   Current asset accounts: {len(common_result['common_accounts']['asset_current'])}")
        
        # Save results to file
        with open('odoo_accounts.json', 'w') as f:
            json.dump({
                'accounts': accounts_result['accounts'],
                'journals': journals_result.get('journals', []),
                'common_accounts': common_result['common_accounts']
            }, f, indent=2)
        print(f"\n💾 Full results saved to 'odoo_accounts.json'")
        
        # Suggest specific accounts for the journal entry
        print(f"\n🎯 FOR YOUR JOURNAL ENTRY, TRY THESE ACCOUNT IDs:")
        
        expense_accounts = common_result['common_accounts']['expense']
        cash_accounts = common_result['common_accounts']['asset_cash']
        current_assets = common_result['common_accounts']['asset_current']
        
        if expense_accounts:
            print(f"   Debit (Office Rent): {expense_accounts[0]['id']} - {expense_accounts[0]['name']}")
        
        if cash_accounts:
            print(f"   Credit (Cash Payment): {cash_accounts[0]['id']} - {cash_accounts[0]['name']}")
        elif current_assets:
            # Look for cash/bank in current assets
            for account in current_assets:
                if any(word in account['name'].lower() for word in ['cash', 'bank', 'checking', 'savings']):
                    print(f"   Credit (Cash Payment): {account['id']} - {account['name']}")
                    break
        
    else:
        print(f"❌ Failed to categorize accounts: {common_result['error']}")
    
    print("\n" + "="*80)
    print("🔧 Copy the suggested account IDs above into your journal entry request!")