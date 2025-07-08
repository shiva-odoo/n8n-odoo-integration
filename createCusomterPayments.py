import xmlrpc.client
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

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

def list_payments():
    """List existing payments"""
    models, db, uid, password = connect_odoo()
    if not models:
        return []
    
    try:
        payments = models.execute_kw(
            db, uid, password,
            'account.payment', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'partner_id', 'amount', 'payment_type', 'state', 'date'], 'limit': 15}
        )
        
        print(f"\n💰 Payments ({len(payments)} found):")
        print("=" * 80)
        
        if not payments:
            print("   No payments found!")
            return []
        
        for payment in payments:
            partner_name = payment['partner_id'][1] if payment.get('partner_id') else 'N/A'
            payment_type = "Received" if payment['payment_type'] == 'inbound' else "Sent"
            date_info = f" | {payment['date']}" if payment.get('date') else ""
            
            print(f"   ID: {payment['id']} | {payment['name']} | {payment_type} | {partner_name} | ${payment['amount']} | {payment['state']}{date_info}")
        
        return payments
        
    except Exception as e:
        print(f"❌ Error listing payments: {e}")
        return []

def create_payment():
    """Create a new payment"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n💰 CREATE PAYMENT")
        print("=" * 18)
        
        # Payment type
        print("Payment Type:")
        print("1. Money Received (from customer)")
        print("2. Money Sent (to vendor)")
        
        choice = input("Choose (1/2): ").strip()
        
        if choice == "1":
            payment_type = 'inbound'
            # Get customers
            partners = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_read',
                [[('customer_rank', '>', 0)]], 
                {'fields': ['id', 'name'], 'limit': 10}
            )
            print(f"\n👥 Customers:")
        elif choice == "2":
            payment_type = 'outbound'
            # Get vendors
            partners = models.execute_kw(
                db, uid, password,
                'res.partner', 'search_read',
                [[('supplier_rank', '>', 0)]], 
                {'fields': ['id', 'name'], 'limit': 10}
            )
            print(f"\n👥 Vendors:")
        else:
            print("❌ Invalid choice!")
            return
        
        if not partners:
            print("   No partners found!")
            return
        
        # Show partners
        for partner in partners:
            print(f"   {partner['id']}: {partner['name']}")
        
        # Get partner
        partner_id = input("Enter Partner ID: ").strip()
        try:
            partner_id = int(partner_id)
            partner_name = next(p['name'] for p in partners if p['id'] == partner_id)
            print(f"✅ Selected: {partner_name}")
        except (ValueError, StopIteration):
            print("❌ Invalid partner ID!")
            return
        
        # Payment details
        amount = input("Amount: ").strip()
        try:
            amount = float(amount)
            if amount <= 0:
                print("❌ Amount must be positive!")
                return
        except ValueError:
            print("❌ Invalid amount!")
            return
        
        payment_date = input("Date (YYYY-MM-DD) or Enter for today: ").strip()
        if not payment_date:
            payment_date = datetime.now().strftime('%Y-%m-%d')
        
        # Summary
        payment_type_name = "Received" if payment_type == 'inbound' else "Sent"
        print(f"\n📋 Summary:")
        print(f"   Type: {payment_type_name}")
        print(f"   Partner: {partner_name}")
        print(f"   Amount: ${amount}")
        print(f"   Date: {payment_date}")
        
        confirm = input("\nCreate payment? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Cancelled.")
            return
        
        # Create payment
        payment_data = {
            'payment_type': payment_type,
            'partner_id': partner_id,
            'amount': amount,
            'date': payment_date,
        }
        
        print("🔄 Creating payment...")
        
        payment_id = models.execute_kw(
            db, uid, password,
            'account.payment', 'create',
            [payment_data]
        )
        
        if payment_id:
            print(f"✅ Payment created successfully!")
            print(f"   Payment ID: {payment_id}")
        else:
            print("❌ Failed to create payment")
            
    except Exception as e:
        print(f"❌ Error creating payment: {e}")

def modify_payment():
    """Modify a payment"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🔧 MODIFY PAYMENT")
        print("=" * 17)
        
        list_payments()
        
        payment_id = input("\nEnter Payment ID to modify: ").strip()
        try:
            payment_id = int(payment_id)
        except ValueError:
            print("❌ Invalid payment ID!")
            return
        
        # Get current info
        current = models.execute_kw(
            db, uid, password,
            'account.payment', 'search_read',
            [[('id', '=', payment_id)]], 
            {'fields': ['name', 'partner_id', 'amount', 'date', 'state', 'payment_type']}
        )
        
        if not current:
            print("❌ Payment not found!")
            return
        
        info = current[0]
        payment_type_name = "Received" if info['payment_type'] == 'inbound' else "Sent"
        
        print(f"\n📋 Current Payment:")
        print(f"   Name: {info['name']}")
        print(f"   Type: {payment_type_name}")
        print(f"   Partner: {info['partner_id'][1] if info.get('partner_id') else 'N/A'}")
        print(f"   Amount: ${info['amount']}")
        print(f"   Date: {info['date']}")
        print(f"   Status: {info['state']}")
        
        if info.get('state') in ['posted', 'reconciled']:
            print(f"\n⚠️  Warning: Payment is {info['state']}")
            print("   Modifications may be limited.")
        
        # Modification options
        print(f"\n🔧 What to modify?")
        print("   1. Amount")
        print("   2. Date")
        print("   3. Show updated info")
        
        choice = input("Choice (1-3): ").strip()
        
        if choice == "1":
            new_amount = input(f"New amount (current: ${info['amount']}): ").strip()
            if new_amount:
                try:
                    new_amount = float(new_amount)
                    if new_amount <= 0:
                        print("❌ Amount must be positive!")
                        return
                    
                    result = models.execute_kw(
                        db, uid, password,
                        'account.payment', 'write',
                        [[payment_id], {'amount': new_amount}]
                    )
                    
                    if result:
                        print(f"✅ Amount updated to: ${new_amount}")
                    else:
                        print("❌ Update failed")
                except ValueError:
                    print("❌ Invalid amount")
                except Exception as e:
                    print(f"❌ Error: {e}")
            
        elif choice == "2":
            new_date = input(f"New date (current: {info['date']}): ").strip()
            if new_date:
                try:
                    result = models.execute_kw(
                        db, uid, password,
                        'account.payment', 'write',
                        [[payment_id], {'date': new_date}]
                    )
                    
                    if result:
                        print(f"✅ Date updated to: {new_date}")
                    else:
                        print("❌ Update failed")
                except Exception as e:
                    print(f"❌ Error: {e}")
            
        elif choice == "3":
            # Show updated info
            updated = models.execute_kw(
                db, uid, password,
                'account.payment', 'read',
                [[payment_id]], 
                {'fields': ['name', 'partner_id', 'amount', 'date', 'state', 'payment_type']}
            )[0]
            
            payment_type_name = "Received" if updated['payment_type'] == 'inbound' else "Sent"
            print(f"\n📋 Updated Payment:")
            print(f"   Name: {updated['name']}")
            print(f"   Type: {payment_type_name}")
            print(f"   Partner: {updated['partner_id'][1] if updated.get('partner_id') else 'N/A'}")
            print(f"   Amount: ${updated['amount']}")
            print(f"   Date: {updated['date']}")
            print(f"   Status: {updated['state']}")
        
        else:
            print("❌ Invalid choice")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def delete_payment():
    """Delete a payment"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🗑️  DELETE PAYMENT")
        print("=" * 17)
        
        list_payments()
        
        payment_id = input("\nEnter Payment ID to delete: ").strip()
        try:
            payment_id = int(payment_id)
        except ValueError:
            print("❌ Invalid payment ID!")
            return
        
        # Get payment info
        payment = models.execute_kw(
            db, uid, password,
            'account.payment', 'search_read',
            [[('id', '=', payment_id)]], 
            {'fields': ['name', 'partner_id', 'amount', 'state', 'payment_type']}
        )
        
        if not payment:
            print("❌ Payment not found!")
            return
        
        info = payment[0]
        payment_type_name = "Received" if info['payment_type'] == 'inbound' else "Sent"
        partner_name = info['partner_id'][1] if info.get('partner_id') else 'Unknown'
        
        print(f"\n📋 Payment to Delete:")
        print(f"   Name: {info['name']}")
        print(f"   Type: {payment_type_name}")
        print(f"   Partner: {partner_name}")
        print(f"   Amount: ${info['amount']}")
        print(f"   Status: {info['state']}")
        
        if info.get('state') in ['posted', 'reconciled']:
            print(f"\n⚠️  WARNING: Payment is {info['state']}")
            print("   This may affect your accounting records!")
        
        print(f"\n🗑️  This action cannot be undone!")
        
        confirm1 = input(f"Delete payment {info['name']}? (yes/no): ").lower().strip()
        if confirm1 != 'yes':
            print("❌ Cancelled.")
            return
        
        confirm2 = input(f"Confirm deletion of ${info['amount']} payment? (yes/no): ").lower().strip()
        if confirm2 != 'yes':
            print("❌ Cancelled.")
            return
        
        print("🔄 Deleting payment...")
        
        try:
            result = models.execute_kw(
                db, uid, password,
                'account.payment', 'unlink',
                [[payment_id]]
            )
            
            if result:
                print("✅ Payment deleted successfully!")
            else:
                print("❌ Delete failed")
                
        except Exception as e:
            print(f"❌ Deletion failed: {e}")
            
            if "posted" in str(e).lower():
                print("💡 Try cancelling the payment first")
                cancel = input("Cancel payment first? (y/n): ").lower().strip()
                if cancel == 'y':
                    try:
                        models.execute_kw(
                            db, uid, password,
                            'account.payment', 'action_cancel',
                            [[payment_id]]
                        )
                        print("✅ Payment cancelled")
                        
                        # Try delete again
                        result = models.execute_kw(
                            db, uid, password,
                            'account.payment', 'unlink',
                            [[payment_id]]
                        )
                        
                        if result:
                            print("✅ Payment deleted after cancellation!")
                        else:
                            print("❌ Still failed to delete")
                            
                    except Exception as cancel_error:
                        print(f"❌ Cancel failed: {cancel_error}")
                        
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Main menu"""
    while True:
        print("\n" + "="*30)
        print("💰 SIMPLE PAYMENT MANAGER")
        print("="*30)
        print("1. List payments")
        print("2. Create payment")
        print("3. Modify payment")
        print("4. Delete payment")
        print("5. Exit")
        
        choice = input("\nChoice (1-5): ").strip()
        
        if choice == "1":
            list_payments()
        elif choice == "2":
            create_payment()
        elif choice == "3":
            modify_payment()
        elif choice == "4":
            delete_payment()
        elif choice == "5":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice!")

if __name__ == "__main__":
    main()