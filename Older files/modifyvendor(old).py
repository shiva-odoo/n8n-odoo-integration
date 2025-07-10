import xmlrpc.client
import os
# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def modify_vendor():
    """Simple script to modify vendor in Odoo"""
    
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
        vendor_id = input("\nEnter Vendor ID to modify: ")
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
            {'fields': ['name', 'email', 'phone', 'vat', 'website']}
        )[0]
        
        print(f"\n📋 Current Vendor Information:")
        print(f"   Name: {current_vendor.get('name', 'N/A')}")
        print(f"   Email: {current_vendor.get('email', 'N/A')}")
        print(f"   Phone: {current_vendor.get('phone', 'N/A')}")
        print(f"   VAT: {current_vendor.get('vat', 'N/A')}")
        print(f"   Website: {current_vendor.get('website', 'N/A')}")
        
        # Collect updates from user
        print("\n✏️  Enter new values (press Enter to skip a field):")
        
        updates = {}
        
        # Name
        new_name = input(f"New Name (current: {current_vendor.get('name', 'N/A')}): ").strip()
        if new_name:
            updates['name'] = new_name
        
        # Email
        new_email = input(f"New Email (current: {current_vendor.get('email', 'N/A')}): ").strip()
        if new_email:
            updates['email'] = new_email
        
        # Phone
        new_phone = input(f"New Phone (current: {current_vendor.get('phone', 'N/A')}): ").strip()
        if new_phone:
            updates['phone'] = new_phone
        
        # VAT
        new_vat = input(f"New VAT (current: {current_vendor.get('vat', 'N/A')}): ").strip()
        if new_vat:
            updates['vat'] = new_vat
        
        # Website
        new_website = input(f"New Website (current: {current_vendor.get('website', 'N/A')}): ").strip()
        if new_website:
            updates['website'] = new_website
        
        # Check if any updates were provided
        if not updates:
            print("\n⚠️  No updates provided. Exiting...")
            return
        
        print(f"\n🔄 Updating vendor with: {updates}")
        
        # Confirm update
        confirm = input("\nProceed with update? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Update cancelled.")
            return
        
        # Update vendor
        result = models.execute_kw(
            db, uid, password,
            'res.partner', 'write',
            [[vendor_id], updates]
        )
        
        if result:
            print(f"\n✅ Vendor {vendor_id} updated successfully!")
            
            # Show updated info
            updated_vendor = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [[vendor_id]], 
                {'fields': ['name', 'email', 'phone', 'vat', 'website']}
            )[0]
            
            print(f"\n📋 Updated Vendor Information:")
            print(f"   Name: {updated_vendor.get('name', 'N/A')}")
            print(f"   Email: {updated_vendor.get('email', 'N/A')}")
            print(f"   Phone: {updated_vendor.get('phone', 'N/A')}")
            print(f"   VAT: {updated_vendor.get('vat', 'N/A')}")
            print(f"   Website: {updated_vendor.get('website', 'N/A')}")
            
        else:
            print(f"❌ Failed to update vendor {vendor_id}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🔧 Odoo Vendor Modification Tool")
    print("=" * 35)
    modify_vendor()