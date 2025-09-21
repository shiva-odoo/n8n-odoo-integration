import xmlrpc.client
from datetime import datetime
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
    Create journal entry from HTTP request data
    
    Expected data format:
    {
        "journal_id": 1,  # optional, defaults to first general journal found
        "date": "2025-01-15",  # optional, defaults to today
        "ref": "JE-001",       # optional reference
        "narration": "Monthly adjustment",  # optional description
        "line_items": [
            {
                "account_id": 101,      # Chart of accounts ID (required)
                "name": "Office rent",  # Line description (required)
                "debit": 1500.00,      # Debit amount (use 0 for credit entries)
                "credit": 0.00,        # Credit amount (use 0 for debit entries)
                "partner_id": 123      # optional, for vendor/customer specific entries
            },
            {
                "account_id": 201,
                "name": "Cash payment",
                "debit": 0.00,
                "credit": 1500.00
            }
        ]
    }
    
    Note: Total debits must equal total credits
    """
    
    # Validate required fields
    if not data.get('line_items') or not isinstance(data['line_items'], list):
        return {
            'success': False,
            'error': 'line_items array is required'
        }
    
    if len(data['line_items']) < 2:
        return {
            'success': False,
            'error': 'Journal entry must have at least 2 line items'
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
        
        # Get journal ID (default to first general journal if not specified)
        journal_id = data.get('journal_id')
        if not journal_id:
            journals = models.execute_kw(
                db, uid, password,
                'account.journal', 'search',
                [[('type', '=', 'general')]], 
                {'limit': 1}
            )
            if not journals:
                return {
                    'success': False,
                    'error': 'No general journal found. Please specify journal_id'
                }
            journal_id = journals[0]
        
        # Verify journal exists
        journal_exists = models.execute_kw(
            db, uid, password,
            'account.journal', 'search_count',
            [[('id', '=', journal_id)]]
        )
        
        if not journal_exists:
            return {
                'success': False,
                'error': f'Journal with ID {journal_id} not found'
            }
        
        # Get journal info for response
        journal_info = models.execute_kw(
            db, uid, password,
            'account.journal', 'read',
            [[journal_id]], 
            {'fields': ['name', 'code']}
        )[0]
        
        # Prepare journal entry data
        entry_date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        # Validate date format
        try:
            datetime.strptime(entry_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'date must be in YYYY-MM-DD format'
            }
        
        journal_entry_data = {
            'move_type': 'entry',
            'journal_id': journal_id,
            'date': entry_date,
        }
        
        # Add reference if provided
        if data.get('ref'):
            journal_entry_data['ref'] = data['ref']
            
        # Add narration if provided
        if data.get('narration'):
            journal_entry_data['narration'] = data['narration']
        
        # Process line items and validate debit/credit balance
        line_ids = []
        total_debits = 0.0
        total_credits = 0.0
        
        for idx, item in enumerate(data['line_items']):
            # Validate required fields
            if not item.get('account_id'):
                return {
                    'success': False,
                    'error': f'Line item {idx + 1}: account_id is required'
                }
            
            if not item.get('name'):
                return {
                    'success': False,
                    'error': f'Line item {idx + 1}: name (description) is required'
                }
            
            # Validate and convert amounts
            try:
                debit = float(item.get('debit', 0.0))
                credit = float(item.get('credit', 0.0))
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': f'Line item {idx + 1}: debit and credit must be valid numbers'
                }
            
            # Validate that line has either debit or credit (not both, not neither)
            if debit > 0 and credit > 0:
                return {
                    'success': False,
                    'error': f'Line item {idx + 1}: cannot have both debit and credit amounts'
                }
            
            if debit == 0 and credit == 0:
                return {
                    'success': False,
                    'error': f'Line item {idx + 1}: must have either debit or credit amount'
                }
            
            # Verify account exists
            account_exists = models.execute_kw(
                db, uid, password,
                'account.account', 'search_count',
                [[('id', '=', item['account_id'])]]
            )
            
            if not account_exists:
                return {
                    'success': False,
                    'error': f'Line item {idx + 1}: Account with ID {item["account_id"]} not found'
                }
            
            # Build line item
            line_item = {
                'account_id': item['account_id'],
                'name': item['name'],
                'debit': debit,
                'credit': credit,
            }
            
            # Add partner if provided
            if item.get('partner_id'):
                # Verify partner exists
                partner_exists = models.execute_kw(
                    db, uid, password,
                    'res.partner', 'search_count',
                    [[('id', '=', item['partner_id'])]]
                )
                
                if not partner_exists:
                    return {
                        'success': False,
                        'error': f'Line item {idx + 1}: Partner with ID {item["partner_id"]} not found'
                    }
                
                line_item['partner_id'] = item['partner_id']
            
            line_ids.append((0, 0, line_item))
            total_debits += debit
            total_credits += credit
        
        # Validate that debits equal credits
        if abs(total_debits - total_credits) > 0.01:  # Allow for small rounding differences
            return {
                'success': False,
                'error': f'Total debits ({total_debits:.2f}) must equal total credits ({total_credits:.2f})'
            }
        
        journal_entry_data['line_ids'] = line_ids
        
        # Create the journal entry
        entry_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [journal_entry_data]
        )
        
        if not entry_id:
            return {
                'success': False,
                'error': 'Failed to create journal entry in Odoo'
            }
        
        # POST THE JOURNAL ENTRY - Move from draft to posted state
        try:
            post_result = models.execute_kw(
                db, uid, password,
                'account.move', 'action_post',
                [[entry_id]]
            )
            
            # Verify the entry was posted successfully
            entry_state = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[entry_id]], 
                {'fields': ['state']}
            )[0]['state']
            
            if entry_state != 'posted':
                return {
                    'success': False,
                    'error': f'Journal entry was created but failed to post. Current state: {entry_state}'
                }
                
        except xmlrpc.client.Fault as e:
            return {
                'success': False,
                'error': f'Journal entry created but failed to post: {str(e)}'
            }
        
        # Get final entry information after posting
        entry_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[entry_id]], 
            {'fields': ['name', 'state', 'amount_total']}
        )[0]
        
        return {
            'success': True,
            'entry_id': entry_id,
            'entry_number': entry_info.get('name'),
            'journal_name': journal_info['name'],
            'journal_code': journal_info['code'],
            'total_amount': total_debits,  # or total_credits, they're equal
            'state': entry_info.get('state'),
            'date': entry_date,
            'ref': data.get('ref'),
            'narration': data.get('narration'),
            'line_count': len(data['line_items']),
            'message': 'Journal entry created and posted successfully'
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

def create(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

# Helper functions for reference
def list_journals():
    """Get list of journals for reference"""
    
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
            [[]], 
            {'fields': ['id', 'name', 'code', 'type']}
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

def list_accounts(company_id=None):
    """Get list of chart of accounts for reference"""
    
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
        
        company_name = None
        
        # If company_id is provided, fetch the company name first
        if company_id:
            company_data = models.execute_kw(
                db, uid, password,
                'res.company', 'search_read',
                [[('id', '=', company_id)]], 
                {'fields': ['name'], 'limit': 1}
            )
            
            if not company_data:
                return {'success': False, 'error': f'Company with ID {company_id} not found'}
            
            company_name = company_data[0]['name']
        
        # Build domain filter for accounts
        domain = [('active', '=', True)]
        
        # If we have a company name, try to filter accounts by company name
        if company_name:
            # Check what fields are available on account.account
            available_fields = models.execute_kw(
                db, uid, password,
                'account.account', 'fields_get',
                [], {'attributes': ['string', 'type']}
            )
            
            # Try different approaches to filter by company using the company name
            if 'company_id' in available_fields:
                # Standard approach: filter by company_id relation
                domain.append(('company_id', '=', company_id))
            elif 'company_ids' in available_fields:
                # Multi-company field approach
                domain.append(('company_ids', 'in', [company_id]))
            elif 'name' in available_fields:
                # Try to filter by account name containing company name
                # This is a fallback approach - might not be very reliable
                domain.append(('name', 'ilike', company_name))
            else:
                # If no suitable field found, get all accounts
                # We'll note this in the response
                pass
        
        accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [domain], 
            {'fields': ['id', 'code', 'name', 'account_type']}
        )
        
        # If we couldn't filter by company directly, try alternative approach
        if company_name and not any(field in ['company_id', 'company_ids'] for field in models.execute_kw(
            db, uid, password, 'account.account', 'fields_get', [], {'attributes': ['string', 'type']}
        ).keys()):
            
            # Alternative: Search through account move lines or journal entries
            # to find accounts used by this company
            try:
                # Get journals for this company
                company_journals = models.execute_kw(
                    db, uid, password,
                    'account.journal', 'search_read',
                    [[('company_id', '=', company_id)]], 
                    {'fields': ['id']}
                )
                
                if company_journals:
                    journal_ids = [j['id'] for j in company_journals]
                    
                    # Get account move lines from these journals to find relevant accounts
                    account_moves = models.execute_kw(
                        db, uid, password,
                        'account.move.line', 'search_read',
                        [[('journal_id', 'in', journal_ids)]], 
                        {'fields': ['account_id'], 'limit': 1000}
                    )
                    
                    if account_moves:
                        # Get unique account IDs used by this company
                        account_ids = list(set([move['account_id'][0] for move in account_moves if move.get('account_id')]))
                        
                        # Now get the actual account details
                        if account_ids:
                            accounts = models.execute_kw(
                                db, uid, password,
                                'account.account', 'search_read',
                                [[('id', 'in', account_ids), ('active', '=', True)]], 
                                {'fields': ['id', 'code', 'name', 'account_type']}
                            )
            except Exception as alt_error:
                # If alternative approach fails, stick with original results
                pass
        
        return {
            'success': True,
            'accounts': accounts,
            'count': len(accounts),
            'company_id': company_id,
            'company_name': company_name,
            'filter_method': 'company_name_based' if company_name else 'all_active'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
    
def get_company_journals(data):
    """
    Get all journals for a specific company
    
    Expected data format:
    {
        "company_id": 1  # Required - Company ID to get journals for
    }
    
    Returns:
    {
        "success": True/False,
        "company_id": 1,
        "company_name": "Company Name",
        "journals": [
            {
                "id": 1,
                "name": "Sales",
                "code": "INV", 
                "type": "sale"
            },
            {
                "id": 2,
                "name": "Purchases",
                "code": "BILL",
                "type": "purchase"
            },
            ...
        ],
        "count": 5
    }
    """
    
    # Validate required fields
    if not data.get('company_id'):
        return {
            'success': False,
            'error': 'company_id is required'
        }
    
    company_id = data['company_id']
    
    # Validate company_id is a number
    try:
        company_id = int(company_id)
    except (ValueError, TypeError):
        return {
            'success': False,
            'error': 'company_id must be a valid number'
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
        
        # Verify company exists and get company name
        company_info = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[('id', '=', company_id)]], 
            {'fields': ['id', 'name'], 'limit': 1}
        )
        
        if not company_info:
            return {
                'success': False,
                'error': f'Company with ID {company_id} not found'
            }
        
        company_name = company_info[0]['name']
        
        # Get all journals for the company
        journals = models.execute_kw(
            db, uid, password,
            'account.journal', 'search_read',
            [[('company_id', '=', company_id)]], 
            {'fields': ['id', 'name', 'code', 'type'], 'order': 'type, name'}
        )
        
        return {
            'success': True,
            'company_id': company_id,
            'company_name': company_name,
            'journals': journals,
            'count': len(journals)
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
