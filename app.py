from flask import Flask, request, jsonify
import os
import json

# Import all your modules
try:
    import createbill
    import createBillCompanywise
    import createcompany
    import createCreditNotes
    import createCusomterPayments
    import createCustomer
    import createInvoice
    import createproduct
    import createrefund
    import createvendor
    import createVendorPayments
    import deletebill
    import deletecompany
    import deletevendor
    import modifybill
    import modifyvendor
    
except ImportError as e:
    print(f"Warning: Could not import some modules: {e}")

app = Flask(__name__)

# Home endpoint with API documentation
@app.route('/')
def home():
    endpoints = {
        "message": "Business Management API",
        "available_endpoints": {
            "Vendor Operations": {
                "/api/vendors": "GET - List all vendors",
                "/api/vendors/<id>": "GET - Get vendor details",
            },
            "Create Operations": {
                "/api/create/bill": "POST - Create bill",
                "/api/create/bill-company": "POST - Create bill by company",
                "/api/create/company": "POST - Create company",
                "/api/create/credit-notes": "POST - Create credit notes",
                "/api/create/customer-payments": "POST - Create customer payments",
                "/api/create/customer": "POST - Create customer",
                "/api/create/invoice": "POST - Create invoice",
                "/api/create/product": "POST - Create product",
                "/api/create/refund": "POST - Create refund",
                "/api/create/vendor": "POST - Create vendor",
                "/api/create/vendor-payments": "POST - Create vendor payments"
            },
            "Delete Operations": {
                "/api/delete/bill": "DELETE - Delete bill",
                "/api/delete/company": "DELETE - Delete company",
                "/api/delete/vendor": "DELETE - Delete vendor"
            },
            "Modify Operations": {
                "/api/modify/bill": "PUT - Modify bill",
                "/api/modify/vendor": "PUT - Modify vendor"
            }
        },
        "example_usage": {
            "get_vendors": {
                "url": "/api/vendors",
                "method": "GET",
                "description": "Get list of all vendors to find vendor_id for bill creation"
            },
            "create_bill_simple": {
                "url": "/api/create/bill",
                "method": "POST",
                "body": {
                    "vendor_id": 123,
                    "description": "Office supplies",
                    "amount": 1500.50,
                    "invoice_date": "2025-01-15",
                    "vendor_ref": "INV-001"
                },
                "description": "Create a simple bill with one line item"
            },
            "create_bill_multiple_items": {
                "url": "/api/create/bill",
                "method": "POST", 
                "body": {
                    "vendor_id": 123,
                    "invoice_date": "2025-01-15",
                    "vendor_ref": "INV-001",
                    "line_items": [
                        {
                            "description": "Office supplies",
                            "quantity": 2,
                            "price_unit": 750.25
                        },
                        {
                            "description": "Software license", 
                            "quantity": 1,
                            "price_unit": 500.00
                        }
                    ]
                },
                "description": "Create a bill with multiple line items"
            }
        },
        "required_fields": {
            "create_bill": {
                "vendor_id": "integer (required) - Get from /api/vendors",
                "description + amount": "string + number (option 1) - For single line item",
                "line_items": "array (option 2) - For multiple line items",
                "invoice_date": "string (optional) - Format: YYYY-MM-DD, defaults to today",
                "vendor_ref": "string (optional) - Vendor reference number"
            }
        }
    }
    return jsonify(endpoints)

# Vendor Operations
@app.route('/api/vendors', methods=['GET'])
def get_vendors():
    """Get list of all vendors"""
    try:
        result = createbill.list_vendors()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vendors/<int:vendor_id>', methods=['GET'])
def get_vendor(vendor_id):
    """Get specific vendor details"""
    try:
        # You can implement this in createbill.py if needed
        return jsonify({
            'success': True, 
            'vendor_id': vendor_id, 
            'message': 'Vendor details endpoint - implementation pending'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Create Operations
@app.route('/api/create/bill', methods=['POST'])
def create_bill():
    try:
        data = request.json or {}
        result = createbill.main(data) if hasattr(createbill, 'main') else createbill.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/bill-company', methods=['POST'])
def create_bill_company():
    try:
        data = request.json or {}
        result = createBillCompanywise.main(data) if hasattr(createBillCompanywise, 'main') else createBillCompanywise.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/company', methods=['POST'])
def create_company():
    try:
        data = request.json or {}
        result = createcompany.main(data) if hasattr(createcompany, 'main') else createcompany.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/credit-notes', methods=['POST'])
def create_credit_notes():
    try:
        data = request.json or {}
        result = createCreditNotes.main(data) if hasattr(createCreditNotes, 'main') else createCreditNotes.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/customer-payments', methods=['POST'])
def create_customer_payments():
    try:
        data = request.json or {}
        result = createCusomterPayments.main(data) if hasattr(createCusomterPayments, 'main') else createCusomterPayments.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/customer', methods=['POST'])
def create_customer():
    try:
        data = request.json or {}
        result = createCustomer.main(data) if hasattr(createCustomer, 'main') else createCustomer.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/invoice', methods=['POST'])
def create_invoice():
    try:
        data = request.json or {}
        result = createInvoice.main(data) if hasattr(createInvoice, 'main') else createInvoice.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/product', methods=['POST'])
def create_product():
    try:
        data = request.json or {}
        result = createproduct.main(data) if hasattr(createproduct, 'main') else createproduct.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/refund', methods=['POST'])
def create_refund():
    try:
        data = request.json or {}
        result = createrefund.main(data) if hasattr(createrefund, 'main') else createrefund.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/vendor', methods=['POST'])
def create_vendor():
    try:
        data = request.json or {}
        result = createvendor.main(data) if hasattr(createvendor, 'main') else createvendor.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/vendor-payments', methods=['POST'])
def create_vendor_payments():
    try:
        data = request.json or {}
        result = createVendorPayments.main(data) if hasattr(createVendorPayments, 'main') else createVendorPayments.create(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Delete Operations
@app.route('/api/delete/bill', methods=['DELETE'])
def delete_bill():
    try:
        data = request.json or {}
        result = deletebill.main(data) if hasattr(deletebill, 'main') else deletebill.delete(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete/company', methods=['DELETE'])
def delete_company():
    try:
        data = request.json or {}
        result = deletecompany.main(data) if hasattr(deletecompany, 'main') else deletecompany.delete(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete/vendor', methods=['DELETE'])
def delete_vendor():
    try:
        data = request.json or {}
        result = deletevendor.main(data) if hasattr(deletevendor, 'main') else deletevendor.delete(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Modify Operations
@app.route('/api/modify/bill', methods=['PUT'])
def modify_bill():
    try:
        data = request.json or {}
        result = modifybill.main(data) if hasattr(modifybill, 'main') else modifybill.modify(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/modify/vendor', methods=['PUT'])
def modify_vendor():
    try:
        data = request.json or {}
        result = modifyvendor.main(data) if hasattr(modifyvendor, 'main') else modifyvendor.modify(data)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Health check endpoint
@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'message': 'Business Management API is running'})

# Test endpoint to verify environment variables
@app.route('/api/test-config')
def test_config():
    """Test endpoint to verify configuration (for debugging)"""
    config_status = {
        'odoo_username': bool(os.getenv("ODOO_USERNAME")),
        'odoo_api_key': bool(os.getenv("ODOO_API_KEY")),
        'environment_vars': list(os.environ.keys())
    }
    return jsonify({
        'success': True,
        'config': config_status,
        'message': 'Configuration check complete'
    })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.errorhandler(400)
def bad_request(error):
    return jsonify({'success': False, 'error': 'Bad request - check your JSON format'}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)