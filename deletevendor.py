import xmlrpc.client
import os
from dotenv import load_dotenv

load_dotenv()

def main(data):
    """
    Delete vendor from HTTP request data
    
    Expected data format:
    {
        "vendor_id": 123,                      # required
        "force_delete": false,                 # optional, force deletion despite transactions
        "archive_instead": false               # optional, archive instead of delete
    }
    """
    
    # Validate required fields
    if not data.get('vendor_id'):
        return {
            'success': False,
            'error': 'vendor_id is required'
        }
    
    try:
        vendor_id = int(data['vendor_id'])
    except (ValueError, TypeError):
        return {
            'success': False,
            'error': 'vendor_id must be a valid number'
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
        
        # Check if vendor exists
        vendor_exists = models.execute_kw(
            db, uid, password,
            'res.partner', 'search',
            [[('id', '=', vendor_id)]], {'limit': 1}
        )
        
        if not vendor_exists:
            return {
                'success': False,
                'error': f'Vendor with ID {vendor_id} not found'
            }
        
        # Get current vendor info
        current_vendor = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[vendor_id]], 
            {'fields': ['name', 'email', 'phone', 'vat', 'active', 'supplier_rank']}
        )[0]
        
        # Check for existing transactions
        transaction_counts = {}
        
        # Check for vendor bills
        try:
            transaction_counts['bills'] = models.execute_kw(
                db, uid, password,
                'account.move', 'search_count',
                [[('partner_id', '=', vendor_id), ('move_type', '=', 'in_invoice')]]
            )
        except Exception:
            transaction_counts['bills'] = 0
        
        # Check for payments
        try:
            transaction_counts['payments'] = models.execute_kw(
                db, uid, password,
                'account.payment', 'search_count',
                [[('partner_id', '=', vendor_id)]]
            )
        except Exception:
            transaction_counts['payments'] = 0
        
        # Check for purchase orders
        try:
            transaction_counts['purchase_orders'] = models.execute_kw(
                db, uid, password,
                'purchase.order', 'search_count',
                [[('partner_id', '=', vendor_id)]]
            )
        except Exception:
            transaction_counts['purchase_orders'] = 0
        
        total_transactions = sum(transaction_counts.values())
        
        # If archive_instead is requested, archive the vendor
        if data.get('archive_instead', False):
            try:
                result = models.execute_kw(
                    db, uid, password,
                    'res.partner', 'write',
                    [[vendor_id], {'active': False}]
                )
                
                if result:
                    return {
                        'success': True,
                        'vendor_id': vendor_id,
                        'vendor_name': current_vendor['name'],
                        'action': 'archived',
                        'transaction_counts': transaction_counts,
                        'message': 'Vendor archived successfully (data preserved)'
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Failed to archive vendor'
                    }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Archiving failed: {str(e)}'
                }
        
        # If vendor has transactions and force_delete is not set, recommend archiving
        if total_transactions > 0 and not data.get('force_delete', False):
            return {
                'success': False,
                'error': f'Vendor has {total_transactions} existing transactions',
                'transaction_counts': transaction_counts,
                'suggestion': 'Set archive_instead: true to safely archive vendor or force_delete: true to delete anyway',
                'risk': 'Deleting vendors with transactions may cause data integrity issues'
            }
        
        # Attempt deletion
        try:
            result = models.execute_kw(
                db, uid, password,
                'res.partner', 'unlink',
                [[vendor_id]]
            )
            
            if result:
                warnings = []
                if total_transactions > 0:
                    warnings.append(f'Vendor had {total_transactions} transactions that may be affected')
                
                return {
                    'success': True,
                    'vendor_id': vendor_id,
                    'vendor_name': current_vendor['name'],
                    'action': 'deleted',
                    'transaction_counts': transaction_counts,
                    'warnings': warnings,
                    'message': 'Vendor deleted successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to delete vendor - unknown error'
                }
                
        except Exception as delete_error:
            error_msg = str(delete_error)
            
            # If deletion failed, try archiving as fallback (if not force_delete)
            if not data.get('force_delete', False):
                try:
                    archive_result = models.execute_kw(
                        db, uid, password,
                        'res.partner', 'write',
                        [[vendor_id], {'active': False}]
                    )
                    
                    if archive_result:
                        return {
                            'success': True,
                            'vendor_id': vendor_id,
                            'vendor_name': current_vendor['name'],
                            'action': 'archived_fallback',
                            'transaction_counts': transaction_counts,
                            'message': 'Could not delete, but vendor archived successfully (data preserved)',
                            'original_error': error_msg
                        }
                except Exception:
                    pass
            
            # Provide specific error explanations
            if "constraint" in error_msg.lower() or "foreign key" in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Vendor has related records that prevent deletion',
                    'suggestion': 'Try archiving instead by setting archive_instead: true',
                    'transaction_counts': transaction_counts
                }
            else:
                return {
                    'success': False,
                    'error': f'Deletion failed: {error_msg}',
                    'suggestion': 'Try archiving instead or remove related transactions first'
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

def list_vendors():
    """Get list of vendors for reference"""
    
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
        
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('supplier_rank', '>', 0)]], 
            {'fields': ['id', 'name', 'email', 'phone', 'active'], 'order': 'name', 'limit': 50}
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