import xmlrpc.client
import os
from dotenv import load_dotenv

load_dotenv()

def delete_company():
    """Simple script to delete a company in Odoo"""
    
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
        
        # List existing companies first
        print("\n📋 Existing Companies:")
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], {'fields': ['id', 'name', 'email']}
        )
        
        if not companies:
            print("   No companies found!")
            return
        
        for company in companies:
            email_info = f" - {company['email']}" if company.get('email') else ""
            print(f"   ID: {company['id']} | {company['name']}{email_info}")
        
        # Get company ID from user
        company_id = input(f"\nEnter Company ID to delete: ")
        try:
            company_id = int(company_id)
        except ValueError:
            print("❌ Invalid company ID. Please enter a number.")
            return
        
        # Check if company exists
        company_exists = models.execute_kw(
            db, uid, password,
            'res.company', 'search',
            [[('id', '=', company_id)]], {'limit': 1}
        )
        
        if not company_exists:
            print(f"❌ Company with ID {company_id} not found!")
            return
        
        # Get company details
        company_info = models.execute_kw(
            db, uid, password,
            'res.company', 'read',
            [[company_id]], 
            {'fields': ['name', 'email', 'phone', 'website', 'vat']}
        )[0]
        
        print(f"\n🏢 Company to Delete:")
        print(f"   ID: {company_id}")
        print(f"   Name: {company_info.get('name', 'N/A')}")
        print(f"   Email: {company_info.get('email', 'N/A')}")
        print(f"   Phone: {company_info.get('phone', 'N/A')}")
        print(f"   Website: {company_info.get('website', 'N/A')}")
        print(f"   VAT: {company_info.get('vat', 'N/A')}")
        
        # Warning about company deletion
        print(f"\n⚠️  WARNING: Deleting a company is a serious operation!")
        print("   This will remove all company-related data including:")
        print("   - All users associated with this company")
        print("   - All financial records")
        print("   - All transactions and invoices")
        print("   - All accounting data")
        print("\n   This action CANNOT be undone!")
        
        # Check if this is the main company
        try:
            # Get current user's company
            user_info = models.execute_kw(
                db, uid, password,
                'res.users', 'read',
                [[uid]], {'fields': ['company_id']}
            )[0]
            
            user_company_id = user_info['company_id'][0] if user_info.get('company_id') else None
            
            if user_company_id == company_id:
                print(f"\n🚨 CRITICAL WARNING: This is YOUR current company!")
                print("   Deleting your own company may cause system issues!")
                
        except Exception as e:
            print(f"\n⚠️  Could not check if this is your current company: {e}")
        
        # Double confirmation
        print(f"\n🗑️  You are about to DELETE company: {company_info.get('name')}")
        
        confirm1 = input("Are you absolutely sure? (yes/no): ").lower().strip()
        if confirm1 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        confirm2 = input(f"Type the company name '{company_info.get('name')}' to confirm: ").strip()
        if confirm2 != company_info.get('name'):
            print("❌ Company name doesn't match. Deletion cancelled.")
            return
        
        final_confirm = input("Type 'DELETE COMPANY' to proceed: ").strip()
        if final_confirm != 'DELETE COMPANY':
            print("❌ Final confirmation failed. Deletion cancelled.")
            return
        
        # Attempt deletion
        print(f"\n🔄 Deleting company {company_id}...")
        
        try:
            result = models.execute_kw(
                db, uid, password,
                'res.company', 'unlink',
                [[company_id]]
            )
            
            if result:
                print(f"✅ Company {company_id} deleted successfully!")
                print(f"   Company '{company_info.get('name')}' has been permanently removed.")
            else:
                print(f"❌ Failed to delete company {company_id}")
                
        except Exception as delete_error:
            error_msg = str(delete_error)
            print(f"❌ Deletion failed: {error_msg}")
            
            # Common error explanations
            if "foreign key" in error_msg.lower():
                print("\n💡 This error usually means:")
                print("   - Company has associated records that prevent deletion")
                print("   - Users, invoices, or other data still reference this company")
                print("   - You may need to delete or reassign related data first")
                
            elif "permission" in error_msg.lower() or "access" in error_msg.lower():
                print("\n💡 This error usually means:")
                print("   - Your user doesn't have permission to delete companies")
                print("   - Contact your system administrator")
                
            elif "constraint" in error_msg.lower():
                print("\n💡 This error usually means:")
                print("   - System constraint prevents company deletion")
                print("   - Company may be referenced by system data")
                
            print("\n🔧 Possible solutions:")
            print("   1. Contact your Odoo administrator")
            print("   2. Archive the company instead of deleting")
            print("   3. Remove all associated data first")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def list_companies_only():
    """Just list companies without deleting"""
    
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
        
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], {'fields': ['id', 'name', 'email', 'phone']}
        )
        
        print(f"\n📋 All Companies ({len(companies)} found):")
        print("=" * 50)
        
        for company in companies:
            print(f"ID: {company['id']}")
            print(f"Name: {company['name']}")
            print(f"Email: {company.get('email', 'N/A')}")
            print(f"Phone: {company.get('phone', 'N/A')}")
            print("-" * 30)
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🗑️  Odoo Company Deletion Tool")
    print("=" * 32)
    
    print("\nWhat would you like to do?")
    print("1. Delete a company")
    print("2. Just list companies")
    
    choice = input("\nChoose option (1/2): ").strip()
    
    if choice == "1":
        delete_company()
    elif choice == "2":
        list_companies_only()
    else:
        print("❌ Invalid choice.")