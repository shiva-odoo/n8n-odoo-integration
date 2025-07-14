import xmlrpc.client
import os
# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def create_company_minimal():
    """Minimal script to create a company in Odoo - no currency issues"""
    
    # Odoo connection details
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
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
        
        # Get company name
        company_name = input("\nEnter Company Name: ").strip()
        if not company_name:
            print("❌ Company name is required!")
            return
        
        # Get optional email
        email = input("Enter Email (optional): ").strip()
        
        # Get optional phone
        phone = input("Enter Phone (optional): ").strip()
        
        # Prepare basic company data
        company_data = {
            'name': company_name,
        }
        
        if email:
            company_data['email'] = email
        if phone:
            company_data['phone'] = phone
        
        # Show what we're creating
        print(f"\n📋 Creating Company:")
        print(f"   Name: {company_name}")
        if email:
            print(f"   Email: {email}")
        if phone:
            print(f"   Phone: {phone}")
        
        # Confirm
        confirm = input("\nProceed? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Cancelled.")
            return
        
        # Create company
        print(f"\n🔄 Creating company...")
        
        company_id = models.execute_kw(
            db, uid, password,
            'res.company', 'create',
            [company_data]
        )
        
        if company_id:
            print(f"✅ Company created successfully!")
            print(f"   Company ID: {company_id}")
            print(f"   Name: {company_name}")
        else:
            print(f"❌ Failed to create company")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if you have permission to create companies")
        print("2. Verify your Odoo credentials")
        print("3. Make sure the company name is unique")

if __name__ == "__main__":
    print("🏢 Simple Company Creator")
    print("=" * 25)
    create_company_minimal()