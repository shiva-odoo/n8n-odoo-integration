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
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
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

def test_vendor_payment():
    """Test creating a vendor payment specifically"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n🧪 TEST VENDOR PAYMENT CREATION")
        print("=" * 35)
        
        # First, let's see what payment types exist
        print("🔍 Checking payment types in your system...")
        
        # Check existing payments to see the pattern
        try:
            all_payments = models.execute_kw(
                db, uid, password,
                'account.payment', 'search_read',
                [[]], 
                {'fields': ['id', 'name', 'payment_type', 'partner_type', 'partner_id'], 'limit': 5}
            )
            
            print("📋 Sample existing payments:")
            for payment in all_payments:
                partner_name = payment['partner_id'][1] if payment.get('partner_id') else 'N/A'
                print(f"   {payment['name']} | Type: {payment.get('payment_type', 'N/A')} | Partner Type: {payment.get('partner_type', 'N/A')} | Partner: {partner_name}")
                
        except Exception as e:
            print(f"Could not fetch existing payments: {e}")
        
        # Get vendors
        vendors = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_read',
            [[('supplier_rank', '>', 0)]], 
            {'fields': ['id', 'name'], 'limit': 5}
        )
        
        if not vendors:
            print("❌ No vendors found!")
            return
        
        print(f"\n👥 Available Vendors:")
        for vendor in vendors:
            print(f"   {vendor['id']}: {vendor['name']}")
        
        # Select vendor
        vendor_id = input("Enter Vendor ID: ").strip()
        try:
            vendor_id = int(vendor_id)
            vendor_name = next(v['name'] for v in vendors if v['id'] == vendor_id)
            print(f"✅ Selected vendor: {vendor_name}")
        except (ValueError, StopIteration):
            print("❌ Invalid vendor ID!")
            return
        
        # Get amount
        amount = input("Payment amount: ").strip()
        try:
            amount = float(amount)
        except ValueError:
            print("❌ Invalid amount!")
            return
        
        # Test different payment data configurations
        print(f"\n🧪 Testing vendor payment creation...")
        
        # Configuration 1: Most explicit
        payment_data_v1 = {
            'payment_type': 'outbound',      # Money going OUT to vendor
            'partner_type': 'supplier',      # Partner is a SUPPLIER
            'partner_id': vendor_id,
            'amount': amount,
            'date': datetime.now().strftime('%Y-%m-%d'),
        }
        
        print(f"📋 Creating vendor payment with data:")
        print(f"   payment_type: 'outbound' (money going out)")
        print(f"   partner_type: 'supplier' (vendor payment)")
        print(f"   partner_id: {vendor_id} ({vendor_name})")
        print(f"   amount: ${amount}")
        
        confirm = input("\nProceed with vendor payment creation? (y/n): ").lower().strip()
        if confirm != 'y':
            print("❌ Cancelled.")
            return
        
        try:
            payment_id = models.execute_kw(
                db, uid, password,
                'account.payment', 'create',
                [payment_data_v1]
            )
            
            if payment_id:
                print(f"✅ SUCCESS! Vendor payment created with ID: {payment_id}")
                
                # Verify the created payment
                created_payment = models.execute_kw(
                    db, uid, password,
                    'account.payment', 'read',
                    [[payment_id]], 
                    {'fields': ['name', 'payment_type', 'partner_type', 'partner_id', 'amount']}
                )[0]
                
                print(f"\n✅ VERIFICATION - Created payment details:")
                print(f"   Name: {created_payment['name']}")
                print(f"   Payment Type: {created_payment['payment_type']}")
                print(f"   Partner Type: {created_payment['partner_type']}")
                print(f"   Partner: {created_payment['partner_id'][1]}")
                print(f"   Amount: ${created_payment['amount']}")
                
                if created_payment['payment_type'] == 'outbound' and created_payment['partner_type'] == 'supplier':
                    print(f"\n🎉 CONFIRMED: This is a VENDOR PAYMENT!")
                else:
                    print(f"\n⚠️  WARNING: This might not be a vendor payment!")
                    
            else:
                print("❌ Failed to create payment")
                
        except Exception as e:
            print(f"❌ Error creating payment: {e}")
            
            # Try alternative approach
            print(f"\n🔄 Trying alternative approach...")
            
            payment_data_v2 = {
                'payment_type': 'outbound',
                'partner_id': vendor_id,
                'amount': amount,
                'date': datetime.now().strftime('%Y-%m-%d'),
            }
            
            try:
                payment_id = models.execute_kw(
                    db, uid, password,
                    'account.payment', 'create',
                    [payment_data_v2]
                )
                
                if payment_id:
                    print(f"✅ Alternative approach worked! Payment ID: {payment_id}")
                else:
                    print("❌ Alternative approach also failed")
                    
            except Exception as e2:
                print(f"❌ Alternative approach failed: {e2}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_vendor_payment()