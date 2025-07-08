import xmlrpc.client
import os
from dotenv import load_dotenv

load_dotenv()

def modify_vendor_bill():
    """Simple script to modify a vendor bill in Odoo"""
    
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
            {'fields': ['id', 'name', 'partner_id', 'amount_total', 'state', 'ref'], 'limit': 10}
        )
        
        if not bills:
            print("❌ No vendor bills found!")
            return
        
        for bill in bills:
            partner_name = bill['partner_id'][1] if bill.get('partner_id') else 'N/A'
            ref_info = f" | Ref: {bill['ref']}" if bill.get('ref') else ""
            print(f"   ID: {bill['id']} | {bill['name']} | {partner_name} | ${bill['amount_total']} | {bill['state']}{ref_info}")
        
        # Step 2: Get bill ID from user
        bill_id = input(f"\nEnter Vendor Bill ID to modify: ")
        try:
            bill_id = int(bill_id)
        except ValueError:
            print("❌ Invalid bill ID. Please enter a number.")
            return
        
        # Step 3: Check if bill exists and get current info
        current_bill = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', bill_id), ('move_type', '=', 'in_invoice')]], 
            {'fields': ['name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state']}
        )
        
        if not current_bill:
            print(f"❌ Vendor bill with ID {bill_id} not found!")
            return
        
        bill_info = current_bill[0]
        
        print(f"\n📋 Current Bill Information:")
        print(f"   Bill Number: {bill_info.get('name', 'N/A')}")
        print(f"   Vendor: {bill_info['partner_id'][1] if bill_info.get('partner_id') else 'N/A'}")
        print(f"   Date: {bill_info.get('invoice_date', 'N/A')}")
        print(f"   Reference: {bill_info.get('ref', 'N/A')}")
        print(f"   Total: ${bill_info.get('amount_total', 0)}")
        print(f"   Status: {bill_info.get('state', 'N/A')}")
        
        # Step 4: Check if bill can be modified
        if bill_info.get('state') in ['posted', 'cancel']:
            print(f"\n⚠️  WARNING: This bill is {bill_info.get('state')}!")
            print("   Posted/cancelled bills have limited modification options.")
            print("   You may need to create a credit note or reset to draft first.")
            
            continue_anyway = input("\nContinue anyway? (y/n): ").lower().strip()
            if continue_anyway != 'y':
                print("❌ Modification cancelled.")
                return
        
        # Step 5: Get line items
        line_items = models.execute_kw(
            db, uid, password,
            'account.move.line', 'search_read',
            [[('move_id', '=', bill_id), ('display_type', '=', False)]], 
            {'fields': ['id', 'name', 'quantity', 'price_unit', 'price_total']}
        )
        
        print(f"\n📝 Current Line Items:")
        for i, line in enumerate(line_items, 1):
            print(f"   {i}. {line['name']} | Qty: {line['quantity']} | Unit: ${line['price_unit']} | Total: ${line['price_total']}")
        
        # Step 6: Modification options
        print(f"\n🔧 What would you like to modify?")
        print("   1. Vendor reference")
        print("   2. Invoice date")
        print("   3. Line item description")
        print("   4. Line item amount")
        print("   5. Add new line item")
        print("   6. Show summary and exit")
        
        choice = input("\nChoose option (1-6): ").strip()
        
        if choice == "1":
            # Modify vendor reference
            new_ref = input(f"New reference (current: {bill_info.get('ref', 'N/A')}): ").strip()
            if new_ref:
                try:
                    result = models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[bill_id], {'ref': new_ref}]
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
            # Modify invoice date
            new_date = input(f"New date YYYY-MM-DD (current: {bill_info.get('invoice_date', 'N/A')}): ").strip()
            if new_date:
                try:
                    result = models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[bill_id], {'invoice_date': new_date}]
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
            # Modify line item description
            if not line_items:
                print("❌ No line items found")
                return
            
            line_num = input(f"Which line to modify (1-{len(line_items)}): ").strip()
            try:
                line_index = int(line_num) - 1
                if 0 <= line_index < len(line_items):
                    line_id = line_items[line_index]['id']
                    current_desc = line_items[line_index]['name']
                    
                    new_desc = input(f"New description (current: {current_desc}): ").strip()
                    if new_desc:
                        try:
                            result = models.execute_kw(
                                db, uid, password,
                                'account.move.line', 'write',
                                [[line_id], {'name': new_desc}]
                            )
                            if result:
                                print(f"✅ Description updated to: {new_desc}")
                            else:
                                print("❌ Failed to update description")
                        except Exception as e:
                            print(f"❌ Error updating description: {e}")
                    else:
                        print("❌ No description provided")
                else:
                    print("❌ Invalid line number")
            except ValueError:
                print("❌ Invalid line number")
        
        elif choice == "4":
            # Modify line item amount
            if not line_items:
                print("❌ No line items found")
                return
            
            line_num = input(f"Which line to modify (1-{len(line_items)}): ").strip()
            try:
                line_index = int(line_num) - 1
                if 0 <= line_index < len(line_items):
                    line_id = line_items[line_index]['id']
                    current_amount = line_items[line_index]['price_unit']
                    
                    new_amount = input(f"New unit price (current: ${current_amount}): ").strip()
                    if new_amount:
                        try:
                            new_amount = float(new_amount)
                            result = models.execute_kw(
                                db, uid, password,
                                'account.move.line', 'write',
                                [[line_id], {'price_unit': new_amount}]
                            )
                            if result:
                                print(f"✅ Amount updated to: ${new_amount}")
                            else:
                                print("❌ Failed to update amount")
                        except ValueError:
                            print("❌ Invalid amount format")
                        except Exception as e:
                            print(f"❌ Error updating amount: {e}")
                    else:
                        print("❌ No amount provided")
                else:
                    print("❌ Invalid line number")
            except ValueError:
                print("❌ Invalid line number")
        
        elif choice == "5":
            # Add new line item
            print(f"\n➕ Adding New Line Item:")
            
            description = input("Description: ").strip()
            if not description:
                print("❌ Description required")
                return
            
            amount = input("Amount: ").strip()
            try:
                amount = float(amount)
            except ValueError:
                print("❌ Invalid amount")
                return
            
            try:
                # Add new line to the bill
                new_line = {
                    'move_id': bill_id,
                    'name': description,
                    'quantity': 1.0,
                    'price_unit': amount,
                }
                
                line_id = models.execute_kw(
                    db, uid, password,
                    'account.move.line', 'create',
                    [new_line]
                )
                
                if line_id:
                    print(f"✅ New line item added: {description} - ${amount}")
                else:
                    print("❌ Failed to add line item")
                    
            except Exception as e:
                print(f"❌ Error adding line item: {e}")
        
        elif choice == "6":
            # Show updated summary
            updated_bill = models.execute_kw(
                db, uid, password,
                'account.move', 'read',
                [[bill_id]], 
                {'fields': ['name', 'partner_id', 'invoice_date', 'ref', 'amount_total', 'state']}
            )[0]
            
            print(f"\n📋 Updated Bill Information:")
            print(f"   Bill Number: {updated_bill.get('name', 'N/A')}")
            print(f"   Vendor: {updated_bill['partner_id'][1] if updated_bill.get('partner_id') else 'N/A'}")
            print(f"   Date: {updated_bill.get('invoice_date', 'N/A')}")
            print(f"   Reference: {updated_bill.get('ref', 'N/A')}")
            print(f"   Total: ${updated_bill.get('amount_total', 0)}")
            print(f"   Status: {updated_bill.get('state', 'N/A')}")
            
        else:
            print("❌ Invalid choice")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def list_vendor_bills():
    """Helper function to list all vendor bills"""
    
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
            {'fields': ['id', 'name', 'partner_id', 'amount_total', 'state', 'ref', 'invoice_date']}
        )
        
        print(f"\n📄 All Vendor Bills ({len(bills)} found):")
        print("=" * 80)
        
        for bill in bills:
            partner_name = bill['partner_id'][1] if bill.get('partner_id') else 'N/A'
            ref_info = f" | Ref: {bill['ref']}" if bill.get('ref') else ""
            date_info = f" | Date: {bill['invoice_date']}" if bill.get('invoice_date') else ""
            
            print(f"ID: {bill['id']} | {bill['name']} | {partner_name} | ${bill['amount_total']} | {bill['state']}{ref_info}{date_info}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🔧 Vendor Bill Modification Tool")
    print("=" * 35)
    
    print("\nWhat would you like to do?")
    print("1. Modify a vendor bill")
    print("2. List all vendor bills")
    
    choice = input("\nChoice (1/2): ").strip()
    
    if choice == "1":
        modify_vendor_bill()
    elif choice == "2":
        list_vendor_bills()
    else:
        print("❌ Invalid choice")