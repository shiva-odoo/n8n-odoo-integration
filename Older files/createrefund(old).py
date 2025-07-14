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

def connect_odoo():
    """Connect to Odoo"""
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            raise Exception("Authentication failed")
        
        print("✅ Connected to Odoo successfully!")
        return models, db, uid, password
        
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return None, None, None, None

def list_refunds():
    """List existing refunds/credit notes"""
    models, db, uid, password = connect_odoo()
    if not models:
        return []
    
    try:
        # Get both customer and vendor refunds
        refunds = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('move_type', 'in', ['out_refund', 'in_refund'])]], 
            {'fields': ['id', 'name', 'partner_id', 'move_type', 'amount_total', 'state', 'invoice_date'], 'limit': 15}
        )
        
        print(f"\n💸 Existing Refunds ({len(refunds)} found):")
        print("=" * 80)
        
        if not refunds:
            print("   No refunds found!")
            return []
        
        for refund in refunds:
            partner_name = refund['partner_id'][1] if refund.get('partner_id') else 'N/A'
            refund_type = "Customer" if refund['move_type'] == 'out_refund' else "Vendor"
            date_info = f" | {refund['invoice_date']}" if refund.get('invoice_date') else ""
            
            print(f"   ID: {refund['id']} | {refund['name']} | {refund_type} | {partner_name} | ${refund['amount_total']} | {refund['state']}{date_info}")
        
        return refunds
        
    except Exception as e:
        print(f"❌ Error listing refunds: {e}")
        return []

def list_customers():
    """List customers for refund selection"""
    models, db, uid, password = connect_odoo()
    if not models:
        return []
    
    try:
        customers = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('customer_rank', '>', 0)]], 
            {'fields': ['id', 'name'], 'limit': 10}
        )
        return customers
    except Exception as e:
        print(f"❌ Error listing customers: {e}")
        return []

def list_vendors():
    """List vendors for refund selection"""
    models, db, uid, password = connect_odoo()
    if not models:
        return []
    
    try:
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('supplier_rank', '>', 0)]], 
            {'fields': ['id', 'name'], 'limit': 10}
        )
        return vendors
    except Exception as e:
        print(f"❌ Error listing vendors: {e}")
        return []

def create_refund():
    """Create a new refund/credit note"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n💸 CREATE REFUND")
        print("=" * 20)
        
        # Step 1: Choose refund type
        print("Refund Type:")
        print("1. Customer Refund (Credit Note)")
        print("2. Vendor Refund")
        
        refund_type = input("Choose type (1/2): ").strip()
        
        if refund_type == "1":
            move_type = 'out_refund'
            print("\n👥 Available Customers:")
            partners = list_customers()
        elif refund_type == "2":
            move_type = 'in_refund'
            print("\n👥 Available Vendors:")
            partners = list_vendors()
        else:
            print("❌ Invalid choice!")
            return
        
        if not partners:
            print("❌ No partners found!")
            return
        
        # Show partners
        for partner in partners:
            print(f"   {partner['id']}: {partner['name']}")
        
        # Get partner selection
        partner_choice = input("\nEnter Partner ID or 'new' for new partner: ").strip()
        
        if partner_choice.lower() == 'new':
            partner_name = input("Enter partner name: ").strip()
            if not partner_name:
                print("❌ Partner name required!")
                return
            
            # Create new partner
            partner_data = {
                'name': partner_name,
                'is_company': True,
            }
            
            if refund_type == "1":
                partner_data['customer_rank'] = 1
            else:
                partner_data['supplier_rank'] = 1
            
            partner_id = models.execute_kw(
                db, uid, password,
                'res.partner', 'create',
                [partner_data]
            )
            
            print(f"✅ Created new partner: {partner_name} (ID: {partner_id})")
            
        else:
            try:
                partner_id = int(partner_choice)
                partner_name = next(p['name'] for p in partners if p['id'] == partner_id)
                print(f"✅ Selected: {partner_name}")
            except (ValueError, StopIteration):
                print("❌ Invalid partner ID!")
                return
        
        # Step 2: Refund details
        print(f"\n📄 Refund Details:")
        
        refund_date = input("Refund date (YYYY-MM-DD) or Enter for today: ").strip()
        if not refund_date:
            refund_date = datetime.now().strftime('%Y-%m-%d')
        
        reference = input("Reference/Reason (optional): ").strip()
        
        # Step 3: Refund amount and description
        print(f"\n💰 Refund Items:")
        
        description = input("Description: ").strip()
        if not description:
            description = "Refund"
        
        amount = input("Refund amount: ").strip()
        try:
            amount = float(amount)
        except ValueError:
            print("❌ Invalid amount!")
            return
        
        # Step 4: Create refund
        print(f"\n📋 Refund Summary:")
        refund_type_name = "Customer Refund" if move_type == 'out_refund' else "Vendor Refund"
        print(f"   Type: {refund_type_name}")
        print(f"   Partner: {partner_name}")
        print(f"   Date: {refund_date}")
        print(f"   Description: {description}")
        print(f"   Amount: ${amount}")
        if reference:
            print(f"   Reference: {reference}")
        
        confirm = input("\nCreate refund? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Cancelled.")
            return
        
        # Prepare refund data
        refund_data = {
            'move_type': move_type,
            'partner_id': partner_id,
            'invoice_date': refund_date,
            'invoice_line_ids': [(0, 0, {
                'name': description,
                'quantity': 1.0,
                'price_unit': amount,
            })]
        }
        
        if reference:
            refund_data['ref'] = reference
        
        print(f"🔄 Creating refund...")
        
        refund_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [refund_data]
        )
        
        if refund_id:
            print(f"✅ Refund created successfully!")
            print(f"   Refund ID: {refund_id}")
            
            # Get created refund info
            try:
                refund_info = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[refund_id]], 
                    {'fields': ['name', 'amount_total']}
                )[0]
                
                print(f"   Refund Number: {refund_info.get('name', 'N/A')}")
                print(f"   Total: ${refund_info.get('amount_total', amount)}")
                
            except Exception as e:
                print(f"   (Could not fetch refund details: {e})")
                
        else:
            print(f"❌ Failed to create refund")
            
    except Exception as e:
        print(f"❌ Error creating refund: {e}")

def modify_refund():
    """Modify an existing refund"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🔧 MODIFY REFUND")
        print("=" * 20)
        
        # List refunds first
        refunds = list_refunds()
        if not refunds:
            return
        
        # Get refund ID
        refund_id = input("\nEnter Refund ID to modify: ").strip()
        try:
            refund_id = int(refund_id)
        except ValueError:
            print("❌ Invalid refund ID!")
            return
        
        # Get current refund info
        current_refund = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', refund_id), ('move_type', 'in', ['out_refund', 'in_refund'])]], 
            {'fields': ['name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state']}
        )
        
        if not current_refund:
            print(f"❌ Refund ID {refund_id} not found!")
            return
        
        refund_info = current_refund[0]
        
        print(f"\n📋 Current Refund Info:")
        print(f"   Number: {refund_info.get('name', 'N/A')}")
        print(f"   Partner: {refund_info['partner_id'][1] if refund_info.get('partner_id') else 'N/A'}")
        print(f"   Date: {refund_info.get('invoice_date', 'N/A')}")
        print(f"   Reference: {refund_info.get('ref', 'N/A')}")
        print(f"   Amount: ${refund_info.get('amount_total', 0)}")
        print(f"   Status: {refund_info.get('state', 'N/A')}")
        
        # Check if refund can be modified
        if refund_info.get('state') in ['posted', 'cancel']:
            print(f"\n⚠️  WARNING: This refund is {refund_info.get('state')}!")
            print("   Posted/cancelled refunds have limited modification options.")
            
            continue_anyway = input("\nContinue anyway? (y/n): ").lower().strip()
            if continue_anyway != 'y':
                print("❌ Modification cancelled.")
                return
        
        # Modification options
        print(f"\n🔧 What would you like to modify?")
        print("   1. Reference/Reason")
        print("   2. Date")
        print("   3. Show summary and exit")
        
        choice = input("\nChoose option (1-3): ").strip()
        
        if choice == "1":
            # Modify reference
            new_ref = input(f"New reference (current: {refund_info.get('ref', 'N/A')}): ").strip()
            if new_ref:
                try:
                    result = models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[refund_id], {'ref': new_ref}]
                    )
                    if result:
                        print(f"✅ Reference updated to: {new_ref}")
                    else:
                        print("❌ Failed to update reference")
                except Exception as e:
                    print(f"❌ Error updating reference: {e}")
            else:
                print("❌ No reference provided")
        
        elif choice == "2":
            # Modify date
            new_date = input(f"New date YYYY-MM-DD (current: {refund_info.get('invoice_date', 'N/A')}): ").strip()
            if new_date:
                try:
                    result = models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[refund_id], {'invoice_date': new_date}]
                    )
                    if result:
                        print(f"✅ Date updated to: {new_date}")
                    else:
                        print("❌ Failed to update date")
                except Exception as e:
                    print(f"❌ Error updating date: {e}")
            else:
                print("❌ No date provided")
        
        elif choice == "3":
            # Show updated summary
            updated_refund = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[refund_id]], 
                {'fields': ['name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state']}
            )[0]
            
            print(f"\n📋 Updated Refund Info:")
            print(f"   Number: {updated_refund.get('name', 'N/A')}")
            print(f"   Partner: {updated_refund['partner_id'][1] if updated_refund.get('partner_id') else 'N/A'}")
            print(f"   Date: {updated_refund.get('invoice_date', 'N/A')}")
            print(f"   Reference: {updated_refund.get('ref', 'N/A')}")
            print(f"   Amount: ${updated_refund.get('amount_total', 0)}")
            print(f"   Status: {updated_refund.get('state', 'N/A')}")
            
        else:
            print("❌ Invalid choice")
            
    except Exception as e:
        print(f"❌ Error modifying refund: {e}")

def delete_refund():
    """Delete a refund"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🗑️  DELETE REFUND")
        print("=" * 20)
        
        # List refunds first
        refunds = list_refunds()
        if not refunds:
            return
        
        # Get refund ID
        refund_id = input("\nEnter Refund ID to delete: ").strip()
        try:
            refund_id = int(refund_id)
        except ValueError:
            print("❌ Invalid refund ID!")
            return
        
        # Get refund info
        refund_info = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', refund_id), ('move_type', 'in', ['out_refund', 'in_refund'])]], 
            {'fields': ['name', 'partner_id', 'amount_total', 'state', 'move_type']}
        )
        
        if not refund_info:
            print(f"❌ Refund ID {refund_id} not found!")
            return
        
        refund_data = refund_info[0]
        refund_type_name = "Customer Refund" if refund_data['move_type'] == 'out_refund' else "Vendor Refund"
        
        print(f"\n📋 Refund to Delete:")
        print(f"   ID: {refund_id}")
        print(f"   Number: {refund_data.get('name', 'N/A')}")
        print(f"   Type: {refund_type_name}")
        print(f"   Partner: {refund_data['partner_id'][1] if refund_data.get('partner_id') else 'N/A'}")
        print(f"   Amount: ${refund_data.get('amount_total', 0)}")
        print(f"   Status: {refund_data.get('state', 'N/A')}")
        
        # Check refund status
        refund_status = refund_data.get('state', 'draft')
        
        if refund_status == 'posted':
            print(f"\n⚠️  WARNING: This refund is POSTED!")
            print("   - Deleting posted refunds affects your accounting records")
            print("   - This may impact financial reports and audit trails")
            
        elif refund_status == 'cancel':
            print(f"\n✅ This refund is cancelled - safe to delete.")
            
        elif refund_status == 'draft':
            print(f"\n✅ This refund is in draft - safe to delete.")
        
        # Deletion warnings
        print(f"\n🗑️  DELETION WARNINGS:")
        print("   ⚠️  This action CANNOT be undone!")
        print("   ⚠️  All refund line items will be deleted")
        if refund_status == 'posted':
            print("   ⚠️  Financial reports may be affected")
        
        # Confirmations
        confirm1 = input(f"\nDelete refund {refund_data.get('name')}? (yes/no): ").lower().strip()
        if confirm1 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        partner_name = refund_data['partner_id'][1] if refund_data.get('partner_id') else 'Unknown'
        confirm2 = input(f"Confirm deletion of ${refund_data.get('amount_total', 0)} refund to {partner_name}? (yes/no): ").lower().strip()
        if confirm2 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        # Delete refund
        print(f"🔄 Deleting refund {refund_id}...")
        
        try:
            result = models.execute_kw(
                db, uid, password,
                'account.move', 'unlink',
                [[refund_id]]
            )
            
            if result:
                print(f"✅ Refund {refund_id} deleted successfully!")
            else:
                print(f"❌ Failed to delete refund {refund_id}")
                
        except Exception as delete_error:
            error_msg = str(delete_error)
            print(f"❌ Deletion failed: {error_msg}")
            
            if "posted" in error_msg.lower() or "state" in error_msg.lower():
                print(f"\n💡 This error usually means:")
                print("   - Posted refunds cannot be deleted directly")
                print("   - Try resetting to draft first, then delete")
                
                # Offer to reset to draft
                reset_option = input("\nTry resetting to draft first? (y/n): ").lower().strip()
                if reset_option == 'y':
                    try:
                        print("🔄 Resetting refund to draft...")
                        reset_result = models.execute_kw(
                            db, uid, password,
                            'account.move', 'button_draft',
                            [[refund_id]]
                        )
                        
                        if reset_result:
                            print("✅ Refund reset to draft. Attempting deletion...")
                            
                            delete_result = models.execute_kw(
                                db, uid, password,
                                'account.move', 'unlink',
                                [[refund_id]]
                            )
                            
                            if delete_result:
                                print(f"✅ Refund {refund_id} deleted successfully after reset!")
                            else:
                                print(f"❌ Still failed to delete after reset")
                        else:
                            print("❌ Failed to reset refund to draft")
                            
                    except Exception as reset_error:
                        print(f"❌ Reset failed: {reset_error}")
                        
    except Exception as e:
        print(f"❌ Error deleting refund: {e}")

def main():
    """Main menu"""
    while True:
        print("\n" + "="*40)
        print("💸 REFUND MANAGEMENT SYSTEM")
        print("="*40)
        print("1. List all refunds")
        print("2. Create new refund")
        print("3. Modify refund")
        print("4. Delete refund")
        print("5. Exit")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            list_refunds()
        elif choice == "2":
            create_refund()
        elif choice == "3":
            modify_refund()
        elif choice == "4":
            delete_refund()
        elif choice == "5":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice!")

if __name__ == "__main__":
    main()