import xmlrpc.client
import os
from dotenv import load_dotenv

load_dotenv()

def delete_vendor():
    """Simple script to delete vendor in Odoo"""
    
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
        
        # Get vendor ID from user
        vendor_id = input("\nEnter Vendor ID to delete: ")
        try:
            vendor_id = int(vendor_id)
        except ValueError:
            print("❌ Invalid vendor ID. Please enter a number.")
            return
        
        # Check if vendor exists
        vendor_exists = models.execute_kw(
            db, uid, password,
            'res.partner', 'search',
            [[('id', '=', vendor_id)]], {'limit': 1}
        )
        
        if not vendor_exists:
            print(f"❌ Vendor with ID {vendor_id} not found!")
            return
        
        # Get current vendor info
        current_vendor = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [[vendor_id]], 
            {'fields': ['name', 'email', 'phone', 'vat', 'active']}
        )[0]
        
        print(f"\n📋 Vendor to Delete:")
        print(f"   ID: {vendor_id}")
        print(f"   Name: {current_vendor.get('name', 'N/A')}")
        print(f"   Email: {current_vendor.get('email', 'N/A')}")
        print(f"   Phone: {current_vendor.get('phone', 'N/A')}")
        print(f"   VAT: {current_vendor.get('vat', 'N/A')}")
        print(f"   Status: {'Active' if current_vendor.get('active') else 'Archived'}")
        
        # Check for existing transactions
        print(f"\n🔍 Checking for existing transactions...")
        
        # Check for vendor bills
        invoice_count = models.execute_kw(
            db, uid, password,
            'account.move', 'search_count',
            [[('partner_id', '=', vendor_id), ('move_type', '=', 'in_invoice')]]
        )
        
        # Check for payments
        payment_count = models.execute_kw(
            db, uid, password,
            'account.payment', 'search_count',
            [[('partner_id', '=', vendor_id)]]
        )
        
        # Check for purchase orders (if module exists)
        po_count = 0
        try:
            po_count = models.execute_kw(
                db, uid, password,
                'purchase.order', 'search_count',
                [[('partner_id', '=', vendor_id)]]
            )
        except:
            pass  # Purchase module might not be installed
        
        total_transactions = invoice_count + payment_count + po_count
        
        print(f"   📄 Vendor Bills: {invoice_count}")
        print(f"   💰 Payments: {payment_count}")
        print(f"   🛒 Purchase Orders: {po_count}")
        print(f"   📊 Total Transactions: {total_transactions}")
        
        # Determine deletion approach
        if total_transactions > 0:
            print(f"\n⚠️  WARNING: This vendor has {total_transactions} existing transactions!")
            print("   Deleting vendors with transactions may cause data integrity issues.")
            print("\n🔧 Available Options:")
            print("   1. Archive vendor (recommended - hides but preserves data)")
            print("   2. Force delete (dangerous - may cause errors)")
            print("   3. Cancel operation")
            
            choice = input("\nChoose option (1/2/3): ").strip()
            
            if choice == "1":
                # Archive vendor
                print(f"\n🗃️  Archiving vendor {vendor_id}...")
                
                confirm = input("Confirm archive operation? (y/n): ").lower().strip()
                if confirm != 'y':
                    print("❌ Operation cancelled.")
                    return
                
                result = models.execute_kw(
                    db, uid, password,
                    'res.partner', 'write',
                    [[vendor_id], {'active': False}]
                )
                
                if result:
                    print(f"✅ Vendor {vendor_id} archived successfully!")
                    print("   The vendor is now hidden but data is preserved.")
                    print("   You can unarchive it later if needed.")
                else:
                    print(f"❌ Failed to archive vendor {vendor_id}")
                    
            elif choice == "2":
                # Force delete
                print(f"\n⚠️  FORCE DELETING vendor {vendor_id}...")
                print("   This may cause database errors or data corruption!")
                
                confirm = input("Are you absolutely sure? Type 'DELETE' to confirm: ").strip()
                if confirm != 'DELETE':
                    print("❌ Operation cancelled.")
                    return
                
                try:
                    result = models.execute_kw(
                        db, uid, password,
                        'res.partner', 'unlink',
                        [[vendor_id]]
                    )
                    
                    if result:
                        print(f"✅ Vendor {vendor_id} force deleted!")
                    else:
                        print(f"❌ Failed to delete vendor {vendor_id}")
                        
                except Exception as e:
                    print(f"❌ Force delete failed: {e}")
                    print("   Consider archiving instead.")
                    
            else:
                print("❌ Operation cancelled.")
                return
                
        else:
            # Safe to delete - no transactions
            print(f"\n✅ Safe to delete - no existing transactions found.")
            print(f"\n🗑️  Deleting vendor {vendor_id}...")
            
            confirm = input("Confirm deletion? (y/n): ").lower().strip()
            if confirm != 'y':
                print("❌ Operation cancelled.")
                return
            
            try:
                result = models.execute_kw(
                    db, uid, password,
                    'res.partner', 'unlink',
                    [[vendor_id]]
                )
                
                if result:
                    print(f"✅ Vendor {vendor_id} deleted successfully!")
                else:
                    print(f"❌ Failed to delete vendor {vendor_id}")
                    
            except Exception as e:
                print(f"❌ Deletion failed: {e}")
                
                # Offer archiving as fallback
                print("\n💡 Deletion failed. Try archiving instead?")
                archive_choice = input("Archive vendor? (y/n): ").lower().strip()
                
                if archive_choice == 'y':
                    result = models.execute_kw(
                        db, uid, password,
                        'res.partner', 'write',
                        [[vendor_id], {'active': False}]
                    )
                    
                    if result:
                        print(f"✅ Vendor {vendor_id} archived successfully!")
                    else:
                        print(f"❌ Archiving also failed.")
                        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🗑️  Odoo Vendor Deletion Tool")
    print("=" * 30)
    delete_vendor()