# updateAuditStatus.py

import os
import xmlrpc.client

def update_audit_status_in_odoo(transaction_id, new_status):
    """
    Updates the custom 'Audit Status' field on a journal entry (account.move) in Odoo.
    Uses the correct custom field name: x_studio_audit_status
    """
    try:
        # Load Odoo credentials from environment
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB")
        username = os.getenv("ODOO_USERNAME")
        password = os.getenv("ODOO_API_KEY")

        if not all([url, db, username, password]):
            return False, {"error": "Missing Odoo connection configuration"}

        # Setup connection
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        uid = common.authenticate(db, username, password, {})

        if not uid:
            return False, {"error": "Authentication with Odoo failed"}

        # Confirm transaction_id is valid integer
        try:
            transaction_id = int(transaction_id)
        except ValueError:
            return False, {"error": f"Invalid transaction_id: {transaction_id}"}

        # Perform the update
        updated = models.execute_kw(
            db, uid, password,
            'account.move', 'write',
            [[transaction_id], {'x_studio_audit_status': new_status}]
        )

        if updated:
            return True, {
                "success": True,
                "transaction_id": transaction_id,
                "new_status": new_status,
                "message": f"Audit status updated to '{new_status}'"
            }
        else:
            return False, {"error": "Write operation failed"}

    except xmlrpc.client.Fault as fault:
        return False, {"error": f"XML-RPC Fault: {fault.faultString}"}
    except Exception as e:
        return False, {"error": f"Unexpected error: {str(e)}"}


def mark_entry_as_paid(data):
    """
    Finds a journal entry by reference, amount, and company name, then marks it as paid.
    Uses correct field names for account.move model in Odoo.
    
    Args:
        data (dict): Contains reference, amount, company_name
    
    Returns:
        tuple: (success_bool, result_dict)
    """
    try:
        reference = data['reference']
        amount = data['amount']
        company_name = data['company_name']
        
        # Load Odoo credentials from environment
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB")
        username = os.getenv("ODOO_USERNAME")
        password = os.getenv("ODOO_API_KEY")

        if not all([url, db, username, password]):
            return False, {"error": "Missing Odoo connection configuration"}

        # Setup connection
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        uid = common.authenticate(db, username, password, {})

        if not uid:
            return False, {"error": "Authentication with Odoo failed"}

        # First, find the company ID by name
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[('name', 'ilike', company_name)]],
            {'fields': ['id', 'name'], 'limit': 1}
        )
        
        if not companies:
            return False, {"error": f"Company '{company_name}' not found"}
        
        company_id = companies[0]['id']
        actual_company_name = companies[0]['name']

        # Convert amount to float if it's a string
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            return False, {"error": f"Invalid amount: {amount}"}

        # Search for the journal entry with correct field names
        domain = [
            ('ref', 'ilike', reference),           # ref field for bank references like 255713924
            ('amount_total', '=', amount),         # amount_total not 'total'
            ('company_id', '=', company_id)        # company_id not 'company_name'
        ]
        
        # Get matching entry IDs
        entry_ids = models.execute_kw(
            db, uid, password,
            'account.move', 'search',
            [domain],
            {'limit': 1}
        )

        if not entry_ids:
            return False, {
                "error": f"No journal entry found with reference '{reference}', amount {amount}, and company '{actual_company_name}'"
            }

        # Get entry details for validation
        journal_entries = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [entry_ids],
            {'fields': ['id', 'name', 'amount_total', 'state', 'payment_state', 'ref']}
        )
        
        journal_entry = journal_entries[0]

        # Check if entry is in draft state
        if journal_entry.get('state') == 'draft':
            return False, {
                "error": f"Journal entry {journal_entry['name']} is in draft state. Please post it first before marking as paid."
            }

        # Mark the entry as paid by updating the payment_state
        updated = models.execute_kw(
            db, uid, password,
            'account.move', 'write',
            [entry_ids, {'payment_state': 'paid'}]
        )

        if updated:
            return {
                "success": True,
                "entry_name": journal_entry['name'],
                "ref_field": journal_entry.get('ref', 'None'),
                "amount": journal_entry['amount_total'],
                "description": data.get('description', 'No description provided'),
                "partner": data.get('partner', 'Unknown'),
                "company": actual_company_name,
                "previous_payment_state": journal_entry.get('payment_state', 'unknown'),
                "new_payment_state": 'paid',
                "message": f"Journal entry '{journal_entry['name']}' marked as paid"
            }
        else:
            return False, {"error": "Failed to update payment status"}

    except xmlrpc.client.Fault as fault:
        return False, {"error": f"XML-RPC Fault: {fault.faultString}"}
    except Exception as e:
        return False, {"error": f"Unexpected error: {str(e)}"}


def handle_bank_suspense_transaction(data):
    """
    Handles bank suspense account transactions by:
    1. Finding or creating a 'Bank Suspense Account'
    2. Finding journal entry by reference and amount
    3. Marking the transaction as a suspense account transaction
    
    Args:
        data (dict): Contains amount and reference
        Required fields:
        - amount (float): Transaction amount
        - reference (str): Journal entry reference (e.g., "SO2024/5103379")
        Optional fields:
        - company_name (str): Company name (required for proper company-specific operations)
    
    Returns:
        dict: Result with success status and transaction details
    """
    try:
        # Extract required fields
        amount = data['amount']
        reference = data['reference']
        company_name = data.get('company_name')
        
        # Load Odoo credentials
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB")
        username = os.getenv("ODOO_USERNAME")
        password = os.getenv("ODOO_API_KEY")

        if not all([url, db, username, password]):
            return {"success": False, "error": "Missing Odoo connection configuration"}

        # Setup connection
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        uid = common.authenticate(db, username, password, {})

        if not uid:
            return {"success": False, "error": "Authentication with Odoo failed"}

        # Get company information - company_name is now required
        if not company_name:
            return {"success": False, "error": "Company name is required"}
            
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[('name', 'ilike', company_name)]],
            {'fields': ['id', 'name'], 'limit': 1}
        )
        
        if not companies:
            return {"success": False, "error": f"Company '{company_name}' not found"}
        
        company_id = companies[0]['id']
        actual_company_name = companies[0]['name']

        # Step 1: Check if 'Bank Suspense Account' exists
        suspense_account = find_or_create_bank_suspense_account(
            models, db, uid, password, company_id, actual_company_name
        )
        
        if not suspense_account['success']:
            return suspense_account

        # Step 2: Find journal entry by reference and amount
        journal_entry = find_journal_entry_by_reference_and_amount(
            models, db, uid, password, reference, amount, company_id
        )
        
        if not journal_entry['success']:
            return journal_entry

        # Step 3: Mark transaction as suspense account transaction
        suspense_result = mark_as_suspense_transaction(
            models, db, uid, password, journal_entry['move_id'], 
            suspense_account['account_id'], amount
        )

        if not suspense_result['success']:
            return suspense_result

        return {
            "success": True,
            "message": "Bank suspense transaction processed successfully",
            "suspense_account": suspense_account,
            "journal_entry": journal_entry,
            "transaction_update": suspense_result,
            "reference": reference,
            "amount": amount,
            "company": actual_company_name
        }

    except xmlrpc.client.Fault as fault:
        return {"success": False, "error": f"XML-RPC Fault: {fault.faultString}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


def find_or_create_bank_suspense_account(models, db, uid, password, company_id, company_name):
    """
    Find existing 'Bank Suspense Account' or create it if it doesn't exist
    """
    try:
        # Check available fields first
        fields_info = models.execute_kw(
            db, uid, password,
            'account.account', 'fields_get',
            [],
            {}
        )
        
        has_company_id = 'company_id' in fields_info
        has_company_ids = 'company_ids' in fields_info
        has_account_type = 'account_type' in fields_info
        has_user_type_id = 'user_type_id' in fields_info

        # Search for existing Bank Suspense Account
        search_domain = [('name', 'ilike', 'Bank Suspense Account')]
        if has_company_id:
            search_domain.append(('company_id', '=', company_id))

        existing_accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [search_domain],
            {'fields': ['id', 'name', 'code', 'account_type'], 'limit': 1}
        )

        if existing_accounts:
            account = existing_accounts[0]
            return {
                "success": True,
                "account_id": account['id'],
                "account_name": account['name'],
                "account_code": account['code'],
                "account_type": account.get('account_type', 'Unknown'),
                "status": "existing",
                "message": f"Using existing Bank Suspense Account: {account['name']} ({account['code']})"
            }

        # Create new Bank Suspense Account if it doesn't exist
        account_code = f"4999{random.randint(10, 99)}"
        
        # Build account data
        account_data = {
            'name': 'Bank Suspense Account',
            'code': account_code,
            'reconcile': True
        }
        
        # Add account type based on available fields
        if has_account_type:
            account_data['account_type'] = 'asset_current'  # Current asset for suspense
        elif has_user_type_id:
            # For older Odoo versions, find appropriate user_type_id
            user_types = models.execute_kw(
                db, uid, password,
                'account.account.type', 'search_read',
                [[('type', '=', 'other')]],
                {'fields': ['id'], 'limit': 1}
            )
            if user_types:
                account_data['user_type_id'] = user_types[0]['id']
            else:
                account_data['user_type_id'] = 1  # Fallback
            
        # Add company reference
        if has_company_id:
            account_data['company_id'] = company_id
        elif has_company_ids:
            account_data['company_ids'] = [(6, 0, [company_id])]

        # Create the account
        account_id = models.execute_kw(
            db, uid, password,
            'account.account', 'create',
            [account_data]
        )

        if account_id:
            created_account = models.execute_kw(
                db, uid, password,
                'account.account', 'read',
                [[account_id]],
                {'fields': ['id', 'name', 'code']}
            )[0]

            return {
                "success": True,
                "account_id": account_id,
                "account_name": created_account['name'],
                "account_code": created_account['code'],
                "account_type": "asset_current",
                "status": "created",
                "message": f"Created new Bank Suspense Account: {created_account['name']} ({created_account['code']})"
            }
        else:
            return {"success": False, "error": "Failed to create Bank Suspense Account"}

    except Exception as e:
        return {"success": False, "error": f"Error with suspense account: {str(e)}"}


def find_journal_entry_by_reference_and_amount(models, db, uid, password, reference, amount, company_id):
    """
    Find journal entry by reference and amount within the specific company
    """
    try:
        # Search for journal entry (account.move) by reference and company
        search_domain = [
            ('ref', '=', reference),
            ('company_id', '=', company_id)
        ]
        
        journal_moves = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [search_domain],
            {'fields': ['id', 'ref', 'amount_total', 'state', 'move_type', 'date', 'company_id']}
        )

        if not journal_moves:
            # Try without company filter as fallback
            fallback_domain = [('ref', '=', reference)]
            journal_moves = models.execute_kw(
                db, uid, password,
                'account.move', 'search_read',
                [fallback_domain],
                {'fields': ['id', 'ref', 'amount_total', 'state', 'move_type', 'date', 'company_id']}
            )
            
            if not journal_moves:
                return {
                    "success": False, 
                    "error": f"No journal entry found with reference: {reference} in company ID: {company_id}"
                }

        # Find the move that matches the amount (or closest match)
        matching_move = None
        for move in journal_moves:
            # Prefer moves from the correct company
            if move.get('company_id') and move['company_id'][0] == company_id:
                if abs(move.get('amount_total', 0) - amount) < 0.01:
                    matching_move = move
                    break
        
        # If no exact company + amount match, try any move with matching amount
        if not matching_move:
            for move in journal_moves:
                if abs(move.get('amount_total', 0) - amount) < 0.01:
                    matching_move = move
                    break
        
        # If still no match, take the first move from the correct company
        if not matching_move:
            for move in journal_moves:
                if move.get('company_id') and move['company_id'][0] == company_id:
                    matching_move = move
                    break
                    
        # Last resort: take any move with the reference
        if not matching_move:
            matching_move = journal_moves[0]
            
        # Get move lines for more details (company-specific)
        move_lines = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[
                ('move_id', '=', matching_move['id']),
                ('company_id', '=', company_id)
            ]],
            {'fields': ['id', 'account_id', 'debit', 'credit', 'name', 'ref', 'company_id']}
        )

        # If no company-specific lines found, get all lines for the move
        if not move_lines:
            move_lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [[('move_id', '=', matching_move['id'])]],
                {'fields': ['id', 'account_id', 'debit', 'credit', 'name', 'ref', 'company_id']}
            )

        company_info = matching_move.get('company_id', [company_id, 'Unknown'])
        return {
            "success": True,
            "move_id": matching_move['id'],
            "reference": matching_move['ref'],
            "amount_total": matching_move.get('amount_total', 0),
            "state": matching_move.get('state'),
            "move_type": matching_move.get('move_type'),
            "date": matching_move.get('date'),
            "company_id": company_info[0] if isinstance(company_info, list) else company_info,
            "company_name": company_info[1] if isinstance(company_info, list) and len(company_info) > 1 else 'Unknown',
            "move_lines": move_lines,
            "move_lines_count": len(move_lines),
            "message": f"Found journal entry {matching_move['ref']} with amount {matching_move.get('amount_total', 0)} in company {company_info[1] if isinstance(company_info, list) else 'Unknown'}"
        }

    except Exception as e:
        return {"success": False, "error": f"Error finding journal entry: {str(e)}"}


def mark_as_suspense_transaction(models, db, uid, password, move_id, suspense_account_id, amount):
    """
    Mark the transaction as a suspense account transaction
    This can involve updating move lines or adding notes
    """
    try:
        # Get current move lines (company-specific)
        move_lines = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', move_id)]],
            {'fields': ['id', 'account_id', 'debit', 'credit', 'name', 'company_id']}
        )

        # Find a move line that matches the amount to update
        line_to_update = None
        for line in move_lines:
            line_amount = line.get('debit', 0) or line.get('credit', 0)
            if abs(line_amount - abs(amount)) < 0.01:  # Match the amount
                line_to_update = line
                break

        if not line_to_update:
            # If no exact match, create a new move line for the suspense account
            return create_suspense_move_line(models, db, uid, password, move_id, suspense_account_id, amount)

        # Update existing move line to use suspense account
        update_data = {
            'account_id': suspense_account_id,
            'name': f"Bank Suspense - {line_to_update.get('name', '')}"
        }

        models.execute_kw(
            db, uid, password,
            'account.move.line', 'write',
            [[line_to_update['id']], update_data]
        )

        # Add a note to the move
        move_update = {
            'narration': f"Transaction marked as Bank Suspense Account transaction. Amount: {amount}"
        }
        
        models.execute_kw(
            db, uid, password,
            'account.move', 'write',
            [[move_id], move_update]
        )

        return {
            "success": True,
            "updated_line_id": line_to_update['id'],
            "suspense_account_id": suspense_account_id,
            "amount": amount,
            "message": f"Updated move line {line_to_update['id']} to use Bank Suspense Account"
        }

    except Exception as e:
        return {"success": False, "error": f"Error marking as suspense transaction: {str(e)}"}


def create_suspense_move_line(models, db, uid, password, move_id, suspense_account_id, amount):
    """
    Create a new move line for the suspense account if no matching line exists
    """
    try:
        # Create balancing move lines for suspense account
        if amount > 0:
            debit_amount = amount
            credit_amount = 0
        else:
            debit_amount = 0
            credit_amount = abs(amount)

        move_line_data = {
            'move_id': move_id,
            'account_id': suspense_account_id,
            'name': 'Bank Suspense Account Entry',
            'debit': debit_amount,
            'credit': credit_amount,
        }

        line_id = models.execute_kw(
            db, uid, password,
            'account.move.line', 'create',
            [move_line_data]
        )

        return {
            "success": True,
            "new_line_id": line_id,
            "suspense_account_id": suspense_account_id,
            "amount": amount,
            "message": f"Created new suspense account move line with ID {line_id}"
        }

    except Exception as e:
        return {"success": False, "error": f"Error creating suspense move line: {str(e)}"}
