import xmlrpc.client
import os
import time
import re

# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def levenshtein_distance(s1, s2):
    """
    Calculate the Levenshtein distance between two strings.
    Returns the minimum number of single-character edits needed to transform s1 into s2.
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

def normalize_company_name(name):
    """
    Normalize company name for better comparison by:
    - Converting to lowercase
    - Removing common business suffixes
    - Removing extra whitespace and punctuation
    - Expanding common abbreviations
    """
    if not name:
        return ""
    
    # Convert to lowercase
    normalized = name.lower().strip()
    
    # Remove common business entity suffixes and abbreviations
    business_suffixes = [
        r'\b(inc\.?|incorporated)\b',
        r'\b(corp\.?|corporation)\b', 
        r'\b(ltd\.?|limited)\b',
        r'\b(llc\.?|l\.l\.c\.?)\b',
        r'\b(llp\.?|l\.l\.p\.?)\b',
        r'\b(plc\.?|p\.l\.c\.?)\b',
        r'\b(co\.?|company)\b',
        r'\b(pvt\.?|private)\b',
        r'\b(pte\.?|pte)\b',
        r'\b(gmbh\.?)\b',
        r'\b(sa\.?|s\.a\.?)\b',
        r'\b(ag\.?|a\.g\.?)\b',
        r'\b(bv\.?|b\.v\.?)\b',
        r'\b(nv\.?|n\.v\.?)\b',
        r'\b(srl\.?|s\.r\.l\.?)\b',
        r'\b(spa\.?|s\.p\.a\.?)\b',
        r'\b(sas\.?|s\.a\.s\.?)\b',
        r'\b(sarl\.?|s\.a\.r\.l\.?)\b'
    ]
    
    for suffix in business_suffixes:
        normalized = re.sub(suffix, '', normalized)
    
    # Remove extra punctuation and whitespace
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized

def calculate_similarity(s1, s2):
    """
    Calculate similarity percentage between two strings using Levenshtein distance.
    Returns a value between 0 and 100 (100 being identical).
    """
    if not s1 or not s2:
        return 0.0
    
    # Normalize both strings
    norm_s1 = normalize_company_name(s1)
    norm_s2 = normalize_company_name(s2)
    
    if not norm_s1 or not norm_s2:
        return 0.0
    
    if norm_s1 == norm_s2:
        return 100.0
    
    # Calculate Levenshtein distance
    distance = levenshtein_distance(norm_s1, norm_s2)
    max_len = max(len(norm_s1), len(norm_s2))
    
    # Convert to similarity percentage
    similarity = ((max_len - distance) / max_len) * 100
    return max(0.0, similarity)

def jaro_winkler_similarity(s1, s2):
    """
    Calculate Jaro-Winkler similarity between two strings.
    Good for detecting typos and similar names.
    """
    def jaro_distance(s1, s2):
        if s1 == s2:
            return 1.0
        
        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0
        
        match_window = max(len1, len2) // 2 - 1
        match_window = max(0, match_window)
        
        s1_matches = [False] * len1
        s2_matches = [False] * len2
        
        matches = 0
        transpositions = 0
        
        # Find matches
        for i in range(len1):
            start = max(0, i - match_window)
            end = min(i + match_window + 1, len2)
            for j in range(start, end):
                if s2_matches[j] or s1[i] != s2[j]:
                    continue
                s1_matches[i] = s2_matches[j] = True
                matches += 1
                break
        
        if matches == 0:
            return 0.0
        
        # Find transpositions
        k = 0
        for i in range(len1):
            if not s1_matches[i]:
                continue
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1
        
        jaro = (matches / len1 + matches / len2 + (matches - transpositions / 2) / matches) / 3
        return jaro
    
    # Normalize strings
    norm_s1 = normalize_company_name(s1)
    norm_s2 = normalize_company_name(s2)
    
    if not norm_s1 or not norm_s2:
        return 0.0
    
    jaro = jaro_distance(norm_s1, norm_s2)
    
    # Apply Winkler prefix bonus
    prefix_len = 0
    for i in range(min(len(norm_s1), len(norm_s2), 4)):
        if norm_s1[i] == norm_s2[i]:
            prefix_len += 1
        else:
            break
    
    return (jaro + (0.1 * prefix_len * (1 - jaro))) * 100

def check_similar_companies(models, db, uid, password, company_name, similarity_threshold=85):
    """
    Check for existing companies with similar names using fuzzy string matching.
    
    Args:
        models: Odoo models proxy
        db: Database name
        uid: User ID
        password: API password
        company_name: New company name to check
        similarity_threshold: Minimum similarity percentage to consider a match (0-100)
    
    Returns:
        dict: Contains 'has_similar', 'similar_companies' list, and 'exact_match' boolean
    """
    try:
        # Get all existing company names
        existing_companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], 
            {'fields': ['id', 'name']}
        )
        
        similar_companies = []
        exact_match = False
        
        for company in existing_companies:
            existing_name = company.get('name', '')
            if not existing_name:
                continue
            
            # Check for exact match (case insensitive)
            if company_name.lower().strip() == existing_name.lower().strip():
                exact_match = True
                similar_companies.append({
                    'id': company['id'],
                    'name': existing_name,
                    'similarity': 100.0,
                    'match_type': 'exact'
                })
                continue
            
            # Calculate similarity using both algorithms
            levenshtein_sim = calculate_similarity(company_name, existing_name)
            jaro_winkler_sim = jaro_winkler_similarity(company_name, existing_name)
            
            # Use the higher of the two similarities
            max_similarity = max(levenshtein_sim, jaro_winkler_sim)
            
            if max_similarity >= similarity_threshold:
                match_type = 'jaro_winkler' if jaro_winkler_sim > levenshtein_sim else 'levenshtein'
                similar_companies.append({
                    'id': company['id'],
                    'name': existing_name,
                    'similarity': round(max_similarity, 2),
                    'match_type': match_type,
                    'levenshtein_similarity': round(levenshtein_sim, 2),
                    'jaro_winkler_similarity': round(jaro_winkler_sim, 2)
                })
        
        # Sort by similarity (highest first)
        similar_companies.sort(key=lambda x: x['similarity'], reverse=True)
        
        return {
            'has_similar': len(similar_companies) > 0,
            'similar_companies': similar_companies,
            'exact_match': exact_match,
            'total_checked': len(existing_companies)
        }
        
    except Exception as e:
        print(f"Error checking similar companies: {str(e)}")
        return {
            'has_similar': False,
            'similar_companies': [],
            'exact_match': False,
            'error': str(e)
        }

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
        "currency_code": "INR",                   # optional - Currency (ISO code)
        "similarity_threshold": 85,               # optional - Similarity threshold for duplicate detection (0-100)
        "allow_similar": False                    # optional - Whether to allow creation despite similar names
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

        # Enhanced duplicate checking with fuzzy matching
        similarity_threshold = data.get('similarity_threshold', 85)  # Default 85% similarity
        allow_similar = data.get('allow_similar', False)
        
        print(f"Checking for similar companies with threshold: {similarity_threshold}%")
        
        similar_check = check_similar_companies(
            models, db, uid, password, 
            data['name'], 
            similarity_threshold
        )
        
        if similar_check.get('error'):
            print(f"Warning: Could not check for similar companies: {similar_check['error']}")
            # Continue with basic exact match check as fallback
            existing_company = models.execute_kw(
                db, uid, password,
                'res.company', 'search_count',
                [[('name', '=', data['name'])]]
            )
            if existing_company:
                return {
                    'success': False,
                    'error': f'Company with name "{data["name"]}" already exists (exact match)'
                }
        else:
            # Check results from fuzzy matching
            if similar_check['exact_match']:
                return {
                    'success': False,
                    'error': f'Company with name "{data["name"]}" already exists (exact match)',
                    'similar_companies': similar_check['similar_companies']
                }
            
            if similar_check['has_similar'] and not allow_similar:
                similar_companies = similar_check['similar_companies']
                error_msg = f'Found {len(similar_companies)} similar company name(s). '
                error_msg += f'Most similar: "{similar_companies[0]["name"]}" '
                error_msg += f'({similar_companies[0]["similarity"]}% similarity). '
                error_msg += 'Set "allow_similar": true to create anyway.'
                
                return {
                    'success': False,
                    'error': error_msg,
                    'similar_companies': similar_companies,
                    'suggestion': 'Consider using a more unique company name or set allow_similar=true'
                }
            
            # Log if similar companies found but creation is allowed
            if similar_check['has_similar'] and allow_similar:
                print(f"Warning: Found {len(similar_check['similar_companies'])} similar companies, but proceeding due to allow_similar=true")

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

        print(f"Company created successfully with ID: {company_id}")

        # Initiate Chart of Accounts installation
        chart_result = ensure_chart_of_accounts(models, db, uid, password, company_id, data.get('country_code'))
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
        
        # Add similarity check results to response for transparency
        if similar_check.get('has_similar') and allow_similar:
            response['similarity_warning'] = {
                'message': f'Company created despite {len(similar_check["similar_companies"])} similar names found',
                'similar_companies': similar_check['similar_companies'][:3]  # Include top 3 matches
            }
        
        # Add chart of accounts status
        response['chart_of_accounts_status'] = chart_ready['message']
        
        # Add journal creation status to response
        if journals_result['success']:
            response['journals_created'] = journals_result['journals']
            response['message'] += f' with {len(journals_result["journals"])} essential journals'
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

def check_company_similarity(data):
    """
    Standalone function to check for similar company names without creating a company.
    Useful for pre-validation in forms.
    
    Expected data format:
    {
        "name": "Company Name",           # required
        "similarity_threshold": 85        # optional, default 85
    }
    """
    if not data.get('name'):
        return {
            'success': False,
            'error': 'name is required'
        }
    
    try:
        similarity_threshold = data.get('similarity_threshold', 85)
        
        similar_check = check_similar_companies(
            data['name'], 
            similarity_threshold
        )
        
        if similar_check.get('error'):
            return {
                'success': False,
                'error': similar_check['error']
            }
        
        return {
            'success': True,
            'company_name': data['name'],
            'similarity_threshold': similarity_threshold,
            'exact_match': similar_check.get('exact_match', False),
            'has_similar': similar_check.get('has_similar', False),
            'similar_companies': similar_check.get('similar_companies', []),
            'total_companies_checked': similar_check.get('total_checked', 0),
            'recommendation': 'safe_to_create' if not similar_check.get('has_similar') else 'review_similarities'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# [Rest of the functions remain the same - wait_for_chart_of_accounts, create_essential_journals, etc.]

def wait_for_chart_of_accounts(models, db, uid, password, company_id, max_wait_time=120, check_interval=5):
    """
    Wait for Chart of Accounts to be installed by checking if accounts exist
    
    Args:
        models: Odoo models proxy
        db: Database name
        uid: User ID
        password: API password
        company_id: Company ID to check
        max_wait_time: Maximum time to wait in seconds (default: 120)
        check_interval: Time between checks in seconds (default: 5)
    
    Returns:
        dict: Success status and message
    """
    start_time = time.time()
    min_accounts_required = 10  # Minimum number of accounts that should exist in a proper chart
    
    print(f"Waiting for Chart of Accounts installation (max {max_wait_time} seconds)...")
    
    # First, check what fields are available on account.account
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
            # Check if accounts exist - use different approaches based on field availability
            if has_company_id:
                # Use company_id filter if available
                account_count = models.execute_kw(
                    db, uid, password,
                    'account.account', 'search_count',
                    [[('company_id', '=', company_id)]]
                )
            else:
                # Fallback: get all accounts and filter manually or use different approach
                # First try to get accounts without company filter
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
                # Try to check essential account types if possible
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
                    
                    # Success - accounts are ready
                    elapsed_time = int(time.time() - start_time)
                    return {
                        'success': True,
                        'message': f'Chart of Accounts ready with {account_count} accounts (took {elapsed_time}s)',
                        'accounts_count': account_count
                    }
                    
                except Exception as type_check_error:
                    print(f"Could not check account types: {type_check_error}")
                    # If we can't check types but have enough accounts, consider it ready
                    elapsed_time = int(time.time() - start_time)
                    return {
                        'success': True,
                        'message': f'Chart of Accounts ready with {account_count} accounts (took {elapsed_time}s)',
                        'accounts_count': account_count
                    }
            
            # Wait before next check
            time.sleep(check_interval)
            
        except Exception as e:
            print(f"Error checking accounts: {str(e)}")
            time.sleep(check_interval)
    
    # Timeout reached
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
    Create essential journals for a new company (Sales, Purchase, Bank, Cash, Miscellaneous)
    """
    try:
        created_journals = []
        journals_to_create = [
            {
                'name': 'Sales',
                'code': 'SAL',
                'type': 'sale',
                'company_id': company_id,
            },
            {
                'name': 'Purchases',
                'code': 'PUR',
                'type': 'purchase',
                'company_id': company_id,
            },
            {
                'name': 'Bank',
                'code': 'BNK',
                'type': 'bank',
                'company_id': company_id,
            },
            {
                'name': 'Cash',
                'code': 'CSH',
                'type': 'cash',
                'company_id': company_id,
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
                    print(f"Created journal: {journal_data['name']} ({journal_data['code']}) - ID: {journal_id}")
                    
            except Exception as journal_error:
                print(f"Failed to create journal {journal_data['name']}: {str(journal_error)}")
                # For sales/purchase journals, this might be due to missing accounts
                if journal_data['type'] in ['sale', 'purchase']:
                    print(f"  -> This is likely due to Chart of Accounts not being fully ready")
                continue
        
        if created_journals:
            return {
                'success': True,
                'journals': created_journals,
                'message': f'Created {len(created_journals)} journals'
            }
        else:
            return {
                'success': False,
                'error': 'No journals were created - they may already exist or Chart of Accounts is not ready'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to create journals: {str(e)}'
        }

def ensure_chart_of_accounts(models, db, uid, password, company_id, country_code=None):
    """
    Initiate chart of accounts installation for the company.
    The actual installation will continue in the background.
    """
    try:
        # Quick check if accounts already exist
        account_count = models.execute_kw(
            db, uid, password,
            'account.account', 'search_count',
            [[('company_id', '=', company_id)]]
        )
        
        if account_count > 0:
            return {'success': True, 'message': 'Chart of accounts already exists', 'accounts_found': account_count}

        # Find chart template
        domain = []
        if country_code:
            domain = [('country_id.code', '=', country_code.upper())]
        templates = models.execute_kw(
            db, uid, password,
            'account.chart.template', 'search_read',
            [domain], {'fields': ['id', 'name'], 'limit': 1}
        )
        if not templates:
            # fallback: get any template
            templates = models.execute_kw(
                db, uid, password,
                'account.chart.template', 'search_read',
                [[]], {'fields': ['id', 'name'], 'limit': 1}
            )
        if not templates:
            return {'success': False, 'error': 'No chart of accounts template found'}

        template = templates[0]
        print(f"Using chart template: {template['name']} (ID: {template['id']})")
        
        # Attempt to initiate chart of accounts installation
        try:
            # Try the most reliable method first
            models.execute_kw(
                db, uid, password,
                'account.chart.template', 'try_loading',
                [[template['id']]], 
                {'company_id': company_id, 'code_digits': 6}
            )
            return {'success': True, 'message': f'Chart of accounts installation initiated with template: {template["name"]}'}
        except Exception as e1:
            try:
                # Fallback to simpler method
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
    Simplified version that just waits a fixed time and checks basic account existence
    """
    print(f"Using simplified chart of accounts check for company {company_id}...")
    
    # Wait a reasonable time for chart installation to begin
    time.sleep(10)
    
    try:
        # Try to get any accounts at all
        account_count = models.execute_kw(
            db, uid, password,
            'account.account', 'search_count',
            [[]]
        )
        
        if account_count > 0:
            return {
                'success': True,
                'message': f'Found {account_count} accounts in system - proceeding with journal creation',
                'accounts_count': account_count
            }
        else:
            return {
                'success': False,
                'message': 'No accounts found - chart of accounts may need manual setup',
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

def create_journals_for_existing_company(company_id):
    """
    Create essential journals for an existing company that doesn't have them
    Useful for fixing companies created before this update
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
        
        # Wait for Chart of Accounts to be ready
        print(f"Checking Chart of Accounts for company {company_id}...")
        chart_ready = wait_for_chart_of_accounts(models, db, uid, password, company_id, max_wait_time=60)
        
        if not chart_ready['success']:
            return {
                'success': False,
                'error': f'Chart of Accounts not ready: {chart_ready["message"]}'
            }
        
        # Create journals
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