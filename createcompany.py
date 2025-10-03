import xmlrpc.client
import os
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
    Create company from HTTP request data following Odoo documentation
    
    Expected data format (based on your form):
    {
        "name": "Company Name",                    # required - Company Name
        "email": "contact@company.com",           # optional - Email
        "phone": "+1234567890",                   # optional - Phone
        "website": "https://website.com",         # optional - Website
        "vat": "VAT123456",                       # optional - Tax ID
        "company_registry": "REG123456",          # optional - Company ID (registry number)
        "street": "123 Main St",                  # optional - Address
        "city": "City Name",                      # optional - City
        "zip": "12345",                           # optional - ZIP
        "state": "State Name",                    # optional - State
        "country_code": "CY",                     # optional - Country (ISO code), defaults to "CY"
        "currency_code": "EUR"                    # optional - Currency (ISO code), defaults to "EUR"
    }
    """
    
    # Validate required fields
    if not data.get('name'):
        return {
            'success': False,
            'error': 'name is required'
        }
    
    # ALWAYS default to Cyprus and EUR - force these values regardless of input
    # This ensures the company is always created for Cyprus with EUR currency
    country_code = 'CY'  # Always use Cyprus
    currency_code = 'EUR'  # Always use Euro
    
    # Update the data object to reflect the forced defaults
    data['country_code'] = country_code
    data['currency_code'] = currency_code
    
    # Handle VAT number - remove CY prefix if present (Cyprus is always the country)
    # Odoo expects VAT without country prefix since country is set separately
    if data.get('vat'):
        vat = data['vat'].strip().upper()
        if vat.startswith('CY'):
            vat = vat[2:]  # Remove CY prefix
            print(f"Normalized VAT: removed 'CY' prefix, using: {vat}")
        data['vat'] = vat
    
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
                # Remove the text state field if we have state_id
                company_data.pop('state', None)
        
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

        # Initiate Chart of Accounts installation (use Cyprus for chart selection)
        chart_result = ensure_chart_of_accounts(models, db, uid, password, company_id, country_code)
        print(f"Chart of accounts installation initiated: {chart_result.get('message', 'In progress')}")

        # Wait for Chart of Accounts to be ready before creating journals
        print("Waiting for Chart of Accounts installation to complete...")
        chart_ready = wait_for_chart_of_accounts(models, db, uid, password, company_id, max_wait_time=120)
        
        # If the advanced method fails, try the simple fallback
        if not chart_ready['success'] and 'company_id' in str(chart_ready.get('message', '')):
            print("Falling back to simplified chart checking method...")
            chart_ready = wait_for_chart_of_accounts_simple(models, db, uid, password, company_id)
        
        if not chart_ready['success']:
            print(f"Warning: {chart_ready['message']}")
            # Continue anyway, but note that some journals might not be created
        else:
            print("Chart of Accounts is ready!")

        # Create custom accounts after Chart of Accounts is ready
        custom_accounts_result = create_custom_accounts(models, db, uid, password, company_id)
        if custom_accounts_result['success']:
            print(f"Successfully created {len(custom_accounts_result['accounts'])} custom accounts")
        else:
            print(f"Custom accounts creation issue: {custom_accounts_result.get('error', 'Unknown error')}")

        # Create essential journals after Chart of Accounts is ready
        journals_result = create_essential_journals(models, db, uid, password, company_id, currency_id)
        if journals_result['success']:
            print(f"Successfully created {len(journals_result['journals'])} journals")
        else:
            print(f"Journal creation issue: {journals_result.get('error', 'Unknown error')}")

        # Get created company information using only safe/available fields
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
        
        # Prepare response with safe field access
        response = {
            'success': True,
            'company_id': company_id,
            'company_name': company_info['name'],
            'message': 'Company created successfully'
        }
        
        # Add default values info to response (only if defaults were actually applied)
        if data.get('country_code') != country_code:
            response['country_default_applied'] = f'Used default country: {country_code}'
        if data.get('currency_code') != currency_code:
            response['currency_default_applied'] = f'Used default currency: {currency_code}'
        
        # Add chart of accounts status
        response['chart_of_accounts_status'] = chart_ready['message']
        
        # Add custom accounts status to response
        if custom_accounts_result['success']:
            response['custom_accounts_created'] = custom_accounts_result['accounts']
            response['message'] += f' with {len(custom_accounts_result["accounts"])} custom accounts'
        else:
            response['custom_accounts_warning'] = custom_accounts_result.get('error')
        
        # Add journal creation status to response
        if journals_result['success']:
            response['journals_created'] = journals_result['journals']
            response['message'] += f' and {len(journals_result["journals"])} essential journals'
        else:
            response['journal_warning'] = journals_result['error']
        
        # Add currency warning if exists
        if currency_warning:
            response['currency_warning'] = currency_warning
        
        # Add optional fields to response if they exist
        optional_response_fields = {
            'email': 'email',
            'phone': 'phone', 
            'website': 'website',
            'vat': 'vat',
            'company_registry': 'company_registry',
            'street': 'street',
            'city': 'city',
            'zip': 'zip'
        }
        
        for response_key, odoo_field in optional_response_fields.items():
            if odoo_field in company_info:
                response[response_key] = company_info.get(odoo_field)
        
        # Handle relational fields safely
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
    """
    try:
        created_journals = []
        
        journals_to_create = [
            {
                'name': 'Sales',
                'code': 'SAL',
                'type': 'sale',
                'company_id': company_id,
                'alias_id': False,
                'purpose': 'Customer invoices and sales transactions'
            },
            {
                'name': 'Purchases',
                'code': 'PUR',
                'type': 'purchase',
                'company_id': company_id,
                'alias_id': False,
                'purpose': 'Vendor bills and purchase transactions'
            },
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
                existing = models.execute_kw(
                    db, uid, password,
                    'account.journal', 'search_count',
                    [[('code', '=', journal_data['code']), ('company_id', '=', company_id)]]
                )
                
                if existing:
                    print(f"Journal {journal_data['code']} ({journal_data['name']}) already exists for company {company_id}")
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
                continue
        
        if created_journals:
            return {
                'success': True,
                'journals': created_journals,
                'message': f'Created {len(created_journals)} essential journals'
            }
        else:
            return {
                'success': False,
                'error': 'No journals were created - they may already exist'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to create journals: {str(e)}'
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