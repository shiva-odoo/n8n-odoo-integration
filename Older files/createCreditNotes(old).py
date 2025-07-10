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
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
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

def list_credit_notes():
    """List existing credit notes"""
    models, db, uid, password = connect_odoo()
    if not models:
        return []
    
    try:
        credit_notes = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('move_type', 'in', ['out_refund', 'in_refund'])]], 
            {'fields': ['id', 'name', 'partner_id', 'move_type', 'amount_total', 'state', 'invoice_date'], 'limit': 15}
        )
        
        print(f"\n📋 Credit Notes ({len(credit_notes)} found):")
        print("=" * 90)
        
        if not credit_notes:
            print("   No credit notes found!")
            return []
        
        for note in credit_notes:
            partner_name = note['partner_id'][1] if note.get('partner_id') else 'N/A'
            note_type = "Customer" if note['move_type'] == 'out_refund' else "Vendor"
            date_info = f" | {note['invoice_date']}" if note.get('invoice_date') else ""
            
            print(f"   ID: {note['id']} | {note['name']} | {note_type} | {partner_name} | ${note['amount_total']} | {note['state']}{date_info}")
        
        return credit_notes
        
    except Exception as e:
        print(f"❌ Error listing credit notes: {e}")
        return []

def list_customers():
    """List customers for credit note selection"""
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
    """List vendors for credit note selection"""
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

def create_credit_note():
    """Create a new credit note"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n📋 CREATE CREDIT NOTE")
        print("=" * 22)
        
        # Step 1: Choose credit note type
        print("Credit Note Type:")
        print("1. Customer Credit Note (refund to customer)")
        print("2. Vendor Credit Note (refund from vendor)")
        
        credit_type = input("Choose type (1/2): ").strip()
        
        if credit_type == "1":
            move_type = 'out_refund'
            print("\n👥 Available Customers:")
            partners = list_customers()
        elif credit_type == "2":
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
            
            if credit_type == "1":
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
        
        # Step 2: Credit note details
        print(f"\n📄 Credit Note Details:")
        
        credit_date = input("Credit note date (YYYY-MM-DD) or Enter for today: ").strip()
        if not credit_date:
            credit_date = datetime.now().strftime('%Y-%m-%d')
        
        reference = input("Reference/Reason (optional): ").strip()
        
        # Step 3: Credit note items
        print(f"\n💰 Credit Note Items:")
        
        description = input("Description: ").strip()
        if not description:
            description = "Credit Note"
        
        amount = input("Credit amount: ").strip()
        try:
            amount = float(amount)
            if amount <= 0:
                print("❌ Amount must be positive!")
                return
        except ValueError:
            print("❌ Invalid amount!")
            return
        
        # Step 4: Create credit note
        print(f"\n📋 Credit Note Summary:")
        credit_type_name = "Customer Credit Note" if move_type == 'out_refund' else "Vendor Credit Note"
        print(f"   Type: {credit_type_name}")
        print(f"   Partner: {partner_name}")
        print(f"   Date: {credit_date}")
        print(f"   Description: {description}")
        print(f"   Amount: ${amount}")
        if reference:
            print(f"   Reference: {reference}")
        
        confirm = input("\nCreate credit note? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Credit note creation cancelled.")
            return
        
        # Prepare credit note data
        credit_data = {
            'move_type': move_type,
            'partner_id': partner_id,
            'invoice_date': credit_date,
            'invoice_line_ids': [(0, 0, {
                'name': description,
                'quantity': 1.0,
                'price_unit': amount,
            })]
        }
        
        if reference:
            try:
                credit_data['ref'] = reference
            except:
                # If ref field doesn't exist, skip it
                pass
        
        print(f"🔄 Creating credit note...")
        
        credit_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [credit_data]
        )
        
        if credit_id:
            print(f"✅ Credit note created successfully!")
            print(f"   Credit Note ID: {credit_id}")
            
            # Get created credit note info
            try:
                credit_info = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[credit_id]], 
                    {'fields': ['name', 'amount_total']}
                )[0]
                
                print(f"   Credit Note Number: {credit_info.get('name', 'N/A')}")
                print(f"   Total: ${credit_info.get('amount_total', amount)}")
                
            except Exception as e:
                print(f"   (Could not fetch credit note details: {e})")
                
        else:
            print(f"❌ Failed to create credit note")
            
    except Exception as e:
        print(f"❌ Error creating credit note: {e}")

def modify_credit_note():
    """Modify an existing credit note"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🔧 MODIFY CREDIT NOTE")
        print("=" * 22)
        
        # List credit notes first
        credit_notes = list_credit_notes()
        if not credit_notes:
            return
        
        # Get credit note ID
        credit_id = input("\nEnter Credit Note ID to modify: ").strip()
        try:
            credit_id = int(credit_id)
        except ValueError:
            print("❌ Invalid credit note ID!")
            return
        
        # Get current credit note info (handle potential missing fields)
        try:
            current_credit = models.execute_kw(
                db, uid, password,
                'account.move', 'search_read',
                [[('id', '=', credit_id), ('move_type', 'in', ['out_refund', 'in_refund'])]], 
                {'fields': ['name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state']}
            )
            has_ref_field = True
        except:
            current_credit = models.execute_kw(
                db, uid, password,
                'account.move', 'search_read',
                [[('id', '=', credit_id), ('move_type', 'in', ['out_refund', 'in_refund'])]], 
                {'fields': ['name', 'partner_id', 'invoice_date', 'amount_total', 'state']}
            )
            has_ref_field = False
        
        if not current_credit:
            print(f"❌ Credit Note ID {credit_id} not found!")
            return
        
        credit_info = current_credit[0]
        
        print(f"\n📋 Current Credit Note Info:")
        print(f"   Number: {credit_info.get('name', 'N/A')}")
        print(f"   Partner: {credit_info['partner_id'][1] if credit_info.get('partner_id') else 'N/A'}")
        print(f"   Date: {credit_info.get('invoice_date', 'N/A')}")
        if has_ref_field:
            print(f"   Reference: {credit_info.get('ref', 'N/A')}")
        else:
            print(f"   Reference: N/A (field not available)")
        print(f"   Amount: ${credit_info.get('amount_total', 0)}")
        print(f"   Status: {credit_info.get('state', 'N/A')}")
        
        # Check if credit note can be modified
        if credit_info.get('state') in ['posted', 'cancel']:
            print(f"\n⚠️  WARNING: This credit note is {credit_info.get('state')}!")
            print("   Posted/cancelled credit notes have limited modification options.")
            
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
            if not has_ref_field:
                print("❌ Reference field not available in this Odoo version")
                return
                
            new_ref = input(f"New reference (current: {credit_info.get('ref', 'N/A')}): ").strip()
            if new_ref:
                try:
                    result = models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[credit_id], {'ref': new_ref}]
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
            new_date = input(f"New date YYYY-MM-DD (current: {credit_info.get('invoice_date', 'N/A')}): ").strip()
            if new_date:
                try:
                    result = models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[credit_id], {'invoice_date': new_date}]
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
            try:
                updated_credit = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[credit_id]], 
                    {'fields': ['name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state']}
                )[0]
                updated_has_ref = True
            except:
                updated_credit = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[credit_id]], 
                    {'fields': ['name', 'partner_id', 'invoice_date', 'amount_total', 'state']}
                )[0]
                updated_has_ref = False
            
            print(f"\n📋 Updated Credit Note Info:")
            print(f"   Number: {updated_credit.get('name', 'N/A')}")
            print(f"   Partner: {updated_credit['partner_id'][1] if updated_credit.get('partner_id') else 'N/A'}")
            print(f"   Date: {updated_credit.get('invoice_date', 'N/A')}")
            if updated_has_ref:
                print(f"   Reference: {updated_credit.get('ref', 'N/A')}")
            else:
                print(f"   Reference: N/A (field not available)")
            print(f"   Amount: ${updated_credit.get('amount_total', 0)}")
            print(f"   Status: {updated_credit.get('state', 'N/A')}")
            
        else:
            print("❌ Invalid choice")
            
    except Exception as e:
        print(f"❌ Error modifying credit note: {e}")

def delete_credit_note():
    """Delete a credit note"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🗑️  DELETE CREDIT NOTE")
        print("=" * 22)
        
        # List credit notes first
        credit_notes = list_credit_notes()
        if not credit_notes:
            return
        
        # Get credit note ID
        credit_id = input("\nEnter Credit Note ID to delete: ").strip()
        try:
            credit_id = int(credit_id)
        except ValueError:
            print("❌ Invalid credit note ID!")
            return
        
        # Get credit note info
        credit_info = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', credit_id), ('move_type', 'in', ['out_refund', 'in_refund'])]], 
            {'fields': ['name', 'partner_id', 'amount_total', 'state', 'move_type']}
        )
        
        if not credit_info:
            print(f"❌ Credit Note ID {credit_id} not found!")
            return
        
        credit_data = credit_info[0]
        credit_type_name = "Customer Credit Note" if credit_data['move_type'] == 'out_refund' else "Vendor Credit Note"
        
        print(f"\n📋 Credit Note to Delete:")
        print(f"   ID: {credit_id}")
        print(f"   Number: {credit_data.get('name', 'N/A')}")
        print(f"   Type: {credit_type_name}")
        print(f"   Partner: {credit_data['partner_id'][1] if credit_data.get('partner_id') else 'N/A'}")
        print(f"   Amount: ${credit_data.get('amount_total', 0)}")
        print(f"   Status: {credit_data.get('state', 'N/A')}")
        
        # Check credit note status
        credit_status = credit_data.get('state', 'draft')
        
        if credit_status == 'posted':
            print(f"\n⚠️  WARNING: This credit note is POSTED!")
            print("   - Deleting posted credit notes affects your accounting records")
            print("   - This may impact financial reports and audit trails")
            
        elif credit_status == 'cancel':
            print(f"\n✅ This credit note is cancelled - safe to delete.")
            
        elif credit_status == 'draft':
            print(f"\n✅ This credit note is in draft - safe to delete.")
        
        # Deletion warnings
        print(f"\n🗑️  DELETION WARNINGS:")
        print("   ⚠️  This action CANNOT be undone!")
        print("   ⚠️  All credit note line items will be deleted")
        if credit_status == 'posted':
            print("   ⚠️  Financial reports may be affected")
        
        # Confirmations
        confirm1 = input(f"\nDelete credit note {credit_data.get('name')}? (yes/no): ").lower().strip()
        if confirm1 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        partner_name = credit_data['partner_id'][1] if credit_data.get('partner_id') else 'Unknown'
        confirm2 = input(f"Confirm deletion of ${credit_data.get('amount_total', 0)} credit note for {partner_name}? (yes/no): ").lower().strip()
        if confirm2 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        # Delete credit note
        print(f"🔄 Deleting credit note {credit_id}...")
        
        try:
            result = models.execute_kw(
                db, uid, password,
                'account.move', 'unlink',
                [[credit_id]]
            )
            
            if result:
                print(f"✅ Credit note {credit_id} deleted successfully!")
            else:
                print(f"❌ Failed to delete credit note {credit_id}")
                
        except Exception as delete_error:
            error_msg = str(delete_error)
            print(f"❌ Deletion failed: {error_msg}")
            
            if "posted" in error_msg.lower() or "state" in error_msg.lower():
                print(f"\n💡 This error usually means:")
                print("   - Posted credit notes cannot be deleted directly")
                print("   - Try resetting to draft first, then delete")
                
                # Offer to reset to draft
                reset_option = input("\nTry resetting to draft first? (y/n): ").lower().strip()
                if reset_option == 'y':
                    try:
                        print("🔄 Resetting credit note to draft...")
                        reset_result = models.execute_kw(
                            db, uid, password,
                            'account.move', 'button_draft',
                            [[credit_id]]
                        )
                        
                        if reset_result:
                            print("✅ Credit note reset to draft. Attempting deletion...")
                            
                            delete_result = models.execute_kw(
                                db, uid, password,
                                'account.move', 'unlink',
                                [[credit_id]]
                            )
                            
                            if delete_result:
                                print(f"✅ Credit note {credit_id} deleted successfully after reset!")
                            else:
                                print(f"❌ Still failed to delete after reset")
                        else:
                            print("❌ Failed to reset credit note to draft")
                            
                    except Exception as reset_error:
                        print(f"❌ Reset failed: {reset_error}")
                        
    except Exception as e:
        print(f"❌ Error deleting credit note: {e}")

def main():
    """Main menu"""
    while True:
        print("\n" + "="*40)
        print("📋 CREDIT NOTES MANAGEMENT SYSTEM")
        print("="*40)
        print("1. List all credit notes")
        print("2. Create new credit note")
        print("3. Modify credit note")
        print("4. Delete credit note")
        print("5. Exit")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            list_credit_notes()
        elif choice == "2":
            create_credit_note()
        elif choice == "3":
            modify_credit_note()
        elif choice == "4":
            delete_credit_note()
        elif choice == "5":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice!")

if __name__ == "__main__":
    main()