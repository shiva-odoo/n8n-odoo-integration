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
    Create bank transaction entry in Odoo using enhanced structure with accounting assignment
    
    Expected data format (from bank statement processing):
    {
        "company_id": 60,
        "date": "2025-07-20",
        "ref": "255492965",
        "narration": "New Share Capital of Kyrastel Investments Ltd",
        "partner": "Kyrastel Investments Ltd",
        "accounting_assignment": {
            "debit_account": "1204",
            "debit_account_name": "Bank",
            "credit_account": "1100",
            "credit_account_name": "Accounts receivable",
            "transaction_type": "share_capital_receipt",
            "requires_vat": false,
            "additional_entries": []
        },
        "line_items": [
            {
                "name": "Bank",
                "debit": 15000.00,
                "credit": 0.00
            },
            {
                "name": "Accounts receivable",
                "debit": 0.00,
                "credit": 15000.00
            }
        ]
    }
    
    Also supports legacy format for backward compatibility:
    {
        "company_id": 1,
        "date": "2025-07-20",
        "ref": "BOC Transfer 09444",
        "narration": "Transaction description",
        "partner": "Partner Name",
        "line_items": [...]
    }
    """
    
    # Validate required fields
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

    # Validate accounting assignment if present
    accounting_assignment = data.get('accounting_assignment', {})
    if accounting_assignment:
        # Validate account codes if provided
        valid_accounts = ["1100", "1204", "2100", "2201", "2202", "3000", "7602", "7901", "8200"]
        
        debit_account = accounting_assignment.get('debit_account', '')
        credit_account = accounting_assignment.get('credit_account', '')
        
        if debit_account and debit_account not in valid_accounts:
            return {
                'success': False,
                'error': f'Invalid debit account code: {debit_account}. Must be one of: {", ".join(valid_accounts)}'
            }
        
        if credit_account and credit_account not in valid_accounts:
            return {
                'success': False,
                'error': f'Invalid credit account code: {credit_account}. Must be one of: {", ".join(valid_accounts)}'
            }
        
        # Validate accounting assignment consistency
        if not validate_accounting_assignment_consistency(data):
            return {
                'success': False,
                'error': 'Accounting assignment accounts do not match line item accounts'
            }

    # Store original date for comparison and fix future dates
    original_date = data['date']
    data['date'] = validate_and_fix_date(data['date'])
    date_was_modified = original_date != data['date']

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
        print(f"=== PROCESSING ENHANCED BANK TRANSACTION ===")
        print(f"Company ID: {company_id}")
        print(f"Date: {data['date']}")
        print(f"Reference: {data['ref']}")
        print(f"Narration: {data['narration']}")
        print(f"Partner: {data.get('partner', 'None')}")
        print(f"Line Items: {len(data['line_items'])}")
        
        # Log accounting assignment details if present
        if accounting_assignment:
            print(f"Transaction Type: {accounting_assignment.get('transaction_type', 'Not specified')}")
            print(f"Debit Account: {accounting_assignment.get('debit_account')} - {accounting_assignment.get('debit_account_name')}")
            print(f"Credit Account: {accounting_assignment.get('credit_account')} - {accounting_assignment.get('credit_account_name')}")
            print(f"Requires VAT: {accounting_assignment.get('requires_vat', False)}")
            
            additional_entries = accounting_assignment.get('additional_entries', [])
            if additional_entries:
                print(f"Additional Entries: {len(additional_entries)}")
        
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
            return {
                'success': False,
                'error': 'Duplicate transaction',
                'message': f'Transaction with reference "{data["ref"]}" already exists',
                'existing_entry_id': duplicate_check['existing_entry_id'],
                'company_id': company_id,
                'company_name': company_details['name'],
                'duplicate_details': duplicate_check
            }
        
        print("✅ No duplicate found, proceeding with transaction creation")
        
        # Step 3: Handle partner information
        partner_id = None
        partner_info = None
        
        if data.get('partner'):
            partner_result = find_or_create_partner(models, db, uid, password, data['partner'], context)
            if partner_result:
                partner_id = partner_result['id']
                partner_info = partner_result
                print(f"✅ Partner resolved: {partner_info['name']} (ID: {partner_id})")
            else:
                return {
                    'success': False,
                    'error': f'Failed to find or create partner: {data["partner"]}'
                }
        
        # Step 4: Enhanced account resolution using accounting assignment
        resolved_line_items = []
        created_accounts = []
        account_mapping = {}
        
        # First, try to map accounts using accounting assignment codes if available
        if accounting_assignment:
            debit_account_code = accounting_assignment.get('debit_account')
            credit_account_code = accounting_assignment.get('credit_account')
            debit_account_name = accounting_assignment.get('debit_account_name')
            credit_account_name = accounting_assignment.get('credit_account_name')
            
            # Create mapping from account codes to names
            if debit_account_code and debit_account_name:
                account_mapping[debit_account_code] = debit_account_name
            if credit_account_code and credit_account_name:
                account_mapping[credit_account_code] = credit_account_name
        
        # Process each line item with enhanced account resolution
        for i, line_item in enumerate(data['line_items']):
            account_name = line_item['name']
            
            # Enhanced account resolution strategy
            account_result = find_or_create_account_enhanced(
                models, db, uid, password, 
                account_name, 
                accounting_assignment, 
                account_mapping, 
                context
            )
            
            if not account_result:
                return {
                    'success': False,
                    'error': f'Could not find or create account for: "{account_name}"'
                }
            
            account_id = account_result['id']
            if account_result.get('created'):
                created_accounts.append(account_result)
            
            resolved_line = {
                'account_id': account_id,
                'name': data['narration'],  # Use narration as line description
                'debit': float(line_item['debit']),
                'credit': float(line_item['credit']),
            }
            
            # Add partner only to receivable/payable accounts
            if partner_id and account_result.get('account_type') in ['asset_receivable', 'liability_payable']:
                resolved_line['partner_id'] = partner_id
            
            resolved_line_items.append(resolved_line)
            
            status = "created" if account_result.get('created') else "found"
            print(f"✅ Line {i+1}: {account_name} -> Account ID {account_id} ({status})")
        
        # Handle additional entries from accounting assignment
        if accounting_assignment and accounting_assignment.get('additional_entries'):
            additional_entries = accounting_assignment['additional_entries']
            print(f"📝 Processing {len(additional_entries)} additional entries...")
            
            for j, entry in enumerate(additional_entries):
                try:
                    entry_account_name = entry.get('account_name', f"Account {entry.get('account_code', 'Unknown')}")
                    
                    # Find or create account for additional entry
                    entry_account_result = find_or_create_account_enhanced(
                        models, db, uid, password,
                        entry_account_name,
                        accounting_assignment,
                        account_mapping,
                        context
                    )
                    
                    if not entry_account_result:
                        print(f"⚠️  Warning: Could not resolve account for additional entry: {entry_account_name}")
                        continue
                    
                    entry_account_id = entry_account_result['id']
                    if entry_account_result.get('created'):
                        created_accounts.append(entry_account_result)
                    
                    additional_line = {
                        'account_id': entry_account_id,
                        'name': entry.get('description', data['narration']),
                        'debit': float(entry.get('debit_amount', 0)),
                        'credit': float(entry.get('credit_amount', 0)),
                    }
                    
                    # Add partner only to receivable/payable accounts
                    if partner_id and entry_account_result.get('account_type') in ['asset_receivable', 'liability_payable']:
                        additional_line['partner_id'] = partner_id
                    
                    resolved_line_items.append(additional_line)
                    
                    status = "created" if entry_account_result.get('created') else "found"
                    print(f"✅ Additional Entry {j+1}: {entry_account_name} -> Account ID {entry_account_id} ({status})")
                    
                except Exception as e:
                    print(f"❌ Error processing additional entry {j+1}: {e}")
                    continue
        
        # If we created any accounts, wait and refresh cache
        if created_accounts:
            print(f"⏳ Created {len(created_accounts)} new accounts, waiting for database sync...")
            time.sleep(1)  # Brief wait for database consistency
            
            # Force cache refresh by doing a simple search
            try:
                models.execute_kw(
                    db, uid, password,
                    'account.account', 'search',
                    [[('id', 'in', [acc['id'] for acc in created_accounts])]], 
                    {'limit': len(created_accounts), 'context': context}
                )
                print("✅ Account cache refreshed")
            except Exception as e:
                print(f"⚠️  Account cache refresh failed: {e}")
        
        # Step 5: Get appropriate journal based on transaction type
        journal_id = get_journal_for_transaction_type(
            models, db, uid, password, 
            accounting_assignment.get('transaction_type', 'general'), 
            data, 
            context
        )
        
        if not journal_id:
            return {
                'success': False,
                'error': 'Could not find appropriate journal'
            }
        
        # Step 6: Get journal details including code
        journal_details = get_journal_details(models, db, uid, password, journal_id, context)
        if not journal_details:
            return {
                'success': False,
                'error': 'Could not retrieve journal details'
            }
        
        print(f"✅ Using Journal: {journal_details['name']} (Code: {journal_details['code']})")
        
        # Step 7: Final validation of resolved line items
        final_total_debits = sum(line['debit'] for line in resolved_line_items)
        final_total_credits = sum(line['credit'] for line in resolved_line_items)
        
        if abs(final_total_debits - final_total_credits) > 0.01:
            return {
                'success': False,
                'error': f'Final line items do not balance: Debits {final_total_debits} vs Credits {final_total_credits}'
            }
        
        print(f"✅ Final validation passed: {len(resolved_line_items)} line items, balanced at {final_total_debits}")
        
        # Step 8: Create Journal Entry with retry mechanism
        journal_entry_id = create_journal_entry_enhanced_with_retry(
            models, db, uid, password,
            journal_id,
            resolved_line_items,
            data,
            partner_id,
            accounting_assignment,
            context
        )
        
        if not journal_entry_id:
            return {
                'success': False,
                'error': 'Failed to create journal entry'
            }
        
        print(f"✅ Journal Entry ID: {journal_entry_id}")
        print(f"✅ Transaction completed successfully")
        
        # Step 9: Prepare enhanced return response
        return {
            'success': True,
            'journal_entry_id': journal_entry_id,
            'date': data['date'],
            'original_date': original_date,
            'date_was_modified': date_was_modified,
            'company_id': company_id,
            'company_name': company_details['name'],
            'journal_id': journal_id,
            'journal_code': journal_details['code'],
            'journal_name': journal_details['name'],
            'journal_type': journal_details['type'],
            'reference': data['ref'],
            'description': data['narration'],
            'partner': partner_info,
            'total_amount': final_total_debits,
            'line_count': len(resolved_line_items),
            'created_accounts': created_accounts,
            'accounting_assignment': accounting_assignment,
            'transaction_type': accounting_assignment.get('transaction_type', 'general'),
            'line_items_processed': [
                {
                    'account_name': data['line_items'][i]['name'] if i < len(data['line_items']) else f"Additional Entry {i - len(data['line_items']) + 1}",
                    'account_id': resolved_line_items[i]['account_id'],
                    'debit': resolved_line_items[i]['debit'],
                    'credit': resolved_line_items[i]['credit'],
                    'partner_id': resolved_line_items[i].get('partner_id')
                }
                for i in range(len(resolved_line_items))
            ],
            'message': 'Enhanced bank transaction entry created successfully with accounting assignment'
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

def validate_accounting_assignment_consistency(data):
    """Validate that accounting assignment accounts match line item accounts"""
    try:
        accounting = data.get('accounting_assignment', {})
        line_items = data.get('line_items', [])
        
        if not accounting:
            return True
        
        debit_account_name = accounting.get('debit_account_name', '')
        credit_account_name = accounting.get('credit_account_name', '')
        
        if not debit_account_name and not credit_account_name:
            return True
        
        # Get line item account names
        line_account_names = [item['name'].lower().strip() for item in line_items]
        
        # Check if accounting assignment accounts exist in line items
        consistency_check = True
        
        if debit_account_name:
            debit_name_lower = debit_account_name.lower().strip()
            if not any(debit_name_lower in line_name or line_name in debit_name_lower for line_name in line_account_names):
                print(f"⚠️  Debit account '{debit_account_name}' not found in line items")
                consistency_check = False
        
        if credit_account_name:
            credit_name_lower = credit_account_name.lower().strip()
            if not any(credit_name_lower in line_name or line_name in credit_name_lower for line_name in line_account_names):
                print(f"⚠️  Credit account '{credit_account_name}' not found in line items")
                consistency_check = False
        
        return consistency_check
        
    except Exception as e:
        print(f"❌ Error validating accounting assignment consistency: {e}")
        return True  # Allow processing to continue if validation fails

def find_or_create_account_enhanced(models, db, uid, password, account_name, accounting_assignment, account_mapping, context):
    """Enhanced account resolution using accounting assignment information"""
    try:
        print(f"🔍 Enhanced account lookup for: '{account_name}'")
        
        # First, try to find by exact name match
        account_result = find_or_create_account_with_retry(models, db, uid, password, account_name, context)
        if account_result:
            return account_result
        
        # If accounting assignment is available, try to find by account code mapping
        if accounting_assignment and account_mapping:
            # Try to find account name in the mapping
            for account_code, mapped_name in account_mapping.items():
                if (account_name.lower().strip() in mapped_name.lower().strip() or 
                    mapped_name.lower().strip() in account_name.lower().strip()):
                    print(f"🔍 Trying account code mapping: {account_code} -> {mapped_name}")
                    
                    # Try to find by code first
                    try:
                        account_ids = models.execute_kw(
                            db, uid, password,
                            'account.account', 'search',
                            [[('code', '=', account_code)]], 
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
                            print(f"✅ Found by code mapping: {account['name']} ({account['code']})")
                            return {
                                'id': account_ids[0],
                                'name': account['name'],
                                'code': account['code'],
                                'account_type': account['account_type'],
                                'created': False
                            }
                    except Exception as e:
                        print(f"❌ Error in code mapping search: {e}")
                        continue
        
        # If still not found, use enhanced account type detection
        if accounting_assignment:
            transaction_type = accounting_assignment.get('transaction_type', '')
            print(f"🔍 Using transaction type '{transaction_type}' for account creation")
            
            # Create account with enhanced type detection
            return create_account_from_transaction_type(
                models, db, uid, password, 
                account_name, 
                transaction_type, 
                context
            )
        
        # Fallback to standard account creation
        return find_or_create_account_with_retry(models, db, uid, password, account_name, context)
        
    except Exception as e:
        print(f"❌ Enhanced account lookup failed: {e}")
        return find_or_create_account_with_retry(models, db, uid, password, account_name, context)

def create_account_from_transaction_type(models, db, uid, password, account_name, transaction_type, context):
    """Create account with type detection based on transaction type and account name"""
    try:
        account_name_lower = account_name.lower().strip()
        
        # Enhanced type mapping based on transaction type and account name
        if transaction_type == 'share_capital_receipt':
            if 'bank' in account_name_lower:
                account_type = 'asset_current'
            elif 'receivable' in account_name_lower or 'accounts receivable' in account_name_lower:
                account_type = 'asset_receivable'
            else:
                account_type = 'equity'
        elif transaction_type == 'consultancy_payment':
            if 'bank' in account_name_lower:
                account_type = 'asset_current'
            elif 'consultancy' in account_name_lower or 'fees' in account_name_lower:
                account_type = 'expense'
            else:
                account_type = 'expense'
        elif transaction_type == 'supplier_payment':
            if 'bank' in account_name_lower:
                account_type = 'asset_current'
            elif 'payable' in account_name_lower:
                account_type = 'liability_payable'
            else:
                account_type = 'expense'
        elif transaction_type == 'bank_charges':
            if 'bank' in account_name_lower and 'charge' not in account_name_lower:
                account_type = 'asset_current'
            else:
                account_type = 'expense'
        elif transaction_type == 'other_income':
            if 'bank' in account_name_lower:
                account_type = 'asset_current'
            else:
                account_type = 'income'  # Fixed: was 'income_other'
        elif transaction_type == 'other_expense':
            if 'bank' in account_name_lower:
                account_type = 'asset_current'
            else:
                account_type = 'expense'
        else:
            # Default type detection
            if 'bank' in account_name_lower:
                account_type = 'asset_current'
            elif 'receivable' in account_name_lower:
                account_type = 'asset_receivable'
            elif 'payable' in account_name_lower:
                account_type = 'liability_payable'
            elif 'capital' in account_name_lower or 'equity' in account_name_lower:
                account_type = 'equity'
            elif 'income' in account_name_lower or 'revenue' in account_name_lower:
                account_type = 'income'
            else:
                account_type = 'expense'
        
        print(f"📝 Creating account '{account_name}' with type '{account_type}' based on transaction type '{transaction_type}'")
        
        # Generate account code based on type
        account_code = generate_account_code_by_type(models, db, uid, password, account_name, account_type, context)
        
        # Prepare account data
        account_data = {
            'name': account_name,
            'code': account_code,
            'account_type': account_type,
            'reconcile': account_type in ['asset_receivable', 'liability_payable'],
        }
        
        # Create the account
        create_context = context.copy()
        create_context.update({
            'check_move_validity': False,
            'force_company': context.get('allowed_company_ids', [1])[0] if context.get('allowed_company_ids') else 1
        })
        
        new_account_id = models.execute_kw(
            db, uid, password,
            'account.account', 'create',
            [account_data], 
            {'context': create_context}
        )
        
        if new_account_id:
            print(f"✅ Created account with enhanced type detection: ID {new_account_id}")
            return {
                'id': new_account_id,
                'name': account_name,
                'code': account_code,
                'account_type': account_type,
                'created': True
            }
        
        return None
        
    except Exception as e:
        print(f"❌ Enhanced account creation failed: {e}")
        return None

def generate_account_code_by_type(models, db, uid, password, account_name, account_type, context):
    """Generate account code based on account type with predefined ranges"""
    try:
        # Predefined account code ranges based on chart of accounts
        type_code_mapping = {
            'asset_current': '1200',        # 1200-1299 for current assets  
            'asset_receivable': '1100',     # 1100-1199 for receivables
            'asset_non_current': '1500',    # 1500-1599 for fixed assets
            'liability_payable': '2100',    # 2100-2199 for payables
            'liability_current': '2200',    # 2200-2299 for current liabilities
            'liability_non_current': '2500', # 2500-2599 for long-term liabilities
            'equity': '3000',               # 3000-3099 for equity
            'income': '4000',               # 4000-4099 for income
            'expense': '5000',              # 5000-5999 for expenses
        }
        
        # Map specific account names to codes if they match our chart of accounts
        specific_mappings = {
            'bank': '1204',
            'accounts receivable': '1100', 
            'accounts payable': '2100',
            'share capital': '3000',
            'consultancy fees': '7602',
            'bank charges': '7901',
            'other non-operating income or expenses': '8200',
            'output vat': '2201',
            'input vat': '2202'
        }
        
        account_name_lower = account_name.lower().strip()
        
        # First check for specific mappings
        for key, code in specific_mappings.items():
            if key in account_name_lower:
                # Check if this exact code already exists
                try:
                    existing = models.execute_kw(
                        db, uid, password,
                        'account.account', 'search',
                        [[('code', '=', code)]], 
                        {'limit': 1, 'context': context}
                    )
                    
                    if not existing:
                        return code
                except Exception as e:
                    print(f"❌ Error checking existing code {code}: {e}")
        
        # Use type-based code generation
        base_code = type_code_mapping.get(account_type, '9000')
        
        # Generate unique code within the range
        for i in range(100):  # Try up to 100 variations
            try:
                # Fixed: Better code generation logic
                if base_code.isdigit() and len(base_code) == 4:
                    # For 4-digit base codes, increment intelligently
                    base_num = int(base_code)
                    test_code = str(base_num + i)
                else:
                    # For other formats, append increment
                    test_code = f"{base_code}{i:02d}" if i < 100 else f"{base_code}{i}"
                
                # Check if code exists
                existing = models.execute_kw(
                    db, uid, password,
                    'account.account', 'search',
                    [[('code', '=', test_code)]], 
                    {'limit': 1, 'context': context}
                )
                
                if not existing:
                    return test_code
                    
            except Exception as e:
                print(f"❌ Error checking code {test_code}: {e}")
                continue
        
        # Fallback to timestamp-based code
        timestamp_suffix = str(int(datetime.now().timestamp()))[-3:]
        fallback_code = f"{base_code[:2]}{timestamp_suffix}" if len(base_code) >= 2 else f"9{timestamp_suffix}"
        return fallback_code
        
    except Exception as e:
        print(f"❌ Error generating account code: {e}")
        return f"9{str(int(datetime.now().timestamp()))[-3:]}"

def get_journal_for_transaction_type(models, db, uid, password, transaction_type, data, context):
    """Get appropriate journal based on transaction type"""
    try:
        print(f"🔍 Finding journal for transaction type: {transaction_type}")
        
        # Map transaction types to preferred journal types
        journal_type_mapping = {
            'share_capital_receipt': 'bank',
            'customer_payment': 'bank', 
            'supplier_payment': 'bank',
            'consultancy_payment': 'bank',
            'bank_charges': 'bank',
            'other_income': 'general',
            'other_expense': 'general'
        }
        
        preferred_journal_type = journal_type_mapping.get(transaction_type, 'bank')
        
        # Try to find journal of preferred type
        try:
            journal_ids = models.execute_kw(
                db, uid, password,
                'account.journal', 'search',
                [[('type', '=', preferred_journal_type)]], 
                {'limit': 1, 'context': context}
            )
            
            if journal_ids:
                return journal_ids[0]
        except Exception as e:
            print(f"❌ Error finding {preferred_journal_type} journal: {e}")
        
        # Fallback to any bank journal
        try:
            journal_ids = models.execute_kw(
                db, uid, password,
                'account.journal', 'search',
                [[('type', '=', 'bank')]], 
                {'limit': 1, 'context': context}
            )
            
            if journal_ids:
                return journal_ids[0]
        except Exception as e:
            print(f"❌ Error finding bank journal: {e}")
        
        # Final fallback to general journal
        try:
            journal_ids = models.execute_kw(
                db, uid, password,
                'account.journal', 'search',
                [[('type', '=', 'general')]], 
                {'limit': 1, 'context': context}
            )
            
            if journal_ids:
                return journal_ids[0]
        except Exception as e:
            print(f"❌ Error finding general journal: {e}")
        
        # Last resort - any journal
        try:
            journal_ids = models.execute_kw(
                db, uid, password,
                'account.journal', 'search',
                [[]], 
                {'limit': 1, 'context': context}
            )
            
            if journal_ids:
                return journal_ids[0]
        except Exception as e:
            print(f"❌ Error finding any journal: {e}")
        
        return None
        
    except Exception as e:
        print(f"❌ Error finding journal: {e}")
        return None

def create_journal_entry_enhanced_with_retry(models, db, uid, password, journal_id, line_items, data, partner_id, accounting_assignment, context, max_retries=3):
    """Create journal entry with enhanced features and retry mechanism"""
    
    for attempt in range(max_retries):
        try:
            return create_journal_entry_enhanced(
                models, db, uid, password, 
                journal_id, line_items, data, 
                partner_id, accounting_assignment, 
                context
            )
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Check if it's an account-related error
            if any(keyword in error_str for keyword in ['account', 'not found', 'invalid', 'missing']):
                if attempt < max_retries - 1:
                    print(f"⚠️  Journal entry creation attempt {attempt + 1} failed (account issue), retrying...")
                    time.sleep(1)  # Longer wait for account issues
                    
                    # Refresh account cache by searching for all used accounts
                    try:
                        account_ids = [line['account_id'] for line in line_items]
                        models.execute_kw(
                            db, uid, password,
                            'account.account', 'search',
                            [[('id', 'in', account_ids)]], 
                            {'context': context}
                        )
                        print("✅ Account cache refreshed before retry")
                    except Exception as cache_error:
                        print(f"⚠️  Account cache refresh failed: {cache_error}")
                    continue
            
            # If not an account error or final attempt, re-raise
            if attempt == max_retries - 1:
                raise e
            else:
                print(f"⚠️  Journal entry creation attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(0.5)
    
    return None

def create_journal_entry_enhanced(models, db, uid, password, journal_id, line_items, data, partner_id, accounting_assignment, context):
    """Create journal entry with enhanced features from accounting assignment"""
    try:
        print(f"📝 Creating enhanced journal entry...")
        
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
        
        # Create journal entry with enhanced data
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
        
        # Add transaction type as internal note if available
        if accounting_assignment and accounting_assignment.get('transaction_type'):
            transaction_type = accounting_assignment['transaction_type']
            if move_data.get('narration'):
                move_data['narration'] += f" (Type: {transaction_type})"
            print(f"📝 Added transaction type: {transaction_type}")
        
        print(f"📝 Creating move with reference: {data['ref']}")
        print(f"📝 Narration: {move_data['narration']}")
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
        try:
            move_verification = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[move_id], ['id', 'state', 'ref', 'line_ids']], 
                {'context': journal_context}
            )
            
            if not move_verification or not move_verification[0].get('line_ids'):
                raise Exception(f"Move {move_id} was not created properly - missing line items")
            
            print(f"✅ Move verification passed - {len(move_verification[0]['line_ids'])} lines created")
        except Exception as verify_error:
            print(f"⚠️  Move verification failed: {verify_error}")
            # Continue anyway, the move was created
        
        # Post the journal entry
        try:
            print(f"📝 Posting journal entry...")
            models.execute_kw(
                db, uid, password,
                'account.move', 'action_post',
                [[move_id]], {'context': journal_context}
            )
            print(f"✅ Journal entry posted successfully")
        except Exception as post_error:
            print(f"⚠️  Journal entry posting failed: {post_error}")
            print(f"✅ Journal entry created but not posted (ID: {move_id})")
        
        return move_id
        
    except Exception as e:
        print(f"❌ Error creating enhanced journal entry: {e}")
        import traceback
        traceback.print_exc()
        return None

# Keep all the existing utility functions from the original code
def find_or_create_account_with_retry(models, db, uid, password, account_name, context, max_retries=3):
    """Find existing account by name/code or create new one with retry mechanism"""
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
    """Find existing account by name/code or create new one"""
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
        
        # Account not found, create new one
        print(f"📝 Creating new account: {account_name}")
        return create_new_account_with_verification(models, db, uid, password, account_name, context)
        
    except Exception as e:
        print(f"❌ Error finding/creating account '{account_name}': {e}")
        import traceback
        traceback.print_exc()
        return None

def create_new_account_with_verification(models, db, uid, password, account_name, context):
    """Create a new account with verification that it was successfully created"""
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

def determine_account_type_and_code(models, db, uid, password, account_name, context):
    """Intelligently determine account type and generate unique code based on account name"""
    try:
        account_name_lower = account_name.lower()
        
        # Account type mapping based on keywords
        type_mapping = {
            # Assets
            'asset_current': [
                'bank', 'cash', 'current account', 'checking', 'savings', 'petty cash',
                'inventory', 'stock', 'prepaid', 'deposits'
            ],
            'asset_receivable': [
                'accounts receivable', 'receivable', 'debtors'
            ],
            'asset_non_current': [
                'fixed asset', 'equipment', 'building', 'land', 'machinery', 'vehicle',
                'furniture', 'computer', 'depreciation'
            ],
            # Liabilities
            'liability_payable': [
                'accounts payable', 'payable', 'creditors'
            ],
            'liability_current': [
                'accrued', 'wages payable', 'tax payable', 'short term loan'
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
                'professional fees', 'maintenance', 'repair', 'consultancy'
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
    """Generate a unique account code based on account type and name"""
    try:
        # Base code mapping for different account types
        base_codes = {
            'asset_current': '1200',
            'asset_receivable': '1100',
            'asset_non_current': '1500',
            'liability_payable': '2100',
            'liability_current': '2200',
            'liability_non_current': '2500',
            'equity': '3000',
            'income': '4000',
            'expense': '5000'
        }
        
        base_code = base_codes.get(account_type, '9000')
        
        # Create a numeric suffix based on account name
        name_hash = hashlib.md5(account_name.encode()).hexdigest()
        numeric_suffix = ''.join(filter(str.isdigit, name_hash))[:3]
        
        # If no digits in hash, use a default
        if not numeric_suffix:
            numeric_suffix = '001'
        
        # Pad to ensure 3 digits
        numeric_suffix = numeric_suffix.zfill(3)
        
        # Combine base code with suffix
        if len(base_code) >= 4:
            proposed_code = f"{base_code[:-3]}{numeric_suffix}"
        else:
            proposed_code = f"{base_code}{numeric_suffix}"
        
        # Check if code already exists and find a unique one
        attempt = 0
        while attempt < 100:  # Prevent infinite loop
            try:
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
                incremented_suffix = str(int(numeric_suffix) + attempt).zfill(3)
                if len(base_code) >= 4:
                    proposed_code = f"{base_code[:-3]}{incremented_suffix}"
                else:
                    proposed_code = f"{base_code}{incremented_suffix}"
                    
            except Exception as e:
                print(f"❌ Error checking code {proposed_code}: {e}")
                attempt += 1
        
        # If all attempts failed, use timestamp-based code
        timestamp_suffix = str(int(datetime.now().timestamp()))[-3:]
        if len(base_code) >= 4:
            proposed_code = f"{base_code[:-3]}{timestamp_suffix}"
        else:
            proposed_code = f"{base_code}{timestamp_suffix}"
        
        print(f"✅ Generated fallback account code: {proposed_code}")
        return proposed_code
        
    except Exception as e:
        print(f"❌ Error generating account code: {e}")
        # Ultimate fallback
        return f"9{str(int(datetime.now().timestamp()))[-3:]}"

def find_or_create_partner(models, db, uid, password, partner_name, context):
    """Find existing partner by name or create new one"""
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
    """Fetch journal details including code, name, and type"""
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
    """Check if a duplicate transaction exists by reference"""
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