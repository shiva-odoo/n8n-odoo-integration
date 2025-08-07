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
            return True, {
                "success": True,
                "entry_name": journal_entry['name'],
                "ref_field": journal_entry.get('ref', 'None'),
                "amount": journal_entry['amount_total'],
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


def create_suspense_account(data):
    """
    Safe version that first checks available fields before creating account
    """
    try:
        company_name = data['company_name']
        amount = data.get('amount')
        reference = data.get('reference')
        
        # Load Odoo credentials
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

        # Check available fields first
        fields_info = models.execute_kw(
            db, uid, password,
            'account.account', 'fields_get',
            [],
            {}
        )
        
        has_company_id = 'company_id' in fields_info
        has_company_ids = 'company_ids' in fields_info
        
        # Find company ID (we'll need it even if we can't filter by it)
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

        # Create account name and code based on reference
        if reference:
            account_name = f"Suspense Account - {reference}"
            try:
                ref_suffix = str(reference)[-4:]
                account_code = f"4999{ref_suffix}"
            except:
                account_code = "499999"
        else:
            account_name = "Suspense Account"
            account_code = "499999"

        # Build account data based on available fields
        account_data = {
            'name': account_name,
            'code': account_code,
        }
        
        # Add account_type if available
        if 'account_type' in fields_info:
            account_data['account_type'] = 'asset_current'
        elif 'user_type_id' in fields_info:
            # Older Odoo versions might use user_type_id
            # You'd need to find the appropriate account type ID
            pass
            
        # Add reconcile if available
        if 'reconcile' in fields_info:
            account_data['reconcile'] = True
            
        # Add company reference if available
        if has_company_id:
            account_data['company_id'] = company_id
        elif has_company_ids:
            account_data['company_ids'] = [(6, 0, [company_id])]

        # Check if account already exists
        try:
            if has_company_id:
                existing_accounts = models.execute_kw(
                    db, uid, password,
                    'account.account', 'search_read',
                    [[('code', '=', account_code), ('company_id', '=', company_id)]],
                    {'fields': ['id', 'name', 'code'], 'limit': 1}
                )
            else:
                existing_accounts = models.execute_kw(
                    db, uid, password,
                    'account.account', 'search_read',
                    [[('code', '=', account_code)]],
                    {'fields': ['id', 'name', 'code'], 'limit': 1}
                )
        except Exception as e:
            # If search fails, try without company filter
            existing_accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [[('code', '=', account_code)]],
                {'fields': ['id', 'name', 'code'], 'limit': 1}
            )

        if existing_accounts:
            return False, {
                "error": f"Account with code '{account_code}' already exists: {existing_accounts[0]['name']}",
                "existing_account": existing_accounts[0]
            }

        # Create the account
        account_id = models.execute_kw(
            db, uid, password,
            'account.account', 'create',
            [account_data]
        )

        if account_id:
            # Get created account details
            created_account = models.execute_kw(
                db, uid, password,
                'account.account', 'read',
                [[account_id]],
                {'fields': ['id', 'name', 'code']}
            )[0]

            return True, {
                "success": True,
                "account_id": account_id,
                "account_name": created_account['name'],
                "account_code": created_account['code'],
                "company": actual_company_name,
                "reference_used": reference,
                "amount_context": amount,
                "fields_used": list(account_data.keys()),
                "message": f"Suspense account '{created_account['name']}' ({created_account['code']}) created successfully"
            }
        else:
            return False, {"error": "Failed to create suspense account"}

    except xmlrpc.client.Fault as fault:
        return False, {"error": f"XML-RPC Fault: {fault.faultString}"}
    except Exception as e:
        return False, {"error": f"Unexpected error: {str(e)}"}
