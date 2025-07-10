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
    Modify vendor bill from HTTP request data
    
    Expected data format:
    {
        "bill_id": 123,                        # required
        "reference": "New reference",          # optional
        "invoice_date": "2025-01-15",         # optional
        "line_items": [                        # optional, to update line items
            {
                "line_id": 456,                # required for existing line
                "description": "Updated desc", # optional
                "quantity": 2,                 # optional
                "price_unit": 150.00          # optional
            }
        ],
        "add_line_item": {                     # optional, to add new line
            "description": "New item",
            "quantity": 1,
            "price_unit": 100.00
        }
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
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
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
        
        # Check if bill exists and get current info
        current_bill = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', bill_id), ('move_type', '=', 'in_invoice')]], 
            {'fields': ['name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state']}
        )
        
        if not current_bill:
            return {
                'success': False,
                'error': f'Vendor bill with ID {bill_id} not found'
            }
        
        bill_info = current_bill[0]
        bill_status = bill_info.get('state', 'draft')
        
        # Warn about posted bills
        warnings = []
        if bill_status in ['posted', 'cancel']:
            warnings.append(f'Bill is {bill_status} - modifications may be limited')
        
        # Track what was updated
        updates_made = []
        
        # Update bill header fields
        bill_updates = {}
        
        if data.get('reference'):
            bill_updates['ref'] = data['reference']
            updates_made.append(f"Reference updated to '{data['reference']}'")
        
        if data.get('invoice_date'):
            try:
                # Validate date format
                from datetime import datetime
                datetime.strptime(data['invoice_date'], '%Y-%m-%d')
                bill_updates['invoice_date'] = data['invoice_date']
                updates_made.append(f"Invoice date updated to {data['invoice_date']}")
            except ValueError:
                return {
                    'success': False,
                    'error': 'invoice_date must be in YYYY-MM-DD format'
                }
        
        # Apply bill header updates
        if bill_updates:
            try:
                models.execute_kw(
                    db, uid, password,
                    'account.move', 'write',
                    [[bill_id], bill_updates]
                )
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Failed to update bill header: {str(e)}'
                }
        
        # Update existing line items
        if data.get('line_items'):
            for line_update in data['line_items']:
                if not line_update.get('line_id'):
                    return {
                        'success': False,
                        'error': 'line_id is required for line item updates'
                    }
                
                try:
                    line_id = int(line_update['line_id'])
                except (ValueError, TypeError):
                    return {
                        'success': False,
                        'error': 'line_id must be a valid number'
                    }
                
                line_updates = {}
                
                if line_update.get('description'):
                    line_updates['name'] = line_update['description']
                
                if line_update.get('quantity') is not None:
                    try:
                        quantity = float(line_update['quantity'])
                        line_updates['quantity'] = quantity
                    except (ValueError, TypeError):
                        return {
                            'success': False,
                            'error': 'quantity must be a valid number'
                        }
                
                if line_update.get('price_unit') is not None:
                    try:
                        price_unit = float(line_update['price_unit'])
                        line_updates['price_unit'] = price_unit
                    except (ValueError, TypeError):
                        return {
                            'success': False,
                            'error': 'price_unit must be a valid number'
                        }
                
                if line_updates:
                    try:
                        models.execute_kw(
                            db, uid, password,
                            'account.move.line', 'write',
                            [[line_id], line_updates]
                        )
                        updates_made.append(f"Line item {line_id} updated")
                    except Exception as e:
                        warnings.append(f"Failed to update line {line_id}: {str(e)}")
        
        # Add new line item
        if data.get('add_line_item'):
            new_line = data['add_line_item']
            
            if not new_line.get('description'):
                return {
                    'success': False,
                    'error': 'description is required for new line item'
                }
            
            try:
                quantity = float(new_line.get('quantity', 1.0))
                price_unit = float(new_line.get('price_unit', 0.0))
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'quantity and price_unit must be valid numbers'
                }
            
            new_line_data = {
                'move_id': bill_id,
                'name': new_line['description'],
                'quantity': quantity,
                'price_unit': price_unit,
            }
            
            try:
                new_line_id = models.execute_kw(
                    db, uid, password,
                    'account.move.line', 'create',
                    [new_line_data]
                )
                if new_line_id:
                    updates_made.append(f"New line item added: {new_line['description']}")
                else:
                    warnings.append("Failed to add new line item")
            except Exception as e:
                warnings.append(f"Failed to add new line item: {str(e)}")
        
        # Get updated bill information
        try:
            updated_bill = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[bill_id]], 
                {'fields': ['name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state']}
            )[0]
        except Exception:
            updated_bill = bill_info  # Use original if update fetch fails
        
        # Return results
        if not updates_made and not warnings:
            return {
                'success': True,
                'bill_id': bill_id,
                'bill_number': updated_bill.get('name'),
                'message': 'No changes were requested',
                'bill_info': updated_bill
            }
        
        return {
            'success': True,
            'bill_id': bill_id,
            'bill_number': updated_bill.get('name'),
            'vendor_name': updated_bill['partner_id'][1] if updated_bill.get('partner_id') else 'Unknown',
            'updates_made': updates_made,
            'warnings': warnings,
            'total_amount': updated_bill.get('amount_total'),
            'state': updated_bill.get('state'),
            'message': f'Bill updated successfully. {len(updates_made)} changes made.'
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

def modify(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

def get_bill_details(bill_id):
    """Get detailed bill information including line items"""
    
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {'success': False, 'error': 'Authentication failed'}
        
        # Get bill info
        bill = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', bill_id), ('move_type', '=', 'in_invoice')]], 
            {'fields': ['id', 'name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state']}
        )
        
        if not bill:
            return {'success': False, 'error': 'Bill not found'}
        
        # Get line items
        line_items = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', bill_id), ('display_type', '=', False)]], 
            {'fields': ['id', 'name', 'quantity', 'price_unit', 'price_total']}
        )
        
        return {
            'success': True,
            'bill': bill[0],
            'line_items': line_items
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }