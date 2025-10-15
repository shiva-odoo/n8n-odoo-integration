import xmlrpc.client
import os
import time
import json # Import json for pretty printing

# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def debug_list_company_taxes(company_id):
    """
    DEBUG FUNCTION: List all taxes for a company to see what actually exists
    This helps identify the exact tax names and structures in Odoo
    """
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
        
        # Get all taxes for this company
        taxes = models.execute_kw(
            db, uid, password,
            'account.tax', 'search_read',
            [[('company_id', '=', company_id)]], 
            {'fields': ['id', 'name', 'amount', 'amount_type', 'type_tax_use'], 'order': 'name'}
        )
        
        print("\n" + "="*80)
        print(f"TAXES FOR COMPANY ID {company_id}:")
        print("="*80)
        for tax in taxes:
            print(f"ID: {tax['id']:4d} | Name: {tax['name']:40s} | Type: {tax['amount_type']:10s} | Amount: {tax.get('amount', 0):6.2f}% | Use: {tax['type_tax_use']}")
        print("="*80 + "\n")
        
        return {
            'success': True,
            'company_id': company_id,
            'taxes': taxes,
            'count': len(taxes)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def main(data):
    """
    Create company from HTTP request data following Odoo documentation
    """
    
    # Validate required fields
    if not data.get('name'):
        return {
            'success': False,
            'error': 'name is required'
        }
    
    # ALWAYS default to Cyprus and EUR - force these values regardless of input
    country_code = 'CY'
    currency_code = 'EUR'
    
    data['country_code'] = country_code
    data['currency_code'] = currency_code
    
    # Handle VAT number: Normalize it, and if it's empty OR a hyphen, set it to '/'
    vat_input = data.get('vat', '').strip().upper()

    # Check if the input is empty OR just a hyphen
    if vat_input and vat_input != '-':
        # If VAT is provided and it's not a hyphen, process it
        if vat_input.startswith('CY'):
            vat_input = vat_input[2:]
            print(f"Normalized VAT: removed 'CY' prefix, using: {vat_input}")
        data['vat'] = vat_input
    else:
        # If no VAT is provided, it's just whitespace, OR it's a hyphen, set it to '/'
        print(f"Input VAT was '{data.get('vat')}', setting field to '/' for Odoo.")
        data['vat'] = '/'

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

        # Check if company already exists
        existing_company = models.execute_kw(
            db, uid, password,
            'res.company', 'search_count',
            [[('name', '=', data['name'])]]
        )

        if existing_company:
            return {
                'success': False,
                'error': f'Company with name "{data["name"]}" already exists'
            }

        available_fields = get_available_company_fields(models, db, uid, password)
        company_data = {'name': data['name']}
        
        field_mapping = {
            'email': data.get('email'),
            'phone': data.get('phone'),
            'website': data.get('website'),
            'vat': data.get('vat'),
            'company_registry': data.get('company_registry'),
            'street': data.get('street'),
            'city': data.get('city'),
            'zip': data.get('zip'),
            'state': data.get('state')
        }
        
        # Only add fields that exist and have values
        for field, value in field_mapping.items():
            if value and field in available_fields:
                company_data[field] = value

        # Handle country (always use Cyprus)
        if 'country_id' in available_fields:
            country_id = get_country_id(models, db, uid, password, country_code)
            if country_id:
                company_data['country_id'] = country_id
            else:
                return {
                    'success': False,
                    'error': f'Country code "{country_code}" not found'
                }

        # Handle currency (always use EUR)
        currency_id = None
        currency_warning = None
        if 'currency_id' in available_fields:
            currency_id = get_currency_id(models, db, uid, password, currency_code)
            if currency_id:
                company_data['currency_id'] = currency_id
            else:
                currency_warning = f'Currency code "{currency_code}" not found - company created without specific currency'

        # Handle state (if state provided and state_id field exists)
        if data.get('state') and company_data.get('country_id') and 'state_id' in available_fields:
            state_id = get_state_id(models, db, uid, password, data['state'], company_data['country_id'])
            if state_id:
                company_data['state_id'] = state_id
                company_data.pop('state', None)
        
        # Log the exact payload before sending it to Odoo for creation
        print("\n--- ODOO CREATE PAYLOAD ---")
        print(json.dumps(company_data, indent=2))
        print("---------------------------\n")

        # Create company
        company_id = models.execute_kw(
            db, uid, password,
            'res.company', 'create',
            [company_data]
        )

        if not company_id:
            return {
                'success': False,
                'error': 'Failed to create company in Odoo'
            }

        print(f"Company created successfully with ID: {company_id}")

        chart_result = ensure_chart_of_accounts(models, db, uid, password, company_id, country_code)
        print(f"Chart of accounts installation initiated: {chart_result.get('message', 'In progress')}")

        print("Waiting for Chart of Accounts installation to complete...")
        chart_ready = wait_for_chart_of_accounts(models, db, uid, password, company_id, max_wait_time=120)
        
        if not chart_ready['success'] and 'company_id' in str(chart_ready.get('message', '')):
            print("Falling back to simplified chart checking method...")
            chart_ready = wait_for_chart_of_accounts_simple(models, db, uid, password, company_id)
        
        if not chart_ready['success']:
            print(f"Warning: {chart_ready['message']}")
        else:
            print("Chart of Accounts is ready!")

        # ===== MOVED: Wait extra time for CoA to create journals =====
        print("Waiting for Chart of Accounts journals to be created...")
        time.sleep(10)

        # ===== MOVED: Disable aliases AFTER CoA creates journals =====
        disable_result = disable_all_journal_aliases(models, db, uid, password, company_id)
        if disable_result['success']:
            print(f"Disabled aliases on {disable_result['count']} journals")
        else:
            print(f"Warning: Could not disable journal aliases: {disable_result.get('error')}")

        custom_accounts_result = create_custom_accounts(models, db, uid, password, company_id)
        if custom_accounts_result['success']:
            print(f"Successfully created {len(custom_accounts_result['accounts'])} custom accounts")
        else:
            print(f"Custom accounts creation issue: {custom_accounts_result.get('error', 'Unknown error')}")

        journals_result = create_essential_journals(models, db, uid, password, company_id, currency_id)
        if journals_result['success']:
            print(f"Successfully created {len(journals_result['journals'])} journals")
            if journals_result.get('existing_count', 0) > 0:
                print(f"Found {journals_result['existing_count']} existing journals")
        else:
            print(f"Journal creation issue: {journals_result.get('error', 'Unknown error')}")

        # Configure taxes based on VAT registration status
        # Wait for taxes to be created by chart of accounts
        is_vat_registered = data.get('is_vat_registered', 'no')
        print(f"\nWaiting for taxes to be created before configuration...")
        print(f"VAT registration status: {is_vat_registered}")
        
        tax_ready = wait_for_taxes_to_exist(models, db, uid, password, company_id, max_wait_time=60)
        
        if tax_ready['success']:
            print(f"Taxes are ready! Found {tax_ready['tax_count']} taxes")
            tax_config_result = configure_taxes_for_company(models, db, uid, password, company_id, is_vat_registered)
            if tax_config_result['success']:
                print(f"Tax configuration completed successfully")
                for update in tax_config_result.get('updates', []):
                    if update.get('success'):
                        print(f"  ✓ {update.get('message', 'Update completed')}")
                    else:
                        print(f"  ✗ {update.get('error', 'Update failed')}")
            else:
                print(f"Tax configuration warning: {tax_config_result.get('error')}")
        else:
            print(f"Warning: Taxes not ready yet - {tax_ready['message']}")
            tax_config_result = {'success': False, 'error': tax_ready['message']}

        safe_read_fields = [
            'name', 'email', 'phone', 'website', 'vat', 'company_registry',
            'currency_id', 'country_id', 'street', 'city', 'zip'
        ]
        read_fields = [field for field in safe_read_fields if field in available_fields]
        company_info = models.execute_kw(
            db, uid, password,
            'res.company', 'read',
            [[company_id]],
            {'fields': read_fields}
        )[0]
        
        response = {
            'success': True,
            'company_id': company_id,
            'company_name': company_info['name'],
            'message': 'Company created successfully'
        }
        
        if data.get('country_code') != country_code:
            response['country_default_applied'] = f'Used default country: {country_code}'
        if data.get('currency_code') != currency_code:
            response['currency_default_applied'] = f'Used default currency: {currency_code}'
        
        response['chart_of_accounts_status'] = chart_ready['message']
        
        if custom_accounts_result['success']:
            response['custom_accounts_created'] = custom_accounts_result['accounts']
            response['message'] += f' with {len(custom_accounts_result["accounts"])} custom accounts'
        else:
            response['custom_accounts_warning'] = custom_accounts_result.get('error')
        
        if journals_result['success']:
            response['journals_created'] = journals_result['journals']
            response['message'] += f' and {len(journals_result["journals"])} essential journals'
            if journals_result.get('existing_count', 0) > 0:
                response['message'] += f' ({journals_result["existing_count"]} existing)'
        else:
            response['journal_warning'] = journals_result['error']
        
        # Add tax configuration results to response
        if tax_config_result['success']:
            response['tax_configuration'] = {
                'vat_registered': is_vat_registered,
                'updates': tax_config_result.get('updates', [])
            }
            response['message'] += f' and configured taxes for VAT registration: {is_vat_registered}'
        else:
            response['tax_configuration_warning'] = tax_config_result.get('error')
        
        if currency_warning:
            response['currency_warning'] = currency_warning
        
        optional_response_fields = {
            'email': 'email', 'phone': 'phone', 'website': 'website', 'vat': 'vat',
            'company_registry': 'company_registry', 'street': 'street', 'city': 'city', 'zip': 'zip'
        }
        
        for response_key, odoo_field in optional_response_fields.items():
            if odoo_field in company_info:
                response[response_key] = company_info.get(odoo_field)
        
        if 'currency_id' in company_info and company_info['currency_id']:
            response['currency'] = company_info['currency_id'][1] if isinstance(company_info['currency_id'], list) else 'N/A'
        
        if 'country_id' in company_info and company_info['country_id']:
            response['country'] = company_info['country_id'][1] if isinstance(company_info['country_id'], list) else 'N/A'
        
        return response
        
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
    
def wait_for_taxes_to_exist(models, db, uid, password, company_id, max_wait_time=60, check_interval=5):
    """
    Wait for taxes to be created by the chart of accounts installation
    Checks for the existence of key taxes like 19%, 19% S, and 19% RC
    """
    start_time = time.time()
    required_taxes = ['19%', '19% S', '19% RC']
    min_tax_count = 10  # Should have at least 10 taxes when chart is installed
    
    print(f"Waiting for taxes to be created (max {max_wait_time} seconds)...")
    
    while time.time() - start_time < max_wait_time:
        try:
            # Count total taxes for this company
            tax_count = models.execute_kw(
                db, uid, password,
                'account.tax', 'search_count',
                [[('company_id', '=', company_id)]]
            )
            
            print(f"Found {tax_count} taxes for company {company_id}")
            
            if tax_count >= min_tax_count:
                # Check if our required taxes exist
                found_taxes = {}
                for tax_name in required_taxes:
                    tax_ids = models.execute_kw(
                        db, uid, password,
                        'account.tax', 'search',
                        [[('name', '=', tax_name), ('company_id', '=', company_id)]],
                        {'limit': 5}
                    )
                    found_taxes[tax_name] = len(tax_ids)
                    print(f"  - Tax '{tax_name}': found {len(tax_ids)} instances")
                
                # Check if all required taxes exist
                all_found = all(count > 0 for count in found_taxes.values())
                
                if all_found:
                    elapsed_time = int(time.time() - start_time)
                    return {
                        'success': True,
                        'message': f'Taxes ready with {tax_count} total taxes (took {elapsed_time}s)',
                        'tax_count': tax_count,
                        'required_taxes_found': found_taxes
                    }
                else:
                    missing = [name for name, count in found_taxes.items() if count == 0]
                    print(f"  Still waiting for taxes: {missing}")
            
            time.sleep(check_interval)
            
        except Exception as e:
            print(f"Error checking taxes: {str(e)}")
            time.sleep(check_interval)
    
    # Timeout reached
    elapsed_time = int(time.time() - start_time)
    try:
        final_tax_count = models.execute_kw(
            db, uid, password,
            'account.tax', 'search_count',
            [[('company_id', '=', company_id)]]
        )
    except:
        final_tax_count = 0
    
    if final_tax_count > 0:
        return {
            'success': True,
            'message': f'Taxes partially ready with {final_tax_count} taxes after {elapsed_time}s (proceeding anyway)',
            'tax_count': final_tax_count,
            'timeout_reached': True
        }
    else:
        return {
            'success': False,
            'message': f'Taxes not created after {elapsed_time}s - manual setup may be required',
            'tax_count': 0,
            'timeout_reached': True
        }


def create_custom_accounts(models, db, uid, password, company_id):
    """
    Create custom accounts for specific business needs
    """
    try:
        print("Checking account.account model structure...")
        
        # Check available fields
        try:
            account_fields = models.execute_kw(
                db, uid, password,
                'account.account', 'fields_get',
                [[]], {'attributes': ['string', 'type']}
            )
            has_company_ids = 'company_ids' in account_fields
            print(f"Account model has company_ids field: {has_company_ids}")
        except Exception as e:
            print(f"Could not check account fields: {e}")
            has_company_ids = False
        
        # Define custom accounts
        custom_accounts_data = [
            {
                'code': '7101',
                'name': 'Office space',
                'account_type': 'expense',
                'reconcile': False,
                'note': 'Office space related expenses - rent, coworking, office facilities'
            },
            {
                'code': '7605',
                'name': 'Portfolio management fees',
                'account_type': 'expense',
                'reconcile': False,
                'note': 'Fees for portfolio management and investment advisory services'
            },
            {
                'code': '7906',
                'name': 'Non Recoverable VAT on expenses',
                'account_type': 'expense',
                'reconcile': False,
                'note': 'VAT on expenses for non-VAT registered companies - not recoverable, treated as additional expense'
            }
        ]
        
        created_accounts = []
        
        for account_data in custom_accounts_data:
            try:
                # Build create data
                create_data = {
                    'code': account_data['code'],
                    'name': account_data['name'],
                    'account_type': account_data['account_type'],
                    'reconcile': account_data['reconcile']
                }
                
                # Add company_ids if field exists (Many2many format)
                if has_company_ids:
                    # Odoo Many2many format: [(6, 0, [list of ids])]
                    # Command 6 means "replace all existing relations with this list"
                    create_data['company_ids'] = [(6, 0, [company_id])]
                    print(f"Setting company_ids to: {create_data['company_ids']}")
                
                note = account_data['note']
                
                # Check if account exists for THIS company
                if has_company_ids:
                    existing = models.execute_kw(
                        db, uid, password,
                        'account.account', 'search_count',
                        [[('code', '=', create_data['code']), ('company_ids', 'in', [company_id])]]
                    )
                else:
                    existing = models.execute_kw(
                        db, uid, password,
                        'account.account', 'search_count',
                        [[('code', '=', create_data['code'])]]
                    )
                
                if existing:
                    print(f"Account {create_data['code']} already exists for company {company_id}")
                    continue
                
                # Create the account
                print(f"Creating account: {create_data['code']} - {create_data['name']} for company {company_id}")
                account_id = models.execute_kw(
                    db, uid, password,
                    'account.account', 'create',
                    [create_data]
                )
                
                if account_id:
                    created_accounts.append({
                        'id': account_id,
                        'code': create_data['code'],
                        'name': create_data['name'],
                        'type': create_data['account_type'],
                        'purpose': note
                    })
                    print(f"✓ Created account: {create_data['code']} - {create_data['name']} (ID: {account_id}) for company {company_id}")
                    print(f"  Purpose: {note}")
                    
            except Exception as account_error:
                print(f"✗ Failed to create account {account_data.get('code', 'unknown')}: {str(account_error)}")
                continue
        
        if created_accounts:
            print(f"\n📋 Custom Accounts Summary: Successfully created {len(created_accounts)} custom accounts for company {company_id}")
            return {
                'success': True,
                'accounts': created_accounts,
                'message': f'Created {len(created_accounts)} custom accounts'
            }
        else:
            return {
                'success': False,
                'error': 'No custom accounts were created - they may already exist or model structure is incompatible'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to create custom accounts: {str(e)}'
        }

def disable_all_journal_aliases(models, db, uid, password, company_id):
    """
    Disable email aliases on ALL journals for a company (including those created by Chart of Accounts)
    This prevents email alias conflicts and disables the email-to-journal feature completely
    """
    try:
        print(f"Disabling email aliases for all journals in company {company_id}...")
        
        # Find all journals for this company
        journals = models.execute_kw(
            db, uid, password,
            'account.journal', 'search',
            [[('company_id', '=', company_id)]]
        )
        
        if not journals:
            return {
                'success': True,
                'count': 0,
                'message': 'No journals found for this company'
            }
        
        # Update each journal to remove/disable alias
        updated_count = 0
        for journal_id in journals:
            try:
                # Set alias_id to False to disable email alias
                models.execute_kw(
                    db, uid, password,
                    'account.journal', 'write',
                    [[journal_id], {'alias_id': False}]
                )
                updated_count += 1
            except Exception as e:
                print(f"Could not disable alias for journal {journal_id}: {str(e)}")
                continue
        
        return {
            'success': True,
            'count': updated_count,
            'message': f'Disabled aliases on {updated_count} journals'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'count': 0
        }

def wait_for_chart_of_accounts(models, db, uid, password, company_id, max_wait_time=120, check_interval=5):
    """
    Wait for Chart of Accounts to be installed by checking if accounts exist
    """
    start_time = time.time()
    min_accounts_required = 10
    
    print(f"Waiting for Chart of Accounts installation (max {max_wait_time} seconds)...")
    
    try:
        account_fields = models.execute_kw(
            db, uid, password,
            'account.account', 'fields_get',
            [[]], {'attributes': ['string', 'type']}
        )
        has_company_id = 'company_id' in account_fields
        print(f"Account model has company_id field: {has_company_id}")
    except Exception as e:
        print(f"Could not check account fields: {e}")
        has_company_id = False
    
    while time.time() - start_time < max_wait_time:
        try:
            if has_company_id:
                account_count = models.execute_kw(
                    db, uid, password,
                    'account.account', 'search_count',
                    [[('company_id', '=', company_id)]]
                )
            else:
                all_accounts = models.execute_kw(
                    db, uid, password,
                    'account.account', 'search_count',
                    [[]]
                )
                
                if all_accounts > min_accounts_required:
                    account_count = all_accounts
                    print(f"Found {all_accounts} total accounts (company filtering not available)")
                else:
                    account_count = 0
            
            print(f"Found {account_count} accounts")
            
            if account_count >= min_accounts_required:
                try:
                    if has_company_id:
                        essential_account_types = ['asset_receivable', 'liability_payable', 'income', 'expense']
                        accounts_with_types = models.execute_kw(
                            db, uid, password,
                            'account.account', 'search_read',
                            [[('company_id', '=', company_id), ('account_type', 'in', essential_account_types)]],
                            {'fields': ['id', 'account_type'], 'limit': len(essential_account_types)}
                        )
                        
                        found_types = set(acc['account_type'] for acc in accounts_with_types)
                        missing_types = set(essential_account_types) - found_types
                        
                        if missing_types:
                            print(f"Waiting for essential account types: {missing_types}")
                            time.sleep(check_interval)
                            continue
                    
                    elapsed_time = int(time.time() - start_time)
                    return {
                        'success': True,
                        'message': f'Chart of Accounts ready with {account_count} accounts (took {elapsed_time}s)',
                        'accounts_count': account_count
                    }
                    
                except Exception as type_check_error:
                    print(f"Could not check account types: {type_check_error}")
                    elapsed_time = int(time.time() - start_time)
                    return {
                        'success': True,
                        'message': f'Chart of Accounts ready with {account_count} accounts (took {elapsed_time}s)',
                        'accounts_count': account_count
                    }
            
            time.sleep(check_interval)
            
        except Exception as e:
            print(f"Error checking accounts: {str(e)}")
            time.sleep(check_interval)
    
    elapsed_time = int(time.time() - start_time)
    try:
        if has_company_id:
            final_account_count = models.execute_kw(
                db, uid, password,
                'account.account', 'search_count',
                [[('company_id', '=', company_id)]]
            )
        else:
            final_account_count = models.execute_kw(
                db, uid, password,
                'account.account', 'search_count',
                [[]]
            )
    except:
        final_account_count = 0
    
    if final_account_count > 0:
        return {
            'success': True,
            'message': f'Chart of Accounts partially ready with {final_account_count} accounts after {elapsed_time}s (may still be installing)',
            'accounts_count': final_account_count,
            'timeout_reached': True
        }
    else:
        return {
            'success': False,
            'message': f'Chart of Accounts not ready after {elapsed_time}s - manual setup may be required',
            'accounts_count': 0,
            'timeout_reached': True
        }

def create_essential_journals(models, db, uid, password, company_id, currency_id=None):
    """
    Create essential journals for a new company
    Only creates journals that don't already exist by type
    """
    try:
        created_journals = []
        
        # First, get all existing journals for this company
        existing_journals = models.execute_kw(
            db, uid, password,
            'account.journal', 'search_read',
            [[('company_id', '=', company_id)]],
            {'fields': ['id', 'name', 'code', 'type']}
        )
        
        existing_types = {j['type']: j for j in existing_journals}
        existing_codes = {j['code']: j for j in existing_journals}
        journal_list = [f"{j['name']} ({j['type']}, {j['code']})" for j in existing_journals]
        print(f"Found existing journals: {journal_list}")
        
        # Note: Sales and Purchases journals are automatically created by Chart of Accounts
        # We only create Bank, Cash, and Journal Voucher journals
        journals_to_create = [
            {
                'name': 'Bank',
                'code': 'BNK',
                'type': 'bank',
                'company_id': company_id,
                'alias_id': False,
                'purpose': 'Bank account transactions and reconciliation'
            },
            {
                'name': 'Cash',
                'code': 'CSH',
                'type': 'cash',
                'company_id': company_id,
                'alias_id': False,
                'purpose': 'Cash transactions and petty cash entries'
            },
            {
                'name': 'Journal Voucher',
                'code': 'JV',
                'type': 'general',
                'company_id': company_id,
                'alias_id': False,
                'purpose': 'Manual journal entries and adjustments'
            }
        ]
        
        if currency_id:
            for journal in journals_to_create:
                journal['currency_id'] = currency_id
        
        print("Creating essential journals...")
        
        for journal_data in journals_to_create:
            try:
                # Special handling for Journal Voucher - always create it regardless of type
                if journal_data['code'] == 'JV':
                    # Only check by code, not by type
                    if journal_data['code'] in existing_codes:
                        existing = existing_codes[journal_data['code']]
                        print(f"✓ Journal code '{journal_data['code']}' already exists: {existing['name']} (type: {existing['type']})")
                        continue
                else:
                    # For Bank and Cash, skip if type already exists
                    if journal_data['type'] in existing_types:
                        existing = existing_types[journal_data['type']]
                        print(f"✓ Journal type '{journal_data['type']}' already exists: {existing['name']} ({existing['code']})")
                        continue
                    
                    # Also check by code to be extra safe
                    if journal_data['code'] in existing_codes:
                        existing = existing_codes[journal_data['code']]
                        print(f"✓ Journal code '{journal_data['code']}' already exists: {existing['name']} (type: {existing['type']})")
                        continue
                
                # Double-check with database query
                db_existing = models.execute_kw(
                    db, uid, password,
                    'account.journal', 'search_count',
                    [[('code', '=', journal_data['code']), ('company_id', '=', company_id)]]
                )
                
                if db_existing:
                    print(f"✓ Journal {journal_data['code']} ({journal_data['name']}) already exists in database")
                    continue
                
                create_data = {k: v for k, v in journal_data.items() if k != 'purpose'}
                
                journal_id = models.execute_kw(
                    db, uid, password,
                    'account.journal', 'create',
                    [create_data]
                )
                
                if journal_id:
                    created_journals.append({
                        'id': journal_id,
                        'name': journal_data['name'],
                        'code': journal_data['code'],
                        'type': journal_data['type'],
                        'purpose': journal_data['purpose']
                    })
                    print(f"✓ Created journal: {journal_data['name']} ({journal_data['code']}) - ID: {journal_id}")
                    
            except Exception as journal_error:
                print(f"✗ Failed to create journal {journal_data['name']}: {str(journal_error)}")
                # Don't return error, just continue - this journal might already exist
                continue
        
        # Return success even if no journals were created (they might all exist)
        return {
            'success': True,
            'journals': created_journals,
            'existing_count': len(existing_journals),
            'message': f'Created {len(created_journals)} new journals, {len(existing_journals)} already existed'
        }
            
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to create journals: {str(e)}'
        }
    
def configure_taxes_for_company(models, db, uid, password, company_id, is_vat_registered):
    """
    Configure tax settings based on VAT registration status
    
    Args:
        models: Odoo models proxy
        db: Database name
        uid: User ID
        password: API password
        company_id: Company ID
        is_vat_registered: "yes" or "no" string indicating VAT registration status
    
    Returns:
        dict: Result with success status and details
    """
    try:
        print(f"Configuring taxes for company {company_id}, VAT registered: {is_vat_registered}")
        
        results = {
            'success': True,
            'vat_registered': is_vat_registered,
            'updates': []
        }
        
        # Step 1: Configure 19% and 19% S taxes if NOT VAT registered
        if is_vat_registered.lower() == "no":
            non_recoverable_result = configure_non_recoverable_vat(
                models, db, uid, password, company_id
            )
            results['updates'].append(non_recoverable_result)
            
            if not non_recoverable_result['success']:
                results['success'] = False
        
        # Step 2: Configure 19% RC (Reverse Charge) taxes for ALL companies
        reverse_charge_result = configure_reverse_charge_taxes(
            models, db, uid, password, company_id
        )
        results['updates'].append(reverse_charge_result)
        
        if not reverse_charge_result['success']:
            results['success'] = False
        
        return results
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to configure taxes: {str(e)}'
        }

def find_or_create_component_tax_with_grid(models, db, uid, password, company_id, name, amount, account_id, type_tax_use, tax_grid_base, tax_grid_tax):
    """
    Find or create a component tax with proper tax grid configuration
    
    Tax grids in Cyprus:
    - +6: Sales (invoices)
    - +7: Purchases (bills) - base/expenses
    - -1: Output VAT (2201)
    - +4: Input VAT (2202)
    """
    try:
        print(f"\n  Looking for tax: '{name}'...")
        
        # Search for existing tax
        existing_tax = models.execute_kw(
            db, uid, password,
            'account.tax', 'search',
            [[('name', '=', name), ('company_id', '=', company_id)]],
            {'limit': 1}
        )
        
        if existing_tax:
            print(f"  ✓ Found existing tax: {name} (ID: {existing_tax[0]})")
            return {'success': True, 'tax_id': existing_tax[0], 'created': False}
        
        # Create new component tax with tax grid
        print(f"  Creating new tax with tax grid...")
        tax_data = {
            'name': name,
            'amount': amount,
            'amount_type': 'percent',
            'type_tax_use': type_tax_use,
            'company_id': company_id,
            'invoice_repartition_line_ids': [
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'base',
                    'tag_ids': [(6, 0, get_tax_grid_tag_ids(models, db, uid, password, company_id, tax_grid_base))],
                }),
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'tax',
                    'account_id': account_id,
                    'tag_ids': [(6, 0, get_tax_grid_tag_ids(models, db, uid, password, company_id, tax_grid_tax))],
                }),
            ],
            'refund_repartition_line_ids': [
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'base',
                    'tag_ids': [(6, 0, get_tax_grid_tag_ids(models, db, uid, password, company_id, tax_grid_base))],
                }),
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'tax',
                    'account_id': account_id,
                    'tag_ids': [(6, 0, get_tax_grid_tag_ids(models, db, uid, password, company_id, tax_grid_tax))],
                }),
            ],
        }
        
        tax_id = models.execute_kw(
            db, uid, password,
            'account.tax', 'create',
            [tax_data]
        )
        
        print(f"  ✓ Created tax: {name} (ID: {tax_id}) with grids: base={tax_grid_base}, tax={tax_grid_tax}")
        return {'success': True, 'tax_id': tax_id, 'created': True}
        
    except Exception as e:
        print(f"  ❌ Failed: {str(e)}")
        return {'success': False, 'error': str(e)}

def get_tax_grid_tag_ids(models, db, uid, password, company_id, grid_code):
    """
    Get tax report tag IDs for a specific grid code (e.g., '+6', '+7', '-1', '+4')
    """
    try:
        # Search for account report tags with the specific code
        tag_ids = models.execute_kw(
            db, uid, password,
            'account.account.tag', 'search',
            [[('name', 'ilike', grid_code), ('applicability', '=', 'taxes')]],
            {'limit': 1}
        )
        
        if tag_ids:
            print(f"    Found tax grid tag for {grid_code}: {tag_ids[0]}")
            return tag_ids
        else:
            print(f"    ⚠️  No tax grid tag found for {grid_code}")
            return []
            
    except Exception as e:
        print(f"    ⚠️  Error finding tag for {grid_code}: {str(e)}")
        return []


def configure_non_recoverable_vat(models, db, uid, password, company_id):
    """
    Configure 19% and 19% S taxes to use Non Recoverable VAT account (7906)
    with tax grid +7 for both base and tax (expenses)
    """
    try:
        print("\n" + "="*80)
        print("STARTING NON-RECOVERABLE VAT CONFIGURATION")
        print("="*80)
        
        # Find the 7906 account
        print(f"\n[STEP 1] Searching for account 'Non Recoverable VAT on expenses'...")
        account_7906 = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('name', '=', 'Non Recoverable VAT on expenses'), ('company_ids', 'in', [company_id])]],
            {'limit': 1}
        )
        
        if not account_7906:
            account_7906 = models.execute_kw(
                db, uid, password,
                'account.account', 'search',
                [[('code', '=', '7906'), ('company_ids', 'in', [company_id])]],
                {'limit': 1}
            )
        
        if not account_7906:
            return {'success': False, 'error': 'Account 7906 not found'}
        
        account_7906_id = account_7906[0]
        print(f"✓ Found account 7906 with ID: {account_7906_id}")
        
        # Get tax grid tag for +7 (purchases/expenses)
        tax_grid_tag_ids = get_tax_grid_tag_ids(models, db, uid, password, company_id, '+7')
        
        # Update 19% and 19% S taxes for PURCHASES only
        tax_names_to_update = ['19%', '19% S']
        updated_taxes = []
        
        for tax_name in tax_names_to_update:
            print(f"\n[STEP 2] Searching for taxes named '{tax_name}'...")
            
            tax_ids = models.execute_kw(
                db, uid, password,
                'account.tax', 'search',
                [[('name', '=', tax_name), ('company_id', '=', company_id), ('type_tax_use', '=', 'purchase')]]  # Only purchases
            )
            
            if not tax_ids:
                print(f"⚠️  No PURCHASE taxes found with name '{tax_name}'")
                continue
            
            print(f"✓ Found {len(tax_ids)} PURCHASE tax(es): {tax_ids}")
            
            for tax_id in tax_ids:
                tax_info = models.execute_kw(
                    db, uid, password,
                    'account.tax', 'read',
                    [[tax_id]],
                    {'fields': ['name', 'type_tax_use']}
                )[0]
                
                print(f"  Updating {tax_info['name']} ({tax_info['type_tax_use']})...")
                
                # Update with tax grid +7 for both base and tax (expenses)
                update_data = {
                    'invoice_repartition_line_ids': [
                        (5, 0, 0),
                        (0, 0, {
                            'factor_percent': 100,
                            'repartition_type': 'base',
                            'tag_ids': [(6, 0, tax_grid_tag_ids)],  # +7 for base
                        }),
                        (0, 0, {
                            'factor_percent': 100,
                            'repartition_type': 'tax',
                            'account_id': account_7906_id,
                            'tag_ids': [(6, 0, tax_grid_tag_ids)],  # +7 for tax (it's an expense)
                        }),
                    ],
                    'refund_repartition_line_ids': [
                        (5, 0, 0),
                        (0, 0, {
                            'factor_percent': 100,
                            'repartition_type': 'base',
                            'tag_ids': [(6, 0, tax_grid_tag_ids)],
                        }),
                        (0, 0, {
                            'factor_percent': 100,
                            'repartition_type': 'tax',
                            'account_id': account_7906_id,
                            'tag_ids': [(6, 0, tax_grid_tag_ids)],
                        }),
                    ],
                }
                
                models.execute_kw(
                    db, uid, password,
                    'account.tax', 'write',
                    [[tax_id], update_data]
                )
                print(f"  ✓ Updated with account 7906 and tax grid +7")
                
                updated_taxes.append({
                    'id': tax_id,
                    'name': tax_name,
                    'type': tax_info['type_tax_use']
                })
        
        print("\n" + "="*80)
        print("NON-RECOVERABLE VAT CONFIGURATION COMPLETE")
        print("="*80)
        
        if updated_taxes:
            return {
                'success': True,
                'message': f'Configured {len(updated_taxes)} taxes with tax grid +7',
                'taxes_updated': updated_taxes
            }
        else:
            return {'success': False, 'error': 'No taxes updated'}
            
    except Exception as e:
        print(f"\n❌❌❌ EXCEPTION: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {'success': False, 'error': str(e)}


def configure_reverse_charge_taxes(models, db, uid, password, company_id):
    """
    Configure 19% RC (Reverse Charge) taxes as GROUP OF TAXES with proper tax grids
    """
    try:
        print("\n" + "="*80)
        print("STARTING REVERSE CHARGE TAX CONFIGURATION")
        print("="*80)
        
        # Find required accounts
        print(f"\n[STEP 1] Searching for accounts...")
        account_2201 = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('name', '=', 'Output VAT (Sales)'), ('company_ids', 'in', [company_id])]],
            {'limit': 1}
        )
        if not account_2201:
            account_2201 = models.execute_kw(
                db, uid, password,
                'account.account', 'search',
                [[('code', '=', '2201'), ('company_ids', 'in', [company_id])]],
                {'limit': 1}
            )
        
        account_2202 = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[('name', '=', 'Input VAT (Purchases)'), ('company_ids', 'in', [company_id])]],
            {'limit': 1}
        )
        if not account_2202:
            account_2202 = models.execute_kw(
                db, uid, password,
                'account.account', 'search',
                [[('code', '=', '2202'), ('company_ids', 'in', [company_id])]],
                {'limit': 1}
            )
        
        if not account_2201 or not account_2202:
            return {'success': False, 'error': 'Required accounts not found: 2201 or 2202'}
        
        account_2201_id = account_2201[0]
        account_2202_id = account_2202[0]
        print(f"✓ Found Output VAT (2201): {account_2201_id}")
        print(f"✓ Found Input VAT (2202): {account_2202_id}")
        
        # Create component taxes for PURCHASES with correct names and tax grids
        print(f"\n[STEP 2] Creating component taxes for PURCHASES...")
        
        # Reverse Charge -19% (purchases) - Tax grid: +7 base, -1 for 2201
        rc_minus_purchase = find_or_create_component_tax_with_grid(
            models, db, uid, password, company_id,
            name='Reverse Charge -19% (purchases)',
            amount=-19,
            account_id=account_2201_id,
            type_tax_use='purchase',
            tax_grid_base='+7',  # Base on tax grid
            tax_grid_tax='-1'    # Output VAT line
        )
        print(f"  Created/Found: Reverse Charge -19% (purchases) - ID: {rc_minus_purchase.get('tax_id')}")
        
        # Reverse Charge +19% (purchases) - Tax grid: +7 base, +4 for 2202
        rc_plus_purchase = find_or_create_component_tax_with_grid(
            models, db, uid, password, company_id,
            name='Reverse Charge +19% (purchases)',
            amount=19,
            account_id=account_2202_id,
            type_tax_use='purchase',
            tax_grid_base='+7',  # Base on tax grid
            tax_grid_tax='+4'    # Input VAT line
        )
        print(f"  Created/Found: Reverse Charge +19% (purchases) - ID: {rc_plus_purchase.get('tax_id')}")
        
        # Create component taxes for SALES with correct names and tax grids
        print(f"\n[STEP 3] Creating component taxes for SALES...")
        
        # Reverse Charge -19% (sales) - Tax grid: +6 base
        rc_minus_sale = find_or_create_component_tax_with_grid(
            models, db, uid, password, company_id,
            name='Reverse Charge -19% (sales)',
            amount=-19,
            account_id=account_2201_id,
            type_tax_use='sale',
            tax_grid_base='+6',  # Base on tax grid
            tax_grid_tax='+6'    # Tax line (adjust if needed)
        )
        print(f"  Created/Found: Reverse Charge -19% (sales) - ID: {rc_minus_sale.get('tax_id')}")
        
        # Reverse Charge +19% (sales) - Tax grid: +6 base
        rc_plus_sale = find_or_create_component_tax_with_grid(
            models, db, uid, password, company_id,
            name='Reverse Charge +19% (sales)',
            amount=19,
            account_id=account_2202_id,
            type_tax_use='sale',
            tax_grid_base='+6',  # Base on tax grid
            tax_grid_tax='+6'    # Tax line (adjust if needed)
        )
        print(f"  Created/Found: Reverse Charge +19% (sales) - ID: {rc_plus_sale.get('tax_id')}")
        
        if not all([rc_minus_purchase['success'], rc_plus_purchase['success'], 
                    rc_minus_sale['success'], rc_plus_sale['success']]):
            return {'success': False, 'error': 'Failed to create component taxes'}
        
        # Find and update 19% RC taxes to GROUP
        print(f"\n[STEP 4] Converting 19% RC taxes to GROUP OF TAXES...")
        rc_tax_ids = models.execute_kw(
            db, uid, password,
            'account.tax', 'search',
            [[('name', '=', '19% RC'), ('company_id', '=', company_id)]]
        )
        
        if not rc_tax_ids:
            return {'success': False, 'error': 'No 19% RC taxes found'}
        
        updated_rc_taxes = []
        for tax_id in rc_tax_ids:
            tax_info = models.execute_kw(
                db, uid, password,
                'account.tax', 'read',
                [[tax_id]],
                {'fields': ['name', 'type_tax_use']}
            )[0]
            
            print(f"  Converting {tax_info['name']} ({tax_info['type_tax_use']}) to GROUP...")
            
            if tax_info['type_tax_use'] == 'sale':
                component_tax_ids = [rc_minus_sale['tax_id'], rc_plus_sale['tax_id']]
            else:  # purchase
                component_tax_ids = [rc_minus_purchase['tax_id'], rc_plus_purchase['tax_id']]
            
            update_data = {
                'amount_type': 'group',
                'children_tax_ids': [(6, 0, component_tax_ids)],
            }
            
            models.execute_kw(
                db, uid, password,
                'account.tax', 'write',
                [[tax_id], update_data]
            )
            print(f"  ✓ Converted to GROUP with children: {component_tax_ids}")
            
            updated_rc_taxes.append({
                'id': tax_id,
                'name': tax_info['name'],
                'type': tax_info['type_tax_use']
            })
        
        print("\n" + "="*80)
        print("REVERSE CHARGE CONFIGURATION COMPLETE")
        print("="*80)
        
        return {
            'success': True,
            'message': f'Configured {len(updated_rc_taxes)} RC taxes with tax grids',
            'taxes_updated': updated_rc_taxes
        }
            
    except Exception as e:
        print(f"\n❌❌❌ EXCEPTION: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {'success': False, 'error': str(e)}

def find_or_create_component_tax(models, db, uid, password, company_id, name, amount, account_id, type_tax_use):
    """
    Find or create a component tax for use in tax groups
    """
    try:
        print(f"\n  [find_or_create_component_tax] Looking for tax: '{name}' (type: {type_tax_use}, company: {company_id})")
        
        # Search for existing tax
        existing_tax = models.execute_kw(
            db, uid, password,
            'account.tax', 'search',
            [[('name', '=', name), ('company_id', '=', company_id)]],
            {'limit': 1}
        )
        
        if existing_tax:
            print(f"  ✓ Found existing component tax: {name} (ID: {existing_tax[0]})")
            return {
                'success': True,
                'tax_id': existing_tax[0],
                'created': False
            }
        
        # Create new component tax
        print(f"  Component tax not found, creating new one...")
        tax_data = {
            'name': name,
            'amount': amount,
            'amount_type': 'percent',
            'type_tax_use': type_tax_use,
            'company_id': company_id,
            'invoice_repartition_line_ids': [
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'base',
                }),
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'tax',
                    'account_id': account_id,
                }),
            ],
            'refund_repartition_line_ids': [
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'base',
                }),
                (0, 0, {
                    'factor_percent': 100,
                    'repartition_type': 'tax',
                    'account_id': account_id,
                }),
            ],
        }
        
        print(f"  Tax data to create: name={name}, amount={amount}%, type={type_tax_use}, account={account_id}")
        
        try:
            tax_id = models.execute_kw(
                db, uid, password,
                'account.tax', 'create',
                [tax_data]
            )
            
            print(f"  ✓✓ Created component tax: {name} (ID: {tax_id})")
            
            return {
                'success': True,
                'tax_id': tax_id,
                'created': True
            }
        except Exception as create_error:
            print(f"  ❌ Failed to create component tax: {str(create_error)}")
            raise
        
    except Exception as e:
        print(f"  ❌❌ Exception in find_or_create_component_tax: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {
            'success': False,
            'error': f'Failed to find/create component tax {name}: {str(e)}'
        }


def ensure_chart_of_accounts(models, db, uid, password, company_id, country_code=None):
    """
    Initiate chart of accounts installation for the company
    """
    try:
        account_count = models.execute_kw(
            db, uid, password,
            'account.account', 'search_count',
            [[('company_id', '=', company_id)]]
        )
        
        if account_count > 0:
            return {'success': True, 'message': 'Chart of accounts already exists', 'accounts_found': account_count}

        domain = []
        if country_code:
            domain = [('country_id.code', '=', country_code.upper())]
        templates = models.execute_kw(
            db, uid, password,
            'account.chart.template', 'search_read',
            [domain], {'fields': ['id', 'name'], 'limit': 1}
        )
        if not templates:
            templates = models.execute_kw(
                db, uid, password,
                'account.chart.template', 'search_read',
                [[]], {'fields': ['id', 'name'], 'limit': 1}
            )
        if not templates:
            return {'success': False, 'error': 'No chart of accounts template found'}

        template = templates[0]
        print(f"Using chart template: {template['name']} (ID: {template['id']})")
        
        try:
            models.execute_kw(
                db, uid, password,
                'account.chart.template', 'try_loading',
                [[template['id']]], 
                {'company_id': company_id, 'code_digits': 6}
            )
            return {'success': True, 'message': f'Chart of accounts installation initiated with template: {template["name"]}'}
        except Exception as e1:
            try:
                models.execute_kw(
                    db, uid, password,
                    'account.chart.template', 'load_for_current_company',
                    [[template['id']]]
                )
                return {'success': True, 'message': f'Chart of accounts installation initiated with alternate method'}
            except Exception as e2:
                print(f"Warning: Chart of accounts installation may need manual intervention: {str(e2)}")
                return {'success': True, 'message': 'Company created, chart of accounts may need manual setup'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def wait_for_chart_of_accounts_simple(models, db, uid, password, company_id, max_wait_time=60):
    """
    Simplified version that just waits and checks basic account existence
    """
    print(f"Using simplified chart of accounts check for company {company_id}...")
    time.sleep(10)
    
    try:
        account_count = models.execute_kw(
            db, uid, password,
            'account.account', 'search_count',
            [[]]
        )
        
        if account_count > 0:
            return {
                'success': True,
                'message': f'Found {account_count} accounts in system - proceeding',
                'accounts_count': account_count
            }
        else:
            return {
                'success': False,
                'message': 'No accounts found - chart may need manual setup',
                'accounts_count': 0
            }
            
    except Exception as e:
        print(f"Simple account check failed: {e}")
        return {
            'success': True,
            'message': 'Could not verify accounts - proceeding anyway',
            'accounts_count': 0
        }

def get_available_company_fields(models, db, uid, password):
    """Get list of available fields for res.company model"""
    try:
        fields_info = models.execute_kw(
            db, uid, password,
            'res.company', 'fields_get',
            [[]], {'attributes': ['string', 'type']}
        )
        return list(fields_info.keys())
    except Exception as e:
        print(f"Error getting fields: {e}")
        return ['name', 'email', 'phone', 'website', 'vat', 'street', 'city', 'zip', 'country_id', 'currency_id']

def create(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

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

def get_currency_id(models, db, uid, password, currency_code):
    """Get currency ID from currency code"""
    try:
        currency_ids = models.execute_kw(
            db, uid, password,
            'res.currency', 'search',
            [[('name', '=', currency_code.upper())]], {'limit': 1}
        )
        return currency_ids[0] if currency_ids else None
    except Exception:
        return None

def get_state_id(models, db, uid, password, state_name, country_id):
    """Get state ID from state name and country"""
    try:
        state_ids = models.execute_kw(
            db, uid, password,
            'res.country.state', 'search',
            [[('name', '=', state_name), ('country_id', '=', country_id)]], {'limit': 1}
        )
        return state_ids[0] if state_ids else None
    except Exception:
        return None

def list_companies():
    """Get list of all companies"""
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
        
        available_fields = get_available_company_fields(models, db, uid, password)
        safe_fields = [field for field in ['id', 'name', 'email', 'phone', 'currency_id', 'country_id', 'vat', 'website'] if field in available_fields]
        
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], 
            {'fields': safe_fields, 'order': 'name'}
        )
        
        return {
            'success': True,
            'companies': companies,
            'count': len(companies)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def get_company_email_partial(data):
    """Get email of a company by name with partial matching option"""
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        company_name = data['company_name']
        exact_match = data.get('exact_match', False)
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {'success': False, 'error': 'Authentication failed'}
        
        basic_fields = ['id', 'name', 'email']
        
        if exact_match:
            domain = [('name', '=', company_name)]
        else:
            domain = [('name', 'ilike', company_name)]
        
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [domain], 
            {'fields': basic_fields, 'limit': 1}
        )
        
        if not companies:
            match_type = "exact" if exact_match else "partial"
            return {
                'success': False,
                'error': f'No company found with {match_type} match for "{company_name}"'
            }
        
        company = companies[0]
        return {
            'success': True,
            'company_name': company.get('name'),
            'email': company.get('email'),
            'company_id': company.get('id'),
            'match_type': 'exact' if exact_match else 'partial'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def list_company_journals(company_id):
    """List all journals for a specific company"""
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
        
        journals = models.execute_kw(
            db, uid, password,
            'account.journal', 'search_read',
            [[('company_id', '=', company_id)]], 
            {'fields': ['id', 'name', 'code', 'type'], 'order': 'type, name'}
        )
        
        return {
            'success': True,
            'company_id': company_id,
            'journals': journals,
            'count': len(journals)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def create_journals_for_existing_company(company_id):
    """Create essential journals for an existing company"""
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
        
        company_info = models.execute_kw(
            db, uid, password,
            'res.company', 'read',
            [[company_id]], 
            {'fields': ['id', 'name', 'currency_id']}
        )
        
        if not company_info:
            return {
                'success': False,
                'error': f'Company with ID {company_id} not found'
            }
        
        company_info = company_info[0]
        currency_id = company_info.get('currency_id')[0] if company_info.get('currency_id') else None
        
        print(f"Checking Chart of Accounts for company {company_id}...")
        chart_ready = wait_for_chart_of_accounts(models, db, uid, password, company_id, max_wait_time=60)
        
        if not chart_ready['success']:
            return {
                'success': False,
                'error': f'Chart of Accounts not ready: {chart_ready["message"]}'
            }
        
        result = create_essential_journals(models, db, uid, password, company_id, currency_id)
        
        if result['success']:
            result['company_name'] = company_info['name']
            result['chart_status'] = chart_ready['message']
            
        return result
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def list_available_currencies():
    """List all available currencies in the Odoo database"""
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
        
        currencies = models.execute_kw(
            db, uid, password,
            'res.currency', 'search_read',
            [[('active', '=', True)]], 
            {'fields': ['id', 'name', 'symbol', 'full_name'], 'order': 'name'}
        )
        
        return {
            'success': True,
            'currencies': currencies,
            'count': len(currencies)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def list_available_countries():
    """List all available countries in the Odoo database"""
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
        
        countries = models.execute_kw(
            db, uid, password,
            'res.country', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'code'], 'order': 'name'}
        )
        
        return {
            'success': True,
            'countries': countries,
            'count': len(countries)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }