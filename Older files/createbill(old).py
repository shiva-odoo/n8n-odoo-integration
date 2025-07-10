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

def create_vendor_bill_simple():
    """Simplified vendor bill creation - avoids complex account lookups"""
    
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
        
        # Step 1: Get vendor
        print("\n👥 Select Vendor:")
        
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('supplier_rank', '>', 0)]], 
            {'fields': ['id', 'name'], 'limit': 10}
        )
        
        if not vendors:
            print("❌ No vendors found! Please create a vendor first.")
            return
        
        print("Available vendors:")
        for vendor in vendors:
            print(f"   {vendor['id']}: {vendor['name']}")
        
        vendor_id = input("\nEnter vendor ID: ").strip()
        try:
            vendor_id = int(vendor_id)
            vendor_name = next(v['name'] for v in vendors if v['id'] == vendor_id)
            print(f"✅ Selected: {vendor_name}")
        except (ValueError, StopIteration):
            print("❌ Invalid vendor ID!")
            return
        
        # Step 2: Bill details
        print(f"\n📄 Bill Details:")
        
        invoice_date = input("Invoice date (YYYY-MM-DD) or Enter for today: ").strip()
        if not invoice_date:
            invoice_date = datetime.now().strftime('%Y-%m-%d')
        
        vendor_ref = input("Vendor reference (optional): ").strip()
        
        # Step 3: Simple line item
        print(f"\n💰 Bill Amount:")
        
        description = input("Description: ").strip()
        if not description:
            description = "Vendor Bill"
        
        amount = input("Total amount: ").strip()
        try:
            amount = float(amount)
        except ValueError:
            print("❌ Invalid amount!")
            return
        
        # Step 4: Create bill with minimal data
        print(f"\n📋 Summary:")
        print(f"   Vendor: {vendor_name}")
        print(f"   Date: {invoice_date}")
        print(f"   Description: {description}")
        print(f"   Amount: ${amount}")
        if vendor_ref:
            print(f"   Reference: {vendor_ref}")
        
        confirm = input("\nCreate bill? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Cancelled.")
            return
        
        # Prepare minimal bill data (let Odoo handle account assignment)
        bill_data = {
            'move_type': 'in_invoice',
            'partner_id': vendor_id,
            'invoice_date': invoice_date,
            'invoice_line_ids': [(0, 0, {
                'name': description,
                'quantity': 1.0,
                'price_unit': amount,
                # Don't specify account_id - let Odoo auto-assign
            })]
        }
        
        if vendor_ref:
            bill_data['ref'] = vendor_ref
        
        print(f"\n🔄 Creating bill...")
        
        bill_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [bill_data]
        )
        
        if bill_id:
            print(f"✅ Vendor bill created!")
            print(f"   Bill ID: {bill_id}")
            
            # Get bill info
            try:
                bill_info = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[bill_id]], 
                    {'fields': ['name', 'amount_total']}
                )[0]
                
                print(f"   Bill Number: {bill_info.get('name', 'N/A')}")
                print(f"   Total: ${bill_info.get('amount_total', amount)}")
                
            except Exception as e:
                print(f"   (Could not fetch bill details: {e})")
                
        else:
            print(f"❌ Failed to create bill")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def list_vendors():
    """Helper function to list vendors"""
    
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
        
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('supplier_rank', '>', 0)]], 
            {'fields': ['id', 'name', 'email']}
        )
        
        print(f"\n📋 Available Vendors ({len(vendors)} found):")
        print("=" * 40)
        
        for vendor in vendors:
            email = f" - {vendor['email']}" if vendor.get('email') else ""
            print(f"ID: {vendor['id']} | {vendor['name']}{email}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("📄 Simple Vendor Bill Creator")
    print("=" * 30)
    
    print("\nWhat would you like to do?")
    print("1. Create vendor bill")
    print("2. List vendors")
    
    choice = input("\nChoice (1/2): ").strip()
    
    if choice == "1":
        create_vendor_bill_simple()
    elif choice == "2":
        list_vendors()
    else:
        print("❌ Invalid choice")