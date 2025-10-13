
import xmlrpc.client
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#test
def resolve_company_id(company_id_input):
    """
    Resolve company_id to integer ID
    Accepts: integer, string number, or company name/code
    Returns: integer company ID or None
    """
    if not company_id_input:
        return None
    
    # If it's already an integer, return it
    if isinstance(company_id_input, int):
        return company_id_input
    
    # If it's a string that can be converted to int
    if isinstance(company_id_input, str):
        # Try converting to int first
        try:
            return int(company_id_input)
        except ValueError:
            # It's a string like "admin" - need to query Odoo
            try:
                models, uid, db, password = get_odoo_connection()
                
                # Try to find company by name or reference
                companies = models.execute_kw(
                    db, uid, password,
                    'res.company', 'search_read',
                    [[('name', 'ilike', company_id_input)]],
                    {'fields': ['id', 'name'], 'limit': 1}
                )
                
                if companies:
                    logger.info(f"Resolved company '{company_id_input}' to ID {companies[0]['id']}")
                    return companies[0]['id']
                
                # If not found, get the user's default company
                logger.warning(f"Company '{company_id_input}' not found, using user's default company")
                user_data = models.execute_kw(
                    db, uid, password,
                    'res.users', 'read',
                    [uid],
                    {'fields': ['company_id']}
                )
                
                if user_data and user_data[0].get('company_id'):
                    return user_data[0]['company_id'][0]
                    
            except Exception as e:
                logger.error(f"Error resolving company_id: {str(e)}")
                return None
    
    return None


def get_odoo_connection():
    """Establish connection to Odoo"""
    try:
        # Load Odoo credentials from environment
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB")
        username = os.getenv("ODOO_USERNAME")
        password = os.getenv("ODOO_API_KEY")

        # DEBUGGING: Print individual checks
        print(f"\n🔍 Connection attempt:")
        print(f"  URL present: {bool(url)} - Value: {url}")
        print(f"  DB present: {bool(db)} - Value: {db}")
        print(f"  Username present: {bool(username)} - Value: {username}")
        print(f"  Password present: {bool(password)} - Length: {len(password) if password else 0}")

        if not all([url, db, username, password]):
            missing = []
            if not url: missing.append("ODOO_URL")
            if not db: missing.append("ODOO_DB")
            if not username: missing.append("ODOO_USERNAME")
            if not password: missing.append("ODOO_API_KEY")
            
            error_msg = f"Missing Odoo connection configuration: {', '.join(missing)}"
            print(f"❌ {error_msg}")
            raise Exception(error_msg)

        # Setup connection
        print(f"🔗 Connecting to {url}...")
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        
        print(f"🔐 Authenticating as {username}...")
        uid = common.authenticate(db, username, password, {})

        if not uid:
            print("❌ Authentication failed - Invalid credentials")
            raise Exception("Authentication with Odoo failed")

        print(f"✅ Successfully authenticated! UID: {uid}")
        return models, uid, db, password
        
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        raise

# ============================================================================
# FINANCIAL REPORTS
# ============================================================================

def get_profit_loss_report(data: Dict) -> Dict:
    """Get Profit & Loss (Income Statement) report"""
    try:
        company_id_input = data.get('company_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        # Resolve company_id (handles both int and string)
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get revenue accounts
        revenue_domain = [
            ('account_type', 'in', ['income', 'income_other'])
        ]
        revenue_accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [revenue_domain],
            {'fields': ['id', 'name', 'code', 'account_type']}
        )
        
        # Get expense accounts
        expense_domain = [
            ('account_type', 'in', ['expense', 'expense_depreciation', 'expense_direct_cost'])
        ]
        expense_accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [expense_domain],
            {'fields': ['id', 'name', 'code', 'account_type']}
        )
        
        # Get account move lines for revenue
        revenue_data = []
        total_revenue = 0
        
        for account in revenue_accounts:
            line_domain = [
                ('account_id', '=', account['id']),
                ('parent_state', '=', 'posted')
            ]
            if date_from:
                line_domain.append(('date', '>=', date_from))
            if date_to:
                line_domain.append(('date', '<=', date_to))
            
            lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [line_domain],
                {'fields': ['debit', 'credit', 'balance']}
            )
            
            account_balance = sum(line['credit'] - line['debit'] for line in lines)
            total_revenue += account_balance
            
            revenue_data.append({
                'account_code': account['code'],
                'account_name': account['name'],
                'amount': account_balance
            })
        
        # Get account move lines for expenses
        expense_data = []
        total_expenses = 0
        
        for account in expense_accounts:
            line_domain = [
                ('account_id', '=', account['id']),
                ('parent_state', '=', 'posted')
            ]
            if date_from:
                line_domain.append(('date', '>=', date_from))
            if date_to:
                line_domain.append(('date', '<=', date_to))
            
            lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [line_domain],
                {'fields': ['debit', 'credit', 'balance']}
            )
            
            account_balance = sum(line['debit'] - line['credit'] for line in lines)
            total_expenses += account_balance
            
            expense_data.append({
                'account_code': account['code'],
                'account_name': account['name'],
                'amount': account_balance
            })
        
        net_profit = total_revenue - total_expenses
        
        return {
            'success': True,
            'report_type': 'Profit & Loss',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'data': {
                'revenue': {
                    'total': total_revenue,
                    'accounts': revenue_data
                },
                'expenses': {
                    'total': total_expenses,
                    'accounts': expense_data
                },
                'net_profit': net_profit
            }
        }
    
    except Exception as e:
        logger.error(f"Error generating P&L report: {str(e)}")
        return {'success': False, 'error': str(e)}


def get_balance_sheet_report(data: Dict) -> Dict:
    """Get Balance Sheet report"""
    try:
        company_id_input = data.get('company_id')
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get all account types for balance sheet
        account_types = {
            'assets': ['asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_prepayments', 'asset_fixed'],
            'liabilities': ['liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current'],
            'equity': ['equity', 'equity_unaffected']
        }
        
        balance_sheet = {}
        
        for category, types in account_types.items():
            accounts_domain = [
                ('account_type', 'in', types)
            ]
            accounts = models.execute_kw(
                db, uid, password,
                'account.account', 'search_read',
                [accounts_domain],
                {'fields': ['id', 'name', 'code', 'account_type']}
            )
            
            category_data = []
            category_total = 0
            
            for account in accounts:
                line_domain = [
                    ('account_id', '=', account['id']),
                    ('parent_state', '=', 'posted'),
                    ('date', '<=', date)
                ]
                
                lines = models.execute_kw(
                    db, uid, password,
                    'account.move.line', 'search_read',
                    [line_domain],
                    {'fields': ['debit', 'credit', 'balance']}
                )
                
                account_balance = sum(line['balance'] for line in lines)
                category_total += account_balance
                
                category_data.append({
                    'account_code': account['code'],
                    'account_name': account['name'],
                    'account_type': account['account_type'],
                    'balance': account_balance
                })
            
            balance_sheet[category] = {
                'total': category_total,
                'accounts': category_data
            }
        
        return {
            'success': True,
            'report_type': 'Balance Sheet',
            'company_id': company_id,
            'date': date,
            'data': balance_sheet
        }
    
    except Exception as e:
        logger.error(f"Error generating balance sheet: {str(e)}")
        return {'success': False, 'error': str(e)}


def get_cash_flow_report(data: Dict) -> Dict:
    """Get Cash Flow Statement"""
    try:
        company_id_input = data.get('company_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get cash and bank accounts
        cash_domain = [
            ('account_type', 'in', ['asset_cash', 'liability_credit_card'])
        ]
        cash_accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [cash_domain],
            {'fields': ['id', 'name', 'code']}
        )
        
        cash_flow_data = []
        opening_balance = 0
        closing_balance = 0
        
        for account in cash_accounts:
            # Opening balance
            opening_domain = [
                ('account_id', '=', account['id']),
                ('parent_state', '=', 'posted')
            ]
            if date_from:
                opening_domain.append(('date', '<', date_from))
            
            opening_lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [opening_domain],
                {'fields': ['balance']}
            )
            account_opening = sum(line['balance'] for line in opening_lines)
            
            # Period movements
            period_domain = [
                ('account_id', '=', account['id']),
                ('parent_state', '=', 'posted')
            ]
            if date_from:
                period_domain.append(('date', '>=', date_from))
            if date_to:
                period_domain.append(('date', '<=', date_to))
            
            period_lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [period_domain],
                {'fields': ['debit', 'credit', 'balance', 'name', 'date']}
            )
            
            inflows = sum(line['debit'] for line in period_lines)
            outflows = sum(line['credit'] for line in period_lines)
            account_closing = account_opening + sum(line['balance'] for line in period_lines)
            
            opening_balance += account_opening
            closing_balance += account_closing
            
            cash_flow_data.append({
                'account_code': account['code'],
                'account_name': account['name'],
                'opening_balance': account_opening,
                'inflows': inflows,
                'outflows': outflows,
                'net_movement': inflows - outflows,
                'closing_balance': account_closing
            })
        
        return {
            'success': True,
            'report_type': 'Cash Flow Statement',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'data': {
                'opening_balance': opening_balance,
                'closing_balance': closing_balance,
                'net_change': closing_balance - opening_balance,
                'accounts': cash_flow_data
            }
        }
    
    except Exception as e:
        logger.error(f"Error generating cash flow report: {str(e)}")
        return {'success': False, 'error': str(e)}


# ============================================================================
# ACCOUNTS REPORTS
# ============================================================================

def get_aged_payables_report(data: Dict) -> Dict:
    """Get Aged Payables (Accounts Payable) report"""
    try:
        company_id_input = data.get('company_id')
        as_of_date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get unpaid vendor bills
        bill_domain = [
            ('company_id', '=', company_id),
            ('move_type', '=', 'in_invoice'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('state', '=', 'posted'),
            ('invoice_date', '<=', as_of_date)
        ]
        
        bills = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [bill_domain],
            {'fields': ['id', 'name', 'partner_id', 'invoice_date', 'invoice_date_due', 
                       'amount_total', 'amount_residual']}
        )
        
        # Categorize by age
        aged_data = {
            'current': [],
            '1-30': [],
            '31-60': [],
            '61-90': [],
            'over_90': []
        }
        
        totals = {
            'current': 0,
            '1-30': 0,
            '31-60': 0,
            '61-90': 0,
            'over_90': 0
        }
        
        as_of = datetime.strptime(as_of_date, '%Y-%m-%d')
        
        for bill in bills:
            due_date = datetime.strptime(bill['invoice_date_due'], '%Y-%m-%d') if bill.get('invoice_date_due') else datetime.strptime(bill['invoice_date'], '%Y-%m-%d')
            days_overdue = (as_of - due_date).days
            
            bill_data = {
                'bill_number': bill['name'],
                'vendor': bill['partner_id'][1] if bill['partner_id'] else 'Unknown',
                'invoice_date': bill['invoice_date'],
                'due_date': bill.get('invoice_date_due'),
                'days_overdue': days_overdue,
                'amount': bill['amount_residual']
            }
            
            if days_overdue <= 0:
                aged_data['current'].append(bill_data)
                totals['current'] += bill['amount_residual']
            elif days_overdue <= 30:
                aged_data['1-30'].append(bill_data)
                totals['1-30'] += bill['amount_residual']
            elif days_overdue <= 60:
                aged_data['31-60'].append(bill_data)
                totals['31-60'] += bill['amount_residual']
            elif days_overdue <= 90:
                aged_data['61-90'].append(bill_data)
                totals['61-90'] += bill['amount_residual']
            else:
                aged_data['over_90'].append(bill_data)
                totals['over_90'] += bill['amount_residual']
        
        return {
            'success': True,
            'report_type': 'Aged Payables',
            'company_id': company_id,
            'as_of_date': as_of_date,
            'data': aged_data,
            'totals': totals,
            'grand_total': sum(totals.values())
        }
    
    except Exception as e:
        logger.error(f"Error generating aged payables: {str(e)}")
        return {'success': False, 'error': str(e)}


def get_aged_receivables_report(data: Dict) -> Dict:
    """Get Aged Receivables (Accounts Receivable) report"""
    try:
        company_id_input = data.get('company_id')
        as_of_date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get unpaid customer invoices
        invoice_domain = [
            ('company_id', '=', company_id),
            ('move_type', '=', 'out_invoice'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('state', '=', 'posted'),
            ('invoice_date', '<=', as_of_date)
        ]
        
        invoices = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [invoice_domain],
            {'fields': ['id', 'name', 'partner_id', 'invoice_date', 'invoice_date_due', 
                       'amount_total', 'amount_residual']}
        )
        
        # Categorize by age
        aged_data = {
            'current': [],
            '1-30': [],
            '31-60': [],
            '61-90': [],
            'over_90': []
        }
        
        totals = {
            'current': 0,
            '1-30': 0,
            '31-60': 0,
            '61-90': 0,
            'over_90': 0
        }
        
        as_of = datetime.strptime(as_of_date, '%Y-%m-%d')
        
        for invoice in invoices:
            due_date = datetime.strptime(invoice['invoice_date_due'], '%Y-%m-%d') if invoice.get('invoice_date_due') else datetime.strptime(invoice['invoice_date'], '%Y-%m-%d')
            days_overdue = (as_of - due_date).days
            
            invoice_data = {
                'invoice_number': invoice['name'],
                'customer': invoice['partner_id'][1] if invoice['partner_id'] else 'Unknown',
                'invoice_date': invoice['invoice_date'],
                'due_date': invoice.get('invoice_date_due'),
                'days_overdue': days_overdue,
                'amount': invoice['amount_residual']
            }
            
            if days_overdue <= 0:
                aged_data['current'].append(invoice_data)
                totals['current'] += invoice['amount_residual']
            elif days_overdue <= 30:
                aged_data['1-30'].append(invoice_data)
                totals['1-30'] += invoice['amount_residual']
            elif days_overdue <= 60:
                aged_data['31-60'].append(invoice_data)
                totals['31-60'] += invoice['amount_residual']
            elif days_overdue <= 90:
                aged_data['61-90'].append(invoice_data)
                totals['61-90'] += invoice['amount_residual']
            else:
                aged_data['over_90'].append(invoice_data)
                totals['over_90'] += invoice['amount_residual']
        
        return {
            'success': True,
            'report_type': 'Aged Receivables',
            'company_id': company_id,
            'as_of_date': as_of_date,
            'data': aged_data,
            'totals': totals,
            'grand_total': sum(totals.values())
        }
    
    except Exception as e:
        logger.error(f"Error generating aged receivables: {str(e)}")
        return {'success': False, 'error': str(e)}


def get_general_ledger_report(data: Dict) -> Dict:
    """Get General Ledger report for all accounts"""
    try:
        company_id_input = data.get('company_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        account_id = data.get('account_id')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get accounts
        account_domain = []
        if account_id:
            account_domain.append(('id', '=', account_id))
        
        accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [account_domain],
            {'fields': ['id', 'name', 'code', 'account_type']}
        )
        
        ledger_data = []
        
        for account in accounts:
            # Get move lines
            line_domain = [
                ('account_id', '=', account['id']),
                ('parent_state', '=', 'posted')
            ]
            if date_from:
                line_domain.append(('date', '>=', date_from))
            if date_to:
                line_domain.append(('date', '<=', date_to))
            
            lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [line_domain],
                {'fields': ['date', 'name', 'ref', 'partner_id', 'debit', 'credit', 'balance', 'move_id']}
            )
            
            if lines:
                ledger_data.append({
                    'account_code': account['code'],
                    'account_name': account['name'],
                    'account_type': account['account_type'],
                    'total_debit': sum(line['debit'] for line in lines),
                    'total_credit': sum(line['credit'] for line in lines),
                    'balance': sum(line['balance'] for line in lines),
                    'transactions': [{
                        'date': line['date'],
                        'description': line['name'],
                        'reference': line.get('ref', ''),
                        'partner': line['partner_id'][1] if line.get('partner_id') else '',
                        'debit': line['debit'],
                        'credit': line['credit'],
                        'balance': line['balance']
                    } for line in lines]
                })
        
        return {
            'success': True,
            'report_type': 'General Ledger',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'data': ledger_data
        }
    
    except Exception as e:
        logger.error(f"Error generating general ledger: {str(e)}")
        return {'success': False, 'error': str(e)}


def get_trial_balance_report(data: Dict) -> Dict:
    """Get Trial Balance report"""
    try:
        company_id_input = data.get('company_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get all accounts
        accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [[]],
            {'fields': ['id', 'name', 'code', 'account_type']}
        )
        
        trial_balance = []
        total_debit = 0
        total_credit = 0
        
        for account in accounts:
            line_domain = [
                ('account_id', '=', account['id']),
                ('parent_state', '=', 'posted')
            ]
            if date_from:
                line_domain.append(('date', '>=', date_from))
            if date_to:
                line_domain.append(('date', '<=', date_to))
            
            lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [line_domain],
                {'fields': ['debit', 'credit', 'balance']}
            )
            
            account_debit = sum(line['debit'] for line in lines)
            account_credit = sum(line['credit'] for line in lines)
            account_balance = sum(line['balance'] for line in lines)
            
            if account_debit != 0 or account_credit != 0:
                trial_balance.append({
                    'account_code': account['code'],
                    'account_name': account['name'],
                    'account_type': account['account_type'],
                    'debit': account_debit,
                    'credit': account_credit,
                    'balance': account_balance
                })
                
                total_debit += account_debit
                total_credit += account_credit
        
        return {
            'success': True,
            'report_type': 'Trial Balance',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'data': trial_balance,
            'totals': {
                'debit': total_debit,
                'credit': total_credit,
                'difference': total_debit - total_credit
            }
        }
    
    except Exception as e:
        logger.error(f"Error generating trial balance: {str(e)}")
        return {'success': False, 'error': str(e)}


# ============================================================================
# TAX REPORTS
# ============================================================================

def get_tax_report(data: Dict) -> Dict:
    """Get Tax Report (VAT/GST)"""
    try:
        company_id_input = data.get('company_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get tax lines
        tax_domain = [
            ('company_id', '=', company_id),
            ('parent_state', '=', 'posted'),
            ('tax_line_id', '!=', False)
        ]
        if date_from:
            tax_domain.append(('date', '>=', date_from))
        if date_to:
            tax_domain.append(('date', '<=', date_to))
        
        tax_lines = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [tax_domain],
            {'fields': ['date', 'name', 'tax_line_id', 'debit', 'credit', 'balance', 'move_id', 'partner_id']}
        )
        
        # Group by tax
        tax_summary = {}
        
        for line in tax_lines:
            tax_id = line['tax_line_id'][0]
            tax_name = line['tax_line_id'][1]
            
            if tax_id not in tax_summary:
                tax_summary[tax_id] = {
                    'tax_name': tax_name,
                    'base_amount': 0,
                    'tax_amount': 0,
                    'transactions': []
                }
            
            tax_amount = line['credit'] - line['debit']
            tax_summary[tax_id]['tax_amount'] += tax_amount
            tax_summary[tax_id]['transactions'].append({
                'date': line['date'],
                'description': line['name'],
                'partner': line['partner_id'][1] if line.get('partner_id') else '',
                'tax_amount': tax_amount
            })
        
        return {
            'success': True,
            'report_type': 'Tax Report',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'data': list(tax_summary.values()),
            'total_tax': sum(tax['tax_amount'] for tax in tax_summary.values())
        }
    
    except Exception as e:
        logger.error(f"Error generating tax report: {str(e)}")
        return {'success': False, 'error': str(e)}


# ============================================================================
# SALES & PURCHASE REPORTS
# ============================================================================

def get_sales_report(data: Dict) -> Dict:
    """Get Sales Report"""
    try:
        company_id_input = data.get('company_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        group_by = data.get('group_by', 'customer')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get customer invoices
        invoice_domain = [
            ('company_id', '=', company_id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted')
        ]
        if date_from:
            invoice_domain.append(('invoice_date', '>=', date_from))
        if date_to:
            invoice_domain.append(('invoice_date', '<=', date_to))
        
        invoices = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [invoice_domain],
            {'fields': ['id', 'name', 'partner_id', 'invoice_date', 'amount_untaxed', 
                       'amount_tax', 'amount_total', 'invoice_user_id']}
        )
        
        # Get invoice lines for product breakdown
        invoice_ids = [inv['id'] for inv in invoices]
        if invoice_ids:
            lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [[('move_id', 'in', invoice_ids), ('product_id', '!=', False)]],
                {'fields': ['product_id', 'quantity', 'price_subtotal', 'move_id']}
            )
        else:
            lines = []
        
        # Group data
        if group_by == 'customer':
            grouped_data = {}
            for invoice in invoices:
                partner_id = invoice['partner_id'][0] if invoice['partner_id'] else 0
                partner_name = invoice['partner_id'][1] if invoice['partner_id'] else 'Unknown'
                
                if partner_id not in grouped_data:
                    grouped_data[partner_id] = {
                        'customer_name': partner_name,
                        'invoice_count': 0,
                        'total_untaxed': 0,
                        'total_tax': 0,
                        'total': 0
                    }
                
                grouped_data[partner_id]['invoice_count'] += 1
                grouped_data[partner_id]['total_untaxed'] += invoice['amount_untaxed']
                grouped_data[partner_id]['total_tax'] += invoice['amount_tax']
                grouped_data[partner_id]['total'] += invoice['amount_total']
        
        elif group_by == 'product':
            grouped_data = {}
            for line in lines:
                product_id = line['product_id'][0]
                product_name = line['product_id'][1]
                
                if product_id not in grouped_data:
                    grouped_data[product_id] = {
                        'product_name': product_name,
                        'quantity_sold': 0,
                        'total_sales': 0
                    }
                
                grouped_data[product_id]['quantity_sold'] += line['quantity']
                grouped_data[product_id]['total_sales'] += line['price_subtotal']
        
        else:  # salesperson
            grouped_data = {}
            for invoice in invoices:
                user_id = invoice['invoice_user_id'][0] if invoice.get('invoice_user_id') else 0
                user_name = invoice['invoice_user_id'][1] if invoice.get('invoice_user_id') else 'Unassigned'
                
                if user_id not in grouped_data:
                    grouped_data[user_id] = {
                        'salesperson': user_name,
                        'invoice_count': 0,
                        'total_sales': 0
                    }
                
                grouped_data[user_id]['invoice_count'] += 1
                grouped_data[user_id]['total_sales'] += invoice['amount_total']
        
        return {
            'success': True,
            'report_type': 'Sales Report',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'group_by': group_by,
            'data': list(grouped_data.values()),
            'summary': {
                'total_invoices': len(invoices),
                'total_amount': sum(inv['amount_total'] for inv in invoices)
            }
        }
    
    except Exception as e:
        logger.error(f"Error generating sales report: {str(e)}")
        return {'success': False, 'error': str(e)}


def get_purchase_report(data: Dict) -> Dict:
    """Get Purchase Report"""
    try:
        company_id_input = data.get('company_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        group_by = data.get('group_by', 'vendor')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get vendor bills
        bill_domain = [
            ('company_id', '=', company_id),
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted')
        ]
        if date_from:
            bill_domain.append(('invoice_date', '>=', date_from))
        if date_to:
            bill_domain.append(('invoice_date', '<=', date_to))
        
        bills = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [bill_domain],
            {'fields': ['id', 'name', 'partner_id', 'invoice_date', 'amount_untaxed', 
                       'amount_tax', 'amount_total']}
        )
        
        # Get bill lines for product breakdown
        bill_ids = [bill['id'] for bill in bills]
        if bill_ids:
            lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [[('move_id', 'in', bill_ids), ('product_id', '!=', False)]],
                {'fields': ['product_id', 'quantity', 'price_subtotal', 'move_id']}
            )
        else:
            lines = []
        
        # Group data
        if group_by == 'vendor':
            grouped_data = {}
            for bill in bills:
                partner_id = bill['partner_id'][0] if bill['partner_id'] else 0
                partner_name = bill['partner_id'][1] if bill['partner_id'] else 'Unknown'
                
                if partner_id not in grouped_data:
                    grouped_data[partner_id] = {
                        'vendor_name': partner_name,
                        'bill_count': 0,
                        'total_untaxed': 0,
                        'total_tax': 0,
                        'total': 0
                    }
                
                grouped_data[partner_id]['bill_count'] += 1
                grouped_data[partner_id]['total_untaxed'] += bill['amount_untaxed']
                grouped_data[partner_id]['total_tax'] += bill['amount_tax']
                grouped_data[partner_id]['total'] += bill['amount_total']
        
        else:  # product
            grouped_data = {}
            for line in lines:
                product_id = line['product_id'][0]
                product_name = line['product_id'][1]
                
                if product_id not in grouped_data:
                    grouped_data[product_id] = {
                        'product_name': product_name,
                        'quantity_purchased': 0,
                        'total_cost': 0
                    }
                
                grouped_data[product_id]['quantity_purchased'] += line['quantity']
                grouped_data[product_id]['total_cost'] += line['price_subtotal']
        
        return {
            'success': True,
            'report_type': 'Purchase Report',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'group_by': group_by,
            'data': list(grouped_data.values()),
            'summary': {
                'total_bills': len(bills),
                'total_amount': sum(bill['amount_total'] for bill in bills)
            }
        }
    
    except Exception as e:
        logger.error(f"Error generating purchase report: {str(e)}")
        return {'success': False, 'error': str(e)}


# ============================================================================
# BANK & PAYMENT REPORTS
# ============================================================================

def get_bank_reconciliation_report(data: Dict) -> Dict:
    """Get Bank Reconciliation Report"""
    try:
        company_id_input = data.get('company_id')
        journal_id = data.get('journal_id')
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        if not journal_id:
            return {'success': False, 'error': 'journal_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get bank journal
        journal = models.execute_kw(
            db, uid, password,
            'account.journal', 'search_read',
            [[('id', '=', journal_id), ('company_id', '=', company_id)]],
            {'fields': ['name', 'default_account_id']}
        )
        
        if not journal:
            return {'success': False, 'error': 'Journal not found'}
        
        account_id = journal[0]['default_account_id'][0]
        
        # Get all bank statement lines
        line_domain = [
            ('account_id', '=', account_id),
            ('date', '<=', date)
        ]
        
        lines = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [line_domain],
            {'fields': ['date', 'name', 'ref', 'debit', 'credit', 'balance', 
                       'reconciled', 'full_reconcile_id']}
        )
        
        reconciled_lines = [l for l in lines if l.get('full_reconcile_id')]
        unreconciled_lines = [l for l in lines if not l.get('full_reconcile_id')]
        
        book_balance = sum(l['balance'] for l in lines)
        unreconciled_amount = sum(l['balance'] for l in unreconciled_lines)
        
        return {
            'success': True,
            'report_type': 'Bank Reconciliation',
            'company_id': company_id,
            'journal_name': journal[0]['name'],
            'as_of_date': date,
            'data': {
                'book_balance': book_balance,
                'reconciled_count': len(reconciled_lines),
                'unreconciled_count': len(unreconciled_lines),
                'unreconciled_amount': unreconciled_amount,
                'unreconciled_transactions': [{
                    'date': line['date'],
                    'description': line['name'],
                    'reference': line.get('ref', ''),
                    'debit': line['debit'],
                    'credit': line['credit'],
                    'balance': line['balance']
                } for line in unreconciled_lines]
            }
        }
    
    except Exception as e:
        logger.error(f"Error generating bank reconciliation: {str(e)}")
        return {'success': False, 'error': str(e)}


def get_payment_report(data: Dict) -> Dict:
    """Get Payment Report (both received and made)"""
    try:
        company_id_input = data.get('company_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        payment_type = data.get('payment_type', 'all')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get payments
        payment_domain = [
            ('company_id', '=', company_id),
            ('state', '=', 'posted')
        ]
        
        if payment_type == 'inbound':
            payment_domain.append(('payment_type', '=', 'inbound'))
        elif payment_type == 'outbound':
            payment_domain.append(('payment_type', '=', 'outbound'))
        
        if date_from:
            payment_domain.append(('date', '>=', date_from))
        if date_to:
            payment_domain.append(('date', '<=', date_to))
        
        payments = models.execute_kw(
            db, uid, password,
            'account.payment', 'search_read',
            [payment_domain],
            {'fields': ['name', 'date', 'partner_id', 'amount', 'payment_type', 
                       'partner_type', 'communication', 'journal_id']}
        )
        
        inbound_total = sum(p['amount'] for p in payments if p['payment_type'] == 'inbound')
        outbound_total = sum(p['amount'] for p in payments if p['payment_type'] == 'outbound')
        
        return {
            'success': True,
            'report_type': 'Payment Report',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'payment_type': payment_type,
            'data': [{
                'payment_number': p['name'],
                'date': p['date'],
                'partner': p['partner_id'][1] if p.get('partner_id') else 'Unknown',
                'payment_type': p['payment_type'],
                'partner_type': p['partner_type'],
                'amount': p['amount'],
                'reference': p.get('communication', ''),
                'journal': p['journal_id'][1] if p.get('journal_id') else ''
            } for p in payments],
            'summary': {
                'total_payments': len(payments),
                'inbound_total': inbound_total,
                'outbound_total': outbound_total,
                'net': inbound_total - outbound_total
            }
        }
    
    except Exception as e:
        logger.error(f"Error generating payment report: {str(e)}")
        return {'success': False, 'error': str(e)}


# ============================================================================
# BUDGET & VARIANCE REPORTS
# ============================================================================

def get_budget_vs_actual_report(data: Dict) -> Dict:
    """Get Budget vs Actual Report"""
    try:
        company_id_input = data.get('company_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Get budgets
        budget_domain = [('company_id', '=', company_id)]
        if date_from:
            budget_domain.append(('date_from', '>=', date_from))
        if date_to:
            budget_domain.append(('date_to', '<=', date_to))
        
        budgets = models.execute_kw(
            db, uid, password,
            'crossovered.budget', 'search_read',
            [budget_domain],
            {'fields': ['name', 'date_from', 'date_to', 'state']}
        )
        
        budget_data = []
        
        for budget in budgets:
            # Get budget lines
            lines = models.execute_kw(
                db, uid, password,
                'crossovered.budget.lines', 'search_read',
                [[('crossovered_budget_id', '=', budget['id'])]],
                {'fields': ['analytic_account_id', 'general_budget_id', 
                           'planned_amount', 'practical_amount', 'percentage']}
            )
            
            budget_data.append({
                'budget_name': budget['name'],
                'date_from': budget['date_from'],
                'date_to': budget['date_to'],
                'status': budget['state'],
                'lines': [{
                    'budget_position': line['general_budget_id'][1] if line.get('general_budget_id') else '',
                    'analytic_account': line['analytic_account_id'][1] if line.get('analytic_account_id') else '',
                    'planned': line['planned_amount'],
                    'actual': line['practical_amount'],
                    'variance': line['planned_amount'] - line['practical_amount'],
                    'percentage': line.get('percentage', 0)
                } for line in lines]
            })
        
        return {
            'success': True,
            'report_type': 'Budget vs Actual',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'data': budget_data
        }
    
    except Exception as e:
        logger.error(f"Error generating budget report: {str(e)}")
        return {'success': False, 'error': str(e)}


# ============================================================================
# PARTNER (CUSTOMER/VENDOR) REPORTS
# ============================================================================

def get_partner_ledger_report(data: Dict) -> Dict:
    """Get Partner Ledger Report"""
    try:
        company_id_input = data.get('company_id')
        partner_id = data.get('partner_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        partner_type = data.get('partner_type', 'all')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        models, uid, db, password = get_odoo_connection()
        
        # Build domain for account move lines
        account_types = []
        if partner_type == 'customer' or partner_type == 'all':
            account_types.append('asset_receivable')
        if partner_type == 'supplier' or partner_type == 'all':
            account_types.append('liability_payable')
        
        account_domain = [
            ('account_type', 'in', account_types)
        ]
        
        accounts = models.execute_kw(
            db, uid, password,
            'account.account', 'search_read',
            [account_domain],
            {'fields': ['id']}
        )
        
        account_ids = [acc['id'] for acc in accounts]
        
        # Get move lines
        line_domain = [
            ('account_id', 'in', account_ids),
            ('parent_state', '=', 'posted')
        ]
        
        if partner_id:
            line_domain.append(('partner_id', '=', partner_id))
        if date_from:
            line_domain.append(('date', '>=', date_from))
        if date_to:
            line_domain.append(('date', '<=', date_to))
        
        lines = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [line_domain],
            {'fields': ['date', 'name', 'ref', 'partner_id', 'debit', 'credit', 
                       'balance', 'move_id', 'account_id']}
        )
        
        # Group by partner
        partner_data = {}
        
        for line in lines:
            p_id = line['partner_id'][0] if line.get('partner_id') else 0
            p_name = line['partner_id'][1] if line.get('partner_id') else 'Unknown'
            
            if p_id not in partner_data:
                partner_data[p_id] = {
                    'partner_name': p_name,
                    'total_debit': 0,
                    'total_credit': 0,
                    'balance': 0,
                    'transactions': []
                }
            
            partner_data[p_id]['total_debit'] += line['debit']
            partner_data[p_id]['total_credit'] += line['credit']
            partner_data[p_id]['balance'] += line['balance']
            partner_data[p_id]['transactions'].append({
                'date': line['date'],
                'description': line['name'],
                'reference': line.get('ref', ''),
                'debit': line['debit'],
                'credit': line['credit'],
                'balance': line['balance']
            })
        
        return {
            'success': True,
            'report_type': 'Partner Ledger',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'partner_type': partner_type,
            'data': list(partner_data.values())
        }
    
    except Exception as e:
        logger.error(f"Error generating partner ledger: {str(e)}")
        return {'success': False, 'error': str(e)}


# ============================================================================
# EXECUTIVE SUMMARY REPORT
# ============================================================================

def get_executive_summary_report(data: Dict) -> Dict:
    """Get Executive Summary with key metrics"""
    try:
        company_id_input = data.get('company_id')
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        if not company_id_input:
            return {'success': False, 'error': 'company_id is required'}
        
        company_id = resolve_company_id(company_id_input)
        if not company_id:
            return {'success': False, 'error': f'Invalid company_id: {company_id_input}'}
        
        # Get multiple reports
        pl_data = get_profit_loss_report({'company_id': company_id, 'date_from': date_from, 'date_to': date_to})
        bs_data = get_balance_sheet_report({'company_id': company_id, 'date': date_to})
        cf_data = get_cash_flow_report({'company_id': company_id, 'date_from': date_from, 'date_to': date_to})
        sales_data = get_sales_report({'company_id': company_id, 'date_from': date_from, 'date_to': date_to})
        purchase_data = get_purchase_report({'company_id': company_id, 'date_from': date_from, 'date_to': date_to})
        
        executive_summary = {
            'revenue': pl_data['data']['revenue']['total'] if pl_data['success'] else 0,
            'expenses': pl_data['data']['expenses']['total'] if pl_data['success'] else 0,
            'net_profit': pl_data['data']['net_profit'] if pl_data['success'] else 0,
            'profit_margin': (pl_data['data']['net_profit'] / pl_data['data']['revenue']['total'] * 100) if pl_data['success'] and pl_data['data']['revenue']['total'] > 0 else 0,
            'total_assets': bs_data['data']['assets']['total'] if bs_data['success'] else 0,
            'total_liabilities': bs_data['data']['liabilities']['total'] if bs_data['success'] else 0,
            'equity': bs_data['data']['equity']['total'] if bs_data['success'] else 0,
            'cash_position': cf_data['data']['closing_balance'] if cf_data['success'] else 0,
            'sales_count': sales_data['summary']['total_invoices'] if sales_data['success'] else 0,
            'purchase_count': purchase_data['summary']['total_bills'] if purchase_data['success'] else 0
        }
        
        return {
            'success': True,
            'report_type': 'Executive Summary',
            'company_id': company_id,
            'date_from': date_from,
            'date_to': date_to,
            'data': executive_summary
        }
    
    except Exception as e:
        logger.error(f"Error generating executive summary: {str(e)}")
        return {'success': False, 'error': str(e)}


# ============================================================================
# DOWNLOAD FUNCTIONS (CSV Export)
# ============================================================================

def download_profit_loss_csv(data: Dict) -> tuple:
    """Generate Profit & Loss Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_profit_loss_report(data)
        
        if not result.get('success'):
            return None, result
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(['Profit & Loss Statement'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result['date_from']} to {result['date_to']}"])
        writer.writerow([])
        
        # Revenue section
        writer.writerow(['REVENUE'])
        writer.writerow(['Account Code', 'Account Name', 'Amount'])
        for acc in result['data']['revenue']['accounts']:
            writer.writerow([acc['account_code'], acc['account_name'], acc['amount']])
        writer.writerow(['Total Revenue', '', result['data']['revenue']['total']])
        writer.writerow([])
        
        # Expenses section
        writer.writerow(['EXPENSES'])
        writer.writerow(['Account Code', 'Account Name', 'Amount'])
        for acc in result['data']['expenses']['accounts']:
            writer.writerow([acc['account_code'], acc['account_name'], acc['amount']])
        writer.writerow(['Total Expenses', '', result['data']['expenses']['total']])
        writer.writerow([])
        
        # Net profit
        writer.writerow(['NET PROFIT', '', result['data']['net_profit']])
        
        filename = f'profit_loss_{result["date_from"]}_{result["date_to"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating P&L CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_balance_sheet_csv(data: Dict) -> tuple:
    """Generate Balance Sheet Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_balance_sheet_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Balance Sheet'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['As of Date:', result['date']])
        writer.writerow([])
        
        # Assets
        writer.writerow(['ASSETS'])
        writer.writerow(['Account Code', 'Account Name', 'Type', 'Balance'])
        for acc in result['data']['assets']['accounts']:
            writer.writerow([acc['account_code'], acc['account_name'], acc['account_type'], acc['balance']])
        writer.writerow(['Total Assets', '', '', result['data']['assets']['total']])
        writer.writerow([])
        
        # Liabilities
        writer.writerow(['LIABILITIES'])
        writer.writerow(['Account Code', 'Account Name', 'Type', 'Balance'])
        for acc in result['data']['liabilities']['accounts']:
            writer.writerow([acc['account_code'], acc['account_name'], acc['account_type'], acc['balance']])
        writer.writerow(['Total Liabilities', '', '', result['data']['liabilities']['total']])
        writer.writerow([])
        
        # Equity
        writer.writerow(['EQUITY'])
        writer.writerow(['Account Code', 'Account Name', 'Type', 'Balance'])
        for acc in result['data']['equity']['accounts']:
            writer.writerow([acc['account_code'], acc['account_name'], acc['account_type'], acc['balance']])
        writer.writerow(['Total Equity', '', '', result['data']['equity']['total']])
        
        filename = f'balance_sheet_{result["date"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Balance Sheet CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_cash_flow_csv(data: Dict) -> tuple:
    """Generate Cash Flow Statement as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_cash_flow_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Cash Flow Statement'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result['date_from']} to {result['date_to']}"])
        writer.writerow([])
        
        writer.writerow(['Opening Balance:', result['data']['opening_balance']])
        writer.writerow([])
        
        writer.writerow(['Account Code', 'Account Name', 'Opening', 'Inflows', 'Outflows', 'Net Movement', 'Closing'])
        for acc in result['data']['accounts']:
            writer.writerow([
                acc['account_code'], 
                acc['account_name'], 
                acc['opening_balance'],
                acc['inflows'],
                acc['outflows'],
                acc['net_movement'],
                acc['closing_balance']
            ])
        
        writer.writerow([])
        writer.writerow(['Closing Balance:', result['data']['closing_balance']])
        writer.writerow(['Net Change:', result['data']['net_change']])
        
        filename = f'cash_flow_{result["date_from"]}_{result["date_to"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Cash Flow CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_trial_balance_csv(data: Dict) -> tuple:
    """Generate Trial Balance Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_trial_balance_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Trial Balance'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result.get('date_from', '')} to {result.get('date_to', '')}"])
        writer.writerow([])
        
        writer.writerow(['Account Code', 'Account Name', 'Account Type', 'Debit', 'Credit', 'Balance'])
        for acc in result['data']:
            writer.writerow([
                acc['account_code'],
                acc['account_name'],
                acc['account_type'],
                acc['debit'],
                acc['credit'],
                acc['balance']
            ])
        
        writer.writerow([])
        writer.writerow(['TOTALS', '', '', result['totals']['debit'], result['totals']['credit'], result['totals']['difference']])
        
        filename = f'trial_balance_{result.get("date_to", "")}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Trial Balance CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_general_ledger_csv(data: Dict) -> tuple:
    """Generate General Ledger Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_general_ledger_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['General Ledger'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result.get('date_from', '')} to {result.get('date_to', '')}"])
        writer.writerow([])
        
        for account in result['data']:
            writer.writerow([f"Account: {account['account_code']} - {account['account_name']}"])
            writer.writerow(['Date', 'Description', 'Reference', 'Partner', 'Debit', 'Credit', 'Balance'])
            
            for txn in account['transactions']:
                writer.writerow([
                    txn['date'],
                    txn['description'],
                    txn['reference'],
                    txn['partner'],
                    txn['debit'],
                    txn['credit'],
                    txn['balance']
                ])
            
            writer.writerow(['TOTAL', '', '', '', account['total_debit'], account['total_credit'], account['balance']])
            writer.writerow([])
        
        filename = f'general_ledger_{result.get("date_to", "")}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating General Ledger CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_aged_receivables_csv(data: Dict) -> tuple:
    """Generate Aged Receivables Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_aged_receivables_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Aged Receivables Report'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['As of Date:', result['as_of_date']])
        writer.writerow([])
        
        categories = ['current', '1-30', '31-60', '61-90', 'over_90']
        category_names = ['Current', '1-30 Days', '31-60 Days', '61-90 Days', 'Over 90 Days']
        
        for cat, cat_name in zip(categories, category_names):
            writer.writerow([f'{cat_name} (Total: {result["totals"][cat]})'])
            if result['data'][cat]:
                writer.writerow(['Invoice #', 'Customer', 'Invoice Date', 'Due Date', 'Days Overdue', 'Amount'])
                for inv in result['data'][cat]:
                    writer.writerow([
                        inv['invoice_number'],
                        inv['customer'],
                        inv['invoice_date'],
                        inv.get('due_date', ''),
                        inv['days_overdue'],
                        inv['amount']
                    ])
            writer.writerow([])
        
        writer.writerow(['GRAND TOTAL', '', '', '', '', result['grand_total']])
        
        filename = f'aged_receivables_{result["as_of_date"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Aged Receivables CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_aged_payables_csv(data: Dict) -> tuple:
    """Generate Aged Payables Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_aged_payables_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Aged Payables Report'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['As of Date:', result['as_of_date']])
        writer.writerow([])
        
        categories = ['current', '1-30', '31-60', '61-90', 'over_90']
        category_names = ['Current', '1-30 Days', '31-60 Days', '61-90 Days', 'Over 90 Days']
        
        for cat, cat_name in zip(categories, category_names):
            writer.writerow([f'{cat_name} (Total: {result["totals"][cat]})'])
            if result['data'][cat]:
                writer.writerow(['Bill #', 'Vendor', 'Invoice Date', 'Due Date', 'Days Overdue', 'Amount'])
                for bill in result['data'][cat]:
                    writer.writerow([
                        bill['bill_number'],
                        bill['vendor'],
                        bill['invoice_date'],
                        bill.get('due_date', ''),
                        bill['days_overdue'],
                        bill['amount']
                    ])
            writer.writerow([])
        
        writer.writerow(['GRAND TOTAL', '', '', '', '', result['grand_total']])
        
        filename = f'aged_payables_{result["as_of_date"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Aged Payables CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_tax_report_csv(data: Dict) -> tuple:
    """Generate Tax Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_tax_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Tax Report (VAT/GST)'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result['date_from']} to {result['date_to']}"])
        writer.writerow([])
        
        for tax_item in result['data']:
            writer.writerow([f"Tax: {tax_item['tax_name']}"])
            writer.writerow(['Date', 'Description', 'Partner', 'Tax Amount'])
            
            for txn in tax_item['transactions']:
                writer.writerow([
                    txn['date'],
                    txn['description'],
                    txn['partner'],
                    txn['tax_amount']
                ])
            
            writer.writerow(['Subtotal', '', '', tax_item['tax_amount']])
            writer.writerow([])
        
        writer.writerow(['TOTAL TAX', '', '', result['total_tax']])
        
        filename = f'tax_report_{result["date_from"]}_{result["date_to"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Tax Report CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_sales_report_csv(data: Dict) -> tuple:
    """Generate Sales Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_sales_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Sales Report'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result['date_from']} to {result['date_to']}"])
        writer.writerow(['Grouped By:', result['group_by']])
        writer.writerow([])
        
        if result['group_by'] == 'customer':
            writer.writerow(['Customer Name', 'Invoice Count', 'Total Untaxed', 'Total Tax', 'Total'])
            for item in result['data']:
                writer.writerow([
                    item['customer_name'],
                    item['invoice_count'],
                    item['total_untaxed'],
                    item['total_tax'],
                    item['total']
                ])
        elif result['group_by'] == 'product':
            writer.writerow(['Product Name', 'Quantity Sold', 'Total Sales'])
            for item in result['data']:
                writer.writerow([
                    item['product_name'],
                    item['quantity_sold'],
                    item['total_sales']
                ])
        else:
            writer.writerow(['Salesperson', 'Invoice Count', 'Total Sales'])
            for item in result['data']:
                writer.writerow([
                    item['salesperson'],
                    item['invoice_count'],
                    item['total_sales']
                ])
        
        writer.writerow([])
        writer.writerow(['Summary'])
        writer.writerow(['Total Invoices:', result['summary']['total_invoices']])
        writer.writerow(['Total Amount:', result['summary']['total_amount']])
        
        filename = f'sales_report_{result["date_from"]}_{result["date_to"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Sales Report CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_purchase_report_csv(data: Dict) -> tuple:
    """Generate Purchase Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_purchase_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Purchase Report'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result['date_from']} to {result['date_to']}"])
        writer.writerow(['Grouped By:', result['group_by']])
        writer.writerow([])
        
        if result['group_by'] == 'vendor':
            writer.writerow(['Vendor Name', 'Bill Count', 'Total Untaxed', 'Total Tax', 'Total'])
            for item in result['data']:
                writer.writerow([
                    item['vendor_name'],
                    item['bill_count'],
                    item['total_untaxed'],
                    item['total_tax'],
                    item['total']
                ])
        else:
            writer.writerow(['Product Name', 'Quantity Purchased', 'Total Cost'])
            for item in result['data']:
                writer.writerow([
                    item['product_name'],
                    item['quantity_purchased'],
                    item['total_cost']
                ])
        
        writer.writerow([])
        writer.writerow(['Summary'])
        writer.writerow(['Total Bills:', result['summary']['total_bills']])
        writer.writerow(['Total Amount:', result['summary']['total_amount']])
        
        filename = f'purchase_report_{result["date_from"]}_{result["date_to"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Purchase Report CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_payment_report_csv(data: Dict) -> tuple:
    """Generate Payment Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_payment_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Payment Report'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result['date_from']} to {result['date_to']}"])
        writer.writerow(['Payment Type:', result['payment_type']])
        writer.writerow([])
        
        writer.writerow(['Payment #', 'Date', 'Partner', 'Type', 'Partner Type', 'Amount', 'Reference', 'Journal'])
        for payment in result['data']:
            writer.writerow([
                payment['payment_number'],
                payment['date'],
                payment['partner'],
                payment['payment_type'],
                payment['partner_type'],
                payment['amount'],
                payment['reference'],
                payment['journal']
            ])
        
        writer.writerow([])
        writer.writerow(['Summary'])
        writer.writerow(['Total Payments:', result['summary']['total_payments']])
        writer.writerow(['Inbound Total:', result['summary']['inbound_total']])
        writer.writerow(['Outbound Total:', result['summary']['outbound_total']])
        writer.writerow(['Net:', result['summary']['net']])
        
        filename = f'payment_report_{result["date_from"]}_{result["date_to"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Payment Report CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_bank_reconciliation_csv(data: Dict) -> tuple:
    """Generate Bank Reconciliation Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_bank_reconciliation_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Bank Reconciliation Report'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Journal:', result['journal_name']])
        writer.writerow(['As of Date:', result['as_of_date']])
        writer.writerow([])
        
        writer.writerow(['Book Balance:', result['data']['book_balance']])
        writer.writerow(['Reconciled Count:', result['data']['reconciled_count']])
        writer.writerow(['Unreconciled Count:', result['data']['unreconciled_count']])
        writer.writerow(['Unreconciled Amount:', result['data']['unreconciled_amount']])
        writer.writerow([])
        
        writer.writerow(['Unreconciled Transactions'])
        writer.writerow(['Date', 'Description', 'Reference', 'Debit', 'Credit', 'Balance'])
        for txn in result['data']['unreconciled_transactions']:
            writer.writerow([
                txn['date'],
                txn['description'],
                txn['reference'],
                txn['debit'],
                txn['credit'],
                txn['balance']
            ])
        
        filename = f'bank_reconciliation_{result["as_of_date"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Bank Reconciliation CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_budget_vs_actual_csv(data: Dict) -> tuple:
    """Generate Budget vs Actual Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_budget_vs_actual_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Budget vs Actual Report'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result.get('date_from', '')} to {result.get('date_to', '')}"])
        writer.writerow([])
        
        for budget in result['data']:
            writer.writerow([f"Budget: {budget['budget_name']}"])
            writer.writerow(['Period:', f"{budget['date_from']} to {budget['date_to']}"])
            writer.writerow(['Status:', budget['status']])
            writer.writerow([])
            
            writer.writerow(['Budget Position', 'Analytic Account', 'Planned', 'Actual', 'Variance', 'Percentage'])
            for line in budget['lines']:
                writer.writerow([
                    line['budget_position'],
                    line['analytic_account'],
                    line['planned'],
                    line['actual'],
                    line['variance'],
                    f"{line['percentage']}%"
                ])
            writer.writerow([])
        
        filename = f'budget_vs_actual_{result.get("date_to", "")}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Budget vs Actual CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_partner_ledger_csv(data: Dict) -> tuple:
    """Generate Partner Ledger Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_partner_ledger_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Partner Ledger Report'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result.get('date_from', '')} to {result.get('date_to', '')}"])
        writer.writerow(['Partner Type:', result['partner_type']])
        writer.writerow([])
        
        for partner in result['data']:
            writer.writerow([f"Partner: {partner['partner_name']}"])
            writer.writerow(['Total Debit:', partner['total_debit']])
            writer.writerow(['Total Credit:', partner['total_credit']])
            writer.writerow(['Balance:', partner['balance']])
            writer.writerow([])
            
            writer.writerow(['Date', 'Description', 'Reference', 'Debit', 'Credit', 'Balance'])
            for txn in partner['transactions']:
                writer.writerow([
                    txn['date'],
                    txn['description'],
                    txn['reference'],
                    txn['debit'],
                    txn['credit'],
                    txn['balance']
                ])
            writer.writerow([])
        
        filename = f'partner_ledger_{result.get("date_to", "")}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Partner Ledger CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}


def download_executive_summary_csv(data: Dict) -> tuple:
    """Generate Executive Summary Report as CSV"""
    try:
        from io import StringIO
        import csv
        
        result = get_executive_summary_report(data)
        
        if not result.get('success'):
            return None, result
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Executive Summary'])
        writer.writerow(['Company ID:', result['company_id']])
        writer.writerow(['Period:', f"{result['date_from']} to {result['date_to']}"])
        writer.writerow([])
        
        writer.writerow(['Key Metrics', 'Value'])
        writer.writerow(['Revenue', result['data']['revenue']])
        writer.writerow(['Expenses', result['data']['expenses']])
        writer.writerow(['Net Profit', result['data']['net_profit']])
        writer.writerow(['Profit Margin (%)', f"{result['data']['profit_margin']:.2f}%"])
        writer.writerow([])
        
        writer.writerow(['Balance Sheet'])
        writer.writerow(['Total Assets', result['data']['total_assets']])
        writer.writerow(['Total Liabilities', result['data']['total_liabilities']])
        writer.writerow(['Equity', result['data']['equity']])
        writer.writerow([])
        
        writer.writerow(['Cash & Operations'])
        writer.writerow(['Cash Position', result['data']['cash_position']])
        writer.writerow(['Sales Count', result['data']['sales_count']])
        writer.writerow(['Purchase Count', result['data']['purchase_count']])
        
        filename = f'executive_summary_{result["date_from"]}_{result["date_to"]}.csv'
        return output.getvalue(), filename
        
    except Exception as e:
        logger.error(f"Error generating Executive Summary CSV: {str(e)}")
        return None, {'success': False, 'error': str(e)}