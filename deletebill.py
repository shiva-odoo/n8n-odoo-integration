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
    Delete vendor bill from HTTP request data
    
    Expected data format:
    {
        "bill_id": 123,                        # required
        "force_delete": false,                 # optional, defaults to false
        "reset_to_draft": true                 # optional, try resetting to draft first
    }
    """
    
    # Validate required fields
    if not data.get('bill_id'):
        return {
            'success': False,
            'error': 'bill_id is required'
        }
    
    try:
        bill_id = int(data['bill_id'])
    except (ValueError, TypeError):
        return {
            'success': False,
            'error': 'bill_id must be a valid number'
        }
    
    # Connection details
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
        
        # Check if bill exists and get detailed info
        current_bill = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', bill_id), ('move_type', '=', 'in_invoice')]], 
            {'fields': ['name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state', 'payment_state']}
        )
        
        if not current_bill:
            return {
                'success': False,
                'error': f'Vendor bill with ID {bill_id} not found'
            }
        
        bill_info = current_bill[0]
        bill_status = bill_info.get('state', 'draft')
        payment_status = bill_info.get('payment_state', 'not_paid')
        
        # Check if bill is safe to delete
        warnings = []
        if bill_status == 'posted':
            warnings.append('Bill is posted - affects accounting records')
            if payment_status in ['paid', 'in_payment', 'partial']:
                warnings.append(f'Bill has payments ({payment_status}) - may cause reconciliation issues')
        
        # Attempt deletion
        try:
            result = models.execute_kw(
                db, uid, password,
                'account.move', 'unlink',
                [[bill_id]]
            )
            
            if result:
                return {
                    'success': True,
                    'bill_id': bill_id,
                    'bill_number': bill_info.get('name'),
                    'vendor_name': bill_info['partner_id'][1] if bill_info.get('partner_id') else 'Unknown',
                    'amount': bill_info.get('amount_total'),
                    'warnings': warnings,
                    'message': 'Vendor bill deleted successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to delete bill - unknown error'
                }
                
        except Exception as delete_error:
            error_msg = str(delete_error)
            
            # If deletion failed and reset_to_draft is requested, try that
            if data.get('reset_to_draft', False) and ('posted' in error_msg.lower() or 'state' in error_msg.lower()):
                try:
                    # Reset to draft first
                    reset_result = models.execute_kw(
                        db, uid, password,
                        'account.move', 'button_draft',
                        [[bill_id]]
                    )
                    
                    if reset_result:
                        # Try deletion again after reset
                        delete_result = models.execute_kw(
                            db, uid, password,
                            'account.move', 'unlink',
                            [[bill_id]]
                        )
                        
                        if delete_result:
                            return {
                                'success': True,
                                'bill_id': bill_id,
                                'bill_number': bill_info.get('name'),
                                'vendor_name': bill_info['partner_id'][1] if bill_info.get('partner_id') else 'Unknown',
                                'amount': bill_info.get('amount_total'),
                                'warnings': warnings,
                                'reset_to_draft': True,
                                'message': 'Bill reset to draft and deleted successfully'
                            }
                        else:
                            return {
                                'success': False,
                                'error': 'Bill reset to draft but deletion still failed'
                            }
                    else:
                        return {
                            'success': False,
                            'error': f'Failed to reset bill to draft: {error_msg}'
                        }
                        
                except Exception as reset_error:
                    return {
                        'success': False,
                        'error': f'Reset failed: {str(reset_error)}. Original error: {error_msg}'
                    }
            
            # Provide helpful error messages
            if "posted" in error_msg.lower() or "state" in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Cannot delete posted bill',
                    'suggestion': 'Try setting reset_to_draft: true or create a credit note instead',
                    'bill_status': bill_status,
                    'payment_status': payment_status
                }
            elif "constraint" in error_msg.lower() or "foreign key" in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Bill has related records that prevent deletion',
                    'suggestion': 'Remove related payments/reconciliations first or cancel the bill instead'
                }
            else:
                return {
                    'success': False,
                    'error': f'Deletion failed: {error_msg}'
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

def delete(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

def list_vendor_bills():
    """Get list of vendor bills for reference"""
    
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
        
        bills = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('move_type', '=', 'in_invoice')]], 
            {'fields': ['id', 'name', 'partner_id', 'amount_total', 'state', 'ref', 'invoice_date', 'payment_state'], 'limit': 20}
        )
        
        return {
            'success': True,
            'bills': bills,
            'count': len(bills)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
    
def get_vendor_bill_details(bill_id):
    """Get complete details of a vendor bill including line items and accounting entries"""
    
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
        
        # Get the main bill details
        bill = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', bill_id), ('move_type', '=', 'in_invoice')]], 
            {'fields': [
                'id', 'name', 'partner_id', 'amount_total', 'amount_untaxed', 
                'amount_tax', 'state', 'ref', 'invoice_date', 'invoice_date_due',
                'payment_state', 'currency_id', 'journal_id', 'company_id',
                'invoice_origin', 'narration', 'payment_reference',
                'line_ids', 'invoice_line_ids'
            ]}
        )
        
        if not bill:
            return {'success': False, 'error': 'Bill not found'}
        
        bill_data = bill[0]
        
        # Get invoice line items (product lines)
        if bill_data.get('invoice_line_ids'):
            invoice_lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [[('id', 'in', bill_data['invoice_line_ids'])]], 
                {'fields': [
                    'id', 'name', 'product_id', 'quantity', 'price_unit',
                    'price_subtotal', 'price_total', 'account_id', 'tax_ids',
                    'analytic_distribution', 'discount', 'product_uom_id'
                ]}
            )
            bill_data['invoice_lines'] = invoice_lines
        else:
            bill_data['invoice_lines'] = []
        
        # Get all accounting move lines (journal entries including tax lines)
        if bill_data.get('line_ids'):
            move_lines = models.execute_kw(
                db, uid, password,
                'account.move.line', 'search_read',
                [[('id', 'in', bill_data['line_ids'])]], 
                {'fields': [
                    'id', 'name', 'account_id', 'debit', 'credit', 'balance',
                    'partner_id', 'product_id', 'quantity', 'price_unit',
                    'tax_line_id', 'tax_ids', 'tax_base_amount', 'tax_repartition_line_id',
                    'analytic_distribution', 'exclude_from_invoice_tab'
                ]}
            )
            
            # Separate different types of lines for clarity
            product_lines = []
            tax_lines = []
            payable_lines = []
            other_lines = []
            
            for line in move_lines:
                if line.get('tax_line_id'):  # This is a tax line
                    tax_lines.append(line)
                elif line.get('exclude_from_invoice_tab') == False:  # Product/service lines
                    product_lines.append(line)
                elif line['credit'] > 0 and not line.get('tax_line_id'):  # Usually accounts payable
                    payable_lines.append(line)
                else:
                    other_lines.append(line)
            
            bill_data['accounting_lines'] = {
                'product_lines': product_lines,
                'tax_lines': tax_lines,
                'payable_lines': payable_lines,
                'other_lines': other_lines,
                'all_lines': move_lines
            }
        else:
            bill_data['accounting_lines'] = {
                'product_lines': [],
                'tax_lines': [],
                'payable_lines': [],
                'other_lines': [],
                'all_lines': []
            }
        
        # Get tax details if there are taxes
        tax_details = []
        if bill_data.get('line_ids'):
            # Get unique tax IDs from move lines
            tax_ids = set()
            for line in bill_data['accounting_lines']['all_lines']:
                if line.get('tax_line_id'):
                    tax_ids.add(line['tax_line_id'][0])
                if line.get('tax_ids'):
                    tax_ids.update(line['tax_ids'])
            
            if tax_ids:
                taxes = models.execute_kw(
                    db, uid, password,
                    'account.tax', 'search_read',
                    [[('id', 'in', list(tax_ids))]], 
                    {'fields': ['id', 'name', 'amount', 'type_tax_use', 'tax_group_id']}
                )
                tax_details = taxes
        
        bill_data['tax_details'] = tax_details
        
        # Calculate totals summary
        total_debit = sum(line['debit'] for line in bill_data['accounting_lines']['all_lines'])
        total_credit = sum(line['credit'] for line in bill_data['accounting_lines']['all_lines'])
        
        return {
            'success': True,
            'bill': bill_data,
            'summary': {
                'total_debit': total_debit,
                'total_credit': total_credit,
                'balance_check': total_debit - total_credit,  # Should be 0
                'line_count': len(bill_data['accounting_lines']['all_lines']),
                'tax_count': len(tax_details),
                'invoice_line_count': len(bill_data['invoice_lines'])
            }
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

