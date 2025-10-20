# compliance.py
import xmlrpc.client
import os
from datetime import datetime, timedelta
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
# COMPLIANCE ITEMS FROM ODOO
# ============================================================================

def get_compliance_items(business_company_id, status=None):
    """Get compliance items from Odoo for a specific company"""
    try:
        company_id = int(business_company_id) if business_company_id else None
        if not company_id:
            return {'success': False, 'error': 'Invalid company_id'}
        
        models, uid, db, password = get_odoo_connection()
        
        compliance_items = []
        
        # 1. VAT RETURNS - Check for unpaid/unfiled VAT
        try:
            vat_domain = [
                ('company_id', '=', company_id),
                ('move_type', '=', 'entry'),
                ('state', '=', 'draft'),
                ('ref', 'ilike', 'VAT')
            ]
            vat_entries = models.execute_kw(
                db, uid, password,
                'account.move', 'search_read',
                [vat_domain],
                {'fields': ['name', 'date', 'ref'], 'limit': 10}
            )
            
            for entry in vat_entries:
                compliance_items.append({
                    'id': f"vat_{entry['id']}",
                    'title': f"VAT Return - {entry.get('ref', entry['name'])}",
                    'description': f"VAT return filing required",
                    'category': 'vat_returns',
                    'status': 'pending',
                    'priority': 'high',
                    'dueDate': entry.get('date', ''),
                    'source': 'odoo',
                    'odoo_id': entry['id']
                })
        except Exception as e:
            logger.warning(f"Could not fetch VAT entries: {e}")
        
        # 2. TAX FILINGS - Check for tax-related pending items
        try:
            tax_domain = [
                ('company_id', '=', company_id),
                ('tax_line_id', '!=', False),
                ('parent_state', '=', 'draft')
            ]
            tax_lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [tax_domain],
                {'fields': ['move_id', 'date', 'tax_line_id'], 'limit': 10}
            )
            
            for line in tax_lines:
                compliance_items.append({
                    'id': f"tax_{line['id']}",
                    'title': f"Tax Filing - {line['tax_line_id'][1] if line.get('tax_line_id') else 'Unknown'}",
                    'description': 'Tax filing pending approval',
                    'category': 'tax_filings',
                    'status': 'pending',
                    'priority': 'high',
                    'dueDate': line.get('date', ''),
                    'source': 'odoo',
                    'odoo_id': line['move_id'][0] if line.get('move_id') else None
                })
        except Exception as e:
            logger.warning(f"Could not fetch tax entries: {e}")
        
        # 3. PAYROLL - Check for draft payroll entries
        try:
            # Check for draft journal entries in payroll journals
            payroll_journals = models.execute_kw(
                db, uid, password,
                'account.journal', 'search_read',
                [[('company_id', '=', company_id), ('type', '=', 'general'), ('name', 'ilike', 'payroll')]],
                {'fields': ['id', 'name']}
            )
            
            if payroll_journals:
                journal_ids = [j['id'] for j in payroll_journals]
                payroll_domain = [
                    ('company_id', '=', company_id),
                    ('journal_id', 'in', journal_ids),
                    ('state', '=', 'draft')
                ]
                payroll_entries = models.execute_kw(
                    db, uid, password,
                    'account.move', 'search_read',
                    [payroll_domain],
                    {'fields': ['name', 'date'], 'limit': 10}
                )
                
                for entry in payroll_entries:
                    compliance_items.append({
                        'id': f"payroll_{entry['id']}",
                        'title': f"Payroll Entry - {entry['name']}",
                        'description': 'Payroll entry pending posting',
                        'category': 'payroll',
                        'status': 'pending',
                        'priority': 'medium',
                        'dueDate': entry.get('date', ''),
                        'source': 'odoo',
                        'odoo_id': entry['id']
                    })
        except Exception as e:
            logger.warning(f"Could not fetch payroll entries: {e}")
        
        # 4. FINANCIAL STATEMENTS - Check for unposted journal entries
        try:
            unposted_domain = [
                ('company_id', '=', company_id),
                ('state', '=', 'draft'),
                ('move_type', 'in', ['entry', 'out_invoice', 'in_invoice'])
            ]
            unposted_moves = models.execute_kw(
                db, uid, password,
                'account.move', 'search_read',
                [unposted_domain],
                {'fields': ['name', 'date', 'move_type'], 'limit': 10}
            )
            
            for move in unposted_moves:
                move_type_map = {
                    'entry': 'Journal Entry',
                    'out_invoice': 'Customer Invoice',
                    'in_invoice': 'Vendor Bill'
                }
                compliance_items.append({
                    'id': f"fs_{move['id']}",
                    'title': f"Unposted {move_type_map.get(move['move_type'], 'Entry')} - {move['name']}",
                    'description': 'Document pending posting for financial statements',
                    'category': 'financial_statements',
                    'status': 'pending',
                    'priority': 'medium',
                    'dueDate': move.get('date', ''),
                    'source': 'odoo',
                    'odoo_id': move['id']
                })
        except Exception as e:
            logger.warning(f"Could not fetch unposted moves: {e}")
        
        # 5. BANK RECONCILIATION - Check for unreconciled items
        try:
            unreconciled_domain = [
                ('company_id', '=', company_id),
                ('account_type', 'in', ['asset_cash', 'liability_credit_card']),
                ('parent_state', '=', 'posted'),
                ('full_reconcile_id', '=', False)
            ]
            unreconciled_lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [unreconciled_domain],
                {'fields': ['date', 'name', 'debit', 'credit'], 'limit': 5}
            )
            
            if unreconciled_lines:
                total_unreconciled = len(unreconciled_lines)
                compliance_items.append({
                    'id': f"bank_recon_{company_id}",
                    'title': f"Bank Reconciliation Required",
                    'description': f"{total_unreconciled}+ unreconciled bank transactions",
                    'category': 'bank_reconciliation',
                    'status': 'pending',
                    'priority': 'high',
                    'dueDate': datetime.now().strftime('%Y-%m-%d'),
                    'source': 'odoo'
                })
        except Exception as e:
            logger.warning(f"Could not fetch unreconciled items: {e}")
        
        # Sort by priority and due date
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        compliance_items.sort(key=lambda x: (
            priority_order.get(x.get('priority', 'low'), 3),
            x.get('dueDate', '')
        ))
        
        # Filter by status if requested
        if status:
            compliance_items = [item for item in compliance_items if item.get('status') == status]
        
        return {
            "success": True,
            "items": compliance_items,
            "total_count": len(compliance_items)
        }
        
    except Exception as e:
        logger.error(f"Error getting compliance items from Odoo: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def create_compliance_item(business_company_id, item_data, created_by):
    """Create a manual compliance reminder (not supported - items are auto-generated from Odoo)"""
    return {
        "success": False,
        "error": "Manual compliance items are not supported. Items are automatically generated from Odoo data."
    }

def update_compliance_item(compliance_id, business_company_id, update_data, updated_by):
    """Update a compliance item in Odoo (e.g., mark invoice as posted)"""
    try:
        # Extract Odoo ID from compliance_id
        if not compliance_id.startswith(('vat_', 'tax_', 'payroll_', 'fs_', 'bank_')):
            return {'success': False, 'error': 'Invalid compliance item ID'}
        
        # If updating status to 'completed', we could post the draft entry in Odoo
        # For now, return success (items auto-update when Odoo state changes)
        logger.info(f"Compliance item {compliance_id} status update requested by {updated_by}")
        
        return {
            "success": True,
            "message": "Compliance item updated. Please complete the action in Odoo to remove it from pending items."
        }
        
    except Exception as e:
        logger.error(f"Error updating compliance item: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def delete_compliance_item(compliance_id, business_company_id):
    """Delete/dismiss a compliance item (not supported - items are auto-generated)"""
    return {
        "success": False,
        "error": "Compliance items are auto-generated from Odoo and cannot be manually deleted. Complete the task in Odoo to remove it."
    }

