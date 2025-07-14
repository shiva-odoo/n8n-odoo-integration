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

def list_products():
    """List all products"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        products = models.execute_kw(
            db, uid, password,
            'product.product', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'default_code', 'list_price'], 'limit': 20}
        )
        
        print(f"\n📦 Products ({len(products)} found):")
        print("=" * 60)
        
        if not products:
            print("   No products found!")
            return
        
        for product in products:
            code_info = f" [{product['default_code']}]" if product.get('default_code') else ""
            print(f"   ID: {product['id']} | {product['name']}{code_info} | ${product['list_price']}")
            
    except Exception as e:
        print(f"❌ Error listing products: {e}")

def create_product():
    """Create a new product with minimal data"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        print("\n➕ CREATE PRODUCT")
        print("=" * 18)
        
        name = input("Product Name: ").strip()
        if not name:
            print("❌ Product name is required!")
            return
        
        # Try different product type approaches
        print("🔄 Creating product...")
        
        # Method 1: Just name (minimal approach)
        try:
            product_data = {'name': name}
            
            product_id = models.execute_kw(
                db, uid, password,
                'product.product', 'create',
                [product_data]
            )
            
            if product_id:
                print(f"✅ Product created successfully!")
                print(f"   Product ID: {product_id}")
                print(f"   Name: {name}")
                
                # Now try to update with additional fields
                code = input("Add product code? (optional): ").strip()
                price = input("Add selling price? (optional): ").strip()
                
                updates = {}
                if code:
                    updates['default_code'] = code
                if price:
                    try:
                        updates['list_price'] = float(price)
                    except ValueError:
                        print("⚠️  Invalid price format")
                
                if updates:
                    try:
                        models.execute_kw(
                            db, uid, password,
                            'product.product', 'write',
                            [[product_id], updates]
                        )
                        print(f"✅ Product details updated!")
                    except Exception as e:
                        print(f"⚠️  Could not update additional details: {e}")
                
                return
            
        except Exception as e1:
            print(f"❌ Method 1 failed: Basic creation error")
            
            # Method 2: Try with different type values
            for product_type in [None, 'consu', 'service']:
                try:
                    print(f"🔄 Trying with type: {product_type or 'default'}")
                    
                    product_data = {'name': name}
                    if product_type:
                        product_data['type'] = product_type
                    
                    product_id = models.execute_kw(
                        db, uid, password,
                        'product.product', 'create',
                        [product_data]
                    )
                    
                    if product_id:
                        print(f"✅ Product created successfully!")
                        print(f"   Product ID: {product_id}")
                        print(f"   Type: {product_type or 'default'}")
                        return
                        
                except Exception as e2:
                    print(f"   Failed with type {product_type}")
                    continue
            
            print(f"❌ All creation methods failed")
            print(f"💡 Your user may not have permission to create products")
            
    except Exception as e:
        print(f"❌ Error creating product: {e}")

def modify_product():
    """Modify a product"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        list_products()
        
        product_id = input("\nEnter Product ID to modify: ").strip()
        try:
            product_id = int(product_id)
        except ValueError:
            print("❌ Invalid product ID!")
            return
        
        # Get current info
        current = models.execute_kw(
            db, uid, password,
            'product.product', 'read',
            [[product_id]], {'fields': ['name', 'default_code', 'list_price']}
        )
        
        if not current:
            print(f"❌ Product not found!")
            return
        
        info = current[0]
        print(f"\nCurrent: {info['name']} | Code: {info.get('default_code', 'None')} | Price: ${info['list_price']}")
        
        # Get updates
        updates = {}
        
        new_name = input("New name (Enter to skip): ").strip()
        if new_name:
            updates['name'] = new_name
        
        new_code = input("New code (Enter to skip): ").strip()
        if new_code:
            updates['default_code'] = new_code
        
        new_price = input("New price (Enter to skip): ").strip()
        if new_price:
            try:
                updates['list_price'] = float(new_price)
            except ValueError:
                print("⚠️  Invalid price")
        
        if not updates:
            print("No changes made.")
            return
        
        result = models.execute_kw(
            db, uid, password,
            'product.product', 'write',
            [[product_id], updates]
        )
        
        if result:
            print("✅ Product updated!")
        else:
            print("❌ Update failed")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def delete_product():
    """Delete a product"""
    models, db, uid, password = connect_odoo()
    if not models:
        return
    
    try:
        list_products()
        
        product_id = input("\nEnter Product ID to delete: ").strip()
        try:
            product_id = int(product_id)
        except ValueError:
            print("❌ Invalid product ID!")
            return
        
        # Get product name for confirmation
        product = models.execute_kw(
            db, uid, password,
            'product.product', 'read',
            [[product_id]], {'fields': ['name']}
        )
        
        if not product:
            print("❌ Product not found!")
            return
        
        name = product[0]['name']
        
        confirm = input(f"Delete '{name}'? (yes/no): ").lower().strip()
        if confirm != 'yes':
            print("❌ Cancelled.")
            return
        
        result = models.execute_kw(
            db, uid, password,
            'product.product', 'unlink',
            [[product_id]]
        )
        
        if result:
            print("✅ Product deleted!")
        else:
            print("❌ Delete failed")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Main menu"""
    while True:
        print("\n" + "="*30)
        print("📦 MINIMAL PRODUCT MANAGER")
        print("="*30)
        print("1. List products")
        print("2. Create product")
        print("3. Modify product")
        print("4. Delete product")
        print("5. Exit")
        
        choice = input("\nChoice (1-5): ").strip()
        
        if choice == "1":
            list_products()
        elif choice == "2":
            create_product()
        elif choice == "3":
            modify_product()
        elif choice == "4":
            delete_product()
        elif choice == "5":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice!")

if __name__ == "__main__":
    main()