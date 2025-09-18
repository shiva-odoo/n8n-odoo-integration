import xmlrpc.client
import os
# Load .env only in development (when .env file exists)
if os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, use system env vars

def main(data):
    """
    Create product from HTTP request data
    
    Expected data format:
    {
        "name": "Product Name",                  # required
        "default_code": "PROD001",               # optional, product code/SKU
        "list_price": 99.99,                     # optional, selling price
        "product_type": "consu",                 # optional, defaults to "consu" (consumable)
        "description": "Product description",    # optional
        "barcode": "1234567890"                  # optional
    }
    """
    
    # Validate required fields
    if not data.get('name'):
        return {
            'success': False,
            'error': 'name is required'
        }
    
    # Connection details
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    if not username or not password:
        return {
            'success': False,
            'error': 'ODOO_USERNAME and ODOO_API_KEY environment variables are required'
        }
    
    try:
        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Authenticate
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {
                'success': False,
                'error': 'Odoo authentication failed'
            }
        
        # Check if product already exists (by name or code)
        search_domain = [('name', '=', data['name'])]
        if data.get('default_code'):
            search_domain = ['|', ('name', '=', data['name']), ('default_code', '=', data['default_code'])]
        
        existing_product = models.execute_kw(
            db, uid, password,
            'product.product', 'search_read',
            [search_domain], 
            {'fields': ['id', 'name', 'default_code'], 'limit': 1}
        )
        
        if existing_product:
            product_info = existing_product[0]
            return {
                'success': True,
                'product_id': product_info['id'],
                'product_name': product_info['name'],
                'default_code': product_info.get('default_code'),
                'message': 'Product already exists',
                'existing': True
            }
        
        # Prepare product data
        product_data = {
            'name': data['name'],
        }
        
        # Add optional fields with validation
        if data.get('default_code'):
            product_data['default_code'] = data['default_code']
        
        if data.get('list_price'):
            try:
                list_price = float(data['list_price'])
                if list_price >= 0:
                    product_data['list_price'] = list_price
                else:
                    return {
                        'success': False,
                        'error': 'list_price must be non-negative'
                    }
            except (ValueError, TypeError):
                return {
                    'success': False,
                    'error': 'list_price must be a valid number'
                }
        
        # Set product type (validate allowed values)
        product_type = data.get('product_type', 'consu')
        if product_type in ['consu', 'service', 'product']:
            product_data['type'] = product_type
        else:
            return {
                'success': False,
                'error': 'product_type must be one of: consu, service, product'
            }
        
        # Add description if provided
        if data.get('description'):
            product_data['description'] = data['description']
        
        # Add barcode if provided
        if data.get('barcode'):
            product_data['barcode'] = data['barcode']
        
        # Create product using multiple methods to handle different Odoo configurations
        product_id = None
        error_messages = []
        
        # Method 1: Try with all fields
        try:
            product_id = models.execute_kw(
                db, uid, password,
                'product.product', 'create',
                [product_data]
            )
        except Exception as e1:
            error_messages.append(f"Method 1 failed: {str(e1)}")
            
            # Method 2: Try with minimal fields only
            try:
                minimal_data = {'name': data['name']}
                if 'type' in product_data:
                    minimal_data['type'] = product_data['type']
                
                product_id = models.execute_kw(
                    db, uid, password,
                    'product.product', 'create',
                    [minimal_data]
                )
                
                # If successful, try to update with additional fields
                if product_id and len(product_data) > len(minimal_data):
                    update_data = {k: v for k, v in product_data.items() if k not in minimal_data}
                    try:
                        models.execute_kw(
                            db, uid, password,
                            'product.product', 'write',
                            [[product_id], update_data]
                        )
                    except Exception as update_error:
                        error_messages.append(f"Update failed: {str(update_error)}")
                        
            except Exception as e2:
                error_messages.append(f"Method 2 failed: {str(e2)}")
                
                # Method 3: Try with product.template instead
                try:
                    template_id = models.execute_kw(
                        db, uid, password,
                        'product.template', 'create',
                        [{'name': data['name']}]
                    )
                    
                    if template_id:
                        # Get the corresponding product.product record
                        product_ids = models.execute_kw(
                            db, uid, password,
                            'product.product', 'search',
                            [[('product_tmpl_id', '=', template_id)]], {'limit': 1}
                        )
                        if product_ids:
                            product_id = product_ids[0]
                            
                except Exception as e3:
                    error_messages.append(f"Method 3 failed: {str(e3)}")
        
        if not product_id:
            return {
                'success': False,
                'error': f'Failed to create product. Errors: {"; ".join(error_messages)}'
            }
        
        # Get created product information
        try:
            product_info = models.execute_kw(
                db, uid, password,
                'product.product', 'read',
                [[product_id]], 
                {'fields': ['name', 'default_code', 'list_price', 'type', 'barcode']}
            )[0]
        except Exception:
            # Fallback if detailed read fails
            product_info = {
                'name': data['name'],
                'default_code': data.get('default_code'),
                'list_price': data.get('list_price', 0.0),
                'type': data.get('product_type', 'consu'),
                'barcode': data.get('barcode')
            }
        
        return {
            'success': True,
            'product_id': product_id,
            'product_name': product_info['name'],
            'default_code': product_info.get('default_code'),
            'list_price': product_info.get('list_price', 0.0),
            'product_type': product_info.get('type'),
            'barcode': product_info.get('barcode'),
            'message': 'Product created successfully',
            'existing': False
        }
        
    except xmlrpc.client.Fault as e:
        return {
            'success': False,
            'error': f'Odoo API error: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }

def create(data):
    """Alias for main function to maintain compatibility"""
    return main(data)

def list_products():
    """Get list of products for reference"""
    
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {'success': False, 'error': 'Authentication failed'}
        
        products = models.execute_kw(
            db, uid, password,
            'product.product', 'search_read',
            [[]], 
            {'fields': ['id', 'name', 'default_code', 'list_price', 'type'], 'limit': 20}
        )
        
        return {
            'success': True,
            'products': products,
            'count': len(products)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
    
def create_vendor_bill(bill_data):
    """Create a vendor bill in Odoo based on JSON input"""
    
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {'success': False, 'error': 'Authentication failed'}
        
        # Validate required fields
        required_fields = ['partner_id', 'invoice_lines']
        for field in required_fields:
            if field not in bill_data:
                return {'success': False, 'error': f'Required field "{field}" is missing'}
        
        if not bill_data['invoice_lines']:
            return {'success': False, 'error': 'At least one invoice line is required'}
        
        # Prepare the bill data
        bill_vals = {
            'move_type': 'in_invoice',  # Vendor bill
            'company_id': 60,  # Fixed company ID
            'partner_id': bill_data['partner_id'],
            'invoice_date': bill_data.get('invoice_date', False),
            'invoice_date_due': bill_data.get('invoice_date_due', False),
            'ref': bill_data.get('ref', False),
            'narration': bill_data.get('narration', False),
            'currency_id': bill_data.get('currency_id', False),
            'journal_id': bill_data.get('journal_id', False),
            'payment_reference': bill_data.get('payment_reference', False),
        }
        
        # Prepare invoice lines
        invoice_lines = []
        for line in bill_data['invoice_lines']:
            if 'account_id' not in line:
                return {'success': False, 'error': 'account_id is required for each invoice line'}
            
            line_vals = {
                'name': line.get('name', '/'),
                'account_id': line['account_id'],
                'quantity': line.get('quantity', 1.0),
                'price_unit': line.get('price_unit', 0.0),
                'product_id': line.get('product_id', False),
                'product_uom_id': line.get('product_uom_id', False),
                'tax_ids': [(6, 0, line.get('tax_ids', []))],
                'analytic_distribution': line.get('analytic_distribution', False),
                'discount': line.get('discount', 0.0),
            }
            
            invoice_lines.append((0, 0, line_vals))
        
        bill_vals['invoice_line_ids'] = invoice_lines
        
        # Remove None/False values
        bill_vals = {k: v for k, v in bill_vals.items() if v is not False and v is not None}
        
        # Create the bill
        bill_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [bill_vals]
        )
        
        if not bill_id:
            return {'success': False, 'error': 'Failed to create bill'}
        
        # Get the created bill details
        created_bill = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', bill_id)]], 
            {'fields': [
                'id', 'name', 'partner_id', 'amount_total', 'amount_untaxed',
                'amount_tax', 'state', 'ref', 'invoice_date', 'invoice_date_due',
                'payment_state', 'currency_id', 'journal_id'
            ]}
        )
        
        return {
            'success': True,
            'bill_id': bill_id,
            'bill': created_bill[0] if created_bill else None,
            'message': f'Vendor bill created successfully with ID: {bill_id}'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def create_customer_invoice(invoice_data):
    """Create a customer invoice in Odoo based on JSON input"""
    
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB")
    username = os.getenv("ODOO_USERNAME")
    password = os.getenv("ODOO_API_KEY")
    
    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        uid = common.authenticate(db, username, password, {})
        if not uid:
            return {'success': False, 'error': 'Authentication failed'}
        
        # Validate required fields
        required_fields = ['partner_id', 'invoice_lines']
        for field in required_fields:
            if field not in invoice_data:
                return {'success': False, 'error': f'Required field "{field}" is missing'}
        
        if not invoice_data['invoice_lines']:
            return {'success': False, 'error': 'At least one invoice line is required'}
        
        # Prepare the invoice data
        invoice_vals = {
            'move_type': 'out_invoice',  # Customer invoice
            'company_id': 60,  # Fixed company ID
            'partner_id': invoice_data['partner_id'],
            'invoice_date': invoice_data.get('invoice_date', False),
            'invoice_date_due': invoice_data.get('invoice_date_due', False),
            'ref': invoice_data.get('ref', False),
            'narration': invoice_data.get('narration', False),
            'currency_id': invoice_data.get('currency_id', False),
            'journal_id': invoice_data.get('journal_id', False),
            'payment_reference': invoice_data.get('payment_reference', False),
        }
        
        # Prepare invoice lines
        invoice_lines = []
        for line in invoice_data['invoice_lines']:
            if 'account_id' not in line:
                return {'success': False, 'error': 'account_id is required for each invoice line'}
            
            line_vals = {
                'name': line.get('name', '/'),
                'account_id': line['account_id'],
                'quantity': line.get('quantity', 1.0),
                'price_unit': line.get('price_unit', 0.0),
                'product_id': line.get('product_id', False),
                'product_uom_id': line.get('product_uom_id', False),
                'tax_ids': [(6, 0, line.get('tax_ids', []))],
                'analytic_distribution': line.get('analytic_distribution', False),
                'discount': line.get('discount', 0.0),
            }
            
            invoice_lines.append((0, 0, line_vals))
        
        invoice_vals['invoice_line_ids'] = invoice_lines
        
        # Remove None/False values
        invoice_vals = {k: v for k, v in invoice_vals.items() if v is not False and v is not None}
        
        # Create the invoice
        invoice_id = models.execute_kw(
            db, uid, password,
            'account.move', 'create',
            [invoice_vals]
        )
        
        if not invoice_id:
            return {'success': False, 'error': 'Failed to create invoice'}
        
        # Get the created invoice details
        created_invoice = models.execute_kw(
            db, uid, password,
            'account.move', 'search_read',
            [[('id', '=', invoice_id)]], 
            {'fields': [
                'id', 'name', 'partner_id', 'amount_total', 'amount_untaxed',
                'amount_tax', 'state', 'ref', 'invoice_date', 'invoice_date_due',
                'payment_state', 'currency_id', 'journal_id'
            ]}
        )
        
        return {
            'success': True,
            'invoice_id': invoice_id,
            'invoice': created_invoice[0] if created_invoice else None,
            'message': f'Customer invoice created successfully with ID: {invoice_id}'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
