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
    Create vendor bill from HTTP request data
    
    Expected data format:
    {
        "vendor_id": 123,
        "invoice_date": "2025-01-15",  # optional, defaults to today, null sets to today
        "due_date": "2025-02-15",      # optional, defaults to today, null sets to today
        "vendor_ref": "INV-001",       # optional
        "description": "Office supplies",
        "amount": 1500.50
    }
    
    Or with multiple line items:
    {
        "vendor_id": 123,
        "invoice_date": "2025-01-15",
        "due_date": "2025-02-15",
        "vendor_ref": "INV-001",
        "line_items": [
            {
                "description": "Office supplies",
                "quantity": 2,
                "price_unit": 750.25,
                "tax_rate": 19
            },
            {
                "description": "Software license",
                "quantity": 1,
                "price_unit": 500.00,
                "tax_rate": 19
            }
        ],
        "subtotal": 1250.50,
        "tax_amount": 237.60,
        "total_amount": 1488.10
    }
    """
    
    # Validate required fields
    if not data.get('vendor_id'):
        return {
            'success': False,
            'error': 'vendor_id is required'
        }
    # Accept extra fields
    payment_reference = data.get('payment_reference')
    subtotal = data.get('subtotal')
    tax_amount = data.get('tax_amount')
    total_amount = data.get('total_amount')
    
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
        
        # Set up company context
        company_id = data.get('company_id')
        if company_id:
            context = {'allowed_company_ids': [company_id], 'default_company_id': company_id}
        else:
            # Get default company if not specified
            company_ids = models.execute_kw(
                db, uid, password,
                'res.company', 'search',
                [[('id', '>', 0)]],
                {'limit': 1}
            )
            company_id = company_ids[0] if company_ids else None
            context = {'default_company_id': company_id} if company_id else {}
        
        # Verify vendor exists and is a supplier
        vendor_id = data['vendor_id']
        vendor_exists = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_count',
            [[('id', '=', vendor_id), ('supplier_rank', '>', 0)]],
            {'context': context}
        )
        
        if not vendor_exists:
            return {
                'success': False,
                'error': f'Vendor with ID {vendor_id} not found or is not a supplier'
            }
        
        # Get vendor name for response
        vendor_info = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[vendor_id]], 
            {'fields': ['name'], 'context': context}
        )[0]
        
        # Get default purchase journal for the company (try with company filter first, then without)
        journal_ids = []
        if company_id:
            try:
                journal_ids = models.execute_kw(
                    db, uid, password,
                    'account.journal', 'search',
                    [[('type', '=', 'purchase'), ('company_id', '=', company_id)]],
                    {'limit': 1, 'context': context}
                )
            except:
                # If company_id filter fails, try without it
                pass
        
        if not journal_ids:
            # Fallback: search without company filter
            journal_ids = models.execute_kw(
                db, uid, password,
                'account.journal', 'search',
                [[('type', '=', 'purchase')]],
                {'limit': 1, 'context': context}
            )
        
        if not journal_ids:
            return {
                'success': False,
                'error': f'No purchase journal found'
            }
        
        journal_id = journal_ids[0]
        
        # Get default expense account (without company_id filter as it may not exist in this version)
        expense_account_ids = models.execute_kw(
            db, uid, password,
            'account.account', 'search',
            [[
                ('account_type', 'in', ['expense', 'asset_current']),  # Try both expense and current asset accounts
                ('deprecated', '=', False)
            ]],
            {'limit': 1, 'context': context}
        )
        
        if not expense_account_ids:
            # Fallback to any account that can be used for expenses
            expense_account_ids = models.execute_kw(
                db, uid, password,
                'account.account', 'search',
                [[
                    ('account_type', 'like', 'expense'),
                    ('deprecated', '=', False)
                ]],
                {'limit': 1, 'context': context}
            )
        
        if not expense_account_ids:
            # Final fallback - try to find any expense-related account
            expense_account_ids = models.execute_kw(
                db, uid, password,
                'account.account', 'search',
                [[
                    ('code', 'like', '5%'),  # Many expense accounts start with 5
                    ('deprecated', '=', False)
                ]],
                {'limit': 1, 'context': context}
            )
        
        default_expense_account = expense_account_ids[0] if expense_account_ids else None
        
        # Helper function to find tax by rate
        def find_tax_by_rate(tax_rate, company_id=None):
            """Find tax record by rate percentage"""
            try:
                domain = [('amount', '=', tax_rate), ('type_tax_use', '=', 'purchase')]
                # Try with company_id first if provided, but don't fail if field doesn't exist
                if company_id:
                    try:
                        tax_ids = models.execute_kw(
                            db, uid, password,
                            'account.tax', 'search',
                            [domain + [('company_id', '=', company_id)]],
                            {'limit': 1, 'context': context}
                        )
                        if tax_ids:
                            return tax_ids[0]
                    except:
                        # company_id field might not exist, try without it
                        pass
                
                # Search without company filter
                tax_ids = models.execute_kw(
                    db, uid, password,
                    'account.tax', 'search',
                    [domain],
                    {'limit': 1, 'context': context}
                )
                return tax_ids[0] if tax_ids else None
            except:
                return None
        
        # Handle invoice_date - default to today if not provided or null
        invoice_date_raw = data.get('invoice_date')
        if invoice_date_raw is None:
            invoice_date = datetime.now().strftime('%Y-%m-%d')
        else:
            invoice_date = invoice_date_raw
        
        # Validate invoice_date format
        try:
            datetime.strptime(invoice_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'invoice_date must be in YYYY-MM-DD format'
            }
        
        # Handle due_date - default to invoice_date + 30 days if not provided
        due_date_raw = data.get('due_date')
        if due_date_raw is None:
            # Set due date to 30 days after invoice date
            invoice_dt = datetime.strptime(invoice_date, '%Y-%m-%d')
            from datetime import timedelta
            due_dt = invoice_dt + timedelta(days=30)
            due_date = due_dt.strftime('%Y-%m-%d')
        else:
            due_date = due_date_raw
        
        # Validate due_date format
        try:
            datetime.strptime(due_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'due_date must be in YYYY-MM-DD format'
            }
        
        # Prepare bill data with all required fields
        bill_data = {
            'move_type': 'in_invoice',
            'partner_id': vendor_id,
            'invoice_date': invoice_date,
            'invoice_date_due': due_date,
            'journal_id': journal_id,
            'company_id': company_id,
        }
        
        # Add vendor reference if provided
        if data.get('vendor_ref'):
            bill_data['ref'] = data['vendor_ref']

        # Add payment_reference if provided
        if payment_reference and payment_reference != 'none':
            bill_data['payment_reference'] = payment_reference

        # Handle line items
        invoice_line_ids = []
        
        if 'line_items' in data and data['line_items']:
            # Multiple line items
            for item in data['line_items']:
                if not item.get('description'):
                    return {
                        'success': False,
                        'error': 'Each line item must have a description'
                    }
                
                try:
                    quantity = float(item.get('quantity', 1.0))
                    price_unit = float(item.get('price_unit', 0.0))
                    tax_rate = float(item.get('tax_rate', 0.0)) if item.get('tax_rate') else None
                except (ValueError, TypeError):
                    return {
                        'success': False,
                        'error': 'quantity, price_unit, and tax_rate must be valid numbers'
                    }
                
                line_item = {
                    'name': item['description'],
                    'quantity': quantity,
                    'price_unit': price_unit,
                }
                
                # Set account_id for the line item if available (crucial for journal entry creation)
                if default_expense_account:
                    line_item['account_id'] = default_expense_account
                # If no default account found, let Odoo use its own defaults
                
                # Apply tax if tax_rate is provided
                if tax_rate is not None and tax_rate > 0:
                    tax_id = find_tax_by_rate(tax_rate, company_id)
                    if tax_id:
                        line_item['tax_ids'] = [(6, 0, [tax_id])]
                    else:
                        # Log warning but continue - tax might be calculated differently
                        print(f"Warning: No tax found for rate {tax_rate}%, continuing without tax")
                
                invoice_line_ids.append((0, 0, line_item))
        
        elif data.get('description') and data.get('amount'):
            # Single line item (backward compatibility)
            try:
                amount = float(data['amount'])
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'amount must be a valid number'
                }
            
            line_item = {
                'name': data['description'],
                'quantity': 1.0,
                'price_unit': amount,
            }
            
            # Set account_id for the line item if available
            if default_expense_account:
                line_item['account_id'] = default_expense_account
            # If no default account found, let Odoo use its own defaults
            
            invoice_line_ids.append((0, 0, line_item))
        
        else:
            return {
                'success': False,
                'error': 'Either provide line_items array or description and amount'
            }
        
        bill_data['invoice_line_ids'] = invoice_line_ids
        
        # Create the bill with proper context
        bill_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [bill_data],
            {'context': context}
        )
        
        if not bill_id:
            return {
                'success': False,
                'error': 'Failed to create bill in Odoo'
            }
        
        # Update with explicit amounts if provided (before posting)
        update_data = {}
        
        # Set explicit amounts if provided
        if subtotal is not None:
            try:
                update_data['amount_untaxed'] = float(subtotal)
            except (ValueError, TypeError):
                pass
        
        if tax_amount is not None:
            try:
                update_data['amount_tax'] = float(tax_amount)
            except (ValueError, TypeError):
                pass
        
        if total_amount is not None:
            try:
                update_data['amount_total'] = float(total_amount)
            except (ValueError, TypeError):
                pass
        
        # Update the bill with explicit amounts if any were provided (before posting)
        if update_data:
            try:
                models.execute_kw(
                    db, uid, password,
                    'account.move', 'write',
                    [[bill_id], update_data],
                    {'context': context}
                )
            except Exception as e:
                # If we can't set the amounts directly, continue
                print(f"Warning: Could not set explicit amounts before posting: {str(e)}")
        
        # POST THE BILL - Move from draft to posted state
        try:
            # First, ensure all required fields are computed
            models.execute_kw(
                db, uid, password,
                'account.move', '_recompute_dynamic_lines',
                [[bill_id]],
                {'context': context}
            )
            
            post_result = models.execute_kw(
                db, uid, password,
                'account.move', 'action_post',
                [[bill_id]],
                {'context': context}
            )
            
            # Verify the bill was posted successfully
            bill_state = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[bill_id]], 
                {'fields': ['state'], 'context': context}
            )[0]['state']
            
            if bill_state != 'posted':
                return {
                    'success': False,
                    'error': f'Bill was created but failed to post. Current state: {bill_state}'
                }
                
        except xmlrpc.client.Fault as e:
            # Get more details about the error
            error_msg = str(e)
            
            # Try to get the bill details for debugging
            try:
                bill_details = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[bill_id]], 
                    {'fields': ['name', 'state', 'journal_id', 'company_id', 'invoice_date', 'invoice_date_due'], 'context': context}
                )[0]
                error_msg += f". Bill details: {bill_details}"
            except:
                pass
            
            return {
                'success': False,
                'error': f'Bill created but failed to post: {error_msg}'
            }
        
        # Get final bill information after posting
        bill_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[bill_id]], 
            {'fields': ['name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'invoice_date_due'], 'context': context}
        )[0]
        
        return {
            'success': True,
            'bill_id': bill_id,
            'bill_number': bill_info.get('name'),
            'vendor_name': vendor_info['name'],
            'total_amount': bill_info.get('amount_total'),
            'subtotal': bill_info.get('amount_untaxed'),
            'tax_amount': bill_info.get('amount_tax'),
            'state': bill_info.get('state'),
            'invoice_date': invoice_date,
            'due_date': bill_info.get('invoice_date_due'),
            'payment_reference': payment_reference if payment_reference != 'none' else None,
            'line_items': data.get('line_items'),
            'message': 'Vendor bill created and posted successfully'
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

# Helper function to list vendors (for reference)
def list_vendors():
    """Get list of vendors for reference"""
    
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
        
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('supplier_rank', '>', 0)]], 
            {'fields': ['id', 'name', 'email']}
        )
        
        return {
            'success': True,
            'vendors': vendors,
            'count': len(vendors)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }