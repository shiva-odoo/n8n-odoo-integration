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

def list_customer_invoices():
    """List existing customer invoices"""
    models, db, uid, password = connect_odoo()
    if not models:
        return []
    
    try:
        invoices = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('move_type', '=', 'out_invoice')]], 
            {'fields': ['id', 'name', 'partner_id', 'amount_total', 'state', 'invoice_date'], 'limit': 15}
        )
        
        print(f"\n📋 Customer Invoices ({len(invoices)} found):")
        print("=" * 90)
        
        if not invoices:
            print("   No customer invoices found!")
            return []
        
        for invoice in invoices:
            partner_name = invoice['partner_id'][1] if invoice.get('partner_id') else 'N/A'
            date_info = f" | {invoice['invoice_date']}" if invoice.get('invoice_date') else ""
            
            print(f"   ID: {invoice['id']} | {invoice['name']} | {partner_name} | ${invoice['amount_total']} | {invoice['state']}{date_info}")
        
        return invoices
        
    except Exception as e:
        print(f"❌ Error listing customer invoices: {e}")
        return []

def list_customers():
    """List customers for invoice selection"""
    models, db, uid, password = connect_odoo()
    if not models:
        return []
    
    try:
        customers = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('customer_rank', '>', 0)]], 
            {'fields': ['id', 'name', 'email'], 'limit': 15}
        )
        return customers
    except Exception as e:
        print(f"❌ Error listing customers: {e}")
        return []

def create_customer_invoice():
    """Create a new customer invoice"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n📋 CREATE CUSTOMER INVOICE")
        print("=" * 28)
        
        # Step 1: Select customer
        print("👥 Available Customers:")
        customers = list_customers()
        
        if not customers:
            print("❌ No customers found!")
            return
        
        # Show customers
        for customer in customers:
            email_info = f" - {customer['email']}" if customer.get('email') else ""
            print(f"   {customer['id']}: {customer['name']}{email_info}")
        
        # Get customer selection
        customer_choice = input("\nEnter Customer ID or 'new' for new customer: ").strip()
        
        if customer_choice.lower() == 'new':
            customer_name = input("Enter customer name: ").strip()
            if not customer_name:
                print("❌ Customer name required!")
                return
            
            customer_email = input("Enter customer email (optional): ").strip()
            
            # Create new customer
            customer_data = {
                'name': customer_name,
                'is_company': True,
                'customer_rank': 1,
                'supplier_rank': 0,
            }
            
            if customer_email:
                customer_data['email'] = customer_email
            
            customer_id = models.execute_kw(
                db, uid, password,
                'res.partner', 'create',
                [customer_data]
            )
            
            print(f"✅ Created new customer: {customer_name} (ID: {customer_id})")
            
        else:
            try:
                customer_id = int(customer_choice)
                customer_name = next(c['name'] for c in customers if c['id'] == customer_id)
                print(f"✅ Selected customer: {customer_name}")
            except (ValueError, StopIteration):
                print("❌ Invalid customer ID!")
                return
        
        # Step 2: Invoice details
        print(f"\n📄 Invoice Details:")
        
        invoice_date = input("Invoice date (YYYY-MM-DD) or Enter for today: ").strip()
        if not invoice_date:
            invoice_date = datetime.now().strftime('%Y-%m-%d')
        
        due_date = input("Due date (YYYY-MM-DD) or Enter to skip: ").strip()
        reference = input("Customer reference (optional): ").strip()
        
        # Step 3: Invoice line items
        print(f"\n💰 Invoice Line Items:")
        
        line_items = []
        line_number = 1
        
        while True:
            print(f"\nLine Item {line_number}:")
            
            description = input("  Description: ").strip()
            if not description:
                if line_number == 1:
                    print("❌ At least one line item is required!")
                    continue
                else:
                    break
            
            quantity = input("  Quantity (default: 1): ").strip()
            try:
                quantity = float(quantity) if quantity else 1.0
            except ValueError:
                print("⚠️  Invalid quantity, using 1")
                quantity = 1.0
            
            unit_price = input("  Unit price: ").strip()
            try:
                unit_price = float(unit_price)
            except ValueError:
                print("❌ Invalid unit price!")
                continue
            
            # Calculate line total
            line_total = quantity * unit_price
            
            line_item = {
                'name': description,
                'quantity': quantity,
                'price_unit': unit_price,
            }
            
            line_items.append((0, 0, line_item))
            
            print(f"✅ Added: {description} | Qty: {quantity} | Unit: ${unit_price} | Total: ${line_total}")
            
            line_number += 1
            
            # Ask for more lines
            more_lines = input("\nAdd another line? (y/n): ").lower().strip()
            if more_lines != 'y':
                break
        
        # Step 4: Create the invoice
        print(f"\n📋 Invoice Summary:")
        total_amount = sum(line[2]['quantity'] * line[2]['price_unit'] for line in line_items)
        
        print(f"   Customer: {customer_name}")
        print(f"   Invoice Date: {invoice_date}")
        if due_date:
            print(f"   Due Date: {due_date}")
        if reference:
            print(f"   Reference: {reference}")
        print(f"   Total Lines: {len(line_items)}")
        print(f"   Total Amount: ${total_amount:.2f}")
        
        confirm = input("\nCreate customer invoice? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Invoice creation cancelled.")
            return
        
        # Prepare invoice data
        invoice_data = {
            'move_type': 'out_invoice',  # Customer invoice
            'partner_id': customer_id,
            'invoice_date': invoice_date,
            'invoice_line_ids': line_items,
        }
        
        if due_date:
            invoice_data['invoice_date_due'] = due_date
        
        # Try to add reference if field exists
        if reference:
            try:
                invoice_data['ref'] = reference
            except:
                print("⚠️  Reference field not available, skipping")
        
        print(f"🔄 Creating customer invoice...")
        
        invoice_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [invoice_data]
        )
        
        if invoice_id:
            print(f"✅ Customer invoice created successfully!")
            print(f"   Invoice ID: {invoice_id}")
            
            # Get created invoice info
            try:
                invoice_info = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[invoice_id]], 
                    {'fields': ['name', 'amount_total', 'state']}
                )[0]
                
                print(f"   Invoice Number: {invoice_info.get('name', 'N/A')}")
                print(f"   Total Amount: ${invoice_info.get('amount_total', 0):.2f}")
                print(f"   Status: {invoice_info.get('state', 'draft')}")
                
            except Exception as e:
                print(f"   (Could not fetch invoice details: {e})")
                
        else:
            print(f"❌ Failed to create customer invoice")
            
    except Exception as e:
        print(f"❌ Error creating customer invoice: {e}")

def modify_customer_invoice():
    """Modify an existing customer invoice"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🔧 MODIFY CUSTOMER INVOICE")
        print("=" * 28)
        
        # List invoices first
        invoices = list_customer_invoices()
        if not invoices:
            return
        
        # Get invoice ID
        invoice_id = input("\nEnter Customer Invoice ID to modify: ").strip()
        try:
            invoice_id = int(invoice_id)
        except ValueError:
            print("❌ Invalid invoice ID!")
            return
        
        # Get current invoice info (handle potential missing fields)
        try:
            current_invoice = models.execute_kw(
                db, uid, password,
                'account.move', 'search_read',
                [[('id', '=', invoice_id), ('move_type', '=', 'out_invoice')]], 
                {'fields': ['name', 'partner_id', 'invoice_date', 'invoice_date_due', 'ref', 'amount_total', 'state']}
            )
            has_ref_field = True
        except:
            current_invoice = models.execute_kw(
                db, uid, password,
                'account.move', 'search_read',
                [[('id', '=', invoice_id), ('move_type', '=', 'out_invoice')]], 
                {'fields': ['name', 'partner_id', 'invoice_date', 'invoice_date_due', 'amount_total', 'state']}
            )
            has_ref_field = False
        
        if not current_invoice:
            print(f"❌ Customer Invoice ID {invoice_id} not found!")
            return
        
        invoice_info = current_invoice[0]
        
        print(f"\n📋 Current Invoice Info:")
        print(f"   Invoice Number: {invoice_info.get('name', 'N/A')}")
        print(f"   Customer: {invoice_info['partner_id'][1] if invoice_info.get('partner_id') else 'N/A'}")
        print(f"   Invoice Date: {invoice_info.get('invoice_date', 'N/A')}")
        print(f"   Due Date: {invoice_info.get('invoice_date_due', 'N/A')}")
        if has_ref_field:
            print(f"   Reference: {invoice_info.get('ref', 'N/A')}")
        else:
            print(f"   Reference: N/A (field not available)")
        print(f"   Amount: ${invoice_info.get('amount_total', 0)}")
        print(f"   Status: {invoice_info.get('state', 'N/A')}")
        
        # Check if invoice can be modified
        if invoice_info.get('state') in ['posted', 'paid']:
            print(f"\n⚠️  WARNING: This invoice is {invoice_info.get('state')}!")
            print("   Posted/paid invoices have limited modification options.")
            
            continue_anyway = input("\nContinue anyway? (y/n): ").lower().strip()
            if continue_anyway != 'y':
                print("❌ Modification cancelled.")
                return
        
        # Modification options
        print(f"\n🔧 What would you like to modify?")
        print("   1. Invoice date")
        print("   2. Due date")
        if has_ref_field:
            print("   3. Customer reference")
            print("   4. Show updated summary")
        else:
            print("   3. Show updated summary")
        
        choice = input("\nChoose option: ").strip()
        
        if choice == "1":
            # Modify invoice date
            new_date = input(f"New invoice date YYYY-MM-DD (current: {invoice_info.get('invoice_date', 'N/A')}): ").strip()
            if new_date:
                try:
                    result = models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[invoice_id], {'invoice_date': new_date}]
                    )
                    if result:
                        print(f"✅ Invoice date updated to: {new_date}")
                    else:
                        print("❌ Failed to update invoice date")
                except Exception as e:
                    print(f"❌ Error updating invoice date: {e}")
            else:
                print("❌ No date provided")
        
        elif choice == "2":
            # Modify due date
            new_due_date = input(f"New due date YYYY-MM-DD (current: {invoice_info.get('invoice_date_due', 'N/A')}): ").strip()
            if new_due_date:
                try:
                    result = models.execute_kw(
                        db, uid, password,
                        'account.move', 'write',
                        [[invoice_id], {'invoice_date_due': new_due_date}]
                    )
                    if result:
                        print(f"✅ Due date updated to: {new_due_date}")
                    else:
                        print("❌ Failed to update due date")
                except Exception as e:
                    print(f"❌ Error updating due date: {e}")
            else:
                print("❌ No date provided")
        
        elif choice == "3":
            if has_ref_field:
                # Modify reference
                new_ref = input(f"New reference (current: {invoice_info.get('ref', 'N/A')}): ").strip()
                if new_ref:
                    try:
                        result = models.execute_kw(
                            db, uid, password,
                            'account.move', 'write',
                            [[invoice_id], {'ref': new_ref}]
                        )
                        if result:
                            print(f"✅ Reference updated to: {new_ref}")
                        else:
                            print("❌ Failed to update reference")
                    except Exception as e:
                        print(f"❌ Error updating reference: {e}")
                else:
                    print("❌ No reference provided")
            else:
                # Show updated summary (when ref field not available)
                choice = "4"
        
        if choice == "4" or (choice == "3" and not has_ref_field):
            # Show updated summary
            try:
                updated_invoice = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[invoice_id]], 
                    {'fields': ['name', 'partner_id', 'invoice_date', 'invoice_date_due', 'ref', 'amount_total', 'state']}
                )[0]
                updated_has_ref = True
            except:
                updated_invoice = models.execute_kw(
                    db, uid, password,
                    'account.move', 'read',
                    [[invoice_id]], 
                    {'fields': ['name', 'partner_id', 'invoice_date', 'invoice_date_due', 'amount_total', 'state']}
                )[0]
                updated_has_ref = False
            
            print(f"\n📋 Updated Invoice Info:")
            print(f"   Invoice Number: {updated_invoice.get('name', 'N/A')}")
            print(f"   Customer: {updated_invoice['partner_id'][1] if updated_invoice.get('partner_id') else 'N/A'}")
            print(f"   Invoice Date: {updated_invoice.get('invoice_date', 'N/A')}")
            print(f"   Due Date: {updated_invoice.get('invoice_date_due', 'N/A')}")
            if updated_has_ref:
                print(f"   Reference: {updated_invoice.get('ref', 'N/A')}")
            else:
                print(f"   Reference: N/A (field not available)")
            print(f"   Amount: ${updated_invoice.get('amount_total', 0)}")
            print(f"   Status: {updated_invoice.get('state', 'N/A')}")
        
        if choice not in ["1", "2", "3", "4"]:
            print("❌ Invalid choice")
            
    except Exception as e:
        print(f"❌ Error modifying customer invoice: {e}")

def delete_customer_invoice():
    """Delete a customer invoice"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🗑️  DELETE CUSTOMER INVOICE")
        print("=" * 28)
        
        # List invoices first
        invoices = list_customer_invoices()
        if not invoices:
            return
        
        # Get invoice ID
        invoice_id = input("\nEnter Customer Invoice ID to delete: ").strip()
        try:
            invoice_id = int(invoice_id)
        except ValueError:
            print("❌ Invalid invoice ID!")
            return
        
        # Get invoice info
        invoice_info = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', invoice_id), ('move_type', '=', 'out_invoice')]], 
            {'fields': ['name', 'partner_id', 'amount_total', 'state', 'payment_state']}
        )
        
        if not invoice_info:
            print(f"❌ Customer Invoice ID {invoice_id} not found!")
            return
        
        invoice_data = invoice_info[0]
        
        print(f"\n📋 Invoice to Delete:")
        print(f"   ID: {invoice_id}")
        print(f"   Invoice Number: {invoice_data.get('name', 'N/A')}")
        print(f"   Customer: {invoice_data['partner_id'][1] if invoice_data.get('partner_id') else 'N/A'}")
        print(f"   Amount: ${invoice_data.get('amount_total', 0)}")
        print(f"   Status: {invoice_data.get('state', 'N/A')}")
        
        # Check payment status if available
        payment_state = invoice_data.get('payment_state', 'not_paid')
        if payment_state != 'not_paid':
            print(f"   Payment Status: {payment_state}")
        
        # Check invoice status
        invoice_status = invoice_data.get('state', 'draft')
        
        if invoice_status == 'posted':
            print(f"\n⚠️  WARNING: This invoice is POSTED!")
            print("   - Deleting posted invoices affects your accounting records")
            print("   - This may impact financial reports and audit trails")
            
            if payment_state in ['paid', 'in_payment', 'partial']:
                print(f"\n🚨 CRITICAL: This invoice has payments!")
                print(f"   Payment Status: {payment_state}")
                print("   - Deleting this invoice may cause payment reconciliation issues")
                print("   - Consider cancelling the invoice instead of deleting")
                
        elif invoice_status == 'cancel':
            print(f"\n✅ This invoice is cancelled - safe to delete.")
            
        elif invoice_status == 'draft':
            print(f"\n✅ This invoice is in draft - safe to delete.")
        
        # Deletion warnings
        print(f"\n🗑️  DELETION WARNINGS:")
        print("   ⚠️  This action CANNOT be undone!")
        print("   ⚠️  All invoice line items will be deleted")
        if invoice_status == 'posted':
            print("   ⚠️  Financial reports may be affected")
            if payment_state != 'not_paid':
                print("   ⚠️  Payment reconciliation may be broken")
        
        # Confirmations
        confirm1 = input(f"\nDelete invoice {invoice_data.get('name')}? (yes/no): ").lower().strip()
        if confirm1 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        customer_name = invoice_data['partner_id'][1] if invoice_data.get('partner_id') else 'Unknown'
        confirm2 = input(f"Confirm deletion of ${invoice_data.get('amount_total', 0)} invoice for {customer_name}? (yes/no): ").lower().strip()
        if confirm2 != 'yes':
            print("❌ Deletion cancelled.")
            return
        
        # Extra confirmation for posted invoices with payments
        if invoice_status == 'posted' and payment_state != 'not_paid':
            confirm3 = input(f"Final warning - invoice is posted with payments. Type 'DELETE INVOICE' to proceed: ").strip()
            if confirm3 != 'DELETE INVOICE':
                print("❌ Final confirmation failed. Deletion cancelled.")
                return
        
        # Delete invoice
        print(f"🔄 Deleting customer invoice {invoice_id}...")
        
        try:
            result = models.execute_kw(
                db, uid, password,
                'account.move', 'unlink',
                [[invoice_id]]
            )
            
            if result:
                print(f"✅ Customer invoice {invoice_id} deleted successfully!")
            else:
                print(f"❌ Failed to delete customer invoice {invoice_id}")
                
        except Exception as delete_error:
            error_msg = str(delete_error)
            print(f"❌ Deletion failed: {error_msg}")
            
            if "posted" in error_msg.lower() or "state" in error_msg.lower():
                print(f"\n💡 This error usually means:")
                print("   - Posted invoices cannot be deleted directly")
                print("   - Try resetting to draft first, then delete")
                
                # Offer to reset to draft
                reset_option = input("\nTry resetting to draft first? (y/n): ").lower().strip()
                if reset_option == 'y':
                    try:
                        print("🔄 Resetting invoice to draft...")
                        reset_result = models.execute_kw(
                            db, uid, password,
                            'account.move', 'button_draft',
                            [[invoice_id]]
                        )
                        
                        if reset_result:
                            print("✅ Invoice reset to draft. Attempting deletion...")
                            
                            delete_result = models.execute_kw(
                                db, uid, password,
                                'account.move', 'unlink',
                                [[invoice_id]]
                            )
                            
                            if delete_result:
                                print(f"✅ Customer invoice {invoice_id} deleted successfully after reset!")
                            else:
                                print(f"❌ Still failed to delete after reset")
                        else:
                            print("❌ Failed to reset invoice to draft")
                            
                    except Exception as reset_error:
                        print(f"❌ Reset failed: {reset_error}")
                        
    except Exception as e:
        print(f"❌ Error deleting customer invoice: {e}")

def main():
    """Main menu"""
    while True:
        print("\n" + "="*45)
        print("📋 CUSTOMER INVOICE MANAGEMENT SYSTEM")
        print("="*45)
        print("1. List all customer invoices")
        print("2. Create new customer invoice")
        print("3. Modify customer invoice")
        print("4. Delete customer invoice")
        print("5. Exit")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            list_customer_invoices()
        elif choice == "2":
            create_customer_invoice()
        elif choice == "3":
            modify_customer_invoice()
        elif choice == "4":
            delete_customer_invoice()
        elif choice == "5":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice!")

if __name__ == "__main__":
    main()