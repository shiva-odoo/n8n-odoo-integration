import os
import xmlrpc.client
from datetime import datetime

def authenticate_odoo():
    """Authenticate with Odoo and return connection objects and uid"""
    try:
        # Connection details
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB")
        username = os.getenv("ODOO_USERNAME")
        password = os.getenv("ODOO_API_KEY")
        
        # Create connection objects
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Authenticate
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return None, None, None, None
        
        print("✅ Odoo authentication successful")
        return common, models, uid, db
        
    except Exception as e:
        print(f"❌ Odoo authentication failed: {str(e)}")
        return None, None, None, None

def get_invoices_list(company_id):
    """Get list of all invoices for a specific company"""
    try:
        common, models, uid, db = authenticate_odoo()
        if not uid:
            return {
                'success': False,
                'error': 'Odoo authentication failed'
            }
        
        # Search for invoices (account.move with move_type = 'out_invoice') - exclude cancelled
        invoice_ids = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'account.move',
            'search',
            [[
                ('company_id', '=', company_id),
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('state', '!=', 'cancel')  # Exclude cancelled invoices
            ]]
        )
        
        # Read invoice data
        invoices = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'account.move',
            'read',
            [invoice_ids],
            {
                'fields': [
                    'name', 'partner_id', 'invoice_date', 'amount_total',
                    'amount_untaxed', 'amount_tax', 'state', 'move_type',
                    'payment_state', 'currency_id', 'ref'
                ]
            }
        )
        
        return {
            'success': True,
            'data': invoices,
            'count': len(invoices)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to retrieve invoices: {str(e)}'
        }

def get_bills_list(company_id):
    """Get list of all bills for a specific company"""
    try:
        common, models, uid, db = authenticate_odoo()
        if not uid:
            return {
                'success': False,
                'error': 'Odoo authentication failed'
            }
        
        # Search for bills (account.move with move_type = 'in_invoice') - exclude cancelled
        bill_ids = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'account.move',
            'search',
            [[
                ('company_id', '=', company_id),
                ('move_type', 'in', ['in_invoice', 'in_refund']),
                ('state', '!=', 'cancel')  # Exclude cancelled bills
            ]]
        )
        
        # Read bill data
        bills = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'account.move',
            'read',
            [bill_ids],
            {
                'fields': [
                    'name', 'partner_id', 'invoice_date', 'amount_total',
                    'amount_untaxed', 'amount_tax', 'state', 'move_type',
                    'payment_state', 'currency_id', 'ref'
                ]
            }
        )
        
        return {
            'success': True,
            'data': bills,
            'count': len(bills)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to retrieve bills: {str(e)}'
        }

def get_customers_list(company_id):
    """Get list of all customers for a specific company"""
    try:
        common, models, uid, db = authenticate_odoo()
        if not uid:
            return {
                'success': False,
                'error': 'Odoo authentication failed'
            }
        
        # Search for customers (res.partner with is_customer = True)
        customer_ids = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'res.partner',
            'search',
            [[
                ('company_id', 'in', [company_id, False]),  # Include company-specific and global partners
                ('is_company', '=', True),
                ('customer_rank', '>', 0)
            ]]
        )
        
        # Read customer data
        customers = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'res.partner',
            'read',
            [customer_ids],
            {
                'fields': [
                    'name', 'email', 'phone', 'street', 'city',
                    'state_id', 'country_id', 'zip', 'vat', 'customer_rank',
                    'is_company', 'parent_id', 'category_id'
                ]
            }
        )
        
        return {
            'success': True,
            'data': customers,
            'count': len(customers)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to retrieve customers: {str(e)}'
        }

def get_vendors_list(company_id):
    """Get list of all vendors for a specific company"""
    try:
        common, models, uid, db = authenticate_odoo()
        if not uid:
            return {
                'success': False,
                'error': 'Odoo authentication failed'
            }
        
        # Search for vendors (res.partner with is_vendor = True)
        vendor_ids = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'res.partner',
            'search',
            [[
                ('company_id', 'in', [company_id, False]),  # Include company-specific and global partners
                ('supplier_rank', '>', 0)
            ]]
        )
        
        # Read vendor data
        vendors = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'res.partner',
            'read',
            [vendor_ids],
            {
                'fields': [
                    'name', 'email', 'phone', 'street', 'city',
                    'state_id', 'country_id', 'zip', 'vat', 'supplier_rank',
                    'is_company', 'parent_id', 'category_id'
                ]
            }
        )
        
        return {
            'success': True,
            'data': vendors,
            'count': len(vendors)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to retrieve vendors: {str(e)}'
        }

def get_bank_transactions_list(company_id):
    """Get list of all bank transactions (journal entries) for a specific company"""
    try:
        common, models, uid, db = authenticate_odoo()
        if not uid:
            return {
                'success': False,
                'error': 'Odoo authentication failed'
            }
        
        # Search for journal entries (account.move.line) related to bank journals
        # First, get bank journal IDs
        bank_journal_ids = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'account.journal',
            'search',
            [[
                ('company_id', '=', company_id)
            ]]
        )
        
        if not bank_journal_ids:
            return {
                'success': True,
                'data': [],
                'count': 0,
                'message': 'No bank journals found for this company'
            }
        
        # Search for journal entries in bank journals (exclude cancelled entries)
        transaction_ids = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'account.move.line',
            'search',
            [[
                ('company_id', '=', company_id),
                ('journal_id', 'in', bank_journal_ids),
                ('move_id.state', '!=', 'cancel')  # Exclude cancelled journal entries
            ]]
        )
        
        # Read transaction data
        transactions = models.execute_kw(
            db, uid, os.getenv("ODOO_API_KEY"),
            'account.move.line',
            'read',
            [transaction_ids],
            {
                'fields': [
                    'name', 'date', 'debit', 'credit', 'balance', 'partner_id', 
                    'ref', 'move_id', 'journal_id', 'account_id', 'currency_id',
                    'amount_currency', 'reconciled', 'payment_id'
                ]
            }
        )
        
        return {
            'success': True,
            'data': transactions,
            'count': len(transactions)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to retrieve bank transactions: {str(e)}'
        }

def get_all_company_data(data):
    """
    Main function to get all data for a specific company
    Args:
        data: Dictionary containing 'company_id'
    Returns:
        Combined JSON response with all entity data
    """
    try:
        # Extract company_id from data
        if 'company_id' not in data:
            return {
                'success': False,
                'error': 'company_id is required in request data'
            }
        
        company_id = int(data['company_id'])
        print(f"🏢 Retrieving data for company ID: {company_id}")
        
        # Initialize response structure
        response = {
            'success': True,
            'company_id': company_id,
            'timestamp': datetime.now().isoformat(),
            'data': {}
        }
        
        # Get invoices
        print("📄 Fetching invoices...")
        invoices_result = get_invoices_list(company_id)
        response['data']['invoices'] = invoices_result
        
        # Get bills
        print("📋 Fetching bills...")
        bills_result = get_bills_list(company_id)
        response['data']['bills'] = bills_result
        
        # Get customers
        print("👥 Fetching customers...")
        customers_result = get_customers_list(company_id)
        response['data']['customers'] = customers_result
        
        # Get vendors
        print("🏪 Fetching vendors...")
        vendors_result = get_vendors_list(company_id)
        response['data']['vendors'] = vendors_result
        
        # Get bank transactions
        print("💳 Fetching bank transactions...")
        transactions_result = get_bank_transactions_list(company_id)
        response['data']['bank_transactions'] = transactions_result
        
        # Add summary
        response['summary'] = {
            'invoices_count': invoices_result.get('count', 0),
            'bills_count': bills_result.get('count', 0),
            'customers_count': customers_result.get('count', 0),
            'vendors_count': vendors_result.get('count', 0),
            'transactions_count': transactions_result.get('count', 0)
        }
        
        # Check if any operation failed
        failed_operations = []
        if not invoices_result.get('success'):
            failed_operations.append('invoices')
        if not bills_result.get('success'):
            failed_operations.append('bills')
        if not customers_result.get('success'):
            failed_operations.append('customers')
        if not vendors_result.get('success'):
            failed_operations.append('vendors')
        if not transactions_result.get('success'):
            failed_operations.append('bank_transactions')
        
        if failed_operations:
            response['warnings'] = f"Failed to retrieve: {', '.join(failed_operations)}"
        
        print("✅ Data retrieval completed successfully")
        return response
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to retrieve company data: {str(e)}',
            'company_id': data.get('company_id'),
            'timestamp': datetime.now().isoformat()
        }

def main(data):
    """
    Main function to process the request and return all company data
    Args:
        data: Dictionary containing 'company_id' and other request parameters
    Returns:
        Dictionary with all company data or error information
    """
    try:
        # Get all data for the company
        result = get_all_company_data(data)
        
        # Log summary for debugging
        if result['success']:
            print(f"\n📊 Summary for Company {result['company_id']}:")
            summary = result.get('summary', {})
            print(f"   Invoices: {summary.get('invoices_count', 0)}")
            print(f"   Bills: {summary.get('bills_count', 0)}")
            print(f"   Customers: {summary.get('customers_count', 0)}")
            print(f"   Vendors: {summary.get('vendors_count', 0)}")
            print(f"   Bank Transactions: {summary.get('transactions_count', 0)}")
        else:
            print(f"❌ Error: {result['error']}")
        
        return result
        
    except Exception as e:
        error_response = {
            'success': False,
            'error': f'Main function error: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }
        print(f"❌ Main function error: {str(e)}")
        return error_response