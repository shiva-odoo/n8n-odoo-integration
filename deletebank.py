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
    Delete bank from HTTP request data
    
    Expected data format:
    {
        "bank_id": 123,                        # required
        "force_delete": false,                 # optional, force deletion despite related records
        "archive_instead": false               # optional, archive instead of delete
    }
    """
    
    # Validate required fields
    if not data.get('bank_id'):
        return {
            'success': False,
            'error': 'bank_id is required'
        }
    
    try:
        bank_id = int(data['bank_id'])
    except (ValueError, TypeError):
        return {
            'success': False,
            'error': 'bank_id must be a valid number'
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
        
        # Check if bank exists
        bank_exists = models.execute_kw(
            db, uid, password,
            'res.bank', 'search',
            [[('id', '=', bank_id)]], {'limit': 1}
        )
        
        if not bank_exists:
            return {
                'success': False,
                'error': f'Bank with ID {bank_id} not found'
            }
        
        # Get current bank info
        current_bank = models.execute_kw(
            db, uid, password,
            'res.bank', 'read',
            [[bank_id]], 
            {'fields': ['name', 'bic', 'active']}
        )[0]
        
        # Check for related records that might prevent deletion
        related_counts = {}
        
        # Check for partner bank accounts using this bank
        try:
            related_counts['partner_bank_accounts'] = models.execute_kw(
                db, uid, password,
                'res.partner.bank', 'search_count',
                [[('bank_id', '=', bank_id)]]
            )
        except Exception:
            related_counts['partner_bank_accounts'] = 0
        
        # Check for company bank accounts
        try:
            related_counts['company_accounts'] = models.execute_kw(
                db, uid, password,
                'res.partner.bank', 'search_count',
                [[('bank_id', '=', bank_id), ('partner_id.is_company', '=', True)]]
            )
        except Exception:
            related_counts['company_accounts'] = 0
        
        total_related = sum(related_counts.values())
        
        # If archive_instead is requested, archive the bank
        if data.get('archive_instead', False):
            try:
                result = models.execute_kw(
                    db, uid, password,
                    'res.bank', 'write',
                    [[bank_id], {'active': False}]
                )
                
                if result:
                    return {
                        'success': True,
                        'bank_id': bank_id,
                        'bank_name': current_bank['name'],
                        'action': 'archived',
                        'related_counts': related_counts,
                        'message': 'Bank archived successfully (data preserved)'
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Failed to archive bank'
                    }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Archiving failed: {str(e)}'
                }
        
        # If bank has related records and force_delete is not set, recommend archiving
        if total_related > 0 and not data.get('force_delete', False):
            return {
                'success': False,
                'error': f'Bank has {total_related} related records',
                'related_counts': related_counts,
                'suggestion': 'Set archive_instead: true to safely archive bank or force_delete: true to delete anyway',
                'risk': 'Deleting banks with related records may cause data integrity issues'
            }
        
        # Attempt deletion
        try:
            result = models.execute_kw(
                db, uid, password,
                'res.bank', 'unlink',
                [[bank_id]]
            )
            
            if result:
                warnings = []
                if total_related > 0:
                    warnings.append(f'Bank had {total_related} related records that may be affected')
                
                return {
                    'success': True,
                    'bank_id': bank_id,
                    'bank_name': current_bank['name'],
                    'action': 'deleted',
                    'related_counts': related_counts,
                    'warnings': warnings,
                    'message': 'Bank deleted successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to delete bank - unknown error'
                }
                
        except Exception as delete_error:
            error_msg = str(delete_error)
            
            # If deletion failed, try archiving as fallback (if not force_delete)
            if not data.get('force_delete', False):
                try:
                    archive_result = models.execute_kw(
                        db, uid, password,
                        'res.bank', 'write',
                        [[bank_id], {'active': False}]
                    )
                    
                    if archive_result:
                        return {
                            'success': True,
                            'bank_id': bank_id,
                            'bank_name': current_bank['name'],
                            'action': 'archived_fallback',
                            'related_counts': related_counts,
                            'message': 'Could not delete, but bank archived successfully (data preserved)',
                            'original_error': error_msg
                        }
                except Exception:
                    pass
            
            # Provide specific error explanations
            if "constraint" in error_msg.lower() or "foreign key" in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Bank has related records that prevent deletion',
                    'suggestion': 'Try archiving instead by setting archive_instead: true',
                    'related_counts': related_counts
                }
            else:
                return {
                    'success': False,
                    'error': f'Deletion failed: {error_msg}',
                    'suggestion': 'Try archiving instead or remove related records first'
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

def list_banks():
    """Get list of banks for reference"""
    
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
        
        banks = models.execute_kw(
            db, uid, password,
            'res.bank', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'bic', 'active'], 'order': 'name', 'limit': 100}
        )
        
        return {
            'success': True,
            'banks': banks,
            'count': len(banks)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def get_bank_info(bank_id):
    """Get detailed bank information by ID"""
    
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
        
        bank_data = models.execute_kw(
            db, uid, password,
            'res.bank', 'read',
            [[bank_id]], 
            {'fields': ['name', 'bic', 'street', 'city', 'zip', 'country', 'state', 'phone', 'email', 'website', 'active']}
        )
        
        if bank_data:
            return {
                'success': True,
                'bank': bank_data[0]
            }
        else:
            return {
                'success': False,
                'error': 'Bank not found'
            }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Example usage
if __name__ == "__main__":
    # First, list banks to see what's available
    print("Listing all banks...")
    banks_result = list_banks()
    print(f"Banks: {banks_result}")
    
    if banks_result.get('success') and banks_result.get('banks'):
        # Example: Delete the first bank (be careful with this!)
        first_bank = banks_result['banks'][0]
        bank_id = first_bank['id']
        
        print(f"\nAttempting to archive bank ID {bank_id} ({first_bank['name']})...")
        
        # First try archiving (safer option)
        delete_data = {
            "bank_id": bank_id,
            "archive_instead": True
        }
        
        result = main(delete_data)
        print(f"Archive Result: {result}")
        
        # Uncomment below to test actual deletion (use with caution!)
        # delete_data = {
        #     "bank_id": bank_id,
        #     "force_delete": True
        # }
        # result = main(delete_data)
        # print(f"Delete Result: {result}")
    else:
        print("No banks found or error occurred")
