import xmlrpc.client
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

def list_customers():
    """List all customers"""
    models, db, uid, password = connect_odoo()
    if not models:
        return []
    
    try:
        customers = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('customer_rank', '>', 0)]], 
            {'fields': ['id', 'name', 'email', 'phone', 'city', 'country_id'], 'limit': 20}
        )
        
        print(f"\n👥 Customers ({len(customers)} found):")
        print("=" * 80)
        
        if not customers:
            print("   No customers found!")
            return []
        
        for customer in customers:
            email_info = f" | {customer['email']}" if customer.get('email') else ""
            phone_info = f" | {customer['phone']}" if customer.get('phone') else ""
            city_info = f" | {customer['city']}" if customer.get('city') else ""
            country_info = f" | {customer['country_id'][1]}" if customer.get('country_id') else ""
            
            print(f"   ID: {customer['id']} | {customer['name']}{email_info}{phone_info}{city_info}{country_info}")
        
        return customers
        
    except Exception as e:
        print(f"❌ Error listing customers: {e}")
        return []

def create_customer():
    """Create a new customer"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n👥 CREATE NEW CUSTOMER")
        print("=" * 25)
        
        # Required field
        name = input("Customer Name (required): ").strip()
        if not name:
            print("❌ Customer name is required!")
            return
        
        # Customer type
        print("\nCustomer Type:")
        print("1. Individual Person")
        print("2. Company")
        
        customer_type = input("Choose type (1/2): ").strip()
        is_company = customer_type == "2"
        
        # Contact details
        print(f"\n📞 Contact Information:")
        email = input("Email (optional): ").strip()
        phone = input("Phone (optional): ").strip()
        website = input("Website (optional): ").strip()
        
        # Address information
        print(f"\n🏠 Address Information:")
        street = input("Street Address (optional): ").strip()
        city = input("City (optional): ").strip()
        zip_code = input("ZIP/Postal Code (optional): ").strip()
        
        # Country
        country_code = input("Country Code (US, CY, GB, etc.) (optional): ").strip().upper()
        
        # Get country ID if provided
        country_id = None
        if country_code:
            try:
                country_ids = models.execute_kw(
                    db, uid, password,
                    'res.country', 'search',
                    [[('code', '=', country_code)]], {'limit': 1}
                )
                if country_ids:
                    country_id = country_ids[0]
                    print(f"✅ Found country: {country_code}")
                else:
                    print(f"⚠️  Country code {country_code} not found, skipping")
            except:
                print(f"⚠️  Could not validate country code")
        
        # Prepare customer data
        customer_data = {
            'name': name,
            'is_company': is_company,
            'customer_rank': 1,  # Mark as customer
            'supplier_rank': 0,  # Not a supplier
        }
        
        # Add optional fields
        if email:
            customer_data['email'] = email
        if phone:
            customer_data['phone'] = phone
        if website:
            customer_data['website'] = website
        if street:
            customer_data['street'] = street
        if city:
            customer_data['city'] = city
        if zip_code:
            customer_data['zip'] = zip_code
        if country_id:
            customer_data['country_id'] = country_id
        
        # Show summary
        print(f"\n📋 Customer Summary:")
        customer_type_name = "Company" if is_company else "Individual"
        print(f"   Name: {name}")
        print(f"   Type: {customer_type_name}")
        if email:
            print(f"   Email: {email}")
        if phone:
            print(f"   Phone: {phone}")
        if website:
            print(f"   Website: {website}")
        
        # Address summary
        address_parts = [street, city, zip_code]
        if country_code:
            address_parts.append(country_code)
        address = ", ".join([part for part in address_parts if part])
        if address:
            print(f"   Address: {address}")
        
        confirm = input("\nCreate customer? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Customer creation cancelled.")
            return
        
        # Create customer
        print("🔄 Creating customer...")
        
        customer_id = models.execute_kw(
            db, uid, password,
            'res.partner', 'create',
            [customer_data]
        )
        
        if customer_id:
            print(f"✅ Customer created successfully!")
            print(f"   Customer ID: {customer_id}")
            print(f"   Name: {name}")
        else:
            print("❌ Failed to create customer")
            
    except Exception as e:
        print(f"❌ Error creating customer: {e}")

def modify_customer():
    """Modify an existing customer"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🔧 MODIFY CUSTOMER")
        print("=" * 20)
        
        # List customers first
        customers = list_customers()
        if not customers:
            return
        
        # Get customer ID
        customer_id = input("\nEnter Customer ID to modify: ").strip()
        try:
            customer_id = int(customer_id)
        except ValueError:
            print("❌ Invalid customer ID!")
            return
        
        # Get current customer info
        current_customer = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('id', '=', customer_id), ('customer_rank', '>', 0)]], 
            {'fields': ['name', 'email', 'phone', 'website', 'street', 'city', 'zip', 'country_id', 'is_company']}
        )
        
        if not current_customer:
            print(f"❌ Customer ID {customer_id} not found!")
            return
        
        customer_info = current_customer[0]
        
        print(f"\n📋 Current Customer Info:")
        customer_type = "Company" if customer_info.get('is_company') else "Individual"
        print(f"   Name: {customer_info.get('name', 'N/A')}")
        print(f"   Type: {customer_type}")
        print(f"   Email: {customer_info.get('email', 'N/A')}")
        print(f"   Phone: {customer_info.get('phone', 'N/A')}")
        print(f"   Website: {customer_info.get('website', 'N/A')}")
        print(f"   Street: {customer_info.get('street', 'N/A')}")
        print(f"   City: {customer_info.get('city', 'N/A')}")
        print(f"   ZIP: {customer_info.get('zip', 'N/A')}")
        if customer_info.get('country_id'):
            print(f"   Country: {customer_info['country_id'][1]}")
        
        # Get updates
        print(f"\n✏️  Enter new values (press Enter to skip):")
        
        updates = {}
        
        new_name = input(f"New Name: ").strip()
        if new_name:
            updates['name'] = new_name
        
        new_email = input(f"New Email: ").strip()
        if new_email:
            updates['email'] = new_email
        
        new_phone = input(f"New Phone: ").strip()
        if new_phone:
            updates['phone'] = new_phone
        
        new_website = input(f"New Website: ").strip()
        if new_website:
            updates['website'] = new_website
        
        new_street = input(f"New Street: ").strip()
        if new_street:
            updates['street'] = new_street
        
        new_city = input(f"New City: ").strip()
        if new_city:
            updates['city'] = new_city
        
        new_zip = input(f"New ZIP: ").strip()
        if new_zip:
            updates['zip'] = new_zip
        
        new_country = input(f"New Country Code (US, CY, GB, etc.): ").strip().upper()
        if new_country:
            try:
                country_ids = models.execute_kw(
                    db, uid, password,
                    'res.country', 'search',
                    [[('code', '=', new_country)]], {'limit': 1}
                )
                if country_ids:
                    updates['country_id'] = country_ids[0]
                    print(f"✅ Country will be updated to: {new_country}")
                else:
                    print(f"⚠️  Country code {new_country} not found, skipping")
            except:
                print(f"⚠️  Could not validate country code")
        
        if not updates:
            print("⚠️  No updates provided.")
            return
        
        print(f"\n🔄 Updates to apply:")
        for key, value in updates.items():
            print(f"   {key}: {value}")
        
        confirm = input("\nProceed with update? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Update cancelled.")
            return
        
        # Update customer
        result = models.execute_kw(
            db, uid, password,
            'res.partner', 'write',
            [[customer_id], updates]
        )
        
        if result:
            print(f"✅ Customer {customer_id} updated successfully!")
        else:
            print(f"❌ Failed to update customer {customer_id}")
            
    except Exception as e:
        print(f"❌ Error modifying customer: {e}")

def delete_customer():
    """Delete a customer"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🗑️  DELETE CUSTOMER")
        print("=" * 20)
        
        # List customers first
        customers = list_customers()
        if not customers:
            return
        
        # Get customer ID
        customer_id = input("\nEnter Customer ID to delete: ").strip()
        try:
            customer_id = int(customer_id)
        except ValueError:
            print("❌ Invalid customer ID!")
            return
        
        # Get customer info
        customer_info = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('id', '=', customer_id), ('customer_rank', '>', 0)]], 
            {'fields': ['name', 'email', 'phone', 'is_company']}
        )
        
        if not customer_info:
            print(f"❌ Customer ID {customer_id} not found!")
            return
        
        customer_data = customer_info[0]
        customer_type = "Company" if customer_data.get('is_company') else "Individual"
        
        print(f"\n📋 Customer to Delete:")
        print(f"   ID: {customer_id}")
        print(f"   Name: {customer_data.get('name', 'N/A')}")
        print(f"   Type: {customer_type}")
        print(f"   Email: {customer_data.get('email', 'N/A')}")
        print(f"   Phone: {customer_data.get('phone', 'N/A')}")
        
        # Check for related records
        print(f"\n🔍 Checking for related records...")
        
        # Check for invoices
        try:
            invoice_count = models.execute_kw(
                db, uid, password,
                'account.move', 'search_count',
                [[('partner_id', '=', customer_id), ('move_type', '=', 'out_invoice')]]
            )
            
            print(f"   📄 Customer Invoices: {invoice_count}")
            
            if invoice_count > 0:
                print(f"   ⚠️  Customer has {invoice_count} invoice(s)")
                print("   ⚠️  Deleting will affect sales records")
        except:
            print("   📄 Could not check invoices")
        
        # Check for payments
        try:
            payment_count = models.execute_kw(
                db, uid, password,
                'account.payment', 'search_count',
                [[('partner_id', '=', customer_id)]]
            )
            
            print(f"   💰 Payments: {payment_count}")
            
            if payment_count > 0:
                print(f"   ⚠️  Customer has {payment_count} payment(s)")
        except:
            print("   💰 Could not check payments")
        
        # Deletion warnings
        print(f"\n🗑️  DELETION WARNINGS:")
        print("   ⚠️  This action CANNOT be undone!")
        print("   ⚠️  All customer data will be permanently removed")
        print("   ⚠️  Related transactions may be affected")
        print("   ⚠️  Consider archiving instead of deleting")
        
        # Confirmations
        confirm1 = input(f"\nDelete customer '{customer_data.get('name')}'? (yes/no): ").lower().strip()
        if confirm1 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        confirm2 = input("Are you absolutely sure? (yes/no): ").lower().strip()
        if confirm2 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        # Final confirmation for customers with transactions
        try:
            total_transactions = invoice_count + payment_count
            if total_transactions > 0:
                confirm3 = input(f"Customer has {total_transactions} transactions. Type 'DELETE CUSTOMER' to proceed: ").strip()
                if confirm3 != 'DELETE CUSTOMER':
                    print("❌ Final confirmation failed. Deletion cancelled.")
                    return
        except:
            pass
        
        # Delete customer
        print(f"🔄 Deleting customer {customer_id}...")
        
        try:
            result = models.execute_kw(
                db, uid, password,
                'res.partner', 'unlink',
                [[customer_id]]
            )
            
            if result:
                print(f"✅ Customer {customer_id} deleted successfully!")
            else:
                print(f"❌ Failed to delete customer {customer_id}")
                
        except Exception as delete_error:
            error_msg = str(delete_error)
            print(f"❌ Deletion failed: {error_msg}")
            
            if "constraint" in error_msg.lower() or "foreign key" in error_msg.lower():
                print(f"\n💡 This error usually means:")
                print("   - Customer has related records (invoices, payments, orders)")
                print("   - These must be removed first")
                print("   - Consider archiving the customer instead")
                
                # Offer archiving option
                archive_option = input("\nTry archiving customer instead? (y/n): ").lower().strip()
                if archive_option == 'y':
                    try:
                        archive_result = models.execute_kw(
                            db, uid, password,
                            'res.partner', 'write',
                            [[customer_id], {'active': False}]
                        )
                        
                        if archive_result:
                            print(f"✅ Customer {customer_id} archived successfully!")
                            print("   Customer is now hidden but data is preserved.")
                        else:
                            print(f"❌ Archiving also failed")
                    except Exception as archive_error:
                        print(f"❌ Archiving failed: {archive_error}")
                        
    except Exception as e:
        print(f"❌ Error deleting customer: {e}")

def archive_customer():
    """Archive a customer (safer than deletion)"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n📦 ARCHIVE CUSTOMER")
        print("=" * 20)
        
        customers = list_customers()
        if not customers:
            return
        
        customer_id = input("\nEnter Customer ID to archive: ").strip()
        try:
            customer_id = int(customer_id)
        except ValueError:
            print("❌ Invalid customer ID!")
            return
        
        # Get customer name
        customer_info = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('id', '=', customer_id)]], 
            {'fields': ['name']}
        )
        
        if not customer_info:
            print(f"❌ Customer not found!")
            return
        
        customer_name = customer_info[0]['name']
        
        print(f"\n📋 Archiving will:")
        print("   ✅ Hide the customer from normal views")
        print("   ✅ Preserve all historical data")
        print("   ✅ Keep all related transactions intact")
        print("   ✅ Allow unarchiving later if needed")
        
        confirm = input(f"\nArchive customer '{customer_name}'? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Archiving cancelled.")
            return
        
        result = models.execute_kw(
            db, uid, password,
            'res.partner', 'write',
            [[customer_id], {'active': False}]
        )
        
        if result:
            print(f"✅ Customer '{customer_name}' archived successfully!")
            print("   Customer is now hidden but can be unarchived if needed.")
        else:
            print(f"❌ Failed to archive customer")
            
    except Exception as e:
        print(f"❌ Error archiving customer: {e}")

def main():
    """Main menu"""
    while True:
        print("\n" + "="*40)
        print("👥 CUSTOMER MANAGEMENT SYSTEM")
        print("="*40)
        print("1. List all customers")
        print("2. Create new customer")
        print("3. Modify customer")
        print("4. Delete customer")
        print("5. Archive customer (safer)")
        print("6. Exit")
        
        choice = input("\nEnter choice (1-6): ").strip()
        
        if choice == "1":
            list_customers()
        elif choice == "2":
            create_customer()
        elif choice == "3":
            modify_customer()
        elif choice == "4":
            delete_customer()
        elif choice == "5":
            archive_customer()
        elif choice == "6":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice!")

if __name__ == "__main__":
    main()