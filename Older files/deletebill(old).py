import xmlrpc.client
import os
# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def delete_vendor_bill():
    """Simple script to delete a vendor bill in Odoo"""
    
    # Odoo connection details
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Authenticate
        uid = common.authenticate(db, username, password, {})
        if not uid:
            print("❌ Authentication failed!")
            return
        
        print("✅ Connected to Odoo successfully!")
        
        # Step 1: List existing vendor bills
        print("\n📄 Existing Vendor Bills:")
        print("=" * 30)
        
        bills = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('move_type', '=', 'in_invoice')]], 
            {'fields': ['id', 'name', 'partner_id', 'amount_total', 'state', 'ref', 'invoice_date'], 'limit': 15}
        )
        
        if not bills:
            print("❌ No vendor bills found!")
            return
        
        for bill in bills:
            partner_name = bill['partner_id'][1] if bill.get('partner_id') else 'N/A'
            ref_info = f" | Ref: {bill['ref']}" if bill.get('ref') else ""
            date_info = f" | {bill['invoice_date']}" if bill.get('invoice_date') else ""
            
            print(f"   ID: {bill['id']} | {bill['name']} | {partner_name} | ${bill['amount_total']} | {bill['state']}{date_info}{ref_info}")
        
        # Step 2: Get bill ID from user
        bill_id = input(f"\nEnter Vendor Bill ID to delete: ")
        try:
            bill_id = int(bill_id)
        except ValueError:
            print("❌ Invalid bill ID. Please enter a number.")
            return
        
        # Step 3: Check if bill exists and get detailed info
        current_bill = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', bill_id), ('move_type', '=', 'in_invoice')]], 
            {'fields': ['name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state', 'payment_state']}
        )
        
        if not current_bill:
            print(f"❌ Vendor bill with ID {bill_id} not found!")
            return
        
        bill_info = current_bill[0]
        
        print(f"\n📋 Bill to Delete:")
        print(f"   ID: {bill_id}")
        print(f"   Bill Number: {bill_info.get('name', 'N/A')}")
        print(f"   Vendor: {bill_info['partner_id'][1] if bill_info.get('partner_id') else 'N/A'}")
        print(f"   Date: {bill_info.get('invoice_date', 'N/A')}")
        print(f"   Reference: {bill_info.get('ref', 'N/A')}")
        print(f"   Total Amount: ${bill_info.get('amount_total', 0)}")
        print(f"   Status: {bill_info.get('state', 'N/A')}")
        print(f"   Payment Status: {bill_info.get('payment_state', 'N/A')}")
        
        # Step 4: Check bill status and warn accordingly
        bill_status = bill_info.get('state', 'draft')
        payment_status = bill_info.get('payment_state', 'not_paid')
        
        if bill_status == 'posted':
            print(f"\n⚠️  WARNING: This bill is POSTED!")
            print("   - Deleting posted bills affects your accounting records")
            print("   - This may impact financial reports and audit trails")
            
            if payment_status in ['paid', 'in_payment', 'partial']:
                print(f"\n🚨 CRITICAL: This bill has payments associated!")
                print(f"   Payment Status: {payment_status}")
                print("   - Deleting this bill may cause payment reconciliation issues")
                print("   - Consider cancelling the bill instead of deleting")
                
                proceed = input("\nThis is very risky! Continue anyway? (yes/no): ").lower().strip()
                if proceed != 'yes':
                    print("❌ Deletion cancelled (recommended).")
                    return
        
        elif bill_status == 'cancel':
            print(f"\n✅ This bill is already cancelled.")
            print("   Safe to delete - no accounting impact.")
            
        elif bill_status == 'draft':
            print(f"\n✅ This bill is in draft status.")
            print("   Safe to delete - minimal accounting impact.")
        
        else:
            print(f"\n⚠️  Unknown bill status: {bill_status}")
            print("   Proceed with caution.")
        
        # Step 5: Check for related line items
        line_items = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_count',
            [[('move_id', '=', bill_id), ('display_type', '=', False)]]
        )
        
        print(f"\n📝 This bill has {line_items} line item(s)")
        
        # Step 6: Deletion warnings and confirmations
        print(f"\n🗑️  DELETION WARNINGS:")
        print("   ⚠️  This action CANNOT be undone!")
        print("   ⚠️  All associated line items will be deleted")
        print("   ⚠️  Accounting entries will be removed")
        if bill_status == 'posted':
            print("   ⚠️  Financial reports may be affected")
            print("   ⚠️  Audit trail will show deletion")
        
        # First confirmation
        confirm1 = input(f"\nAre you sure you want to delete bill {bill_info.get('name')}? (yes/no): ").lower().strip()
        if confirm1 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        # Second confirmation with bill details
        vendor_name = bill_info['partner_id'][1] if bill_info.get('partner_id') else 'Unknown'
        confirm2 = input(f"Confirm deletion of ${bill_info.get('amount_total', 0)} bill from {vendor_name}? (yes/no): ").lower().strip()
        if confirm2 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        # Final confirmation for posted bills
        if bill_status == 'posted':
            final_confirm = input("FINAL WARNING: Type 'DELETE POSTED BILL' to proceed: ").strip()
            if final_confirm != 'DELETE POSTED BILL':
                print("❌ Final confirmation failed. Deletion cancelled.")
                return
        
        # Step 7: Attempt deletion
        print(f"\n🔄 Deleting vendor bill {bill_id}...")
        
        try:
            # Try to delete the bill
            result = models.execute_kw(
                db, uid, password,
                'account.move', 'unlink',
                [[bill_id]]
            )
            
            if result:
                print(f"✅ Vendor bill {bill_id} deleted successfully!")
                print(f"   Bill '{bill_info.get('name')}' has been permanently removed.")
            else:
                print(f"❌ Failed to delete vendor bill {bill_id}")
                
        except Exception as delete_error:
            error_msg = str(delete_error)
            print(f"❌ Deletion failed: {error_msg}")
            
            # Provide specific error explanations
            if "posted" in error_msg.lower() or "state" in error_msg.lower():
                print(f"\n💡 This error usually means:")
                print("   - Posted bills cannot be deleted directly")
                print("   - You need to reset to draft first, then delete")
                print("   - Or create a credit note instead")
                
                # Offer to reset to draft
                reset_option = input("\nTry resetting to draft first? (y/n): ").lower().strip()
                if reset_option == 'y':
                    try:
                        print("🔄 Resetting bill to draft...")
                        reset_result = models.execute_kw(
                            db, uid, password,
                            'account.move', 'button_draft',
                            [[bill_id]]
                        )
                        
                        if reset_result:
                            print("✅ Bill reset to draft. Attempting deletion...")
                            
                            delete_result = models.execute_kw(
                                db, uid, password,
                                'account.move', 'unlink',
                                [[bill_id]]
                            )
                            
                            if delete_result:
                                print(f"✅ Bill {bill_id} deleted successfully after reset!")
                            else:
                                print(f"❌ Still failed to delete after reset")
                        else:
                            print("❌ Failed to reset bill to draft")
                            
                    except Exception as reset_error:
                        print(f"❌ Reset failed: {reset_error}")
                        
            elif "constraint" in error_msg.lower() or "foreign key" in error_msg.lower():
                print(f"\n💡 This error usually means:")
                print("   - Bill has related records (payments, reconciliations)")
                print("   - These must be removed first")
                print("   - Consider cancelling instead of deleting")
                
            elif "permission" in error_msg.lower() or "access" in error_msg.lower():
                print(f"\n💡 This error usually means:")
                print("   - Your user doesn't have permission to delete bills")
                print("   - Contact your system administrator")
                
            print(f"\n🔧 Alternative options:")
            print("   1. Cancel the bill instead of deleting")
            print("   2. Create a credit note")
            print("   3. Contact your Odoo administrator")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def list_vendor_bills_only():
    """Helper function to just list vendor bills"""
    
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
    username = 'admin@omnithrivetech.com'
    password = '08d538a8d48fa4ad9d9fb0bbea9edb6d155a66fc'
    
    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            print("❌ Authentication failed!")
            return
        
        bills = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('move_type', '=', 'in_invoice')]], 
            {'fields': ['id', 'name', 'partner_id', 'amount_total', 'state', 'ref', 'invoice_date', 'payment_state']}
        )
        
        print(f"\n📄 All Vendor Bills ({len(bills)} found):")
        print("=" * 90)
        
        for bill in bills:
            partner_name = bill['partner_id'][1] if bill.get('partner_id') else 'N/A'
            ref_info = f" | Ref: {bill['ref']}" if bill.get('ref') else ""
            payment_info = f" | Pay: {bill['payment_state']}" if bill.get('payment_state') else ""
            
            print(f"ID: {bill['id']} | {bill['name']} | {partner_name} | ${bill['amount_total']} | {bill['state']} | {bill['invoice_date']}{ref_info}{payment_info}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🗑️  Vendor Bill Deletion Tool")
    print("=" * 32)
    
    print("\nWhat would you like to do?")
    print("1. Delete a vendor bill")
    print("2. List all vendor bills")
    
    choice = input("\nChoice (1/2): ").strip()
    
    if choice == "1":
        delete_vendor_bill()
    elif choice == "2":
        list_vendor_bills_only()
    else:
        print("❌ Invalid choice")