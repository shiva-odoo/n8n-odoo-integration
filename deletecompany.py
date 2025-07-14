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
    Delete company from HTTP request data
    
    Expected data format:
    {
        "company_id": 123,                     # required
        "force_delete": false,                 # optional, defaults to false
        "archive_instead": false               # optional, archive instead of delete
    }
    """
    
    # Validate required fields
    if not data.get('company_id'):
        return {
            'success': False,
            'error': 'company_id is required'
        }
    
    try:
        company_id = int(data['company_id'])
    except (ValueError, TypeError):
        return {
            'success': False,
            'error': 'company_id must be a valid number'
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
        
        # Check if company exists
        company_exists = models.execute_kw(
            db, uid, password,
            'res.company', 'search',
            [[('id', '=', company_id)]], {'limit': 1}
        )
        
        if not company_exists:
            return {
                'success': False,
                'error': f'Company with ID {company_id} not found'
            }
        
        # Get company details
        company_info = models.execute_kw(
            db, uid, password,
            'res.company', 'read',
            [[company_id]], 
            {'fields': ['name', 'email', 'phone', 'website', 'vat']}
        )[0]
        
        # Check if this is the current user's company
        try:
            user_info = models.execute_kw(
                db, uid, password,
                'res.users', 'read',
                [[uid]], {'fields': ['company_id']}
            )[0]
            
            user_company_id = user_info['company_id'][0] if user_info.get('company_id') else None
            is_current_company = user_company_id == company_id
        except Exception:
            is_current_company = False
        
        warnings = []
        if is_current_company:
            warnings.append('This is your current company - deletion may cause system issues')
        
        # If archive_instead is requested, archive the company
        if data.get('archive_instead', False):
            try:
                result = models.execute_kw(
                    db, uid, password,
                    'res.company', 'write',
                    [[company_id], {'active': False}]
                )
                
                if result:
                    return {
                        'success': True,
                        'company_id': company_id,
                        'company_name': company_info['name'],
                        'action': 'archived',
                        'warnings': warnings,
                        'message': 'Company archived successfully (data preserved)'
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Failed to archive company'
                    }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Archiving failed: {str(e)}'
                }
        
        # Attempt deletion
        try:
            result = models.execute_kw(
                db, uid, password,
                'res.company', 'unlink',
                [[company_id]]
            )
            
            if result:
                return {
                    'success': True,
                    'company_id': company_id,
                    'company_name': company_info['name'],
                    'action': 'deleted',
                    'warnings': warnings,
                    'message': 'Company deleted successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to delete company - unknown error'
                }
                
        except Exception as delete_error:
            error_msg = str(delete_error)
            
            # Provide specific error explanations and suggest archiving
            if "foreign key" in error_msg.lower() or "constraint" in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Company has associated records that prevent deletion',
                    'suggestion': 'Try archiving instead by setting archive_instead: true',
                    'associated_data': 'Users, invoices, or other data still reference this company'
                }
            elif "permission" in error_msg.lower() or "access" in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Insufficient permissions to delete company',
                    'suggestion': 'Contact your system administrator'
                }
            else:
                # If deletion failed, offer archiving as alternative
                if not data.get('force_delete', False):
                    try:
                        # Try archiving instead
                        archive_result = models.execute_kw(
                            db, uid, password,
                            'res.company', 'write',
                            [[company_id], {'active': False}]
                        )
                        
                        if archive_result:
                            return {
                                'success': True,
                                'company_id': company_id,
                                'company_name': company_info['name'],
                                'action': 'archived_fallback',
                                'warnings': warnings + ['Deletion failed, archived instead'],
                                'message': 'Could not delete, but company archived successfully (data preserved)',
                                'original_error': error_msg
                            }
                    except Exception:
                        pass
                
                return {
                    'success': False,
                    'error': f'Deletion failed: {error_msg}',
                    'suggestion': 'Try archiving instead or contact administrator'
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

def list_companies():
    """Get list of companies for reference"""
    
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
        
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'email', 'phone', 'active'], 'order': 'name'}
        )
        
        return {
            'success': True,
            'companies': companies,
            'count': len(companies)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }