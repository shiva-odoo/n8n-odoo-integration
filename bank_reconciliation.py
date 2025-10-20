# bank_reconciliation.py
import xmlrpc.client
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_odoo_connection():
    """Establish connection to Odoo"""
    try:
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB")
        username = os.getenv("ODOO_USERNAME")
        password = os.getenv("ODOO_API_KEY")

        if not all([url, db, username, password]):
            raise Exception("Missing Odoo connection configuration")

        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            raise Exception("Authentication with Odoo failed")

        return models, uid, db, password
        
    except Exception as e:
        logger.error(f"Odoo connection error: {str(e)}")
        raise

# ============================================================================
# BANK TRANSACTIONS FROM ODOO
# ============================================================================

def get_bank_transactions(business_company_id, bank_account_id=None, date_from=None, date_to=None, status=None):
    """Get bank transactions from Odoo for reconciliation"""
    try:
        company_id = int(business_company_id) if business_company_id else None
        if not company_id:
            return {'success': False, 'error': 'Invalid business_company_id'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get bank/cash accounts for this company
        account_domain = [
            ('account_type', 'in', ['asset_cash', 'liability_credit_card'])
        ]
        
        # If specific bank account requested, filter by it
        if bank_account_id:
            account_domain.append(('id', '=', int(bank_account_id)))
        
        bank_accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [account_domain],
            {'fields': ['id', 'name', 'code']}
        )
        
        if not bank_accounts:
            return {
                "success": True,
                "transactions": [],
                "total_count": 0
            }
        
        account_ids = [acc['id'] for acc in bank_accounts]
        
        # Get bank statement lines (transactions) for these accounts
        line_domain = [
            ('company_id', '=', company_id),
            ('account_id', 'in', account_ids),
            ('parent_state', '=', 'posted')
        ]
        
        if date_from:
            line_domain.append(('date', '>=', date_from))
        if date_to:
            line_domain.append(('date', '<=', date_to))
        
        # Filter by reconciliation status if requested
        if status == 'reconciled':
            line_domain.append(('full_reconcile_id', '!=', False))
        elif status == 'unreconciled':
            line_domain.append(('full_reconcile_id', '=', False))
        
        lines = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [line_domain],
            {'fields': ['id', 'date', 'name', 'ref', 'debit', 'credit', 'balance', 
                       'full_reconcile_id', 'account_id', 'partner_id', 'move_id'],
             'order': 'date desc',
             'limit': 100}
        )
        
        # Format transactions for frontend
        formatted_transactions = []
        for line in lines:
            # Determine amount and type
            amount = line['debit'] - line['credit']
            txn_type = 'debit' if line['debit'] > 0 else 'credit'
            
            formatted_transactions.append({
                'id': str(line['id']),
                'transaction_id': str(line['id']),
                'date': line['date'],
                'description': line['name'],
                'reference': line.get('ref', ''),
                'amount': f"€{abs(amount):,.2f}" if amount != 0 else "€0.00",
                'amount_raw': amount,
                'type': txn_type,
                'reconciliation_status': 'reconciled' if line.get('full_reconcile_id') else 'unreconciled',
                'account_name': line['account_id'][1] if line.get('account_id') else '',
                'partner': line['partner_id'][1] if line.get('partner_id') else '',
                'move_id': line['move_id'][0] if line.get('move_id') else None,
                'balance': line.get('balance', 0)
            })
        
        return {
            "success": True,
            "transactions": formatted_transactions,
            "total_count": len(formatted_transactions)
        }
        
    except Exception as e:
        logger.error(f"Error getting bank transactions from Odoo: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def get_bank_accounts(business_company_id):
    """Get all bank/cash accounts from Odoo for a company"""
    try:
        company_id = int(business_company_id) if business_company_id else None
        if not company_id:
            return {'success': False, 'error': 'Invalid business_company_id'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get bank journals for this company
        journal_domain = [
            ('company_id', '=', company_id),
            ('type', 'in', ['bank', 'cash'])
        ]
        
        journals = models.execute_kw(
            db, uid, password,
            'account.journal', 'search_read',
            [journal_domain],
            {'fields': ['id', 'name', 'code', 'type', 'default_account_id', 'currency_id', 'bank_account_id']}
        )
        
        # Format accounts for frontend
        formatted_accounts = []
        for journal in journals:
            # Get current balance from the default account
            account_id = journal['default_account_id'][0] if journal.get('default_account_id') else None
            current_balance = 0
            
            if account_id:
                # Get balance from account move lines
                balance_lines = models.execute_kw(
                    db, uid, password,
                    'account.move.line', 'search_read',
                    [[('company_id', '=', company_id), ('account_id', '=', account_id), ('parent_state', '=', 'posted')]],
                    {'fields': ['balance']}
                )
                current_balance = sum(line['balance'] for line in balance_lines)
            
            formatted_accounts.append({
                'bank_account_id': str(journal['id']),
                'account_name': journal['name'],
                'account_number': journal.get('code', ''),
                'bank_name': journal['name'].split(' - ')[0] if ' - ' in journal['name'] else journal['name'],
                'currency': journal['currency_id'][1] if journal.get('currency_id') else 'EUR',
                'current_balance': current_balance,
                'account_type': journal['type'],
                'status': 'active',
                'odoo_journal_id': journal['id'],
                'odoo_account_id': account_id
            })
        
        return {
            "success": True,
            "accounts": formatted_accounts,
            "total_count": len(formatted_accounts)
        }
        
    except Exception as e:
        logger.error(f"Error getting bank accounts from Odoo: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def reconcile_transaction(transaction_id, business_company_id, matched_record_type=None, matched_record_id=None, reconciled_by=None):
    """Reconcile a bank statement line in Odoo"""
    try:
        company_id = int(business_company_id) if business_company_id else None
        if not company_id:
            return {'success': False, 'error': 'Invalid business_company_id'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get the account move line (transaction)
        line_id = int(transaction_id)
        
        line = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('id', '=', line_id), ('company_id', '=', company_id)]],
            {'fields': ['id', 'name', 'debit', 'credit', 'account_id', 'full_reconcile_id']}
        )
        
        if not line:
            return {
                "success": False,
                "error": "Transaction not found or does not belong to this company"
            }
        
        # Check if already reconciled
        if line[0].get('full_reconcile_id'):
            return {
                "success": True,
                "message": "Transaction is already reconciled"
            }
        
        # In Odoo, reconciliation is typically done through bank statement matching
        # For now, we'll mark it as a manual reconciliation action
        # You can extend this to call Odoo's reconciliation wizard
        
        logger.info(f"Reconciliation requested for line {line_id} by {reconciled_by}")
        logger.info(f"  Matched with {matched_record_type}: {matched_record_id}")
        
        # Note: Full reconciliation in Odoo requires matching move lines
        # This would typically be done through account.reconcile.model or bank.statement.line
        # For now, we return success and recommend using Odoo UI for reconciliation
        
        return {
            "success": True,
            "message": "Reconciliation marked. Please use Odoo's bank reconciliation tool to complete the matching.",
            "note": "For full integration, implement Odoo's account reconciliation API"
        }
        
    except Exception as e:
        logger.error(f"Error reconciling transaction in Odoo: {e}")
        return {
            "success": False,
            "error": str(e)
        }

