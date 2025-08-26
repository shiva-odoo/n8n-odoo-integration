import xmlrpc.client
import os
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
        "country_code": "IN",                     # optional - Country (ISO code)
        "currency_code": "INR"                    # optional - Currency (ISO code)
    }
    """
    
    # Validate required fields
    if not data.get('name'):
        return {
            'success': False,
            'error': 'name is required'
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
        
        # Get available fields for res.company model to avoid field errors
        available_fields = get_available_company_fields(models, db, uid, password)
        
        # Prepare company data with only available fields
        company_data = {
            'name': data['name'],
        }
        
        # Add optional fields only if they exist in this Odoo version
        field_mapping = {
            'email': data.get('email'),
            'phone': data.get('phone'),
            'website': data.get('website'),
            'vat': data.get('vat'),                    # Tax ID
            'company_registry': data.get('company_registry'),  # Company ID
            'street': data.get('street'),
            'city': data.get('city'),
            'zip': data.get('zip'),
            'state': data.get('state')
        }
        
        # Only add fields that exist and have values
        for field, value in field_mapping.items():
            if value and field in available_fields:
                company_data[field] = value
        
        # Handle country (if country_code provided and country_id field exists)
        if data.get('country_code') and 'country_id' in available_fields:
            country_id = get_country_id(models, db, uid, password, data['country_code'])
            if country_id:
                company_data['country_id'] = country_id
            else:
                return {
                    'success': False,
                    'error': f'Country code "{data["country_code"]}" not found'
                }
        
        # Handle currency (if currency_code provided and currency_id field exists)
        currency_id = None
        currency_warning = None
        if data.get('currency_code') and 'currency_id' in available_fields:
            currency_id = get_currency_id(models, db, uid, password, data['currency_code'])
            if currency_id:
                company_data['currency_id'] = currency_id
            else:
                currency_warning = f'Currency code "{data["currency_code"]}" not found - company created without specific currency'
        
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
        
        # Set up complete accounting structure for the new company
        accounting_setup_result = setup_company_accounting(models, db, uid, password, company_id, currency_id)
        
        if not accounting_setup_result['success']:
            # Company was created but accounting setup failed
            print(f"Warning: Company created but accounting setup failed: {accounting_setup_result['error']}")
        
        # Get created company information using only safe/available fields
        safe_read_fields = [
            'name', 'email', 'phone', 'website', 'vat', 'company_registry',
            'currency_id', 'country_id', 'street', 'city', 'zip'
        ]
        # Filter to only fields that actually exist
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
        
        # Add accounting setup status to response
        if accounting_setup_result['success']:
            response['accounting_setup'] = accounting_setup_result
            response['message'] += ' with complete accounting setup'
        else:
            response['accounting_warning'] = accounting_setup_result['error']
        
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

def setup_company_accounting(models, db, uid, password, company_id, currency_id=None):
    """
    Set up complete accounting structure for a new company including:
    - Basic chart of accounts
    - Default accounts configuration
    - Essential journals with proper accounts
    - Fiscal settings
    """
    try:
        setup_results = {
            'accounts_created': [],
            'journals_created': [],
            'company_defaults_set': False,
            'warnings': []
        }
        
        # Step 1: Create essential accounts
        accounts_result = create_essential_accounts(models, db, uid, password, company_id, currency_id)
        if accounts_result['success']:
            setup_results['accounts_created'] = accounts_result['accounts']
        else:
            setup_results['warnings'].append(f"Account creation: {accounts_result['error']}")
        
        # Step 2: Set company default accounts
        if accounts_result['success'] and accounts_result['account_ids']:
            defaults_result = set_company_default_accounts(models, db, uid, password, company_id, accounts_result['account_ids'])
            setup_results['company_defaults_set'] = defaults_result['success']
            if not defaults_result['success']:
                setup_results['warnings'].append(f"Default accounts: {defaults_result['error']}")
        
        # Step 3: Create journals with proper account configuration
        journals_result = create_complete_journals(models, db, uid, password, company_id, currency_id, accounts_result.get('account_ids', {}))
        if journals_result['success']:
            setup_results['journals_created'] = journals_result['journals']
        else:
            setup_results['warnings'].append(f"Journal creation: {journals_result['error']}")
        
        # Step 4: Set up basic fiscal configuration
        fiscal_result = setup_basic_fiscal_config(models, db, uid, password, company_id)
        if not fiscal_result['success']:
            setup_results['warnings'].append(f"Fiscal config: {fiscal_result['error']}")
        
        # Determine overall success
        success = (accounts_result['success'] and 
                  setup_results['company_defaults_set'] and 
                  journals_result['success'])
        
        return {
            'success': success,
            'details': setup_results,
            'message': 'Complete accounting setup completed' if success else 'Partial accounting setup completed with warnings'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to set up accounting: {str(e)}'
        }

def create_essential_accounts(models, db, uid, password, company_id, currency_id=None):
    """
    Create essential accounts needed for basic operations
    """
    try:
        created_accounts = []
        account_ids = {}
        
        # Define essential accounts to create
        accounts_to_create = [
            {
                'code': '1100',
                'name': 'Account Receivable',
                'user_type_id': get_account_type_id(models, db, uid, password, 'asset_receivable'),
                'reconcile': True,
                'company_id': company_id,
            },
            {
                'code': '2100',
                'name': 'Account Payable',
                'user_type_id': get_account_type_id(models, db, uid, password, 'liability_payable'),
                'reconcile': True,
                'company_id': company_id,
            },
            {
                'code': '4000',
                'name': 'Product Sales',
                'user_type_id': get_account_type_id(models, db, uid, password, 'income'),
                'company_id': company_id,
            },
            {
                'code': '5000',
                'name': 'Product Purchases',
                'user_type_id': get_account_type_id(models, db, uid, password, 'expense'),
                'company_id': company_id,
            },
            {
                'code': '1000',
                'name': 'Bank Current Account',
                'user_type_id': get_account_type_id(models, db, uid, password, 'asset_current'),
                'company_id': company_id,
            }
        ]
        
        # Add currency if specified
        if currency_id:
            for account in accounts_to_create:
                account['currency_id'] = currency_id
        
        # Create each account
        for account_data in accounts_to_create:
            try:
                # Check if account with this code already exists for this company
                existing = models.execute_kw(
                    db, uid, password,
                    'account.account', 'search_count',
                    [[('code', '=', account_data['code']), ('company_id', '=', company_id)]]
                )
                
                if existing:
                    # Get existing account ID
                    existing_ids = models.execute_kw(
                        db, uid, password,
                        'account.account', 'search',
                        [[('code', '=', account_data['code']), ('company_id', '=', company_id)]], {'limit': 1}
                    )
                    if existing_ids:
                        account_ids[account_data['name']] = existing_ids[0]
                    continue
                
                account_id = models.execute_kw(
                    db, uid, password,
                    'account.account', 'create',
                    [account_data]
                )
                
                if account_id:
                    created_accounts.append({
                        'id': account_id,
                        'name': account_data['name'],
                        'code': account_data['code']
                    })
                    account_ids[account_data['name']] = account_id
                    print(f"Created account: {account_data['name']} (ID: {account_id})")
                    
            except Exception as account_error:
                print(f"Failed to create account {account_data['name']}: {str(account_error)}")
                continue
        
        return {
            'success': len(account_ids) >= 2,  # At least receivable and payable
            'accounts': created_accounts,
            'account_ids': account_ids,
            'message': f'Created/found {len(account_ids)} essential accounts'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to create accounts: {str(e)}'
        }

def set_company_default_accounts(models, db, uid, password, company_id, account_ids):
    """
    Set default accounts for the company (receivable, payable, etc.)
    """
    try:
        update_data = {}
        
        # Set default receivable account
        if 'Account Receivable' in account_ids:
            update_data['account_default_receivable_id'] = account_ids['Account Receivable']
        
        # Set default payable account
        if 'Account Payable' in account_ids:
            update_data['account_default_payable_id'] = account_ids['Account Payable']
        
        if update_data:
            models.execute_kw(
                db, uid, password,
                'res.company', 'write',
                [[company_id], update_data]
            )
            
            return {
                'success': True,
                'message': f'Set {len(update_data)} default accounts for company'
            }
        else:
            return {
                'success': False,
                'error': 'No default accounts could be set - missing receivable or payable accounts'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to set default accounts: {str(e)}'
        }

def create_complete_journals(models, db, uid, password, company_id, currency_id=None, account_ids=None):
    """
    Create essential journals with proper default accounts configured
    """
    try:
        created_journals = []
        account_ids = account_ids or {}
        
        # Define essential journals with their default accounts
        journals_to_create = [
            {
                'name': 'Customer Invoices',
                'code': 'INV',
                'type': 'sale',
                'company_id': company_id,
                'default_account_id': account_ids.get('Product Sales'),
            },
            {
                'name': 'Vendor Bills',
                'code': 'BILL',
                'type': 'purchase', 
                'company_id': company_id,
                'default_account_id': account_ids.get('Product Purchases'),
            },
            {
                'name': 'Bank',
                'code': 'BNK1',
                'type': 'bank',
                'company_id': company_id,
                'default_account_id': account_ids.get('Bank Current Account'),
            },
            {
                'name': 'Miscellaneous Operations',
                'code': 'MISC',
                'type': 'general',
                'company_id': company_id,
            }
        ]
        
        # Add currency if specified
        if currency_id:
            for journal in journals_to_create:
                journal['currency_id'] = currency_id
        
        # Create each journal
        for journal_data in journals_to_create:
            try:
                # Remove default_account_id if it's None to avoid errors
                if journal_data.get('default_account_id') is None:
                    journal_data.pop('default_account_id', None)
                
                # Check if journal with this code already exists for this company
                existing = models.execute_kw(
                    db, uid, password,
                    'account.journal', 'search_count',
                    [[('code', '=', journal_data['code']), ('company_id', '=', company_id)]]
                )
                
                if existing:
                    print(f"Journal {journal_data['code']} already exists for company {company_id}")
                    continue
                
                journal_id = models.execute_kw(
                    db, uid, password,
                    'account.journal', 'create',
                    [journal_data]
                )
                
                if journal_id:
                    created_journals.append({
                        'id': journal_id,
                        'name': journal_data['name'],
                        'code': journal_data['code'],
                        'type': journal_data['type']
                    })
                    print(f"Created journal: {journal_data['name']} (ID: {journal_id})")
                    
            except Exception as journal_error:
                print(f"Failed to create journal {journal_data['name']}: {str(journal_error)}")
                continue
        
        return {
            'success': len(created_journals) > 0,
            'journals': created_journals,
            'message': f'Created {len(created_journals)} journals'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to create journals: {str(e)}'
        }

def setup_basic_fiscal_config(models, db, uid, password, company_id):
    """
    Set up basic fiscal configuration for the company
    """
    try:
        # Set basic fiscal year settings
        fiscal_data = {
            'fiscalyear_last_day': 31,
            'fiscalyear_last_month': '12',  # December
        }
        
        # Try to update fiscal settings - this might not be available in all versions
        try:
            models.execute_kw(
                db, uid, password,
                'res.company', 'write',
                [[company_id], fiscal_data]
            )
        except:
            pass  # Not critical if this fails
        
        return {
            'success': True,
            'message': 'Basic fiscal configuration set'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to set fiscal configuration: {str(e)}'
        }

def get_account_type_id(models, db, uid, password, account_type_xmlid):
    """
    Get account type ID from XML ID or type name
    """
    try:
        # Try to get by XML ID first (more reliable)
        xml_id_mappings = {
            'asset_receivable': 'account.data_account_type_receivable',
            'liability_payable': 'account.data_account_type_payable',
            'income': 'account.data_account_type_revenue',
            'expense': 'account.data_account_type_expenses',
            'asset_current': 'account.data_account_type_current_assets'
        }
        
        if account_type_xmlid in xml_id_mappings:
            try:
                type_data = models.execute_kw(
                    db, uid, password,
                    'ir.model.data', 'get_object_reference',
                    [xml_id_mappings[account_type_xmlid].split('.')[0], xml_id_mappings[account_type_xmlid].split('.')[1]]
                )
                return type_data[1]
            except:
                pass
        
        # Fallback: search by type name patterns
        type_name_patterns = {
            'asset_receivable': ['Receivable', 'receivable'],
            'liability_payable': ['Payable', 'payable'],
            'income': ['Income', 'Revenue', 'income', 'revenue'],
            'expense': ['Expense', 'expenses', 'expense'],
            'asset_current': ['Current Assets', 'current', 'asset']
        }
        
        if account_type_xmlid in type_name_patterns:
            for pattern in type_name_patterns[account_type_xmlid]:
                type_ids = models.execute_kw(
                    db, uid, password,
                    'account.account.type', 'search',
                    [[('name', 'ilike', pattern)]], {'limit': 1}
                )
                if type_ids:
                    return type_ids[0]
        
        # Final fallback: get any type (better than failing)
        type_ids = models.execute_kw(
            db, uid, password,
            'account.account.type', 'search',
            [[]], {'limit': 1}
        )
        return type_ids[0] if type_ids else 1
        
    except Exception as e:
        print(f"Error getting account type for {account_type_xmlid}: {e}")
        return 1  # Fallback to ID 1

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
        # Return basic fields that should exist in most Odoo versions
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
    """Get list of all companies for reference"""
    
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
        
        # Get available fields first
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
    """
    Get email of a company by name with partial matching option
    
    Args:
        company_name (str): The company name to search for
        exact_match (bool): If True, uses exact match; if False, uses partial match (default: False)
    
    Returns:
        dict: Success status and company data or error message
    """
    
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        company_name = data['company_name']
        exact_match = data.get('exact_match', False)  # Default to partial match
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {'success': False, 'error': 'Authentication failed'}
        
        # Define basic fields that should exist in res.company
        basic_fields = ['id', 'name', 'email']
        
        # Choose search operator based on exact_match parameter
        if exact_match:
            domain = [('name', '=', company_name)]
        else:
            domain = [('name', 'ilike', company_name)]  # Case-insensitive partial match
        
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
    """
    List all journals for a specific company
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

def fix_existing_company_accounting(company_id):
    """
    Fix accounting setup for an existing company that was created without proper setup
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
        
        # Get company info to check if it exists and get currency
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
        
        # Set up complete accounting structure
        result = setup_company_accounting(models, db, uid, password, company_id, currency_id)
        
        if result['success']:
            result['company_name'] = company_info['name']
            result['message'] = f'Fixed accounting setup for company: {company_info["name"]}'
            
        return result
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def list_available_currencies():
    """
    List all available currencies in the Odoo database
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
    """
    List all available countries in the Odoo database
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