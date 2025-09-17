from flask import Flask, request, jsonify
import os
import json
from flask_cors import CORS

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
    import createjournal
    import createtransaction
    import getDetailsByCompany
    import updateAuditStatus
    
    
except ImportError as e:
    print(f"Warning: Could not import some modules: {e}")

import base64
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PDF extraction availability (set based on your setup)
PDF_EXTRACTION_AVAILABLE = False  # Change to True if you have PDF processing modules
import upload
import onboarding
import auth
import admin
from middleware import jwt_required, admin_required, get_current_user
from flask import g
import validatecompany
import batchupdate
import classifydocument
import splitinvoice
import matchingworkflow
import processtransaction
import process_bill
import process_invoice

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": ["*"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# Home endpoint with comprehensive API documentation

@app.route('/')
def home():
    endpoints = {
        "message": "Complete Business Management API",
        "version": "4.0",
        "total_endpoints": 35,
        "available_endpoints": {
            "PDF Extraction (NEW - 4 endpoints)": {
                "/api/extract-pdf-data": "POST - Extract structured data from PDF files",
                "/api/process-document": "POST - Complete document processing (extract + create records)",
                "/api/extract-from-url": "POST - Extract from file URL",
                "/api/extraction-status": "GET - Check extraction status"
            },
            "Reference Data (11 endpoints)": {
                "/api/vendors": "GET - List all vendors",
                "/api/companies": "GET - List all companies", 
                "/api/customers": "GET - List all customers",
                "/api/products": "GET - List all products",
                "/api/payments": "GET - List all payments",
                "/api/vendor-payments": "GET - List vendor payments",
                "/api/credit-notes": "GET - List all credit notes",
                "/api/invoices": "GET - List all customer invoices",
                "/api/refunds": "GET - List all refunds",
                "/api/bills": "GET - List all vendor bills",
                "/api/journals": "GET - List all journals",
                "/api/accounts": "GET - List chart of accounts",
                "/api/companies/<id>/vendors": "GET - Get vendors for specific company",
                "/api/getDetailsByCompany": "GET - Get details by company ID"
            },
            "Create Operations (12 endpoints)": {
                "/api/create/vendor": "POST - Create vendor with full address support",
                "/api/create/company": "POST - Create company with country validation",
                "/api/create/customer": "POST - Create customer with contact details",
                "/api/create/product": "POST - Create product with pricing & codes",
                "/api/create/bill": "POST - Create vendor bill with line items",
                "/api/create/bill-company": "POST - Create company-specific vendor bill",
                "/api/create/invoice": "POST - Create customer invoice with line items",
                "/api/create/journal": "POST - Create journal entry with debit/credit lines",
                "/api/create/customer-payments": "POST - Process customer payments (received/sent)",
                "/api/create/vendor-payments": "POST - Process vendor payments",
                "/api/create/credit-notes": "POST - Create customer/vendor credit notes",
                "/api/create/refund": "POST - Process customer/vendor refunds",
                "/api/create/transaction": "POST - Create bank transaction"
            },
            "Update Operations (2 endpoints)": {
                "/api/modify/vendor": "PUT - Update vendor with change tracking",
                "/api/modify/bill": "PUT - Modify vendor bills & line items"
            },
            "Delete Operations (3 endpoints)": {
                "/api/delete/vendor": "DELETE - Delete/archive vendors safely",
                "/api/delete/company": "DELETE - Delete/archive companies safely", 
                "/api/delete/bill": "DELETE - Delete bills with safety checks"
            },
            "Utility (5 endpoints)": {
                "/health": "GET - Health check",
                "/api/test-config": "GET - Configuration test",
                "/api/docs/vendor": "GET - Vendor API documentation",
                "/api/docs/bill": "GET - Bill API documentation",
                "/api/docs/journal": "GET - Journal entry API documentation",
                "/api/docs/payment": "GET - Payment API documentation"
            }
        },
        "advanced_examples": {
            "smart_vendor_payment": {
                "url": "/api/create/vendor-payments",
                "method": "POST",
                "body": {
                    "vendor_id": 123,
                    "amount": 2500.00,
                    "payment_date": "2025-01-15",
                    "reference": "Payment for Invoice INV-2025-001"
                },
                "description": "Create vendor payment with validation"
            },
            "journal_entry": {
                "url": "/api/create/journal",
                "method": "POST",
                "body": {
                    "date": "2025-01-15",
                    "ref": "JE-001",
                    "narration": "Monthly rent payment",
                    "line_items": [
                        {
                            "account_id": 101,
                            "name": "Office rent",
                            "debit": 1500.00,
                            "credit": 0.00
                        },
                        {
                            "account_id": 201,
                            "name": "Cash payment",
                            "debit": 0.00,
                            "credit": 1500.00
                        }
                    ]
                },
                "description": "Create journal entry with balanced debit/credit"
            },
            "safe_vendor_deletion": {
                "url": "/api/delete/vendor",
                "method": "DELETE",
                "body": {
                    "vendor_id": 123,
                    "archive_instead": True
                },
                "description": "Safely delete vendor with archive fallback"
            },
            "advanced_bill_modification": {
                "url": "/api/modify/bill",
                "method": "PUT",
                "body": {
                    "bill_id": 456,
                    "reference": "Updated reference",
                    "line_items": [
                        {
                            "line_id": 789,
                            "description": "Updated description",
                            "price_unit": 175.00
                        }
                    ],
                    "add_line_item": {
                        "description": "Additional service",
                        "quantity": 1,
                        "price_unit": 300.00
                    }
                },
                "description": "Modify bill with line item management"
            },
            "company_deletion_with_safety": {
                "url": "/api/delete/company",
                "method": "DELETE",
                "body": {
                    "company_id": 2,
                    "archive_instead": True
                },
                "description": "Delete company with automatic archive fallback"
            }
        }
    }
    return jsonify(endpoints)



# Reference Data Operations
@app.route('/api/vendors', methods=['GET'])
def get_vendors():
    """Get list of all vendors"""
    try:
        result = createbill.list_vendors()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/companies', methods=['GET'])
def get_companies():
    """Get list of all companies"""
    try:
        result = createBillCompanywise.list_companies()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customers', methods=['GET'])
def get_customers():
    """Get list of all customers"""
    try:
        result = createCustomer.list_customers()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/products', methods=['GET'])
def get_products():
    """Get list of all products"""
    try:
        result = createproduct.list_products()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/payments', methods=['GET'])
def get_payments():
    """Get list of all payments"""
    try:
        result = createCusomterPayments.list_payments()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vendor-payments', methods=['GET'])
def get_vendor_payments():
    """Get list of vendor payments"""
    try:
        result = createVendorPayments.list_vendor_payments()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/credit-notes', methods=['GET'])
def get_credit_notes():
    """Get list of all credit notes"""
    try:
        result = createCreditNotes.list_credit_notes()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/invoices', methods=['GET'])
def get_invoices():
    """Get list of all customer invoices"""
    try:
        result = createInvoice.list_customer_invoices()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/refunds', methods=['GET'])
def get_refunds():
    """Get list of all refunds"""
    try:
        result = createrefund.list_refunds()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bills', methods=['GET'])
def get_bills():
    """Get list of all vendor bills"""
    try:
        result = deletebill.list_vendor_bills()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/journals', methods=['GET'])
def get_journals():
    """Get list of all journals"""
    try:
        result = createjournal.list_journals()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get list of chart of accounts"""
    try:
        # Get company_id from query parameters
        company_id = request.args.get('company_id', type=int)
        
        result = createjournal.list_accounts(company_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/companies/<int:company_id>/vendors', methods=['GET'])
def get_vendors_by_company(company_id):
    """Get vendors available to a specific company"""
    try:
        result = createBillCompanywise.list_vendors_by_company(company_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vendors/<int:vendor_id>', methods=['GET'])
def get_vendor(vendor_id):
    """Get specific vendor details"""
    try:
        result = modifyvendor.get_vendor_details(vendor_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bills/<int:bill_id>', methods=['GET'])
def get_bill_details(bill_id):
    """Get specific bill details with line items"""
    try:
        result = modifybill.get_bill_details(bill_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Create Operations
@app.route('/api/create/bill', methods=['POST'])
def create_bill():
    """Create vendor bill"""
    try:
        data = request.json or {}
        result = createbill.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/create/transaction', methods=['POST'])
def create_transaction():
    """Create bank transaction"""
    try:
        data = request.json or {}
        result = createtransaction.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/getDetailsByCompany', methods=['POST'])
def get_details_by_company():
    """Get details by company ID"""
    try:
        data = request.json or {}
        result = getDetailsByCompany.get_all_company_data(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/getDetailsOfCompany', methods=['POST'])
def get_details_of_company():
    """Get details by company ID"""
    try:
        data = request.json or {}
        result = createcompany.get_company_email_partial(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/markAsPaid', methods=['POST'])
def mark_as_paid():
    """Mark journal entry as paid"""
    try:
        data = request.json or {}
        result = updateAuditStatus.mark_entry_as_paid(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/createSuspenseAccount', methods=['POST'])
def create_suspense_account():
    """Create suspense account for unallocated payments"""
    try:
        data = request.json or {}
        result = updateAuditStatus.handle_bank_suspense_transaction(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/bill-company', methods=['POST'])
def create_bill_company():
    """Create vendor bill with company selection"""
    try:
        data = request.json or {}
        result = createBillCompanywise.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/vendor', methods=['POST'])
def create_vendor():
    """Create vendor"""
    try:
        data = request.json or {}
        result = createvendor.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/company', methods=['POST'])
def create_company():
    """Create company"""
    try:
        data = request.json or {}
        result = createcompany.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/create/credit-notes', methods=['POST'])
def create_credit_notes():
    """Create credit note"""
    try:
        data = request.json or {}
        result = createCreditNotes.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/customer-payments', methods=['POST'])
def create_customer_payments():
    """Create customer payment"""
    try:
        data = request.json or {}
        result = createCusomterPayments.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/vendor-payments', methods=['POST'])
def create_vendor_payments():
    """Create vendor payment"""
    try:
        data = request.json or {}
        result = createVendorPayments.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/customer', methods=['POST'])
def create_customer():
    """Create customer"""
    try:
        data = request.json or {}
        result = createCustomer.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/invoice', methods=['POST'])
def create_invoice():
    """Create customer invoice"""
    try:
        data = request.json or {}
        result = createInvoice.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/product', methods=['POST'])
def create_product():
    """Create product"""
    try:
        data = request.json or {}
        result = createproduct.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/refund', methods=['POST'])
def create_refund():
    """Create refund"""
    try:
        data = request.json or {}
        result = createrefund.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/journal', methods=['POST'])
def create_journal():
    """Create journal entry"""
    try:
        data = request.json or {}
        result = createjournal.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Delete Operations (with smart safety features)
@app.route('/api/delete/bill', methods=['DELETE'])
def delete_bill():
    """Delete vendor bill with safety checks"""
    try:
        data = request.json or {}
        result = deletebill.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete/company', methods=['DELETE'])
def delete_company():
    """Delete company with archive fallback"""
    try:
        data = request.json or {}
        result = deletecompany.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete/vendor', methods=['DELETE'])
def delete_vendor():
    """Delete vendor with transaction validation"""
    try:
        data = request.json or {}
        result = deletevendor.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Modify Operations (with change tracking)
@app.route('/api/modify/bill', methods=['PUT'])
def modify_bill():
    """Modify vendor bill with line item management"""
    try:
        data = request.json or {}
        result = modifybill.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/modify/vendor', methods=['PUT'])
def modify_vendor():
    """Modify vendor with change tracking"""
    try:
        data = request.json or {}
        result = modifyvendor.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Utility endpoints
@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy', 
        'message': 'Complete Business Management API is running',
        'version': '4.0',
        'total_endpoints': 35
    })

@app.route('/api/test-config')
def test_config():
    """Test endpoint to verify configuration (for debugging)"""
    config_status = {
        'odoo_username': bool(os.getenv("ODOO_USERNAME")),
        'odoo_api_key': bool(os.getenv("ODOO_API_KEY")),
        'flask_debug': os.getenv('FLASK_DEBUG', 'False'),
        'port': os.environ.get('PORT', '5000')
    }
    return jsonify({
        'success': True,
        'config': config_status,
        'message': 'Configuration check complete',
        'api_version': '4.0'
    })

# Enhanced API Documentation endpoints
@app.route('/api/docs/vendor', methods=['GET'])
def vendor_docs():
    """Comprehensive vendor API documentation"""
    docs = {
        "create_vendor": {
            "endpoint": "/api/create/vendor",
            "method": "POST",
            "description": "Create a new vendor with full address support",
            "required_fields": ["name"],
            "optional_fields": [
                "email", "phone", "website", "vat", 
                "street", "city", "zip", "country_code", 
                "state_code", "payment_terms", "currency_code"
            ],
            "examples": {
                "basic": {
                    "name": "ABC Company",
                    "email": "contact@abc.com"
                },
                "comprehensive": {
                    "name": "XYZ Technologies",
                    "email": "billing@xyz.com",
                    "phone": "+1-555-123-4567",
                    "vat": "US123456789",
                    "street": "123 Tech Street",
                    "city": "San Francisco",
                    "zip": "94105",
                    "country_code": "US",
                    "state_code": "CA",
                    "payment_terms": 30,
                    "currency_code": "USD"
                }
            }
        },
        "modify_vendor": {
            "endpoint": "/api/modify/vendor",
            "method": "PUT",
            "description": "Update vendor information with change tracking",
            "required_fields": ["vendor_id"],
            "example": {
                "vendor_id": 123,
                "name": "Updated Company Name",
                "email": "new@email.com",
                "phone": "+1-555-999-8888"
            }
        },
        "delete_vendor": {
            "endpoint": "/api/delete/vendor",
            "method": "DELETE",
            "description": "Safely delete vendor with transaction validation",
            "required_fields": ["vendor_id"],
            "examples": {
                "safe_delete": {
                    "vendor_id": 123,
                    "archive_instead": True
                },
                "force_delete": {
                    "vendor_id": 123,
                    "force_delete": True
                }
            }
        }
    }
    return jsonify(docs)

@app.route('/api/docs/bill', methods=['GET'])
def bill_docs():
    """Comprehensive bill API documentation"""
    docs = {
        "create_bill": {
            "endpoint": "/api/create/bill",
            "method": "POST",
            "description": "Create a vendor bill with line items",
            "required_fields": ["vendor_id"],
            "examples": {
                "single_item": {
                    "vendor_id": 123,
                    "description": "Office supplies",
                    "amount": 1500.50,
                    "invoice_date": "2025-01-15",
                    "vendor_ref": "INV-001"
                },
                "multiple_items": {
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
                }
            }
        },
        "modify_bill": {
            "endpoint": "/api/modify/bill",
            "method": "PUT",
            "description": "Modify vendor bill with line item management",
            "required_fields": ["bill_id"],
            "example": {
                "bill_id": 456,
                "reference": "Updated reference",
                "line_items": [
                    {
                        "line_id": 789,
                        "description": "Updated description",
                        "price_unit": 175.00
                    }
                ],
                "add_line_item": {
                    "description": "Additional service",
                    "quantity": 1,
                    "price_unit": 300.00
                }
            }
        },
        "delete_bill": {
            "endpoint": "/api/delete/bill",
            "method": "DELETE",
            "description": "Delete vendor bill with safety checks",
            "required_fields": ["bill_id"],
            "examples": {
                "simple_delete": {
                    "bill_id": 123
                },
                "force_delete_with_reset": {
                    "bill_id": 123,
                    "reset_to_draft": True
                }
            }
        }
    }
    return jsonify(docs)

@app.route('/api/docs/journal', methods=['GET'])
def journal_docs():
    """Comprehensive journal entry API documentation"""
    docs = {
        "create_journal": {
            "endpoint": "/api/create/journal",
            "method": "POST",
            "description": "Create a journal entry with debit/credit lines",
            "required_fields": ["line_items"],
            "optional_fields": ["journal_id", "date", "ref", "narration"],
            "validation_rules": [
                "Must have at least 2 line items",
                "Total debits must equal total credits",
                "Each line must have either debit OR credit (not both)",
                "All account_id values must exist in chart of accounts"
            ],
            "examples": {
                "simple_journal_entry": {
                    "date": "2025-01-15",
                    "ref": "JE-001",
                    "narration": "Monthly office rent payment",
                    "line_items": [
                        {
                            "account_id": 101,
                            "name": "Office rent - January 2025",
                            "debit": 1500.00,
                            "credit": 0.00
                        },
                        {
                            "account_id": 201,
                            "name": "Cash payment for rent",
                            "debit": 0.00,
                            "credit": 1500.00
                        }
                    ]
                },
                "multi_line_with_partners": {
                    "journal_id": 1,
                    "date": "2025-01-15",
                    "ref": "JE-002",
                    "narration": "Multiple expense allocation",
                    "line_items": [
                        {
                            "account_id": 102,
                            "name": "Office supplies",
                            "debit": 500.00,
                            "credit": 0.00,
                            "partner_id": 123
                        },
                        {
                            "account_id": 103,
                            "name": "Software license",
                            "debit": 800.00,
                            "credit": 0.00
                        },
                        {
                            "account_id": 201,
                            "name": "Bank payment",
                            "debit": 0.00,
                            "credit": 1300.00
                        }
                    ]
                }
            },
            "helper_endpoints": {
                "list_journals": "GET /api/journals - List all available journals",
                "list_accounts": "GET /api/accounts - List chart of accounts"
            }
        }
    }
    return jsonify(docs)

@app.route('/api/docs/payment', methods=['GET'])
def payment_docs():
    """Payment API documentation"""
    docs = {
        "customer_payments": {
            "endpoint": "/api/create/customer-payments",
            "method": "POST",
            "description": "Process customer payments (received/sent)",
            "example": {
                "payment_type": "received",
                "partner_id": 123,
                "amount": 1500.00,
                "payment_date": "2025-01-15"
            }
        },
        "vendor_payments": {
            "endpoint": "/api/create/vendor-payments",
            "method": "POST",
            "description": "Process vendor payments",
            "example": {
                "vendor_id": 123,
                "amount": 2500.00,
                "payment_date": "2025-01-15",
                "reference": "Payment for Invoice INV-2025-001"
            }
        }
    }
    return jsonify(docs)

@app.route('/api/update/audit-status', methods=['PUT'])
def update_audit_status():
    """
    Update the audit status of one or more journal entries in Odoo
    Accepts either a single object or a list of objects with transaction_id and audit_status
    """
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "No JSON body provided"}), 400

        updates = data if isinstance(data, list) else [data]

        results = []
        for item in updates:
            transaction_id = item.get("transaction_id")
            audit_status = item.get("audit_status")

            if not transaction_id or not audit_status:
                results.append({
                    "success": False,
                    "error": "Missing transaction_id or audit_status",
                    "data": item
                })
                continue

            success, result = updateAuditStatus.update_audit_status_in_odoo(transaction_id, audit_status)
            results.append({
                "transaction_id": transaction_id,
                "audit_status": audit_status,
                **result
            })

        return jsonify({
            "success": all(r.get("success") for r in results),
            "results": results
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/company/validate', methods=['POST'])
def validate_company():
    """Validate company data and optionally search Cyprus registry"""
    try:
        data = request.json or {}
        result = validatecompany.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ================================
# AUTHENTICATION ROUTES
# ================================

@app.route("/api/auth/login", methods=["POST"])
def login():
    """Authenticate user and return JWT token"""
    try:
        data = request.get_json()
        
        if not data or not data.get('username') or not data.get('password'):
            return jsonify({
                "success": False,
                "error": "Username and password are required"
            }), 400
        
        username = data['username'].strip()
        password = data['password']
        
        # Authenticate user
        result = auth.authenticate_user(username, password)
        
        if result["success"]:
            return jsonify({
                "success": True,
                "token": result["token"],
                "user": result["user"],
                "expires_in": result["expires_in"]
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": result["error"]
            }), 401
            
    except Exception as e:
        print(f"❌ Login error: {e}")
        return jsonify({
            "success": False,
            "error": "Login failed"
        }), 500

@app.route("/api/auth/refresh", methods=["POST"])
def refresh_token():
    """Refresh JWT token"""
    try:
        data = request.get_json()
        current_token = data.get('token')
        
        if not current_token:
            return jsonify({
                "success": False,
                "error": "Token is required"
            }), 400
        
        result = auth.refresh_token(current_token)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 401
            
    except Exception as e:
        print(f"❌ Token refresh error: {e}")
        return jsonify({
            "success": False,
            "error": "Token refresh failed"
        }), 500

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    """Logout user (client-side token removal)"""
    return jsonify({
        "success": True,
        "message": "Logged out successfully"
    }), 200

@app.route("/api/auth/me", methods=["GET"])
@jwt_required
def get_current_user_info():
    """Get current authenticated user information"""
    try:
        current_user = get_current_user()
        return jsonify({
            "success": True,
            "user": current_user
        }), 200
    except Exception as e:
        print(f"❌ Get user info error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get user information"
        }), 500

# ================================
# ADMIN ROUTES (Protected)
# ================================

@app.route("/api/admin/companies", methods=["GET"])
@jwt_required
@admin_required
def get_onboarding_submissions():
    """Get all company onboarding submissions for admin dashboard"""
    try:
        result = admin.get_all_companies()
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        print(f"❌ Admin get onboarding submissions error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to retrieve onboarding submissions"
        }), 500

@app.route("/api/admin/companies/<submission_id>", methods=["GET"])
@jwt_required
@admin_required
def get_onboarding_details(submission_id):
    """Get detailed information for a specific onboarding submission"""
    try:
        result = admin.get_company_details(submission_id)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 404 if "not found" in result["error"].lower() else 500
            
    except Exception as e:
        print(f"❌ Admin get onboarding details error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to retrieve onboarding details"
        }), 500

@app.route("/api/admin/companies/<submission_id>/approve", methods=["PUT"])
@jwt_required
@admin_required
def approve_onboarding_submission(submission_id):
    """Approve a company onboarding submission"""
    try:
        current_user = get_current_user()
        admin_username = current_user['username']
        admin_email = current_user['email']
        
        result = admin.approve_company(submission_id, admin_username, admin_email)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Admin approve onboarding submission error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to approve onboarding submission"
        }), 500

@app.route("/api/admin/companies/<submission_id>/reject", methods=["PUT"])
@jwt_required
@admin_required
def reject_onboarding_submission(submission_id):
    """Reject a company onboarding submission"""
    try:
        data = request.get_json()
        reason = data.get('reason', 'No reason provided')
        
        current_user = get_current_user()
        admin_username = current_user['username']
        
        result = admin.reject_company(submission_id, admin_username, reason)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Admin reject onboarding submission error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to reject onboarding submission"
        }), 500

@app.route("/api/admin/companies/<submission_id>/files", methods=["PUT"])
def update_submission_files(submission_id):
    """Update the files field for a specific onboarding submission"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "JSON body is required"
            }), 400
        
        files_data = data.get('files')
        
        if not files_data:
            return jsonify({
                "success": False,
                "error": "files field is required in request body"
            }), 400
        
        result = admin.update_submission_files(submission_id, files_data)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Update submission files error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to update submission files"
        }), 500

@app.route("/api/admin/companies/<submission_id>/documents", methods=["GET"])
@jwt_required
@admin_required
def get_company_documents_endpoint(submission_id):
    """Get documents for a specific company submission"""
    try:
        result = admin.get_company_documents(submission_id)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 404 if "not found" in result["error"].lower() else 500
            
    except Exception as e:
        print(f"❌ Get company documents error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to retrieve documents"
        }), 500

# ================================
# USER ROUTES (Protected)
# ================================

@app.route("/api/user/profile", methods=["GET"])
@jwt_required
def get_user_profile():
    """Get current user's profile information"""
    try:
        current_user = get_current_user()
        
        return jsonify({
            "success": True,
            "profile": current_user
        }), 200
        
    except Exception as e:
        print(f"❌ Get user profile error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get user profile"
        }), 500

@app.route("/api/onboarding", methods=["POST"])
def onboard_company():
    """Handle company onboarding form submission and forward to n8n"""
    try:
        result = onboarding.main(request.form, request.files.getlist("files"))
        status_code = 200 if result.get("status") == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# ================================
# UPLOAD AND BATCH ROUTES (No Duplicates)
# ================================

@app.route("/api/upload", methods=["POST"])
@jwt_required
def upload_files():
    """Upload files with batch tracking"""
    try:
        current_user = get_current_user()
        files = request.files.getlist("files")
        
        if not files:
            return jsonify({
                "status": "error", 
                "error": "No files uploaded"
            }), 400
        
        # Prepare form data with user context
        form_data = {
            'company_name': current_user['company_name'],
            'email': current_user['email'],
            'user_id': current_user['username'],
            'company_id': current_user.get('company_id', '')
        }
        
        # Call upload.main which now handles batch creation
        result = upload.main(form_data, files)
        
        status_code = 200 if result.get("status") == "success" else 500
        return jsonify(result), status_code
        
    except Exception as e:
        return jsonify({
            "status": "error", 
            "error": str(e)
        }), 500

@app.route("/api/batches", methods=["GET"])
@jwt_required
def get_user_batches():
    """Get current user's batches for smart polling"""
    try:
        current_user = get_current_user()
        result = upload.get_user_batches(current_user['username'])
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/batches/<batch_id>/status", methods=["PUT"])
def update_batch_status_endpoint(batch_id):
    """Update batch status (called by n8n) - No auth required for n8n"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "JSON body is required"
            }), 400
        
        # Call the batchupdate function
        result = batchupdate.update_batch_status(batch_id, data)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Update batch status error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to update batch status"
        }), 500
    
@app.route("/api/batches/<batch_id>/file-status", methods=["PUT"])
def update_file_status_endpoint(batch_id):
    """Update individual file status within a batch (called by n8n) - No auth required for n8n"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "JSON body is required"
            }), 400
        
        # Validate required fields
        file_id = data.get('file_id')
        if not file_id:
            return jsonify({
                "success": False,
                "error": "file_id is required in request body"
            }), 400
        
        # Extract file status data (status and document_type)
        file_status_data = {}
        
        if 'status' in data:
            allowed_statuses = ['uploaded', 'processing', 'complete', 'pending', 'error']
            if data['status'] in allowed_statuses:
                file_status_data['status'] = data['status']
            else:
                return jsonify({
                    "success": False,
                    "error": f"Invalid status. Must be one of: {allowed_statuses}"
                }), 400
        
        if 'document_type' in data:
            allowed_types = ['bill', 'invoice', 'bank_statement', 'legal_document', 'unknown']
            if data['document_type'] in allowed_types:
                file_status_data['document_type'] = data['document_type']
            else:
                return jsonify({
                    "success": False,
                    "error": f"Invalid document_type. Must be one of: {allowed_types}"
                }), 400
        
        if not file_status_data:
            return jsonify({
                "success": False,
                "error": "At least one of 'status' or 'document_type' must be provided"
            }), 400
        
        # Call the batchupdate function
        result = batchupdate.update_file_status(batch_id, file_id, file_status_data)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Update file status error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to update file status"
        }), 500


    

# ================================
# CLAUDE ENDPOINTS
# ================================

@app.route('/api/classify-document', methods=['POST'])
def classify_document():
    """
    N8N HTTP Request endpoint for document classification
    
    Expected JSON body:
    {
        "company_name": "ENAMI LIMITED",
        "s3_key": "clients/ENAMI LIMITED/invoice_2025_0445.pdf",
        "bucket_name": "company-documents-2025"  // Optional
    }
    
    Returns:
    {
        "success": true,
        "result": {
            "document_type": "bill",
            "category": "money_going_out", 
            "company_name": "ENAMI LIMITED",
            "total_amount": 892.50
        }
    }
    """
    try:
        # Validate request
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Request must be JSON"
            }), 400
        
        data = request.get_json()
        
        # Call the classification function
        result = classifydocument.main(data)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Classify document endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500

@app.route('/api/classify-document/health', methods=['GET'])
def classify_document_health():
    """Health check endpoint for document classification service"""
    try:
        result = classifydocument.health_check()
        status_code = 200 if result.get("healthy") else 503
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({
            "healthy": False,
            "error": str(e)
        }), 503
    
@app.route('/api/split-document', methods=['POST'])
def split_document():
    """
    Split multi-invoice PDF documents into individual invoices with OCR extraction
    
    Expected JSON body:
    {
        "s3_key": "clients/Company Name/merged-invoices.pdf",
        "bucket_name": "company-documents-2025"  // Optional
    }
    
    Returns:
    {
        "success": true,
        "invoices": [
            {
                "invoice_index": 1,
                "page_range": "1-2",
                "raw_text": "Complete OCR text from pages 1-2..."
            },
            {
                "invoice_index": 2,
                "page_range": "3-3",
                "raw_text": "Complete OCR text from page 3..."
            }
        ],
        "total_invoices": 2
    }
    """
    try:
        # Validate request
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Request must be JSON"
            }), 400
        
        data = request.get_json()
        
        # Call the splitting function
        result = splitinvoice.main(data)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Split document endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@app.route('/api/split-document/health', methods=['GET'])
def split_document_health():
    """Health check endpoint for document splitting service"""
    try:
        result = splitinvoice.health_check()
        status_code = 200 if result.get("healthy") else 503
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({
            "healthy": False,
            "error": str(e)
        }), 503
    
@app.route('/api/process_transaction', methods=['POST'])
def process_transaction_document():
    """
     PDF documents into individual invoices with OCR extraction
    """
    try:
        # Validate request
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Request must be JSON"
            }), 400
        
        data = request.get_json()
        
        # Call the splitting function
        result = processtransaction.main(data)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Process Transaction endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@app.route('/api/matching_workflow', methods=['POST'])
def matching_workflow_dynamodb():
    """
     PDF documents into individual invoices with OCR extraction
    """
    try:
        # Validate request
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Request must be JSON"
            }), 400
        
        data = request.get_json()
        
        # Call the splitting function
        result = matchingworkflow.main(data)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Matching Workflow endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500
    
# Add this import at the top of your app.py file


# Add this route to your app.py file
@app.route('/api/process-bill', methods=['POST'])
def process_bill_endpoint():
    """
    Process multi-invoice PDF documents into structured vendor bill data
    Combines document splitting and data extraction in one operation
    
    Expected JSON body:
    {
        "s3_key": "clients/Company Name/vendor-bills.pdf",
        "company_name": "ACME Corporation Ltd",
        "bucket_name": "company-documents-2025"  // Optional
    }
    
    Returns:
    {
        "success": true,
        "total_bills": 3,
        "bills": [
            {
                "bill_index": 1,
                "page_range": "1-1",
                "document_classification": {
                    "document_type": "vendor_bill",
                    "company_position": "recipient",
                    "direction_confidence": "high",
                    "detection_details": "Company found in 'Bill To' section"
                },
                "company_validation": {
                    "expected_company": "ACME Corporation Ltd",
                    "found_companies": ["ACME Corporation Ltd", "Supplier Inc"],
                    "company_match": "exact_match",
                    "match_details": "Exact match found in billing address"
                },
                "company_data": {
                    "name": "ACME Corporation Ltd",
                    "email": "billing@acme.com",
                    "phone": "+1234567890",
                    "street": "123 Business Ave",
                    "city": "Business City",
                    "zip": "12345",
                    "country_code": "US"
                },
                "vendor_data": {
                    "name": "Supplier Inc",
                    "email": "invoices@supplier.com",
                    "phone": "+0987654321",
                    "street": "456 Vendor St",
                    "city": "Supplier Town",
                    "zip": "67890",
                    "country_code": "US",
                    "invoice_date": "2025-03-15",
                    "due_date": "2025-04-15",
                    "vendor_ref": "INV-2025-001",
                    "payment_reference": "PAY-REF-12345",
                    "subtotal": 1000.00,
                    "tax_amount": 100.00,
                    "total_amount": 1100.00,
                    "currency_code": "USD",
                    "line_items": [
                        {
                            "description": "Professional Services - March 2025",
                            "quantity": 1,
                            "price_unit": 1000.00,
                            "line_total": 1000.00,
                            "tax_rate": 10.0
                        }
                    ]
                },
                "extraction_confidence": {
                    "vendor_name": "high",
                    "total_amount": "high",
                    "line_items": "medium",
                    "dates": "high",
                    "company_validation": "high",
                    "document_classification": "high"
                },
                "missing_fields": []
            }
            // Additional bills...
        ],
        "processing_summary": {
            "bills_processed": 3,
            "bills_with_issues": 0,
            "success_rate": "100.0%"
        },
        "validation_results": [
            {
                "bill_index": 1,
                "issues": [],
                "warnings": [],
                "mandatory_fields_present": true
            }
            // Additional validation results...
        ],
        "metadata": {
            "company_name": "ACME Corporation Ltd",
            "s3_key": "clients/Company Name/vendor-bills.pdf",
            "token_usage": {
                "input_tokens": 2500,
                "output_tokens": 1800
            }
        }
    }
    
    Error Response:
    {
        "success": false,
        "error": "Missing required fields: company_name",
        "details": "Additional error context if available"
    }
    """
    try:
        # Validate request format
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Request must be JSON",
                "details": "Content-Type must be application/json"
            }), 400
        
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return jsonify({
                "success": False,
                "error": "Empty request body",
                "details": "JSON body is required"
            }), 400
        
        required_fields = ['s3_key', 'company_name']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                "success": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}",
                "details": f"Required fields are: {', '.join(required_fields)}"
            }), 400
        
        # Validate field types and values
        if not isinstance(data['s3_key'], str) or not data['s3_key'].strip():
            return jsonify({
                "success": False,
                "error": "Invalid s3_key",
                "details": "s3_key must be a non-empty string"
            }), 400
            
        if not isinstance(data['company_name'], str) or not data['company_name'].strip():
            return jsonify({
                "success": False,
                "error": "Invalid company_name", 
                "details": "company_name must be a non-empty string"
            }), 400
        
        # Optional bucket_name validation
        if 'bucket_name' in data and (not isinstance(data['bucket_name'], str) or not data['bucket_name'].strip()):
            return jsonify({
                "success": False,
                "error": "Invalid bucket_name",
                "details": "bucket_name must be a non-empty string if provided"
            }), 400
        
        # Log processing start
        print(f"🏭 Processing bills for company: {data['company_name']}")
        print(f"📄 S3 document: {data['s3_key']}")
        
        # Call the bill processing function
        result = process_bill.main(data)
        
        # Handle successful processing
        if result["success"]:
            # Log success metrics
            total_bills = result.get("total_bills", 0)
            bills_with_issues = result.get("processing_summary", {}).get("bills_with_issues", 0)
            success_rate = result.get("processing_summary", {}).get("success_rate", "0%")
            
            print(f"✅ Successfully processed {total_bills} bills")
            print(f"📊 Success rate: {success_rate}")
            if bills_with_issues > 0:
                print(f"⚠️  Bills with issues: {bills_with_issues}")
            
            # Return successful response
            return jsonify(result), 200
        else:
            # Log processing failure
            error_msg = result.get("error", "Unknown error")
            print(f"❌ Bill processing failed: {error_msg}")
            
            # Return error response with appropriate status code
            status_code = 422 if "validation" in error_msg.lower() else 500
            
            return jsonify({
                "success": False,
                "error": error_msg,
                "details": result.get("raw_response", "No additional details available")[:200] if result.get("raw_response") else None
            }), status_code
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        return jsonify({
            "success": False,
            "error": "Invalid JSON format",
            "details": str(e)
        }), 400
        
    except Exception as e:
        print(f"❌ Process bill endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "details": "An unexpected error occurred while processing the request"
        }), 500

# Add this health check endpoint as well
@app.route('/api/process-bill/health', methods=['GET'])
def process_bill_health():
    """
    Health check endpoint for the bill processing service
    
    Returns:
    {
        "healthy": true,
        "service": "claude-bill-processing",
        "version": "2.0",
        "capabilities": [
            "document_splitting",
            "data_extraction", 
            "company_validation",
            "monetary_calculation",
            "confidence_scoring"
        ],
        "anthropic_configured": true,
        "aws_configured": true,
        "s3_bucket": "company-documents-2025"
    }
    """
    try:
        result = process_bill.health_check()
        
        if result["healthy"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 503
            
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return jsonify({
            "healthy": False,
            "error": "Health check failed",
            "details": str(e)
        }), 503

@app.route('/api/process-invoice', methods=['POST'])
def process_invoice_endpoint():
    """
    Process multi-invoice PDF documents into structured customer invoice data
    Combines document splitting and data extraction in one operation
    
    Expected JSON body:
    {
        "s3_key": "clients/Company Name/customer-invoices.pdf",
        "company_name": "ACME Corporation Ltd",
        "bucket_name": "company-documents-2025"  // Optional
    }
    
    Returns:
    {
        "success": true,
        "total_invoices": 3,
        "invoices": [
            {
                "invoice_index": 1,
                "page_range": "1-1",
                "document_classification": {
                    "document_type": "customer_invoice",
                    "company_position": "issuer",
                    "direction_confidence": "high",
                    "detection_details": "Company found in 'From' section"
                },
                "company_validation": {
                    "expected_company": "ACME Corporation Ltd",
                    "found_companies": ["ACME Corporation Ltd", "Customer Inc"],
                    "company_match": "exact_match",
                    "match_details": "Exact match found in issuer address"
                },
                "company_data": {
                    "name": "ACME Corporation Ltd",
                    "email": "invoices@acme.com",
                    "phone": "+1234567890",
                    "street": "123 Business Ave",
                    "city": "Business City",
                    "zip": "12345",
                    "country_code": "US"
                },
                "customer_data": {
                    "name": "Customer Inc",
                    "email": "billing@customer.com",
                    "phone": "+0987654321",
                    "street": "456 Customer St",
                    "city": "Customer Town",
                    "zip": "67890",
                    "country_code": "US",
                    "invoice_date": "2025-03-15",
                    "due_date": "2025-04-15",
                    "invoice_ref": "INV-2025-001",
                    "payment_reference": "PAY-REF-12345",
                    "description": "Professional Services - March 2025",
                    "subtotal": 1000.00,
                    "tax_amount": 100.00,
                    "total_amount": 1100.00,
                    "currency_code": "USD",
                    "line_items": [
                        {
                            "description": "Professional Services - March 2025",
                            "quantity": 1,
                            "price_unit": 1000.00,
                            "line_total": 1000.00,
                            "tax_rate": 10.0
                        }
                    ]
                },
                "accounting_assignment": {
                    "debit_account": "1100",
                    "debit_account_name": "Accounts receivable",
                    "credit_account": "4000",
                    "credit_account_name": "Service revenue",
                    "vat_treatment": "standard_vat",
                    "requires_reverse_charge": false,
                    "additional_entries": [
                        {
                            "account_code": "2201",
                            "account_name": "Output VAT",
                            "debit_amount": 0,
                            "credit_amount": 100.00,
                            "description": "Output VAT 10%"
                        }
                    ]
                },
                "extraction_confidence": {
                    "customer_name": "high",
                    "total_amount": "high",
                    "line_items": "medium",
                    "dates": "high",
                    "company_validation": "high",
                    "document_classification": "high"
                },
                "missing_fields": []
            }
            // Additional invoices...
        ],
        "processing_summary": {
            "invoices_processed": 3,
            "invoices_with_issues": 0,
            "success_rate": "100.0%"
        },
        "validation_results": [
            {
                "invoice_index": 1,
                "issues": [],
                "warnings": [],
                "mandatory_fields_present": true
            }
            // Additional validation results...
        ],
        "metadata": {
            "company_name": "ACME Corporation Ltd",
            "s3_key": "clients/Company Name/customer-invoices.pdf",
            "token_usage": {
                "input_tokens": 2500,
                "output_tokens": 1800
            }
        }
    }
    
    Error Response:
    {
        "success": false,
        "error": "Missing required fields: company_name",
        "details": "Additional error context if available"
    }
    """
    try:
        # Validate request format
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Request must be JSON",
                "details": "Content-Type must be application/json"
            }), 400
        
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return jsonify({
                "success": False,
                "error": "Empty request body",
                "details": "JSON body is required"
            }), 400
        
        required_fields = ['s3_key', 'company_name']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                "success": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}",
                "details": f"Required fields are: {', '.join(required_fields)}"
            }), 400
        
        # Validate field types and values
        if not isinstance(data['s3_key'], str) or not data['s3_key'].strip():
            return jsonify({
                "success": False,
                "error": "Invalid s3_key",
                "details": "s3_key must be a non-empty string"
            }), 400
            
        if not isinstance(data['company_name'], str) or not data['company_name'].strip():
            return jsonify({
                "success": False,
                "error": "Invalid company_name", 
                "details": "company_name must be a non-empty string"
            }), 400
        
        # Optional bucket_name validation
        if 'bucket_name' in data and (not isinstance(data['bucket_name'], str) or not data['bucket_name'].strip()):
            return jsonify({
                "success": False,
                "error": "Invalid bucket_name",
                "details": "bucket_name must be a non-empty string if provided"
            }), 400
        
        # Log processing start
        print(f"📋 Processing invoices for company: {data['company_name']}")
        print(f"📄 S3 document: {data['s3_key']}")
        
        # Call the invoice processing function
        result = process_invoice.main(data)
        
        # Handle successful processing
        if result["success"]:
            # Log success metrics
            total_invoices = result.get("total_invoices", 0)
            invoices_with_issues = result.get("processing_summary", {}).get("invoices_with_issues", 0)
            success_rate = result.get("processing_summary", {}).get("success_rate", "0%")
            
            print(f"✅ Successfully processed {total_invoices} invoices")
            print(f"📊 Success rate: {success_rate}")
            if invoices_with_issues > 0:
                print(f"⚠️  Invoices with issues: {invoices_with_issues}")
            
            # Return successful response
            return jsonify(result), 200
        else:
            # Log processing failure
            error_msg = result.get("error", "Unknown error")
            print(f"❌ Invoice processing failed: {error_msg}")
            
            # Return error response with appropriate status code
            status_code = 422 if "validation" in error_msg.lower() else 500
            
            return jsonify({
                "success": False,
                "error": error_msg,
                "details": result.get("raw_response", "No additional details available")[:200] if result.get("raw_response") else None
            }), status_code
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        return jsonify({
            "success": False,
            "error": "Invalid JSON format",
            "details": str(e)
        }), 400
        
    except Exception as e:
        print(f"❌ Process invoice endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "details": "An unexpected error occurred while processing the request"
        }), 500



# ================================
# HELPER FUNCTIONS
# ================================

@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "bookkeeping-backend"
    }), 200

# Error handlers
@app.errorhandler(401)
def unauthorized(error):
    return jsonify({
        "success": False,
        "error": "Authentication required"
    }), 401

@app.errorhandler(403)
def forbidden(error):
    return jsonify({
        "success": False,
        "error": "Insufficient permissions"
    }), 403

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
    port = int(os.environ.get('PORT', 8080))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=True)