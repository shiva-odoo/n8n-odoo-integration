import os
import xmlrpc.client
from datetime import datetime
import hashlib
import time

# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def main(data):
    """
    Create multiple bank transaction entries in Odoo using flexible line items structure
    
    Expected data format:
    {
        "transactions": [
            {
                "company_id": 1,
                "date": "2025-07-20",
                "ref": "BOC Transfer 09444",
                "narration": "New Share Capital of Kyrastel Investments Ltd - Bank Credit Advice 34",
                "partner": "New Share Capital of Kyrastel Investments Ltd",
                "line_items": [
                    {
                        "name": "Bank of Cyprus",
                        "debit": 15000.00,
                        "credit": 0.00
                    },
                    {
                        "name": "Share Capital",
                        "debit": 0.00,
                        "credit": 15000.00
                    }
                ]
            },
            {
                "company_id": 1,
                "date": "2025-07-21",
                "ref": "BOC Transfer 09445",
                "narration": "Additional investment from partner",
                "partner": "Investment Partner Ltd",
                "line_items": [
                    {
                        "name": "Bank of Cyprus",
                        "debit": 10000.00,
                        "credit": 0.00
                    },
                    {
                        "name": "Share Capital",
                        "debit": 0.00,
                        "credit": 10000.00
                    }
                ]
            }
        ]
    }
    """
    
    # Validate input structure
    if not isinstance(data, dict) or 'transactions' not in data:
        return {
            'success': False,
            'error': 'Input must be a dictionary with "transactions" array'
        }
    
    if not isinstance(data['transactions'], list) or len(data['transactions']) == 0:
        return {
            'success': False,
            'error': 'transactions must be a non-empty array'
        }
    
    # Process each transaction
    results = []
    successful_transactions = 0
    failed_transactions = 0
    
    print(f"=== PROCESSING {len(data['transactions'])} TRANSACTIONS ===")
    
    for i, transaction_data in enumerate(data['transactions']):
        print(f"\n--- Processing Transaction {i+1}/{len(data['transactions'])} ---")
        
        # Process single transaction
        result = process_single_transaction(transaction_data, i+1)
        results.append(result)
        
        if result['success']:
            successful_transactions += 1
            print(f"✅ Transaction {i+1} completed successfully")
        else:
            failed_transactions += 1
            print(f"❌ Transaction {i+1} failed: {result['error']}")
    
    # Calculate success rate
    total_transactions = len(data['transactions'])
    success_rate = (successful_transactions / total_transactions * 100) if total_transactions > 0 else 0
    
    print(f"\n=== BATCH PROCESSING SUMMARY ===")
    print(f"Total Transactions: {total_transactions}")
    print(f"Successful: {successful_transactions}")
    print(f"Failed: {failed_transactions}")
    print(f"Success Rate: {success_rate:.1f}%")
    
    return {
        'success': failed_transactions == 0,  # Only true if all transactions succeeded
        'batch_summary': {
            'total_transactions': total_transactions,
            'successful_transactions': successful_transactions,
            'failed_transactions': failed_transactions,
            'success_rate': f"{success_rate:.1f}%"
        },
        'transaction_results': results,
        'message': f'Processed {total_transactions} transactions: {successful_transactions} successful, {failed_transactions} failed'
    }

def process_single_transaction(transaction_data, transaction_index):
    """
    Process a single transaction and create journal entry
    """
    try:
        # Validate required fields for this transaction
        required_fields = ['company_id', 'date', 'ref', 'narration', 'line_items']
        
        missing_fields = [field for field in required_fields if not transaction_data.get(field)]
        if missing_fields:
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': f'Missing required fields: {", ".join(missing_fields)}',
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }

        # Validate line_items
        if not isinstance(transaction_data['line_items'], list) or len(transaction_data['line_items']) < 2:
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': 'line_items must be a list with at least 2 entries',
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }

        # Validate each line item
        for i, line in enumerate(transaction_data['line_items']):
            required_line_fields = ['name', 'debit', 'credit']
            missing_line_fields = [field for field in required_line_fields if field not in line]
            if missing_line_fields:
                return {
                    'success': False,
                    'transaction_index': transaction_index,
                    'error': f'Line item {i+1} missing fields: {", ".join(missing_line_fields)}',
                    'transaction_ref': transaction_data.get('ref', 'Unknown')
                }
            
            # Validate debit/credit are numbers
            try:
                float(line['debit'])
                float(line['credit'])
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'transaction_index': transaction_index,
                    'error': f'Line item {i+1} debit/credit must be valid numbers',
                    'transaction_ref': transaction_data.get('ref', 'Unknown')
                }

        # Validate company_id is a number
        try:
            company_id = int(transaction_data['company_id'])
        except (ValueError, TypeError):
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': 'company_id must be a valid integer',
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }

        # Validate that debits equal credits
        total_debits = sum(float(line['debit']) for line in transaction_data['line_items'])
        total_credits = sum(float(line['credit']) for line in transaction_data['line_items'])
        
        if abs(total_debits - total_credits) > 0.01:  # Allow for small rounding differences
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': f'Debits ({total_debits}) must equal credits ({total_credits})',
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }

        # STEP 1: Store original date for comparison and fix future dates
        original_date = transaction_data['date']
        transaction_data['date'] = validate_and_fix_date(transaction_data['date'])
        date_was_modified = original_date != transaction_data['date']

        # Connection details
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB")
        username = os.getenv("ODOO_USERNAME")
        password = os.getenv("ODOO_API_KEY")
        
        if not all([url, db, username, password]):
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': 'Missing Odoo connection environment variables',
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }
        
        print(f"Company ID: {company_id}")
        print(f"Date: {transaction_data['date']}")
        print(f"Reference: {transaction_data['ref']}")
        print(f"Narration: {transaction_data['narration']}")
        print(f"Partner: {transaction_data.get('partner', 'None')}")
        print(f"Line Items: {len(transaction_data['line_items'])}")
        
        # Initialize connection
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Authenticate
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': 'Odoo authentication failed',
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }
        
        print("✅ Odoo authentication successful")
        
        # Step 1: Verify company exists and get its details
        company_details = verify_company_exists(models, db, uid, password, company_id)
        if not company_details:
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': f'Company with ID {company_id} not found',
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }
        
        print(f"✅ Found Company: {company_details['name']}")
        
        # Update context to work with specific company
        context = {'allowed_company_ids': [company_id]}
        
        # Step 2: Check for duplicate transaction by reference
        duplicate_check = check_for_duplicate_by_ref(
            models, db, uid, password, transaction_data['ref'], company_id, context
        )
        
        if duplicate_check['is_duplicate']:
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': 'Duplicate transaction',
                'message': f'Transaction with reference "{transaction_data["ref"]}" already exists',
                'existing_entry_id': duplicate_check['existing_entry_id'],
                'company_id': company_id,
                'company_name': company_details['name'],
                'duplicate_details': duplicate_check,
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }
        
        print("✅ No duplicate found, proceeding with transaction creation")
        
        # Step 3: Handle partner information
        partner_id = None
        partner_info = None
        
        if transaction_data.get('partner'):
            partner_result = find_or_create_partner(models, db, uid, password, transaction_data['partner'], context)
            if partner_result:
                partner_id = partner_result['id']
                partner_info = partner_result
                print(f"✅ Partner resolved: {partner_info['name']} (ID: {partner_id})")
            else:
                return {
                    'success': False,
                    'transaction_index': transaction_index,
                    'error': f'Failed to find or create partner: {transaction_data["partner"]}',
                    'transaction_ref': transaction_data.get('ref', 'Unknown')
                }
        
        # Step 4: Pre-create all accounts first (batch creation)
        resolved_line_items = []
        created_accounts = []
        
        # First pass: Create all accounts that don't exist
        for i, line_item in enumerate(transaction_data['line_items']):
            account_result = find_or_create_account_with_retry(models, db, uid, password, line_item['name'], context)
            
            if not account_result:
                return {
                    'success': False,
                    'transaction_index': transaction_index,
                    'error': f'Could not find or create account for: "{line_item["name"]}"',
                    'transaction_ref': transaction_data.get('ref', 'Unknown')
                }
            
            account_id = account_result['id']
            if account_result.get('created'):
                created_accounts.append(account_result)
            
            resolved_line = {
                'account_id': account_id,
                'name': transaction_data['narration'],  # Use narration as line description
                'debit': float(line_item['debit']),
                'credit': float(line_item['credit']),
            }
            
            # Add partner to each line if available
            if partner_id:
                resolved_line['partner_id'] = partner_id
            
            resolved_line_items.append(resolved_line)
            
            status = "created" if account_result.get('created') else "found"
            print(f"✅ Line {i+1}: {line_item['name']} -> Account ID {account_id} ({status})")
        
        # If we created any accounts, wait and refresh cache
        if created_accounts:
            print(f"⏳ Created {len(created_accounts)} new accounts, waiting for database sync...")
            time.sleep(1)  # Brief wait for database consistency
            
            # Force cache refresh by doing a simple search
            models.execute_kw(
                db, uid, password,
                'account.account', 'search',
                [[('id', 'in', [acc['id'] for acc in created_accounts])]], 
                {'limit': len(created_accounts), 'context': context}
            )
            print("✅ Account cache refreshed")
        
        # Step 5: Get default journal (or determine from line items)
        journal_id = get_default_journal_for_transaction(models, db, uid, password, transaction_data, context)
        
        if not journal_id:
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': 'Could not find appropriate journal',
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }
        
        # Step 6: Get journal details including code
        journal_details = get_journal_details(models, db, uid, password, journal_id, context)
        if not journal_details:
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': 'Could not retrieve journal details',
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }
        
        print(f"✅ Using Journal: {journal_details['name']} (Code: {journal_details['code']})")
        
        # Step 7: Create Journal Entry with retry mechanism
        journal_entry_id = create_journal_entry_flexible_with_retry(
            models, db, uid, password,
            journal_id,
            resolved_line_items,
            transaction_data,
            partner_id,
            context
        )
        
        if not journal_entry_id:
            return {
                'success': False,
                'transaction_index': transaction_index,
                'error': 'Failed to create journal entry',
                'transaction_ref': transaction_data.get('ref', 'Unknown')
            }
        
        print(f"✅ Journal Entry ID: {journal_entry_id}")
        print(f"✅ Transaction completed successfully")
        
        # Step 8: Prepare enhanced return response
        return {
            'success': True,
            'transaction_index': transaction_index,
            'journal_entry_id': journal_entry_id,
            'date': transaction_data['date'],
            'original_date': original_date,
            'date_was_modified': date_was_modified,
            'company_id': company_id,
            'company_name': company_details['name'],
            'journal_id': journal_id,
            'journal_code': journal_details['code'],
            'journal_name': journal_details['name'],
            'journal_type': journal_details['type'],
            'reference': transaction_data['ref'],
            'description': transaction_data['narration'],
            'partner': partner_info,
            'total_amount': total_debits,
            'line_count': len(transaction_data['line_items']),
            'created_accounts': created_accounts,
            'line_items_processed': [
                {
                    'account_name': transaction_data['line_items'][i]['name'],
                    'account_id': resolved_line_items[i]['account_id'],
                    'debit': resolved_line_items[i]['debit'],
                    'credit': resolved_line_items[i]['credit'],
                    'partner_id': partner_id
                }
                for i in range(len(transaction_data['line_items']))
            ],
            'message': 'Flexible bank transaction entry created successfully'
        }
        
    except xmlrpc.client.Fault as e:
        error_msg = f'Odoo API error: {str(e)}'
        print(f"❌ {error_msg}")
        return {
            'success': False,
            'transaction_index': transaction_index,
            'error': error_msg,
            'transaction_ref': transaction_data.get('ref', 'Unknown')
        }
    except Exception as e:
        error_msg = f'Unexpected error: {str(e)}'
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'transaction_index': transaction_index,
            'error': error_msg,
            'transaction_ref': transaction_data.get('ref', 'Unknown')
        }

def find_or_create_account_with_retry(models, db, uid, password, account_name, context, max_retries=3):
    """
    Find existing account by name/code or create new one with retry mechanism
    Returns account details including ID and creation status
    """
    for attempt in range(max_retries):
        try:
            result = find_or_create_account(models, db, uid, password, account_name, context)
            if result:
                return result
            
            if attempt < max_retries - 1:
                print(f"⚠️  Attempt {attempt + 1} failed for account '{account_name}', retrying...")
                time.sleep(0.5)  # Brief wait before retry
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️  Attempt {attempt + 1} failed with error: {e}, retrying...")
                time.sleep(0.5)
            else:
                raise e
    
    return None

def find_or_create_account(models, db, uid, password, account_name, context):
    """
    Find existing account by name/code or create new one
    Returns account details including ID and creation status
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
                [account_ids, ['name', 'code', 'account_type']], 
                {'context': context}
            )
            account = account_details[0]
            print(f"✅ Exact name match: {account['name']} ({account['code']})")
            return {
                'id': account_ids[0],
                'name': account['name'],
                'code': account['code'],
                'account_type': account['account_type'],
                'created': False
            }
        
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
                [account_ids, ['name', 'code', 'account_type']], 
                {'context': context}
            )
            account = account_details[0]
            print(f"✅ Exact code match: {account['name']} ({account['code']})")
            return {
                'id': account_ids[0],
                'name': account['name'],
                'code': account['code'],
                'account_type': account['account_type'],
                'created': False
            }
        
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
                [account_ids, ['name', 'code', 'account_type']], 
                {'context': context}
            )
            account = account_details[0]
            print(f"✅ Partial name match: {account['name']} ({account['code']})")
            return {
                'id': account_ids[0],
                'name': account['name'],
                'code': account['code'],
                'account_type': account['account_type'],
                'created': False
            }
        
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
                            [account_ids, ['name', 'code', 'account_type']], 
                            {'context': context}
                        )
                        account = account_details[0]
                        print(f"✅ Keyword match: {account['name']} ({account['code']})")
                        return {
                            'id': account_ids[0],
                            'name': account['name'],
                            'code': account['code'],
                            'account_type': account['account_type'],
                            'created': False
                        }
        
        # Account not found, create new one
        print(f"📝 Creating new account: {account_name}")
        return create_new_account_with_verification(models, db, uid, password, account_name, context)
        
    except Exception as e:
        print(f"❌ Error finding/creating account '{account_name}': {e}")
        import traceback
        traceback.print_exc()
        return None

def create_new_account_with_verification(models, db, uid, password, account_name, context):
    """
    Create a new account with verification that it was successfully created
    """
    try:
        # Determine account type and code based on name patterns
        account_type, account_code = determine_account_type_and_code(models, db, uid, password, account_name, context)
        
        # Prepare account data
        account_data = {
            'name': account_name,
            'code': account_code,
            'account_type': account_type,
            'reconcile': False,  # Default to False, can be True for receivables/payables
        }
        
        # Set reconcile to True for specific account types
        if account_type in ['asset_receivable', 'liability_payable']:
            account_data['reconcile'] = True
        
        print(f"📝 Creating account with data: {account_data}")
        
        # Create the account with explicit context
        create_context = context.copy()
        create_context.update({
            'check_move_validity': False,  # Skip some validations during creation
            'force_company': context.get('allowed_company_ids', [1])[0] if context.get('allowed_company_ids') else 1
        })
        
        new_account_id = models.execute_kw(
            db, uid, password,
            'account.account', 'create',
            [account_data], 
            {'context': create_context}
        )
        
        if not new_account_id:
            print(f"❌ Failed to create account: {account_name}")
            return None
        
        print(f"✅ Account created with ID: {new_account_id}")
        
        # Verify the account was created by reading it back
        max_verification_attempts = 3
        for attempt in range(max_verification_attempts):
            try:
                verification_context = context.copy()
                account_details = models.execute_kw(
                    db, uid, password,
                    'account.account', 'read',
                    [[new_account_id], ['id', 'name', 'code', 'account_type']], 
                    {'context': verification_context}
                )
                
                if account_details:
                    account = account_details[0]
                    print(f"✅ Account verified: {account['name']} (ID: {new_account_id}, Code: {account['code']}, Type: {account['account_type']})")
                    return {
                        'id': new_account_id,
                        'name': account['name'],
                        'code': account['code'],
                        'account_type': account['account_type'],
                        'created': True
                    }
                else:
                    if attempt < max_verification_attempts - 1:
                        print(f"⚠️  Account verification attempt {attempt + 1} failed, retrying...")
                        time.sleep(0.3)
                    else:
                        print(f"❌ Account verification failed after {max_verification_attempts} attempts")
                        
            except Exception as verify_error:
                if attempt < max_verification_attempts - 1:
                    print(f"⚠️  Account verification error on attempt {attempt + 1}: {verify_error}, retrying...")
                    time.sleep(0.3)
                else:
                    print(f"❌ Account verification failed with error: {verify_error}")
        
        # If verification failed but creation succeeded, return basic info
        print(f"⚠️  Using account without full verification")
        return {
            'id': new_account_id,
            'name': account_name,
            'code': account_code,
            'account_type': account_type,
            'created': True
        }
            
    except Exception as e:
        print(f"❌ Error creating account '{account_name}': {e}")
        import traceback
        traceback.print_exc()
        return None

def create_journal_entry_flexible_with_retry(models, db, uid, password, journal_id, line_items, data, partner_id, context, max_retries=3):
    """Create journal entry with retry mechanism for account availability issues"""
    
    for attempt in range(max_retries):
        try:
            return create_journal_entry_flexible(models, db, uid, password, journal_id, line_items, data, partner_id, context)
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Check if it's an account-related error
            if any(keyword in error_str for keyword in ['account', 'not found', 'invalid', 'missing']):
                if attempt < max_retries - 1:
                    print(f"⚠️  Journal entry creation attempt {attempt + 1} failed (account issue), retrying...")
                    time.sleep(1)  # Longer wait for account issues
                    
                    # Refresh account cache by searching for all used accounts
                    account_ids = [line['account_id'] for line in line_items]
                    models.execute_kw(
                        db, uid, password,
                        'account.account', 'search',
                        [[('id', 'in', account_ids)]], 
                        {'context': context}
                    )
                    print("✅ Account cache refreshed before retry")
                    continue
            
            # If not an account error or final attempt, re-raise
            if attempt == max_retries - 1:
                raise e
            else:
                print(f"⚠️  Journal entry creation attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(0.5)
    
    return None

def determine_account_type_and_code(models, db, uid, password, account_name, context):
    """
    Intelligently determine account type and generate unique code based on account name
    """
    try:
        account_name_lower = account_name.lower()
        
        # Account type mapping based on keywords
        type_mapping = {
            # Assets
            'asset_current': [
                'bank', 'cash', 'current account', 'checking', 'savings', 'petty cash',
                'accounts receivable', 'receivable', 'debtors', 'inventory', 'stock',
                'prepaid', 'deposits'
            ],
            'asset_non_current': [
                'fixed asset', 'equipment', 'building', 'land', 'machinery', 'vehicle',
                'furniture', 'computer', 'depreciation'
            ],
            # Liabilities
            'liability_current': [
                'accounts payable', 'payable', 'creditors', 'accrued', 'wages payable',
                'tax payable', 'short term loan'
            ],
            'liability_non_current': [
                'long term loan', 'mortgage', 'bonds', 'deferred tax'
            ],
            # Equity
            'equity': [
                'share capital', 'capital', 'equity', 'retained earnings', 'reserves',
                'common stock', 'preferred stock', 'owner equity'
            ],
            # Income
            'income': [
                'revenue', 'sales', 'income', 'service income', 'interest income',
                'rental income', 'fees', 'commission'
            ],
            # Expenses
            'expense': [
                'expense', 'cost', 'salary', 'wage', 'rent', 'utilities', 'insurance',
                'supplies', 'travel', 'marketing', 'advertising', 'office', 'telephone',
                'professional fees', 'maintenance', 'repair'
            ]
        }
        
        # Find matching account type
        detected_type = 'asset_current'  # Default fallback
        
        for account_type, keywords in type_mapping.items():
            for keyword in keywords:
                if keyword in account_name_lower:
                    detected_type = account_type
                    print(f"🔍 Detected account type '{detected_type}' from keyword '{keyword}'")
                    break
            if detected_type != 'asset_current':
                break
        
        # Generate unique account code
        account_code = generate_unique_account_code(models, db, uid, password, account_name, detected_type, context)
        
        return detected_type, account_code
        
    except Exception as e:
        print(f"❌ Error determining account type: {e}")
        return 'asset_current', '999999'  # Safe fallback

def generate_unique_account_code(models, db, uid, password, account_name, account_type, context):
    """
    Generate a unique account code based on account type and name
    """
    try:
        # Base code mapping for different account types
        base_codes = {
            'asset_current': '1',
            'asset_non_current': '15',
            'liability_current': '2',
            'liability_non_current': '25',
            'equity': '3',
            'income': '4',
            'expense': '5'
        }
        
        base_code = base_codes.get(account_type, '9')
        
        # Create a numeric suffix based on account name
        name_hash = hashlib.md5(account_name.encode()).hexdigest()
        numeric_suffix = ''.join(filter(str.isdigit, name_hash))[:4]
        
        # If no digits in hash, use a default
        if not numeric_suffix:
            numeric_suffix = '0001'
        
        # Pad to ensure 4 digits
        numeric_suffix = numeric_suffix.zfill(4)
        
        # Combine base code with suffix
        proposed_code = f"{base_code}{numeric_suffix}"
        
        # Check if code already exists and find a unique one
        attempt = 0
        while attempt < 100:  # Prevent infinite loop
            existing_accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search',
                [[('code', '=', proposed_code)]], 
                {'limit': 1, 'context': context}
            )
            
            if not existing_accounts:
                print(f"✅ Generated unique account code: {proposed_code}")
                return proposed_code
            
            # Code exists, try with incremented suffix
            attempt += 1
            incremented_suffix = str(int(numeric_suffix) + attempt).zfill(4)
            proposed_code = f"{base_code}{incremented_suffix}"
        
        # If all attempts failed, use timestamp-based code
        timestamp_suffix = str(int(datetime.now().timestamp()))[-4:]
        proposed_code = f"{base_code}{timestamp_suffix}"
        
        print(f"✅ Generated fallback account code: {proposed_code}")
        return proposed_code
        
    except Exception as e:
        print(f"❌ Error generating account code: {e}")
        # Ultimate fallback
        return f"9{str(int(datetime.now().timestamp()))[-5:]}"

def find_or_create_partner(models, db, uid, password, partner_name, context):
    """
    Find existing partner by name or create new one
    Returns partner details including ID
    """
    try:
        print(f"🔍 Looking for partner: '{partner_name}'")
        
        # First check if partner_name is actually an ID (integer)
        try:
            partner_id = int(partner_name)
            # If it's an ID, try to fetch the partner details
            partner_data = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [[partner_id], ['id', 'name', 'email', 'phone', 'is_company', 'vat']], 
                {'context': context}
            )
            
            if partner_data:
                partner = partner_data[0]
                print(f"✅ Found partner by ID: {partner['name']} (ID: {partner['id']})")
                return {
                    'id': partner['id'],
                    'name': partner['name'],
                    'email': partner.get('email'),
                    'phone': partner.get('phone'),
                    'is_company': partner.get('is_company'),
                    'vat': partner.get('vat'),
                    'created': False
                }
        except ValueError:
            # Not an integer, continue with name search
            pass
        
        # Search for existing partner by exact name match
        partner_ids = models.execute_kw(
            db, uid, password,
            'res.partner', 'search',
            [[('name', '=', partner_name)]], 
            {'limit': 1, 'context': context}
        )
        
        if partner_ids:
            partner_data = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [partner_ids, ['id', 'name', 'email', 'phone', 'is_company', 'vat']], 
                {'context': context}
            )
            
            partner = partner_data[0]
            print(f"✅ Found existing partner: {partner['name']} (ID: {partner['id']})")
            return {
                'id': partner['id'],
                'name': partner['name'],
                'email': partner.get('email'),
                'phone': partner.get('phone'),
                'is_company': partner.get('is_company'),
                'vat': partner.get('vat'),
                'created': False
            }
        
        # Try partial match (case insensitive)
        partner_ids = models.execute_kw(
            db, uid, password,
            'res.partner', 'search',
            [[('name', 'ilike', partner_name)]], 
            {'limit': 1, 'context': context}
        )
        
        if partner_ids:
            partner_data = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [partner_ids, ['id', 'name', 'email', 'phone', 'is_company', 'vat']], 
                {'context': context}
            )
            
            partner = partner_data[0]
            print(f"✅ Found partner by partial match: {partner['name']} (ID: {partner['id']})")
            return {
                'id': partner['id'],
                'name': partner['name'],
                'email': partner.get('email'),
                'phone': partner.get('phone'),
                'is_company': partner.get('is_company'),
                'vat': partner.get('vat'),
                'created': False
            }
        
        # Partner not found, create new one
        print(f"📝 Creating new partner: {partner_name}")
        
        # Determine if it's a company based on name patterns
        is_company = any(keyword in partner_name.lower() for keyword in 
                        ['ltd', 'limited', 'corp', 'corporation', 'inc', 'llc', 'plc', 'sa', 'bv', 'gmbh'])
        
        partner_data = {
            'name': partner_name,
            'is_company': is_company,
            'customer_rank': 1,  # Mark as customer
            'supplier_rank': 1,  # Mark as supplier (can be both)
        }
        
        new_partner_id = models.execute_kw(
            db, uid, password,
            'res.partner', 'create',
            [partner_data], 
            {'context': context}
        )
        
        if new_partner_id:
            print(f"✅ Created new partner: {partner_name} (ID: {new_partner_id})")
            return {
                'id': new_partner_id,
                'name': partner_name,
                'email': None,
                'phone': None,
                'is_company': is_company,
                'vat': None,
                'created': True
            }
        else:
            print(f"❌ Failed to create partner: {partner_name}")
            return None
            
    except Exception as e:
        print(f"❌ Error finding/creating partner '{partner_name}': {e}")
        import traceback
        traceback.print_exc()
        return None

def get_journal_details(models, db, uid, password, journal_id, context):
    """
    Fetch journal details including code, name, and type
    """
    try:
        journal_data = models.execute_kw(
            db, uid, password,
            'account.journal', 'read',
            [[journal_id], ['id', 'name', 'code', 'type']], 
            {'context': context}
        )
        
        if not journal_data:
            print(f"❌ Journal with ID {journal_id} not found")
            return None
        
        journal = journal_data[0]
        print(f"✅ Journal details retrieved: {journal['name']} ({journal['code']}) - Type: {journal['type']}")
        
        return journal
        
    except Exception as e:
        print(f"❌ Error retrieving journal details: {e}")
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

def create_journal_entry_flexible(models, db, uid, password, journal_id, line_items, data, partner_id, context):
    """Create journal entry using flexible line items with partner support"""
    try:
        print(f"📝 Creating flexible journal entry...")
        
        # Prepare line_ids for Odoo (using (0, 0, values) format)
        line_ids = []
        for line_item in line_items:
            line_ids.append((0, 0, line_item))
        
        # Create enhanced context for journal entry creation
        journal_context = context.copy()
        journal_context.update({
            'check_move_validity': True,  # Enable move validation
            'skip_invoice_sync': True,    # Skip invoice synchronization if applicable
            'force_company': context.get('allowed_company_ids', [1])[0] if context.get('allowed_company_ids') else 1
        })
        
        # Create journal entry
        move_data = {
            'journal_id': journal_id,
            'date': data['date'],
            'ref': data['ref'],
            'narration': data['narration'],
            'line_ids': line_ids,
            'move_type': 'entry',  # Explicitly set as journal entry
        }
        
        # Add partner to the main journal entry if available
        if partner_id:
            move_data['partner_id'] = partner_id
            print(f"📝 Adding partner ID {partner_id} to journal entry")
        
        print(f"📝 Creating move with reference: {data['ref']}")
        print(f"📝 Narration: {data['narration']}")
        print(f"📝 Line items count: {len(line_items)}")
        
        move_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [move_data], {'context': journal_context}
        )
        
        if not move_id:
            raise Exception("Failed to create account move")
        
        print(f"✅ Move created with ID: {move_id}")
        
        # Verify the move was created properly before posting
        move_verification = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[move_id], ['id', 'state', 'ref', 'line_ids']], 
            {'context': journal_context}
        )
        
        if not move_verification or not move_verification[0].get('line_ids'):
            raise Exception(f"Move {move_id} was not created properly - missing line items")
        
        print(f"✅ Move verification passed - {len(move_verification[0]['line_ids'])} lines created")
        
        # Post the journal entry
        print(f"📝 Posting journal entry...")
        models.execute_kw(
            db, uid, password,
            'account.move', 'action_post',
            [[move_id]], {'context': journal_context}
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