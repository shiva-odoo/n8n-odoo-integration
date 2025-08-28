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

def normalize_date(date_value):
    """
    Normalize date values - if null, "null", "none", empty string, or None, return today's date
    Otherwise return the date value as-is
    """
    if (date_value is None or 
        date_value == "" or 
        str(date_value).lower() in ["null", "none"]):
        return datetime.now().strftime('%Y-%m-%d')
    return date_value

def check_duplicate_bill(models, db, uid, password, vendor_id, invoice_date, total_amount, vendor_ref=None):
    """
    Check if a bill with the same vendor, date, total amount, and reference already exists
    
    Returns:
        - None if no duplicate found
        - Bill data if duplicate found
    """
    try:
        # Build search criteria
        search_domain = [
            ('move_type', '=', 'in_invoice'),  # Vendor bills only
            ('partner_id', '=', vendor_id),
            ('invoice_date', '=', invoice_date),
            ('state', '!=', 'cancel'),  # Exclude cancelled bills
        ]
        
        # Add reference to search criteria if provided
        if vendor_ref:
            search_domain.append(('ref', '=', vendor_ref))
        else:
            # If no reference provided, search for bills without reference
            search_domain.append(('ref', '=', False))
        
        # Search for existing bills
        existing_bills = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [search_domain],
            {'fields': ['id', 'name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'ref']}
        )
        
        # Check if any bill matches the total amount (with small tolerance for rounding)
        for bill in existing_bills:
            if abs(float(bill['amount_total']) - float(total_amount)) < 0.01:
                return bill
        
        return None
        
    except Exception as e:
        print(f"Error checking for duplicates: {str(e)}")
        return None

def calculate_line_items_totals(line_items):
    """
    Calculate subtotal, tax, and total from line items
    Returns (subtotal, tax_amount, total)
    """
    subtotal = 0.0
    tax_amount = 0.0
    
    for item in line_items:
        try:
            quantity = float(item.get('quantity', 1.0))
            price_unit = float(item.get('price_unit', 0.0))
            tax_rate = float(item.get('tax_rate', 0.0)) if item.get('tax_rate') else 0.0
            
            line_subtotal = quantity * price_unit
            line_tax = line_subtotal * (tax_rate / 100.0)
            
            subtotal += line_subtotal
            tax_amount += line_tax
        except (ValueError, TypeError):
            continue
    
    total = subtotal + tax_amount
    return subtotal, tax_amount, total

def create_combined_description(line_items):
    """
    Create a combined description from multiple line items
    """
    if not line_items or len(line_items) == 0:
        return "Various services"
    
    if len(line_items) == 1:
        return line_items[0].get('description', 'Service')
    
    # For multiple items, create a summary
    descriptions = []
    for item in line_items[:3]:  # Show first 3 items
        desc = item.get('description', 'Service')
        if len(desc) > 50:  # Truncate long descriptions
            desc = desc[:47] + "..."
        descriptions.append(desc)
    
    result = "; ".join(descriptions)
    if len(line_items) > 3:
        result += f" (and {len(line_items) - 3} more)"
    
    return result

def calculate_total_amount(data):
    """
    Calculate the expected total amount from the data
    """
    if 'total_amount' in data:
        return float(data['total_amount'])
    elif 'line_items' in data and data['line_items']:
        _, _, total = calculate_line_items_totals(data['line_items'])
        return total
    elif 'amount' in data:
        return float(data['amount'])
    else:
        return 0.0

def force_exact_amounts_by_adjusting_lines(models, db, uid, password, bill_id, subtotal, tax_amount, total_amount, company_id=None):
    """
    Force exact amounts by creating ONE line item with the right tax configuration
    to achieve the exact subtotal, tax, and total amounts specified
    """
    try:
        # Get all existing invoice lines for this bill  
        line_ids = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search',
            [[('move_id', '=', bill_id), ('exclude_from_invoice_tab', '=', False)]]
        )
        
        if not line_ids:
            print("No invoice lines found to adjust")
            return False

        # Get the first line details for account info
        first_line = models.execute_kw(
            db, uid, password,
            'account.move.line', 'read',
            [line_ids[:1]],
            {'fields': ['account_id', 'name']}
        )[0]
        
        # Delete all existing lines
        models.execute_kw(
            db, uid, password,
            'account.move.line', 'unlink',
            [line_ids]
        )
        
        # Calculate what tax rate we need to achieve the desired amounts
        # If subtotal * (1 + tax_rate/100) = total, then tax_rate = ((total/subtotal) - 1) * 100
        if float(subtotal) > 0 and float(tax_amount) > 0:
            needed_tax_rate = (float(tax_amount) / float(subtotal)) * 100
            print(f"Calculated needed tax rate: {needed_tax_rate:.2f}%")
            
            # Try to find a tax with this rate, or closest to it
            tax_domain = [('type_tax_use', '=', 'purchase')]
            if company_id:
                tax_domain.append(('company_id', '=', company_id))
            
            # First try to find exact match
            exact_tax_ids = models.execute_kw(
                db, uid, password,
                'account.tax', 'search',
                [tax_domain + [('amount', '=', needed_tax_rate)]],
                {'limit': 1}
            )
            
            tax_id = exact_tax_ids[0] if exact_tax_ids else None
            
            if not tax_id:
                # No exact match, try to find closest tax or create one if possible
                all_taxes = models.execute_kw(
                    db, uid, password,
                    'account.tax', 'search_read',
                    [tax_domain],
                    {'fields': ['id', 'amount'], 'limit': 20}
                )
                
                if all_taxes:
                    # Find closest tax rate
                    closest_tax = min(all_taxes, key=lambda t: abs(t['amount'] - needed_tax_rate))
                    tax_id = closest_tax['id']
                    print(f"Using closest available tax: {closest_tax['amount']:.2f}% (tax_id: {tax_id})")
            
            # Create new line item with calculated tax
            new_line_data = {
                'move_id': bill_id,
                'name': first_line['name'],  # Use the original description
                'account_id': first_line['account_id'][0],
                'quantity': 1.0,
                'price_unit': float(subtotal),
                'exclude_from_invoice_tab': False,
            }
            
            if tax_id:
                new_line_data['tax_ids'] = [(6, 0, [tax_id])]
            
            # Create the new line
            new_line_id = models.execute_kw(
                db, uid, password,
                'account.move.line', 'create',
                [new_line_data]
            )
            
            print(f"Created new line with subtotal ${subtotal} and tax_id {tax_id}")
            
        else:
            # No tax needed, create line with total amount
            new_line_data = {
                'move_id': bill_id,
                'name': first_line['name'],
                'account_id': first_line['account_id'][0],
                'quantity': 1.0,
                'price_unit': float(total_amount),
                'exclude_from_invoice_tab': False,
            }
            
            models.execute_kw(
                db, uid, password,
                'account.move.line', 'create',
                [new_line_data]
            )
            print(f"Created single line with total amount ${total_amount} (no tax)")
        
        # Force Odoo to recalculate totals from the new line
        try:
            models.execute_kw(
                db, uid, password,
                'account.move', '_recompute_dynamic_lines',
                [[bill_id]]
            )
        except:
            pass
        
        # Check the results
        bill_amounts = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[bill_id]], 
            {'fields': ['amount_untaxed', 'amount_tax', 'amount_total']}
        )[0]
        
        print(f"After line recreation: untaxed={bill_amounts['amount_untaxed']}, tax={bill_amounts['amount_tax']}, total={bill_amounts['amount_total']}")
        
        # If the automatic tax calculation doesn't give us exact amounts, try manual override
        total_diff = abs(float(bill_amounts['amount_total']) - float(total_amount))
        subtotal_diff = abs(float(bill_amounts['amount_untaxed']) - float(subtotal))
        
        if total_diff > 0.01 or subtotal_diff > 0.01:
            print(f"Computed amounts not exact, trying manual override...")
            # Try direct field updates as last resort
            try:
                models.execute_kw(
                    db, uid, password,
                    'account.move', 'write',
                    [[bill_id], {
                        'amount_untaxed': float(subtotal),
                        'amount_tax': float(tax_amount) if tax_amount else 0.0,
                        'amount_total': float(total_amount)
                    }]
                )
                
                # Read again to check if override worked
                bill_amounts = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[bill_id]], 
                    {'fields': ['amount_untaxed', 'amount_tax', 'amount_total']}
                )[0]
                print(f"After manual override: untaxed={bill_amounts['amount_untaxed']}, tax={bill_amounts['amount_tax']}, total={bill_amounts['amount_total']}")
            except Exception as e:
                print(f"Manual override failed: {str(e)}")
        
        # Final check
        total_diff = abs(float(bill_amounts['amount_total']) - float(total_amount))
        return total_diff < 0.01
        
    except Exception as e:
        print(f"Error adjusting invoice lines: {str(e)}")
        return False

def main(data):
    """
    Create vendor bill from HTTP request data with hybrid approach:
    - Try individual line items first
    - Fall back to consolidated approach if totals don't match
    - ENSURE EXACT AMOUNTS for consolidated approach
    """
    
    # Validate required fields
    if not data.get('vendor_id'):
        return {
            'success': False,
            'error': 'vendor_id is required'
        }
    
    # Accept extra fields
    payment_reference = data.get('payment_reference')
    provided_subtotal = data.get('subtotal')
    provided_tax_amount = data.get('tax_amount')
    provided_total_amount = data.get('total_amount')
    
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
        
        # Verify vendor exists
        vendor_id = data['vendor_id']
        vendor_exists = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_count',
            [[('id', '=', vendor_id), ('supplier_rank', '>', 0)]]
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
            {'fields': ['name']}
        )[0]
        
        # Normalize and prepare dates
        invoice_date = normalize_date(data.get('invoice_date'))
        due_date = normalize_date(data.get('due_date'))
        
        # Validate date formats
        try:
            datetime.strptime(invoice_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'invoice_date must be in YYYY-MM-DD format'
            }
        
        try:
            datetime.strptime(due_date, '%Y-%m-%d')
        except ValueError:
            return {
                'success': False,
                'error': 'due_date must be in YYYY-MM-DD format'
            }
        
        # Calculate expected total amount
        expected_total = calculate_total_amount(data)
        
        # Check for duplicate bill
        vendor_ref = data.get('vendor_ref')
        existing_bill = check_duplicate_bill(
            models, db, uid, password, 
            vendor_id, invoice_date, expected_total, vendor_ref
        )
        
        if existing_bill:
            # Return existing bill details instead of creating a duplicate
            return {
                'success': True,
                'bill_id': existing_bill['id'],
                'bill_number': existing_bill['name'],
                'vendor_name': vendor_info['name'],
                'total_amount': existing_bill['amount_total'],
                'subtotal': existing_bill['amount_untaxed'],
                'tax_amount': existing_bill['amount_tax'],
                'state': existing_bill['state'],
                'invoice_date': invoice_date,
                'vendor_ref': existing_bill.get('ref'),
                'message': 'Bill already exists - no duplicate created'
            }
        
        # Helper function to find tax by rate
        def find_tax_by_rate(tax_rate, company_id=None):
            """Find tax record by rate percentage"""
            try:
                domain = [('amount', '=', tax_rate), ('type_tax_use', '=', 'purchase')]
                if company_id:
                    domain.append(('company_id', '=', company_id))
                
                tax_ids = models.execute_kw(
                    db, uid, password,
                    'account.tax', 'search',
                    [domain],
                    {'limit': 1}
                )
                return tax_ids[0] if tax_ids else None
            except:
                return None
        
        # Prepare bill data
        bill_data = {
            'move_type': 'in_invoice',
            'partner_id': vendor_id,
            'invoice_date': invoice_date,
            'invoice_date_due': due_date,
        }
        
        # Add vendor reference if provided
        if data.get('vendor_ref'):
            bill_data['ref'] = data['vendor_ref']

        # Add company_id if provided (for multi-company setup)
        company_id = None
        if data.get('company_id'):
            company_id = data['company_id']
            bill_data['company_id'] = company_id

        # Add payment_reference if provided
        if payment_reference and payment_reference != 'none':
            bill_data['payment_reference'] = payment_reference

        # HYBRID APPROACH: Check if line items match provided totals
        use_individual_items = True
        tolerance = 0.50  # Allow 50 cents tolerance for rounding differences
        
        if ('line_items' in data and data['line_items'] and 
            provided_subtotal is not None and provided_total_amount is not None):
            
            # Calculate what the totals would be from line items
            calc_subtotal, calc_tax, calc_total = calculate_line_items_totals(data['line_items'])
            
            # Check if calculated totals match provided totals within tolerance
            subtotal_diff = abs(calc_subtotal - float(provided_subtotal))
            total_diff = abs(calc_total - float(provided_total_amount))
            
            if subtotal_diff > tolerance or total_diff > tolerance:
                print(f"Line item totals don't match provided amounts (diff: subtotal={subtotal_diff:.2f}, total={total_diff:.2f}). Using consolidated approach.")
                use_individual_items = False
        
        # Handle line items based on chosen approach
        invoice_line_ids = []
        used_description = "Various services"  # Default description, will be updated based on approach
        
        if use_individual_items and 'line_items' in data and data['line_items']:
            # INDIVIDUAL LINE ITEMS APPROACH
            descriptions = []
            for item in data['line_items']:
                if not item.get('description'):
                    return {
                        'success': False,
                        'error': 'Each line item must have a description'
                    }
                
                descriptions.append(item['description'])
                
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
                
                # Apply tax if tax_rate is provided
                if tax_rate is not None and tax_rate > 0:
                    tax_id = find_tax_by_rate(tax_rate, company_id)
                    if tax_id:
                        line_item['tax_ids'] = [(6, 0, [tax_id])]
                    else:
                        # Log warning but continue - tax might be calculated differently
                        print(f"Warning: No tax found for rate {tax_rate}%, continuing without tax")
                
                invoice_line_ids.append((0, 0, line_item))
            
            # For individual items, create combined description from all items
            used_description = "; ".join(descriptions)
        
        elif (not use_individual_items and provided_subtotal is not None and 
              provided_total_amount is not None):
            # CONSOLIDATED APPROACH - Single line item with exact amounts forced later
            
            if data.get('line_items'):
                description = create_combined_description(data['line_items'])
            elif data.get('description'):
                description = data['description']
            else:
                description = "Telecommunications services"
            
            used_description = description
            
            # Create SINGLE line item with subtotal as price_unit (no tax applied here)
            # We'll override the bill totals after creation to match exact input amounts
            subtotal = float(provided_subtotal)
            
            line_item = {
                'name': description,
                'quantity': 1.0,
                'price_unit': subtotal,  # Use subtotal as base price
                # Deliberately NOT applying tax_ids - we'll set exact amounts manually
            }
            
            invoice_line_ids.append((0, 0, line_item))
            print(f"Consolidated approach: Creating single line item with subtotal ${subtotal}, will force exact amounts after posting")
        
        elif data.get('description') and data.get('amount'):
            # BACKWARD COMPATIBILITY - Single line item
            try:
                # Use subtotal if available, otherwise use amount
                if provided_subtotal is not None:
                    amount = float(provided_subtotal)
                else:
                    amount = float(data['amount'])
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'amount must be a valid number'
                }
            
            used_description = data['description']  # Track the single description
            
            line_item = {
                'name': data['description'],
                'quantity': 1.0,
                'price_unit': amount,
            }
            
            invoice_line_ids.append((0, 0, line_item))
        
        else:
            return {
                'success': False,
                'error': 'Either provide line_items array or description and amount'
            }
        
        bill_data['invoice_line_ids'] = invoice_line_ids
        
        # Create the bill
        context = {'allowed_company_ids': [company_id]} if company_id else {}
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
        
        # POST THE BILL - Move from draft to posted state
        try:
            post_result = models.execute_kw(
                db, uid, password,
                'account.move', 'action_post',
                [[bill_id]]
            )
            
            # Verify the bill was posted successfully
            bill_state = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[bill_id]], 
                {'fields': ['state']}
            )[0]['state']
            
            if bill_state != 'posted':
                return {
                    'success': False,
                    'error': f'Bill was created but failed to post. Current state: {bill_state}'
                }
                
        except xmlrpc.client.Fault as e:
            return {
                'success': False,
                'error': f'Bill created but failed to post: {str(e)}'
            }
        
        
        # For consolidated approach with exact amounts requirement, apply enforcement
        amounts_set_successfully = True
        if (not use_individual_items and provided_subtotal is not None and 
            provided_total_amount is not None):
            
            print("Consolidated approach detected - enforcing exact amounts by adjusting invoice lines...")
            
            # Use the new line-based adjustment approach
            amounts_set_successfully = force_exact_amounts_by_adjusting_lines(
                models, db, uid, password, bill_id, 
                provided_subtotal, provided_tax_amount, provided_total_amount, company_id
            )
            
            if not amounts_set_successfully:
                print("Warning: Could not achieve exact amounts through line adjustment")
        
        # Get final bill information after posting and amount adjustments
        bill_info = models.execute_kw(
            db, uid, password,
            'account.move', 'read',
            [[bill_id]], 
            {'fields': ['name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state', 'invoice_date_due']}
        )[0]
        
        # Additional validation for consolidated approach
        warning_message = None
        if (not use_individual_items and provided_subtotal is not None and 
            provided_total_amount is not None):
            
            # Check final amounts against input
            final_subtotal = float(bill_info['amount_untaxed'])
            final_total = float(bill_info['amount_total'])
            final_tax = float(bill_info['amount_tax'])
            
            subtotal_diff = abs(final_subtotal - float(provided_subtotal))
            total_diff = abs(final_total - float(provided_total_amount))
            
            if subtotal_diff > 0.01 or total_diff > 0.01:
                warning_message = f"Warning: Final amounts may not exactly match input (subtotal diff: ${subtotal_diff:.2f}, total diff: ${total_diff:.2f})"
                print(warning_message)
        
        success_message = 'Vendor bill created and posted successfully'
        if warning_message:
            success_message += f". {warning_message}"
        elif not use_individual_items:
            success_message += " using consolidated approach with exact amounts"
        
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
            'due_date': due_date,
            'payment_reference': payment_reference if payment_reference != 'none' else None,
            'line_items': data.get('line_items') if use_individual_items else None,
            'description': used_description,
            'processing_method': 'individual_items' if use_individual_items else 'consolidated',
            'amounts_match_input': amounts_set_successfully if not use_individual_items else True,
            'message': success_message
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