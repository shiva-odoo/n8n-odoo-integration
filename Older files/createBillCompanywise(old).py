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

def create_vendor_bill_with_company():
    """Create vendor bill with company selection"""
    
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
        
        # Step 1: Select Company
        print("\n🏢 Select Company:")
        
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'currency_id'], 'order': 'name'}
        )
        
        if not companies:
            print("❌ No companies found!")
            return
        
        print("Available companies:")
        for company in companies:
            currency_name = company['currency_id'][1] if company.get('currency_id') else 'N/A'
            print(f"   {company['id']}: {company['name']} ({currency_name})")
        
        company_id = input("\nEnter company ID: ").strip()
        try:
            company_id = int(company_id)
            company_name = next(c['name'] for c in companies if c['id'] == company_id)
            currency_name = next(c['currency_id'][1] for c in companies if c['id'] == company_id and c.get('currency_id'))
            print(f"✅ Selected: {company_name} ({currency_name})")
        except (ValueError, StopIteration):
            print("❌ Invalid company ID!")
            return
        
        # Step 2: Get vendors for selected company
        print(f"\n👥 Select Vendor for {company_name}:")
        
        # First, get vendors specifically for this company
        company_vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('supplier_rank', '>', 0), ('company_id', '=', company_id)]], 
            {'fields': ['id', 'name', 'company_id'], 'order': 'name'}
        )
        
        # Then get global vendors (no company assigned)
        global_vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('supplier_rank', '>', 0), ('company_id', '=', False)]], 
            {'fields': ['id', 'name', 'company_id'], 'order': 'name'}
        )
        
        # Combine and display vendors
        vendors = company_vendors + global_vendors
        
        if not vendors:
            print("❌ No vendors found for this company! Please create a vendor first.")
            print("\nDebugging info:")
            print(f"   Company ID searched: {company_id}")
            print(f"   Company vendors found: {len(company_vendors)}")
            print(f"   Global vendors found: {len(global_vendors)}")
            return
        
        print("Available vendors:")
        
        # Show company-specific vendors first
        if company_vendors:
            print(f"  📋 Company-specific vendors for {company_name}:")
            for vendor in company_vendors:
                vendor_company = f" (Company: {vendor['company_id'][1]})" if vendor.get('company_id') else " (ERROR: No company)"
                print(f"     {vendor['id']}: {vendor['name']}{vendor_company}")
        
        # Then show global vendors
        if global_vendors:
            print(f"  🌍 Global vendors (available to all companies):")
            for vendor in global_vendors:
                print(f"     {vendor['id']}: {vendor['name']} (Global)")
        
        print(f"\n  Total: {len(company_vendors)} company-specific + {len(global_vendors)} global = {len(vendors)} vendors")
        
        vendor_id = input("\nEnter vendor ID: ").strip()
        try:
            vendor_id = int(vendor_id)
            vendor_name = next(v['name'] for v in vendors if v['id'] == vendor_id)
            print(f"✅ Selected: {vendor_name}")
        except (ValueError, StopIteration):
            print("❌ Invalid vendor ID!")
            return
        
        # Step 3: Bill details
        print(f"\n📄 Bill Details for {company_name}:")
        
        invoice_date = input("Invoice date (YYYY-MM-DD) or Enter for today: ").strip()
        if not invoice_date:
            invoice_date = datetime.now().strftime('%Y-%m-%d')
        
        vendor_ref = input("Vendor reference (optional): ").strip()
        
        # Step 4: Simple line item
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
        
        # Step 5: Create bill with company context
        print(f"\n📋 Summary:")
        print(f"   Company: {company_name}")
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
        
        # Prepare bill data with company context
        bill_data = {
            'move_type': 'in_invoice',
            'partner_id': vendor_id,
            'company_id': company_id,  # Set the company
            'invoice_date': invoice_date,
            'invoice_line_ids': [(0, 0, {
                'name': description,
                'quantity': 1.0,
                'price_unit': amount,
                'company_id': company_id,  # Set company for line item too
            })]
        }
        
        if vendor_ref:
            bill_data['ref'] = vendor_ref
        
        print(f"\n🔄 Creating bill for {company_name}...")
        
        # Create bill with company context
        bill_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [bill_data],
            {'context': {'default_company_id': company_id}}  # Set company context
        )
        
        if bill_id:
            print(f"✅ Vendor bill created for {company_name}!")
            print(f"   Bill ID: {bill_id}")
            
            # Get bill info
            try:
                bill_info = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[bill_id], ['name', 'amount_total', 'company_id']],
                    {'context': {'company_id': company_id}}
                )[0]
                
                print(f"   Bill Number: {bill_info.get('name', 'N/A')}")
                print(f"   Total: ${bill_info.get('amount_total', amount)}")
                bill_company = bill_info['company_id'][1] if bill_info.get('company_id') else 'N/A'
                print(f"   Company: {bill_company}")
                
            except Exception as e:
                print(f"   (Could not fetch bill details: {e})")
                # Try simpler approach without context
                try:
                    bill_info = models.execute_kw(
                        db, uid, password,
                        'account.move', 'read',
                        [[bill_id], ['name', 'amount_total']]
                    )[0]
                    
                    print(f"   Bill Number: {bill_info.get('name', 'N/A')}")
                    print(f"   Total: ${bill_info.get('amount_total', amount)}")
                    
                except Exception as e2:
                    print(f"   (Simple fetch also failed: {e2})")
                    print(f"   Bill created with ID: {bill_id}, but details unavailable")
                
        else:
            print(f"❌ Failed to create bill")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def list_companies():
    """List all companies in the system"""
    
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
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
            [[]], 
            {'fields': ['id', 'name', 'currency_id', 'country_id'], 'order': 'name'}
        )
        
        print(f"\n🏢 Available Companies ({len(companies)} found):")
        print("=" * 60)
        
        for company in companies:
            currency = company['currency_id'][1] if company.get('currency_id') else 'N/A'
            country = company['country_id'][1] if company.get('country_id') else 'N/A'
            print(f"ID: {company['id']} | {company['name']}")
            print(f"     Currency: {currency} | Country: {country}")
            print("-" * 60)
            
    except Exception as e:
        print(f"❌ Error: {e}")

def check_company_setup():
    """Check if companies have proper journal setup"""
    
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            print("❌ Authentication failed!")
            return
        
        # Get companies
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], 
            {'fields': ['id', 'name'], 'order': 'name'}
        )
        
        print(f"\n🔍 Company Setup Check:")
        print("=" * 50)
        
        for company in companies:
            company_id = company['id']
            company_name = company['name']
            
            print(f"\n🏢 {company_name} (ID: {company_id})")
            
            # Check purchase journals
            purchase_journals = models.execute_kw(
                db, uid, password,
                'account.journal', 'search_read',
                [[('company_id', '=', company_id), ('type', '=', 'purchase')]], 
                {'fields': ['id', 'name', 'code']}
            )
            
            if purchase_journals:
                print("   ✅ Purchase journals found:")
                for journal in purchase_journals:
                    print(f"      • {journal['name']} ({journal['code']}) - ID: {journal['id']}")
            else:
                print("   ❌ No purchase journals found!")
                print("      This company cannot create vendor bills.")
            
            # Check sale journals
            sale_journals = models.execute_kw(
                db, uid, password,
                'account.journal', 'search_read',
                [[('company_id', '=', company_id), ('type', '=', 'sale')]], 
                {'fields': ['id', 'name', 'code']}
            )
            
            if sale_journals:
                print("   ✅ Sale journals found:")
                for journal in sale_journals[:2]:  # Show first 2
                    print(f"      • {journal['name']} ({journal['code']}) - ID: {journal['id']}")
                if len(sale_journals) > 2:
                    print(f"      ... and {len(sale_journals) - 2} more")
            else:
                print("   ❌ No sale journals found!")
            
            # Check vendors for this company
            vendor_count = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_count',
                [[('supplier_rank', '>', 0), '|', ('company_id', '=', company_id), ('company_id', '=', False)]]
            )
            
            print(f"   📊 Available vendors: {vendor_count}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def list_vendors_by_company():
    """List vendors grouped by company"""
    
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            print("❌ Authentication failed!")
            return
        
        # Get companies
        companies = models.execute_kw(
            db, uid, password,
            'res.company', 'search_read',
            [[]], 
            {'fields': ['id', 'name'], 'order': 'name'}
        )
        
        print(f"\n👥 Vendors by Company:")
        print("=" * 50)
        
        for company in companies:
            company_id = company['id']
            company_name = company['name']
            
            # Get company-specific vendors
            company_vendors = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_read',
                [[('supplier_rank', '>', 0), ('company_id', '=', company_id)]], 
                {'fields': ['id', 'name', 'email'], 'order': 'name'}
            )
            
            # Get global vendors available to this company
            global_vendors = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_read',
                [[('supplier_rank', '>', 0), ('company_id', '=', False)]], 
                {'fields': ['id', 'name', 'email'], 'order': 'name'}
            )
            
            print(f"\n🏢 {company_name} (ID: {company_id})")
            print("-" * 30)
            
            if company_vendors:
                print(f"   📋 Company-specific vendors ({len(company_vendors)}):")
                for vendor in company_vendors:
                    email = f" - {vendor['email']}" if vendor.get('email') else ""
                    print(f"      • {vendor['name']}{email} (ID: {vendor['id']})")
            
            if global_vendors:
                print(f"   🌍 Global vendors available ({len(global_vendors)}):")
                for vendor in global_vendors[:3]:  # Show first 3
                    email = f" - {vendor['email']}" if vendor.get('email') else ""
                    print(f"      • {vendor['name']}{email} (ID: {vendor['id']})")
                if len(global_vendors) > 3:
                    print(f"      ... and {len(global_vendors) - 3} more global vendors")
            
            if not company_vendors and not global_vendors:
                print("   ❌ No vendors available for this company")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def list_vendors():
    """Helper function to list all vendors (original function)"""
    
    url = 'https://omnithrive-technologies1.odoo.com'
    db = 'omnithrive-technologies1'
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
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
            {'fields': ['id', 'name', 'email', 'company_id'], 'order': 'name'}
        )
        
        print(f"\n📋 All Vendors ({len(vendors)} found):")
        print("=" * 60)
        
        for vendor in vendors:
            email = f" - {vendor['email']}" if vendor.get('email') else ""
            company_info = f" (Company: {vendor['company_id'][1]})" if vendor.get('company_id') else " (Global)"
            print(f"ID: {vendor['id']} | {vendor['name']}{email}{company_info}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("📄 Multi-Company Vendor Bill Creator")
    print("=" * 40)
    
    print("\nWhat would you like to do?")
    print("1. Create vendor bill (with company selection)")
    print("2. List companies")
    print("3. List vendors by company")
    print("4. List all vendors")
    print("5. Check company setup (journals & vendors)")
    
    choice = input("\nChoice (1/2/3/4/5): ").strip()
    
    if choice == "1":
        create_vendor_bill_with_company()
    elif choice == "2":
        list_companies()
    elif choice == "3":
        list_vendors_by_company()
    elif choice == "4":
        list_vendors()
    elif choice == "5":
        check_company_setup()
    else:
        print("❌ Invalid choice")