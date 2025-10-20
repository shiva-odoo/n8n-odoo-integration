from flask import Flask, request, jsonify, make_response
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
import createsharetransaction
import process_share_documents
import processonboardingdoc
import update_transactions_table as transactions
import update_bills_table as bills
import update_invoices_table as invoices
import update_share_transactions_table as share_transactions
import update_payroll_transactions_table as payroll_transactions
import reports
import process_payroll
import dashboard
import company_profile
import bank_reconciliation
import compliance
import create_payroll_transaction as createpayrolltransaction


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
        "message": "Complete Business Management API with Portal Features",
        "version": "5.0",
        "total_endpoints": 50,
        "available_endpoints": {
            "Authentication (4 endpoints)": {
                "/api/auth/login": "POST - User login with JWT",
                "/api/auth/refresh": "POST - Refresh JWT token",
                "/api/auth/logout": "POST - User logout",
                "/api/auth/me": "GET - Get current user info"
            },
            "Dashboard (3 endpoints)": {
                "/api/dashboard/metrics": "GET - Dashboard metrics (documents, revenue, compliance)",
                "/api/dashboard/recent-documents": "GET - Recent documents list",
                "/api/dashboard/compliance-items": "GET - Compliance items for dashboard"
            },
            "Company Profile (2 endpoints)": {
                "/api/company/profile": "GET - Get company profile",
                "/api/company/profile": "PUT/POST - Update company profile"
            },
            "Bank Reconciliation (3 endpoints)": {
                "/api/bank/transactions": "GET - Bank transactions for reconciliation",
                "/api/bank/accounts": "GET - Bank accounts list",
                "/api/bank/reconcile": "POST - Reconcile a transaction"
            },
            "Compliance Center (4 endpoints)": {
                "/api/compliance/items": "GET - Get compliance items",
                "/api/compliance/items": "POST - Create compliance item",
                "/api/compliance/items/<id>": "PUT - Update compliance item",
                "/api/compliance/items/<id>": "DELETE - Delete compliance item"
            },
            "PDF Extraction (4 endpoints)": {
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
    
@app.route('/api/bills/<int:bill_id>', methods=['GET'])
def get_detailed_bills(bill_id):
    """Get detailed information for a specific vendor bill"""
    try:
        # Validate bill_id
        if not bill_id or bill_id <= 0:
            return jsonify({
                'success': False, 
                'error': 'Invalid bill ID provided'
            }), 400
        
        # Call the function to get bill details
        result = deletebill.get_vendor_bill_details(bill_id)
        
        # Return appropriate HTTP status based on result
        if result['success']:
            return jsonify(result), 200
        else:
            # Check if it's a "not found" error
            if 'not found' in result.get('error', '').lower():
                return jsonify(result), 404
            else:
                return jsonify(result), 500
                
    except ValueError:
        return jsonify({
            'success': False, 
            'error': 'Bill ID must be a valid integer'
        }), 400
    except Exception as e:
        return jsonify({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }), 500
    

@app.route('/api/invoices/<int:invoice_id>', methods=['GET'])
def get_detailed_invoice(invoice_id):
    """Get detailed information for a specific customer invoice"""
    try:
        # Validate invoice_id
        if not invoice_id or invoice_id <= 0:
            return jsonify({
                'success': False, 
                'error': 'Invalid invoice ID provided'
            }), 400
        
        # Call the function to get invoice details
        result = createproduct.get_customer_invoice_details(invoice_id)
        
        # Return appropriate HTTP status based on result
        if result['success']:
            return jsonify(result), 200
        else:
            # Check if it's a "not found" error
            if 'not found' in result.get('error', '').lower():
                return jsonify(result), 404
            else:
                return jsonify(result), 500
                
    except ValueError:
        return jsonify({
            'success': False, 
            'error': 'Invoice ID must be a valid integer'
        }), 400
    except Exception as e:
        return jsonify({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }), 500


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
# DASHBOARD ROUTES (Protected)
# ================================

@app.route("/api/dashboard/metrics", methods=["GET"])
@jwt_required
def get_dashboard_metrics():
    """Get dashboard metrics for the current user's company"""
    try:
        current_user = get_current_user()
        username = current_user.get('username')
        company_name = current_user.get('company_name')
        
        # IMPORTANT: Get business_company_id from query parameter (sent by frontend)
        # This is the company ID from DynamoDB onboarding_submissions (e.g., "139", "124", "125")
        business_company_id = request.args.get('company_id')
        
        # Fallback to JWT business_company_id if not provided in query
        if not business_company_id:
            business_company_id = current_user.get('business_company_id')
        
        if not business_company_id:
            return jsonify({
                "success": False,
                "error": "Company ID (business_company_id) is required. Please provide ?company_id=XXX"
            }), 400
        
        print(f"📊 Dashboard metrics for business_company_id: {business_company_id}, username: {username}")
        
        result = dashboard.get_dashboard_metrics(business_company_id, username, company_name)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        print(f"❌ Dashboard metrics error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get dashboard metrics"
        }), 500

@app.route("/api/dashboard/recent-documents", methods=["GET"])
@jwt_required
def get_recent_documents():
    """Get recent documents for the current user's company"""
    try:
        current_user = get_current_user()
        username = current_user.get('username')
        company_name = current_user.get('company_name')
        
        # IMPORTANT: Get business_company_id from query parameter (sent by frontend)
        business_company_id = request.args.get('company_id')
        
        # Fallback to JWT business_company_id if not provided in query
        if not business_company_id:
            business_company_id = current_user.get('business_company_id')
        
        if not business_company_id:
            return jsonify({
                "success": False,
                "error": "Company ID (business_company_id) is required. Please provide ?company_id=XXX"
            }), 400
        
        # Get limit from query params (default 10)
        limit = request.args.get('limit', 10, type=int)
        
        print(f"📄 Recent documents for business_company_id: {business_company_id}, username: {username}, limit: {limit}")
        
        result = dashboard.get_recent_documents(business_company_id, username, company_name, limit)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        print(f"❌ Recent documents error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get recent documents"
        }), 500

@app.route("/api/dashboard/compliance-items", methods=["GET"])
@jwt_required
def get_dashboard_compliance_items():
    """Get compliance items for dashboard"""
    try:
        current_user = get_current_user()
        username = current_user.get('username')
        company_name = current_user.get('company_name')
        
        # IMPORTANT: Get business_company_id from query parameter (sent by frontend)
        business_company_id = request.args.get('company_id')
        
        # Fallback to JWT business_company_id if not provided in query
        if not business_company_id:
            business_company_id = current_user.get('business_company_id')
        
        if not business_company_id:
            return jsonify({
                "success": False,
                "error": "Company ID (business_company_id) is required. Please provide ?company_id=XXX"
            }), 400
        
        print(f"✅ Compliance items for business_company_id: {business_company_id}, username: {username}")
        
        result = dashboard.get_compliance_items(business_company_id, username, company_name)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        print(f"❌ Dashboard compliance items error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get compliance items"
        }), 500

# ================================
# COMPANY PROFILE ROUTES (Protected)
# ================================

@app.route("/api/company/profile", methods=["GET"])
@jwt_required
def get_company_profile():
    """Get company profile for the current user"""
    try:
        current_user = get_current_user()
        company_id = current_user.get('company_id')
        username = current_user.get('username')
        
        if not company_id:
            return jsonify({
                "success": False,
                "error": "Company ID not found for user"
            }), 400
        
        result = company_profile.get_company_profile(company_id, username)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        print(f"❌ Get company profile error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get company profile"
        }), 500

@app.route("/api/company/profile", methods=["PUT", "POST"])
@jwt_required
def update_company_profile():
    """Update company profile for the current user"""
    try:
        current_user = get_current_user()
        company_id = current_user.get('company_id')
        username = current_user.get('username')
        
        if not company_id:
            return jsonify({
                "success": False,
                "error": "Company ID not found for user"
            }), 400
        
        profile_data = request.get_json()
        
        if not profile_data:
            return jsonify({
                "success": False,
                "error": "Profile data is required"
            }), 400
        
        result = company_profile.update_company_profile(company_id, username, profile_data)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Update company profile error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to update company profile"
        }), 500

# ================================
# BANK RECONCILIATION ROUTES (Protected)
# ================================

@app.route("/api/bank/transactions", methods=["GET"])
@jwt_required
def get_bank_transactions():
    """Get bank transactions for reconciliation"""
    try:
        current_user = get_current_user()
        
        # IMPORTANT: Get business_company_id from query parameter (sent by frontend)
        business_company_id = request.args.get('company_id')
        
        # Fallback to JWT business_company_id if not provided in query
        if not business_company_id:
            business_company_id = current_user.get('business_company_id')
        
        if not business_company_id:
            return jsonify({
                "success": False,
                "error": "Company ID (business_company_id) is required. Please provide ?company_id=XXX"
            }), 400
        
        # Get query parameters
        bank_account_id = request.args.get('bank_account_id')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        status = request.args.get('status')
        
        print(f"🏦 Bank transactions for business_company_id: {business_company_id}")
        
        result = bank_reconciliation.get_bank_transactions(
            business_company_id, 
            bank_account_id, 
            date_from, 
            date_to, 
            status
        )
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        print(f"❌ Get bank transactions error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get bank transactions"
        }), 500

@app.route("/api/bank/accounts", methods=["GET"])
@jwt_required
def get_bank_accounts():
    """Get bank accounts for the current user's company"""
    try:
        current_user = get_current_user()
        
        # IMPORTANT: Get business_company_id from query parameter (sent by frontend)
        business_company_id = request.args.get('company_id')
        
        # Fallback to JWT business_company_id if not provided in query
        if not business_company_id:
            business_company_id = current_user.get('business_company_id')
        
        if not business_company_id:
            return jsonify({
                "success": False,
                "error": "Company ID (business_company_id) is required. Please provide ?company_id=XXX"
            }), 400
        
        print(f"🏦 Bank accounts for business_company_id: {business_company_id}")
        
        result = bank_reconciliation.get_bank_accounts(business_company_id)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        print(f"❌ Get bank accounts error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get bank accounts"
        }), 500

@app.route("/api/bank/reconcile", methods=["POST"])
@jwt_required
def reconcile_transaction():
    """Reconcile a bank transaction"""
    try:
        current_user = get_current_user()
        username = current_user.get('username')
        
        data = request.get_json()
        
        if not data or not data.get('transaction_id'):
            return jsonify({
                "success": False,
                "error": "Transaction ID is required"
            }), 400
        
        # IMPORTANT: Get business_company_id from request body
        business_company_id = data.get('company_id') or data.get('business_company_id')
        
        # Fallback to JWT business_company_id if not provided in request
        if not business_company_id:
            business_company_id = current_user.get('business_company_id')
        
        if not business_company_id:
            return jsonify({
                "success": False,
                "error": "Company ID (business_company_id) is required in request body"
            }), 400
        
        print(f"🔄 Reconciling transaction {data['transaction_id']} for business_company_id: {business_company_id}")
        
        result = bank_reconciliation.reconcile_transaction(
            data['transaction_id'],
            business_company_id,
            data.get('matched_record_type'),
            data.get('matched_record_id'),
            username
        )
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Reconcile transaction error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to reconcile transaction"
        }), 500

# ================================
# COMPLIANCE CENTER ROUTES (Protected)
# ================================

@app.route("/api/compliance/items", methods=["GET"])
@jwt_required
def get_compliance_items():
    """Get compliance items for the current user's company"""
    try:
        current_user = get_current_user()
        company_id = current_user.get('company_id')
        
        if not company_id:
            return jsonify({
                "success": False,
                "error": "Company ID not found for user"
            }), 400
        
        status = request.args.get('status')
        
        result = compliance.get_compliance_items(company_id, status)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        print(f"❌ Get compliance items error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to get compliance items"
        }), 500

@app.route("/api/compliance/items", methods=["POST"])
@jwt_required
def create_compliance_item():
    """Create a new compliance item"""
    try:
        current_user = get_current_user()
        company_id = current_user.get('company_id')
        username = current_user.get('username')
        
        if not company_id:
            return jsonify({
                "success": False,
                "error": "Company ID not found for user"
            }), 400
        
        item_data = request.get_json()
        
        if not item_data:
            return jsonify({
                "success": False,
                "error": "Item data is required"
            }), 400
        
        result = compliance.create_compliance_item(company_id, item_data, username)
        
        if result["success"]:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Create compliance item error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to create compliance item"
        }), 500

@app.route("/api/compliance/items/<compliance_id>", methods=["PUT"])
@jwt_required
def update_compliance_item(compliance_id):
    """Update a compliance item"""
    try:
        current_user = get_current_user()
        company_id = current_user.get('company_id')
        username = current_user.get('username')
        
        if not company_id:
            return jsonify({
                "success": False,
                "error": "Company ID not found for user"
            }), 400
        
        update_data = request.get_json()
        
        if not update_data:
            return jsonify({
                "success": False,
                "error": "Update data is required"
            }), 400
        
        result = compliance.update_compliance_item(compliance_id, company_id, update_data, username)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Update compliance item error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to update compliance item"
        }), 500

@app.route("/api/compliance/items/<compliance_id>", methods=["DELETE"])
@jwt_required
def delete_compliance_item(compliance_id):
    """Delete a compliance item"""
    try:
        current_user = get_current_user()
        company_id = current_user.get('company_id')
        
        if not company_id:
            return jsonify({
                "success": False,
                "error": "Company ID not found for user"
            }), 400
        
        result = compliance.delete_compliance_item(compliance_id, company_id)
        
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"❌ Delete compliance item error: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to delete compliance item"
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
    

    
@app.route('/api/process/onboarding_doc/<submission_id>', methods=['POST'])
def process_onboarding_document(submission_id):
    """Process onboarding document and update company information"""
    try:
        data = request.json or {}
        
        # Process the onboarding document(s) to extract company information
        result = processonboardingdoc.process_onboarding_document(data)
        
        # Check if processing was successful
        if isinstance(result, dict) and result.get('success') == False:
            # Processing failed, return the error
            return jsonify(result), 400
        
        # Remove metadata before updating (it's not a company field)
        company_data = {k: v for k, v in result.items() if k != '_metadata'}
        
        # Update the company information in the database
        # This will automatically exclude name, email, and company_registry
        update_result = admin.update_company_info(submission_id, company_data)
        
        if not update_result.get('success', False):
            # Update failed
            return jsonify({
                'success': False,
                'error': 'Document processed successfully but failed to update database',
                'processing_result': result,
                'update_error': update_result.get('error')
            }), 500
        
        # Both processing and updating were successful
        return jsonify({
            'success': True,
            'message': 'Document processed and company information updated successfully',
            'submission_id': submission_id,
            'extracted_data': result,
            'update_result': {
                'updated_fields': update_result.get('updated_fields', []),
                'excluded_fields': update_result.get('excluded_fields', [])
            }
        })
        
    except Exception as e:
        print(f"❌ API error processing onboarding document: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'Internal server error: {str(e)}'
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
    """Upload files with batch tracking - NOW CHECKS UPLOAD_READY"""
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
        
        # Call upload.main which now handles:
        # 1. Upload ready check (NEW)
        # 2. Batch creation
        # 3. n8n forwarding
        result = upload.main(form_data, files)
        
        # Handle PROFILE_INCOMPLETE error specifically
        if result.get("error_code") == "PROFILE_INCOMPLETE":
            return jsonify(result), 403  # Forbidden - profile incomplete
        
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
            allowed_types = ['bill', 'invoice', 'bank_statement', 'share_document', 'unknown']
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
    
@app.route('/api/process-share-document', methods=['POST'])
def process_share_document_endpoint():
    """
    Process multi-document PDF containing share capital transactions into structured data
    Combines document splitting and data extraction in one operation
    
    Expected JSON body:
    {
        "s3_key": "clients/Company Name/share-allotments.pdf",
        "company_name": "ACME Corporation Ltd",
        "bucket_name": "company-documents-2025"  // Optional
    }
    
    Returns:
    {
        "success": true,
        "total_transactions": 2,
        "transactions": [
            {
                "transaction_index": 1,
                "page_range": "1",
                "document_classification": {
                    "document_type": "share_capital_transaction",
                    "company_position": "issuer",
                    "direction_confidence": "high",
                    "detection_details": "Share allotment resolution detected"
                },
                "company_validation": {
                    "expected_company": "ACME Corporation Ltd",
                    "found_companies": ["ACME Corporation Ltd"],
                    "company_match": "exact_match",
                    "match_details": "Exact match found in issuer details"
                },
                "company_data": {
                    "name": "ACME Corporation Ltd",
                    "email": "shares@acme.com",
                    "phone": "+1234567890",
                    "street": "123 Business Ave",
                    "city": "Business City",
                    "zip": "12345",
                    "country_code": "US"
                },
                "partner_data": {
                    "name": "John Alexander Smith",
                    "email": "j.smith@email.com",
                    "phone": "+357 99 987654",
                    "street": "45 Investment Street",
                    "city": "Limassol",
                    "zip": "3456",
                    "country_code": "CY",
                    "transaction_date": "2025-01-15",
                    "due_date": "2025-02-15",
                    "transaction_ref": "SA-2025-001",
                    "payment_reference": "SHARE-ALLOT-001",
                    "description": "Allotment of 15,000 ordinary shares at €1.00 nominal value each",
                    "subtotal": 15000.00,
                    "tax_amount": 0.00,
                    "total_amount": 15000.00,
                    "currency_code": "EUR",
                    "share_details": [
                        {
                            "share_type": "Ordinary",
                            "number_of_shares": 15000,
                            "nominal_value_per_share": 1.00,
                            "total_value": 15000.00,
                            "description": "15,000 ordinary shares with voting rights"
                        }
                    ]
                },
                "accounting_assignment": {
                    "debit_account": "1100",
                    "debit_account_name": "Accounts receivable",
                    "credit_account": "3000",
                    "credit_account_name": "Share Capital",
                    "vat_treatment": "",
                    "requires_reverse_charge": false,
                    "additional_entries": []
                },
                "extraction_confidence": {
                    "partner_name": "high",
                    "total_amount": "high",
                    "share_details": "high",
                    "dates": "medium",
                    "company_validation": "high",
                    "document_classification": "high"
                },
                "missing_fields": []
            }
            // Additional transactions...
        ],
        "processing_summary": {
            "transactions_processed": 2,
            "transactions_with_issues": 0,
            "success_rate": "100.0%"
        },
        "validation_results": [
            {
                "transaction_index": 1,
                "issues": [],
                "warnings": [],
                "mandatory_fields_present": true,
                "structure_complete": true
            }
            // Additional validation results...
        ],
        "metadata": {
            "company_name": "ACME Corporation Ltd",
            "s3_key": "clients/Company Name/share-allotments.pdf",
            "token_usage": {
                "input_tokens": 3245,
                "output_tokens": 1876
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
        print(f"📈 Processing share transactions for company: {data['company_name']}")
        print(f"📄 S3 document: {data['s3_key']}")
        
        # Call the share document processing function
        result = process_share_documents.main(data)
        
        # Handle successful processing
        if result["success"]:
            # Log success metrics
            total_transactions = result.get("total_transactions", 0)
            transactions_with_issues = result.get("processing_summary", {}).get("transactions_with_issues", 0)
            success_rate = result.get("processing_summary", {}).get("success_rate", "0%")
            
            print(f"✅ Successfully processed {total_transactions} share transactions")
            print(f"📊 Success rate: {success_rate}")
            if transactions_with_issues > 0:
                print(f"⚠️  Transactions with issues: {transactions_with_issues}")
            
            # Return successful response
            return jsonify(result), 200
        else:
            # Log processing failure
            error_msg = result.get("error", "Unknown error")
            print(f"❌ Share transaction processing failed: {error_msg}")
            
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
        print(f"❌ Process share document endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "details": "An unexpected error occurred while processing the request"
        }), 500
    
@app.route('/api/process-payroll-document', methods=['POST'])
def process_payroll_document_endpoint():
    """
    Process payroll document into structured journal entry data
    Extracts consolidated payroll journal entry from payroll document
    
    Expected JSON body:
    {
        "s3_key": "clients/Company Name/payroll-june-2025.pdf",
        "company_name": "ACME Corporation Ltd",
        "bucket_name": "company-documents-2025"  // Optional
    }
    
    Returns:
    {
        "success": true,
        "payroll_data": {
            "period": "June 2025",
            "month": "June",
            "year": "2025",
            "pay_date": "2025-06-30",
            "num_employees": 3,
            "currency_code": "EUR",
            "description": "Payroll for June 2025 - 3 employees: Gross wages €1,050.00, Staff bonus €27.83, Net wages payable €929.77",
            "total_gross_wages": 1050.00,
            "total_net_wages": 929.77,
            "total_deductions": 92.40,
            "total_employer_contributions": 66.00,
            "journal_entry_lines": [
                {
                    "account_code": "7000",
                    "account_name": "Gross wages",
                    "description": "Total gross salaries for June 2025",
                    "debit_amount": 1050.00,
                    "credit_amount": 0
                },
                {
                    "account_code": "7003",
                    "account_name": "Staff bonus",
                    "description": "Total staff bonuses for June 2025",
                    "debit_amount": 27.83,
                    "credit_amount": 0
                },
                {
                    "account_code": "7006",
                    "account_name": "Employers n.i.",
                    "description": "Employer social insurance contribution (~8.3%)",
                    "debit_amount": 66.00,
                    "credit_amount": 0
                },
                {
                    "account_code": "2210",
                    "account_name": "PAYE/NIC",
                    "description": "Total social insurance payable (employee 92.40 + employer 66.00)",
                    "debit_amount": 0,
                    "credit_amount": 158.40
                },
                {
                    "account_code": "2250",
                    "account_name": "Net wages",
                    "description": "Total net wages payable to all employees",
                    "debit_amount": 0,
                    "credit_amount": 929.77
                }
            ]
        },
        "company_validation": {
            "expected_company": "ACME Corporation Ltd",
            "found_company": "ACME Corporation Ltd",
            "company_match": "exact_match",
            "match_details": "Exact match found in payroll document header"
        },
        "extraction_confidence": {
            "period_info": "high",
            "amounts": "high",
            "employee_count": "high",
            "company_validation": "high"
        },
        "validation_summary": {
            "debits_equal_credits": true,
            "total_debits": 1143.83,
            "total_credits": 1143.83,
            "balance_difference": 0.00
        },
        "validation_results": {
            "issues": [],
            "warnings": [],
            "data_complete": true,
            "accounting_balanced": true
        },
        "processing_summary": {
            "data_complete": true,
            "accounting_balanced": true,
            "issues_count": 0,
            "warnings_count": 0,
            "processing_success": true
        },
        "metadata": {
            "company_name": "ACME Corporation Ltd",
            "company_context_loaded": true,
            "expected_employees": 3,
            "payroll_frequency": "Monthly",
            "s3_key": "clients/Company Name/payroll-june-2025.pdf",
            "token_usage": {
                "input_tokens": 2845,
                "output_tokens": 1456
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
        print(f"💰 Processing payroll document for company: {data['company_name']}")
        print(f"📄 S3 document: {data['s3_key']}")
        
        # Call the payroll document processing function
        result = process_payroll.main(data)
        
        # Handle successful processing
        if result["success"]:
            # Log success metrics
            payroll_data = result.get("payroll_data", {})
            period = payroll_data.get("period", "Unknown")
            num_employees = payroll_data.get("num_employees", 0)
            total_gross = payroll_data.get("total_gross_wages", 0)
            total_net = payroll_data.get("total_net_wages", 0)
            
            validation_summary = result.get("validation_summary", {})
            accounting_balanced = validation_summary.get("debits_equal_credits", False)
            
            processing_summary = result.get("processing_summary", {})
            processing_success = processing_summary.get("processing_success", False)
            issues_count = processing_summary.get("issues_count", 0)
            warnings_count = processing_summary.get("warnings_count", 0)
            
            print(f"✅ Successfully processed payroll for period: {period}")
            print(f"👥 Employees: {num_employees}")
            print(f"💵 Gross wages: €{total_gross:.2f}, Net wages: €{total_net:.2f}")
            print(f"⚖️  Accounting balanced: {accounting_balanced}")
            print(f"📊 Processing success: {processing_success}")
            
            if issues_count > 0:
                print(f"⚠️  Issues found: {issues_count}")
            if warnings_count > 0:
                print(f"⚠️  Warnings: {warnings_count}")
            
            # Determine HTTP status code based on validation
            status_code = 200 if processing_success else 207  # 207 Multi-Status for partial success
            
            # Return successful response
            return jsonify(result), status_code
        else:
            # Log processing failure
            error_msg = result.get("error", "Unknown error")
            print(f"❌ Payroll processing failed: {error_msg}")
            
            # Return error response with appropriate status code
            status_code = 422 if "validation" in error_msg.lower() or "parsing" in error_msg.lower() else 500
            
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
        print(f"❌ Process payroll document endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "details": "An unexpected error occurred while processing the request"
        }), 500




# ================================
# GET JOURNALS TESTING
# ================================

@app.route('/api/getJournalsByCompany', methods=['POST'])
def get_journals_by_company():
    """Get all journals for a specific company ID"""
    try:
        data = request.json or {}
        result = createjournal.get_company_journals(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/create/share-transaction', methods=['POST'])
def create_share_capital_endpoint():
    """Create share capital transaction"""
    try:
        data = request.json or {}
        result = createsharetransaction.main(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/create/payroll-transaction', methods=['POST'])
def create_payroll_transaction_endpoint():
    """
    Create payroll journal entry from processed payroll data
    
    Expected JSON body (output from /api/process-payroll-document):
    {
        "payroll_data": {
            "period": "202506 - JUNE",
            "year": "2025",
            "month": "June",
            "pay_date": "2025-06-30" or null,
            "currency_code": "EUR",
            "description": "Payroll for June 2025...",
            "journal_entry_lines": [
                {
                    "account_code": "7000",
                    "account_name": "Gross wages",
                    "description": "Total gross salaries",
                    "debit_amount": 1050.00,
                    "credit_amount": 0
                },
                ...
            ]
        },
        "matched_company": {
            "id": 124,
            "name": "ENAMI Limited"
        },
        "journal_id": 801
    }
    
    Or can accept array format (will use first element):
    [
        {
            "payroll_data": {...},
            "matched_company": {...},
            "journal_id": 801
        }
    ]
    
    Returns:
    Success Response (Created):
    {
        "success": true,
        "exists": false,
        "entry_id": 12345,
        "entry_number": "SAL/2025/06/0001",
        "company_name": "ENAMI Limited",
        "period": "202506 - JUNE",
        "year": "2025",
        "transaction_date": "2025-06-30",
        "state": "posted",
        "journal_name": "Salary Journal",
        "journal_code": "SAL",
        "total_debits": 1200.68,
        "total_credits": 1200.68,
        "line_items": [
            {
                "id": 67890,
                "name": "Total gross salaries for June 2025",
                "debit": 1050.00,
                "credit": 0.0,
                "account_id": [123, "7000 Gross wages"]
            },
            ...
        ],
        "line_count": 7,
        "missing_accounts": null,
        "message": "Payroll journal entry created and posted successfully"
    }
    
    Success Response (Already Exists):
    {
        "success": true,
        "exists": true,
        "entry_id": 12340,
        "entry_number": "SAL/2025/06/0001",
        "date": "2025-06-30",
        "state": "posted",
        "ref": "Payroll - 202506 - JUNE 2025",
        "line_items": [...],
        "message": "Payroll entry for this period already exists - no duplicate created"
    }
    
    Error Response:
    {
        "success": false,
        "error": "Journal entry is not balanced. Debits: 1200.68, Credits: 1130.67, Difference: 70.01",
        "details": {
            "total_debits": 1200.68,
            "total_credits": 1130.67,
            "balance_difference": 70.01
        }
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
        
        # Handle array input (extract first element)
        if isinstance(data, list):
            if not data:
                return jsonify({
                    "success": False,
                    "error": "Empty data array provided",
                    "details": "Array must contain at least one element"
                }), 400
            data = data[0]
        
        # Validate nested structure
        if not isinstance(data, dict):
            return jsonify({
                "success": False,
                "error": "Invalid data format",
                "details": "Data must be a JSON object or array containing objects"
            }), 400
        
        # Check for required top-level fields
        required_fields = ['payroll_data', 'matched_company', 'journal_id']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return jsonify({
                "success": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}",
                "details": f"Required fields are: {', '.join(required_fields)}"
            }), 400
        
        # Validate matched_company structure
        matched_company = data.get('matched_company', {})
        if not isinstance(matched_company, dict) or not matched_company.get('id'):
            return jsonify({
                "success": False,
                "error": "Invalid matched_company",
                "details": "matched_company must contain an 'id' field"
            }), 400
        
        # Validate journal_id
        journal_id = data.get('journal_id')
        if not isinstance(journal_id, int) or journal_id <= 0:
            return jsonify({
                "success": False,
                "error": "Invalid journal_id",
                "details": "journal_id must be a positive integer"
            }), 400
        
        # Validate payroll_data structure
        payroll_data = data.get('payroll_data', {})
        if not isinstance(payroll_data, dict):
            return jsonify({
                "success": False,
                "error": "Invalid payroll_data",
                "details": "payroll_data must be a JSON object"
            }), 400
        
        # Validate journal_entry_lines
        journal_entry_lines = payroll_data.get('journal_entry_lines', [])
        if not isinstance(journal_entry_lines, list) or not journal_entry_lines:
            return jsonify({
                "success": False,
                "error": "Invalid or missing journal_entry_lines",
                "details": "payroll_data must contain a non-empty journal_entry_lines array"
            }), 400
        
        # Log processing start
        company_name = matched_company.get('name', 'Unknown')
        company_id = matched_company.get('id')
        period = payroll_data.get('period', payroll_data.get('month', 'Unknown'))
        
        print(f"💰 Creating payroll transaction for company: {company_name} (ID: {company_id})")
        print(f"📅 Period: {period}")
        print(f"📊 Journal lines: {len(journal_entry_lines)}")
        
        # Call the payroll transaction creation function
        result = createpayrolltransaction.main(data)
        
        # Handle successful creation
        if result.get("success"):
            exists = result.get("exists", False)
            entry_number = result.get("entry_number", "Unknown")
            
            if exists:
                # Entry already existed
                print(f"ℹ️  Payroll entry already exists: {entry_number}")
                print(f"📅 Date: {result.get('date')}")
                
                return jsonify(result), 200
            else:
                # New entry created
                total_debits = result.get("total_debits", 0)
                total_credits = result.get("total_credits", 0)
                line_count = result.get("line_count", 0)
                state = result.get("state", "unknown")
                
                print(f"✅ Payroll entry created successfully: {entry_number}")
                print(f"⚖️  Debits: €{total_debits:.2f}, Credits: €{total_credits:.2f}")
                print(f"📝 Lines created: {line_count}")
                print(f"📌 Status: {state}")
                
                # Warn about missing accounts if any
                missing_accounts = result.get("missing_accounts")
                if missing_accounts:
                    print(f"⚠️  Warning: Some accounts were not found: {missing_accounts}")
                
                return jsonify(result), 201  # 201 Created
        else:
            # Handle creation failure
            error_msg = result.get("error", "Unknown error")
            print(f"❌ Payroll transaction creation failed: {error_msg}")
            
            # Determine appropriate status code
            error_lower = error_msg.lower()
            
            if "not found" in error_lower or "does not exist" in error_lower:
                status_code = 404
            elif "not balanced" in error_lower or "difference" in error_lower:
                status_code = 422  # Unprocessable Entity
            elif "already exists" in error_lower or "duplicate" in error_lower:
                status_code = 409  # Conflict
            elif "authentication" in error_lower or "odoo_" in error_lower:
                status_code = 503  # Service Unavailable
            else:
                status_code = 500  # Internal Server Error
            
            return jsonify(result), status_code
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        return jsonify({
            "success": False,
            "error": "Invalid JSON format",
            "details": str(e)
        }), 400
        
    except KeyError as e:
        print(f"❌ Missing key error: {e}")
        return jsonify({
            "success": False,
            "error": f"Missing required field: {str(e)}",
            "details": "Check that all required fields are present in the request"
        }), 400
        
    except ValueError as e:
        print(f"❌ Value error: {e}")
        return jsonify({
            "success": False,
            "error": "Invalid data value",
            "details": str(e)
        }), 400
        
    except Exception as e:
        print(f"❌ Create payroll transaction endpoint error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "details": "An unexpected error occurred while creating the payroll transaction"
        }), 500


# ============================================
# FINANCIAL PROFILE ROUTES (NEW)
# ============================================

@app.route("/api/profile/financial", methods=["GET"])
@jwt_required
def get_financial_profile():
    """Get user's financial profile"""
    try:
        current_user = get_current_user()
        username = current_user['username']
        
        profile = upload.get_financial_profile(username)
        
        return jsonify({
            "status": "success",
            "data": profile
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@app.route("/api/profile/financial", methods=["POST", "PUT"])
@jwt_required
def update_financial_profile():
    """Update user's financial profile"""
    try:
        current_user = get_current_user()
        username = current_user['username']
        data = request.json
        
        # Validate and update profile
        result = upload.update_financial_profile(username, data)
        
        if result["success"]:
            return jsonify({
                "status": "success",
                "message": "Profile updated successfully",
                "upload_ready": result["upload_ready"]
            }), 200
        else:
            return jsonify({
                "status": "error",
                "error": result["error"],
                "details": result.get("details", [])
            }), 400
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@app.route("/api/profile/upload-ready", methods=["GET"])
@jwt_required
def check_upload_ready():
    """Check if user can upload files"""
    try:
        current_user = get_current_user()
        username = current_user['username']
        
        result = upload.check_upload_ready(username)
        
        return jsonify({
            "status": "success",
            "upload_ready": result["upload_ready"],
            "missing_fields": result.get("missing_fields", [])
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# ================================
# DYNAMO DB TABLE UPDATE ENDPOINTS
# ================================

# Add this route to your Flask app

@app.route("/api/transactions-table/update", methods=["POST"])
def update_transactions_table():
    """
    Create multiple transaction entries in DynamoDB
    Accepts the JSON array of transactions in multiple formats:
    - Direct array: [transaction1, transaction2, ...]
    - Wrapped in transactions key: {"transactions": [transaction1, transaction2, ...]}
    - Nested array: [[transaction1, transaction2, ...]]
    """
    try:
        # Try multiple ways to get JSON data
        data = None
        try:
            data = request.get_json()
        except Exception:
            try:
                data = request.get_json(force=True)
            except Exception as e:
                print(f"⚠️ Failed to parse JSON: {e}")
                return jsonify({
                    "success": False,
                    "error": "Invalid JSON format"
                }), 400
        
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        # Handle multiple data formats
        transactions_list = None
        
        # Format 1: Direct array [transaction1, transaction2, ...]
        if isinstance(data, list):
            # Check if it's a nested array [[transaction1, transaction2, ...]]
            if len(data) == 1 and isinstance(data[0], dict) and 'transactions' in data[0]:
                # Format 2b: [{"transactions": [...]}]
                transactions_list = data[0]['transactions']
            elif len(data) > 0 and isinstance(data[0], list):
                # Format 3: Nested array [[...]]
                transactions_list = data[0]
            else:
                # Format 1: Direct array
                transactions_list = data
        
        # Format 2a: Wrapped in object {"transactions": [...]}
        elif isinstance(data, dict):
            if 'transactions' in data:
                transactions_list = data['transactions']
            elif 'data' in data:
                # Alternative key name
                transactions_list = data['data']
            else:
                # Single transaction as object
                transactions_list = [data]
        
        # Validate we have a list
        if transactions_list is None:
            return jsonify({
                "success": False,
                "error": "Could not parse transactions data. Expected array of transactions or object with 'transactions' key"
            }), 400
        
        if not isinstance(transactions_list, list):
            return jsonify({
                "success": False,
                "error": "Transactions must be an array"
            }), 400
        
        if len(transactions_list) == 0:
            return jsonify({
                "success": False,
                "error": "No transactions provided"
            }), 400
        
        # Validate that list contains objects
        if not all(isinstance(item, dict) for item in transactions_list):
            return jsonify({
                "success": False,
                "error": "All transactions must be objects"
            }), 400
        
        # Process all transactions
        result = transactions.process_transactions(transactions_list)
        
        status_code = 201 if result["success"] else 207  # 207 for partial success
        return jsonify(result), status_code
            
    except Exception as e:
        print(f"❌ Transactions table update error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": "Failed to update transactions table",
            "details": str(e)
        }), 500
    
@app.route("/api/bills-table/update", methods=["POST"])
def update_bills_table():
    """
    Create a single bill entry in DynamoDB
    Accepts the JSON bill data in multiple formats:
    - Direct bill object: {bill_id: ..., bill_number: ..., ...}
    - Wrapped in bill key: {"bill": {bill_id: ..., ...}}
    - Wrapped in data key: {"data": {bill_id: ..., ...}}
    """
    try:
        # Try multiple ways to get JSON data
        data = None
        try:
            data = request.get_json()
        except Exception:
            try:
                data = request.get_json(force=True)
            except Exception as e:
                print(f"⚠️ Failed to parse JSON: {e}")
                return jsonify({
                    "success": False,
                    "error": "Invalid JSON format"
                }), 400
       
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
       
        # Handle multiple data formats
        bill_data = None
       
        # Format 1: Array with single bill [bill_object]
        if isinstance(data, list):
            if len(data) == 0:
                return jsonify({
                    "success": False,
                    "error": "Empty array provided"
                }), 400
            elif len(data) > 1:
                return jsonify({
                    "success": False,
                    "error": f"Expected single bill, received {len(data)} bills. This endpoint processes one bill at a time."
                }), 400
            else:
                # Extract the single bill from array
                bill_data = data[0]
        
        # Format 2-4: Object formats
        elif isinstance(data, dict):
            # Format 2: Direct bill object
            if 'bill_id' in data or 'bill_number' in data or 'total_amount' in data or 'vendor_name' in data:
                bill_data = data
            # Format 3: Wrapped in 'bill' key
            elif 'bill' in data and isinstance(data['bill'], dict):
                bill_data = data['bill']
            # Format 4: Wrapped in 'data' key
            elif 'data' in data and isinstance(data['data'], dict):
                bill_data = data['data']
            else:
                # Try to use the data as-is
                bill_data = data
        else:
            return jsonify({
                "success": False,
                "error": "Expected bill data as object/dictionary or array with single bill"
            }), 400
       
        # Validate we have bill data
        if bill_data is None:
            return jsonify({
                "success": False,
                "error": "Could not parse bill data. Expected bill object"
            }), 400
       
        if not isinstance(bill_data, dict):
            return jsonify({
                "success": False,
                "error": "Bill data must be an object/dictionary"
            }), 400
       
        # Process the bill
        result = bills.process_bill(bill_data)
       
        status_code = 201 if result["success"] else 500
        return jsonify(result), status_code
           
    except Exception as e:
        print(f"❌ Bills table update error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": "Failed to update bills table",
            "details": str(e)
        }), 500

#check    
@app.route("/api/invoices-table/update", methods=["POST"])
def update_invoices_table():
    """
    Create a single invoice entry in DynamoDB
    Accepts the JSON invoice data in multiple formats:
    - Direct invoice object: {invoice_id: ..., invoice_number: ..., ...}
    - Wrapped in invoice key: {"invoice": {invoice_id: ..., ...}}
    - Wrapped in data key: {"data": {invoice_id: ..., ...}}
    - Array with single invoice: [{invoice_id: ..., ...}]
    """
    try:
        # Try multiple ways to get JSON data
        data = None
        try:
            data = request.get_json()
        except Exception:
            try:
                data = request.get_json(force=True)
            except Exception as e:
                print(f"⚠️ Failed to parse JSON: {e}")
                return jsonify({
                    "success": False,
                    "error": "Invalid JSON format"
                }), 400
       
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
       
        # Handle multiple data formats
        invoice_data = None
       
        # Format 1: Array with single invoice [invoice_object]
        if isinstance(data, list):
            if len(data) == 0:
                return jsonify({
                    "success": False,
                    "error": "Empty array provided"
                }), 400
            elif len(data) > 1:
                return jsonify({
                    "success": False,
                    "error": f"Expected single invoice, received {len(data)} invoices. This endpoint processes one invoice at a time."
                }), 400
            else:
                # Extract the single invoice from array
                invoice_data = data[0]
        
        # Format 2-4: Object formats
        elif isinstance(data, dict):
            # Format 2: Direct invoice object
            if 'invoice_id' in data or 'invoice_number' in data or 'total_amount' in data or 'customer' in data:
                invoice_data = data
            # Format 3: Wrapped in 'invoice' key
            elif 'invoice' in data and isinstance(data['invoice'], dict):
                invoice_data = data['invoice']
            # Format 4: Wrapped in 'data' key
            elif 'data' in data and isinstance(data['data'], dict):
                invoice_data = data['data']
            else:
                # Try to use the data as-is
                invoice_data = data
        else:
            return jsonify({
                "success": False,
                "error": "Expected invoice data as object/dictionary or array with single invoice"
            }), 400
       
        # Validate we have invoice data
        if invoice_data is None:
            return jsonify({
                "success": False,
                "error": "Could not parse invoice data. Expected invoice object"
            }), 400
       
        if not isinstance(invoice_data, dict):
            return jsonify({
                "success": False,
                "error": "Invoice data must be an object/dictionary"
            }), 400
       
        # Process the invoice
        result = invoices.process_invoice(invoice_data)
       
        status_code = 201 if result["success"] else 500
        return jsonify(result), status_code
           
    except Exception as e:
        print(f"❌ Invoices table update error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": "Failed to update invoices table",
            "details": str(e)
        }), 500
    
@app.route("/api/update/share-transactions-table", methods=["POST"])
def update_share_transactions_table():
    """
    Create a single share transaction entry in DynamoDB
    Accepts the JSON share transaction data in multiple formats:
    - Direct transaction object: {transaction_id: ..., entry_number: ..., ...}
    - Wrapped in transaction key: {"transaction": {transaction_id: ..., ...}}
    - Wrapped in data key: {"data": {transaction_id: ..., ...}}
    - Wrapped in share_transaction key: {"share_transaction": {transaction_id: ..., ...}}
    """
    try:
        # Try multiple ways to get JSON data
        data = None
        try:
            data = request.get_json()
        except Exception:
            try:
                data = request.get_json(force=True)
            except Exception as e:
                print(f"⚠️ Failed to parse JSON: {e}")
                return jsonify({
                    "success": False,
                    "error": "Invalid JSON format"
                }), 400
       
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
       
        # Handle multiple data formats
        transaction_data = None
       
        # Format 1: Array with single transaction [transaction_object]
        if isinstance(data, list):
            if len(data) == 0:
                return jsonify({
                    "success": False,
                    "error": "Empty array provided"
                }), 400
            elif len(data) > 1:
                return jsonify({
                    "success": False,
                    "error": f"Expected single share transaction, received {len(data)} transactions. This endpoint processes one transaction at a time."
                }), 400
            else:
                # Extract the single transaction from array
                transaction_data = data[0]
        
        # Format 2-5: Object formats
        elif isinstance(data, dict):
            # Format 2: Direct transaction object
            if 'transaction_id' in data or 'entry_number' in data or 'total_amount' in data or 'partner' in data or 'move_type' in data:
                transaction_data = data
            # Format 3: Wrapped in 'transaction' key
            elif 'transaction' in data and isinstance(data['transaction'], dict):
                transaction_data = data['transaction']
            # Format 4: Wrapped in 'share_transaction' key
            elif 'share_transaction' in data and isinstance(data['share_transaction'], dict):
                transaction_data = data['share_transaction']
            # Format 5: Wrapped in 'data' key
            elif 'data' in data and isinstance(data['data'], dict):
                transaction_data = data['data']
            else:
                # Try to use the data as-is
                transaction_data = data
        else:
            return jsonify({
                "success": False,
                "error": "Expected share transaction data as object/dictionary or array with single transaction"
            }), 400
       
        # Validate we have transaction data
        if transaction_data is None:
            return jsonify({
                "success": False,
                "error": "Could not parse share transaction data. Expected transaction object"
            }), 400
       
        if not isinstance(transaction_data, dict):
            return jsonify({
                "success": False,
                "error": "Share transaction data must be an object/dictionary"
            }), 400
       
        # Process the share transaction
        result = share_transactions.process_share_transaction(transaction_data)
       
        status_code = 201 if result["success"] else 500
        return jsonify(result), status_code
           
    except Exception as e:
        print(f"❌ Share transactions table update error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": "Failed to update share transactions table",
            "details": str(e)
        }), 500

@app.route("/api/update/payroll-transactions-table", methods=["POST"])
def update_payroll_transactions_table():
    """
    Create a single payroll transaction entry in DynamoDB
    Accepts the JSON payroll transaction data in multiple formats:
    - Direct transaction object: {entry_id: ..., entry_number: ..., ...}
    - Wrapped in transaction key: {"transaction": {entry_id: ..., ...}}
    - Wrapped in data key: {"data": {entry_id: ..., ...}}
    - Wrapped in payroll_transaction key: {"payroll_transaction": {entry_id: ..., ...}}
    """
    try:
        # Try multiple ways to get JSON data
        data = None
        try:
            data = request.get_json()
        except Exception:
            try:
                data = request.get_json(force=True)
            except Exception as e:
                print(f"⚠️ Failed to parse JSON: {e}")
                return jsonify({
                    "success": False,
                    "error": "Invalid JSON format"
                }), 400
       
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
       
        # Handle multiple data formats
        transaction_data = None
       
        # Format 1: Array with single transaction [transaction_object]
        if isinstance(data, list):
            if len(data) == 0:
                return jsonify({
                    "success": False,
                    "error": "Empty array provided"
                }), 400
            elif len(data) > 1:
                return jsonify({
                    "success": False,
                    "error": f"Expected single payroll transaction, received {len(data)} transactions. This endpoint processes one transaction at a time."
                }), 400
            else:
                # Extract the single transaction from array
                transaction_data = data[0]
        
        # Format 2-5: Object formats
        elif isinstance(data, dict):
            # Format 2: Direct transaction object (check for payroll-specific fields)
            if 'entry_id' in data or 'entry_number' in data or 'total_debits' in data or 'period' in data or 'move_type' in data:
                transaction_data = data
            # Format 3: Wrapped in 'transaction' key
            elif 'transaction' in data and isinstance(data['transaction'], dict):
                transaction_data = data['transaction']
            # Format 4: Wrapped in 'payroll_transaction' key
            elif 'payroll_transaction' in data and isinstance(data['payroll_transaction'], dict):
                transaction_data = data['payroll_transaction']
            # Format 5: Wrapped in 'data' key
            elif 'data' in data and isinstance(data['data'], dict):
                transaction_data = data['data']
            else:
                # Try to use the data as-is
                transaction_data = data
        else:
            return jsonify({
                "success": False,
                "error": "Expected payroll transaction data as object/dictionary or array with single transaction"
            }), 400
       
        # Validate we have transaction data
        if transaction_data is None:
            return jsonify({
                "success": False,
                "error": "Could not parse payroll transaction data. Expected transaction object"
            }), 400
       
        if not isinstance(transaction_data, dict):
            return jsonify({
                "success": False,
                "error": "Payroll transaction data must be an object/dictionary"
            }), 400
       
        # Process the payroll transaction
        result = payroll_transactions.process_payroll_transaction(transaction_data)
       
        status_code = 201 if result["success"] else 500
        return jsonify(result), status_code
           
    except Exception as e:
        print(f"❌ Payroll transactions table update error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": "Failed to update payroll transactions table",
            "details": str(e)
        }), 500


# ============================================================================
# FINANCIAL REPORTS (NEW SECTION)
# ============================================================================

@app.route('/api/reports/profit-loss', methods=['POST'])
def get_profit_loss():
    """Get Profit & Loss Report"""
    try:
        data = request.json or {}
        result = reports.get_profit_loss_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/balance-sheet', methods=['POST'])
def get_balance_sheet():
    """Get Balance Sheet Report"""
    try:
        data = request.json or {}
        result = reports.get_balance_sheet_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/cash-flow', methods=['POST'])
def get_cash_flow():
    """Get Cash Flow Statement"""
    try:
        data = request.json or {}
        result = reports.get_cash_flow_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ACCOUNTS REPORTS
# ============================================================================

@app.route('/api/reports/aged-payables', methods=['POST'])
def get_aged_payables():
    """Get Aged Payables Report"""
    try:
        data = request.json or {}
        result = reports.get_aged_payables_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/aged-receivables', methods=['POST'])
def get_aged_receivables():
    """Get Aged Receivables Report"""
    try:
        data = request.json or {}
        result = reports.get_aged_receivables_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/general-ledger', methods=['POST'])
def get_general_ledger():
    """Get General Ledger Report"""
    try:
        data = request.json or {}
        result = reports.get_general_ledger_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/trial-balance', methods=['POST'])
def get_trial_balance():
    """Get Trial Balance Report"""
    try:
        data = request.json or {}
        result = reports.get_trial_balance_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# TAX REPORTS
# ============================================================================

@app.route('/api/reports/tax', methods=['POST'])
def get_tax_report():
    """Get Tax Report (VAT/GST)"""
    try:
        data = request.json or {}
        result = reports.get_tax_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# SALES & PURCHASE REPORTS
# ============================================================================

@app.route('/api/reports/sales', methods=['POST'])
def get_sales_report():
    """Get Sales Report"""
    try:
        data = request.json or {}
        result = reports.get_sales_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/purchases', methods=['POST'])
def get_purchase_report():
    """Get Purchase Report"""
    try:
        data = request.json or {}
        result = reports.get_purchase_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# BANK & PAYMENT REPORTS
# ============================================================================

@app.route('/api/reports/bank-reconciliation', methods=['POST'])
def get_bank_reconciliation():
    """Get Bank Reconciliation Report"""
    try:
        data = request.json or {}
        result = reports.get_bank_reconciliation_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/payments', methods=['POST'])
def get_payment_report():
    """Get Payment Report"""
    try:
        data = request.json or {}
        result = reports.get_payment_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# BUDGET & VARIANCE REPORTS
# ============================================================================

@app.route('/api/reports/budget-vs-actual', methods=['POST'])
def get_budget_vs_actual():
    """Get Budget vs Actual Report"""
    try:
        data = request.json or {}
        result = reports.get_budget_vs_actual_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# PARTNER REPORTS
# ============================================================================

@app.route('/api/reports/partner-ledger', methods=['POST'])
def get_partner_ledger():
    """Get Partner Ledger Report"""
    try:
        data = request.json or {}
        result = reports.get_partner_ledger_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# EXECUTIVE SUMMARY
# ============================================================================

@app.route('/api/reports/executive-summary', methods=['POST'])
def get_executive_summary():
    """Get Executive Summary Report with key metrics"""
    try:
        data = request.json or {}
        result = reports.get_executive_summary_report(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# REPORT DOWNLOAD ENDPOINTS
# ============================================================================

@app.route('/api/reports/download/profit-loss', methods=['POST'])
def download_profit_loss():
    """Download Profit & Loss Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_profit_loss_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/balance-sheet', methods=['POST'])
def download_balance_sheet():
    """Download Balance Sheet Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_balance_sheet_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/cash-flow', methods=['POST'])
def download_cash_flow():
    """Download Cash Flow Statement as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_cash_flow_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/trial-balance', methods=['POST'])
def download_trial_balance():
    """Download Trial Balance Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_trial_balance_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/general-ledger', methods=['POST'])
def download_general_ledger():
    """Download General Ledger Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_general_ledger_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/aged-receivables', methods=['POST'])
def download_aged_receivables():
    """Download Aged Receivables Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_aged_receivables_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/aged-payables', methods=['POST'])
def download_aged_payables():
    """Download Aged Payables Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_aged_payables_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/tax', methods=['POST'])
def download_tax_report():
    """Download Tax Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_tax_report_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/sales', methods=['POST'])
def download_sales_report():
    """Download Sales Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_sales_report_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/purchases', methods=['POST'])
def download_purchase_report():
    """Download Purchase Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_purchase_report_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/payments', methods=['POST'])
def download_payment_report():
    """Download Payment Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_payment_report_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/bank-reconciliation', methods=['POST'])
def download_bank_reconciliation():
    """Download Bank Reconciliation Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_bank_reconciliation_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/budget-vs-actual', methods=['POST'])
def download_budget_vs_actual():
    """Download Budget vs Actual Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_budget_vs_actual_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/partner-ledger', methods=['POST'])
def download_partner_ledger():
    """Download Partner Ledger Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_partner_ledger_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reports/download/executive-summary', methods=['POST'])
def download_executive_summary():
    """Download Executive Summary Report as CSV"""
    try:
        data = request.json or {}
        csv_content, filename = reports.download_executive_summary_csv(data)
        
        if csv_content is None:
            return jsonify(filename), 400
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================
# HELPER FUNCTIONS
# ================================

@app.route('/api/invoices/create', methods=['POST'])
def create_customer_invoice_endpoint():
    """Create a new customer invoice"""
    try:
        invoice_data = request.get_json()
        
        if not invoice_data:
            return jsonify({
                'success': False, 
                'error': 'No JSON data provided'
            }), 400
        
        result = createproduct.create_customer_invoice(invoice_data)
        
        if result['success']:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }), 500


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