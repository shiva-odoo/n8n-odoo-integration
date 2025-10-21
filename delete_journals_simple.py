import xmlrpc.client
import os

# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars


def delete_all_journal_aliases(company_id=None):
    """
    Delete/disable ALL journal aliases (keeps the journals)
    
    Args:
        company_id: Optional - if provided, only delete aliases for this company
                    if None, deletes aliases for ALL journals
    
    Returns:
        dict: Result with success status and details
    """
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
        
        # Build search domain
        domain = [('alias_id', '!=', False)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        # Find journals with aliases
        journals = models.execute_kw(
            db, uid, password,
            'account.journal', 'search_read',
            [domain],
            {'fields': ['id', 'name', 'code', 'type', 'alias_id', 'company_id']}
        )
        
        if not journals:
            return {
                'success': True,
                'message': 'No journal aliases found to delete',
                'deleted_count': 0
            }
        
        print(f"\nFound {len(journals)} journals with aliases:")
        for journal in journals:
            company_name = journal['company_id'][1] if journal.get('company_id') else 'N/A'
            alias_name = journal['alias_id'][1] if isinstance(journal['alias_id'], list) else str(journal['alias_id'])
            print(f"  - {journal['name']} ({journal['code']}) | Company: {company_name} | Alias: {alias_name}")
        
        # Remove aliases from journals
        journal_ids = [j['id'] for j in journals]
        
        print(f"\nRemoving aliases from {len(journal_ids)} journals...")
        
        try:
            models.execute_kw(
                db, uid, password,
                'account.journal', 'write',
                [journal_ids, {'alias_id': False}]
            )
            print(f"✓ Successfully removed aliases from {len(journal_ids)} journals")
            
            return {
                'success': True,
                'deleted_count': len(journal_ids),
                'message': f'Successfully removed aliases from {len(journal_ids)} journals'
            }
            
        except Exception as write_error:
            print(f"Batch write failed: {str(write_error)}")
            print("Trying one by one...")
            
            deleted_count = 0
            failed_deletions = []
            
            for journal in journals:
                try:
                    models.execute_kw(
                        db, uid, password,
                        'account.journal', 'write',
                        [[journal['id']], {'alias_id': False}]
                    )
                    deleted_count += 1
                    print(f"  ✓ Removed alias from: {journal['name']} ({journal['code']})")
                except Exception as e:
                    print(f"  ✗ Failed to remove alias from {journal['name']}: {str(e)}")
                    failed_deletions.append({
                        'journal_id': journal['id'],
                        'name': journal['name'],
                        'code': journal['code'],
                        'error': str(e)
                    })
            
            result = {
                'success': deleted_count > 0,
                'deleted_count': deleted_count,
                'total_found': len(journal_ids),
                'message': f'Removed aliases from {deleted_count} out of {len(journal_ids)} journals'
            }
            
            if failed_deletions:
                result['failed_deletions'] = failed_deletions
            
            return result
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to delete journal aliases: {str(e)}'
        }


def list_journals_with_aliases(company_id=None):
    """
    List all journals that have aliases
    """
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
        
        domain = [('alias_id', '!=', False)]
        if company_id:
            domain.append(('company_id', '=', company_id))
        
        journals = models.execute_kw(
            db, uid, password,
            'account.journal', 'search_read',
            [domain],
            {'fields': ['id', 'name', 'code', 'type', 'alias_id', 'company_id'], 'order': 'company_id, name'}
        )
        
        return {
            'success': True,
            'journals': journals,
            'count': len(journals)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def delete_orphaned_aliases():
    """
    Delete ALL aliases from mail.alias table that are related to account.journal
    This catches orphaned aliases that aren't linked to journals anymore
    """
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
        
        print("Searching for all aliases in mail.alias table...")
        
        # Get ALL aliases
        all_aliases = models.execute_kw(
            db, uid, password,
            'mail.alias', 'search_read',
            [[]],
            {'fields': ['id', 'alias_name', 'alias_model_id']}
        )
        
        if not all_aliases:
            return {
                'success': True,
                'message': 'No aliases found in database',
                'deleted_count': 0
            }
        
        print(f"\nFound {len(all_aliases)} total aliases in database:")
        for alias in all_aliases:
            model_info = alias['alias_model_id'][1] if isinstance(alias['alias_model_id'], list) else 'N/A'
            print(f"  - ID: {alias['id']} | Name: {alias.get('alias_name', 'N/A')} | Model: {model_info}")
        
        # Filter for journal-related aliases (by name pattern)
        journal_aliases = [a for a in all_aliases 
                          if a.get('alias_name') and isinstance(a.get('alias_name'), str) and 
                          any(keyword in a.get('alias_name', '').lower() 
                          for keyword in ['journal', 'purchase', 'sale', 'bill', 'invoice', 'customer', 'vendor'])]
        
        if not journal_aliases:
            print("\nNo journal-related aliases found")
            return {
                'success': True,
                'message': 'No journal-related aliases found',
                'deleted_count': 0
            }
        
        print(f"\nFound {len(journal_aliases)} journal-related aliases to delete:")
        for alias in journal_aliases:
            print(f"  - ID: {alias['id']} | Name: {alias.get('alias_name', 'N/A')}")
        
        # Delete them
        alias_ids = [a['id'] for a in journal_aliases]
        deleted_count = 0
        failed_deletions = []
        
        for alias_id in alias_ids:
            try:
                models.execute_kw(
                    db, uid, password,
                    'mail.alias', 'unlink',
                    [[alias_id]]
                )
                deleted_count += 1
                print(f"  ✓ Deleted alias ID: {alias_id}")
            except Exception as e:
                print(f"  ✗ Failed to delete alias ID {alias_id}: {str(e)}")
                failed_deletions.append({'alias_id': alias_id, 'error': str(e)})
        
        result = {
            'success': deleted_count > 0,
            'deleted_count': deleted_count,
            'total_found': len(alias_ids),
            'message': f'Deleted {deleted_count} out of {len(alias_ids)} aliases'
        }
        
        if failed_deletions:
            result['failed_deletions'] = failed_deletions
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to delete aliases: {str(e)}'
        }


def list_all_aliases():
    """
    List ALL aliases in the mail.alias table
    """
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
        
        aliases = models.execute_kw(
            db, uid, password,
            'mail.alias', 'search_read',
            [[]],
            {'fields': ['id', 'alias_name', 'alias_model_id'], 'order': 'id'}
        )
        
        return {
            'success': True,
            'aliases': aliases,
            'count': len(aliases)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


# Example usage:
if __name__ == '__main__':
    # List ALL aliases in database
    print("=" * 80)
    print("LISTING ALL ALIASES IN DATABASE")
    print("=" * 80)
    result = list_all_aliases()
    if result['success']:
        print(f"\nFound {result['count']} total aliases:")
        for a in result['aliases']:
            model = a['alias_model_id'][1] if isinstance(a['alias_model_id'], list) else 'N/A'
            print(f"  - ID: {a['id']} | Name: {a.get('alias_name', 'N/A')} | Model: {model}")
    
    # Uncomment to delete orphaned journal aliases
    # print("\n" + "=" * 80)
    # print("DELETING ORPHANED JOURNAL ALIASES")
    # print("=" * 80)
    # result = delete_orphaned_aliases()
    # print(f"\nResult: {result}")