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
    import createjournal
    import createtransaction
    import getDetailsByCompany
    import updateAuditStatus
    import openaipdf

    
except ImportError as e:
    print(f"Warning: Could not import some modules: {e}")

app = Flask(__name__)

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

# NEW PDF EXTRACTION ENDPOINTS
@app.route('/api/extract-pdf-data', methods=['POST'])
def extract_pdf_data():
    """
    Extract structured data from PDF files
    Expected input from n8n: file_name, file_content (base64), file_type
    """
    if not PDF_EXTRACTION_AVAILABLE:
        return jsonify({"success": False, "error": "PDF extraction not available"}), 500
    
    try:
        data = request.get_json()
        
        # Validate input
        if not data:
            return jsonify({"success": False, "error": "No JSON data provided"}), 400
            
        required_fields = ['file_name', 'file_content']
        for field in required_fields:
            if field not in data:
                return jsonify({"success": False, "error": f"Missing required field: {field}"}), 400
        
        file_name = data['file_name']
        file_content_b64 = data['file_content']
        file_type = data.get('file_type', 'application/pdf')
        
        logger.info(f"Processing file: {file_name}, type: {file_type}")
        
        # Decode base64 content
        try:
            file_content = base64.b64decode(file_content_b64)
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid base64 content: {str(e)}"}), 400
        
        # Process based on file type
        if file_type == 'application/pdf':
            result = pdf_extractor.extract_from_pdf(file_content, file_name)
        elif file_type.startswith('image/'):
            image_data = f"data:{file_type};base64,{file_content_b64}"
            result = pdf_extractor.extract_from_image(image_data, file_name)
        else:
            return jsonify({"success": False, "error": f"Unsupported file type: {file_type}"}), 400
        
        if result["success"]:
            # Format data for your existing Odoo APIs
            formatted_data = pdf_extractor.format_for_odoo_apis(result["extracted_data"])
            result["formatted_for_odoo"] = formatted_data
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Extraction error: {str(e)}")
        return jsonify({"success": False, "error": f"Internal server error: {str(e)}"}), 500

@app.route('/api/process-document', methods=['POST'])
def process_document():
    """
    Complete document processing: Extract data + Create vendor + Create company + Create bill
    This is the main endpoint for n8n workflow
    """
    if not PDF_EXTRACTION_AVAILABLE:
        return jsonify({"success": False, "error": "PDF extraction not available"}), 500
    
    try:
        # Extract data from the same request
        file_name = request.json.get('file_name')
        file_content_b64 = request.json.get('file_content')
        file_type = request.json.get('file_type', 'application/pdf')
        
        if not file_name or not file_content_b64:
            return jsonify({"success": False, "error": "file_name and file_content are required"}), 400
        
        # Decode and extract
        file_content = base64.b64decode(file_content_b64)
        
        if file_type == 'application/pdf':
            extraction_result = pdf_extractor.extract_from_pdf(file_content, file_name)
        elif file_type.startswith('image/'):
            image_data = f"data:{file_type};base64,{file_content_b64}"
            extraction_result = pdf_extractor.extract_from_image(image_data, file_name)
        else:
            return jsonify({"success": False, "error": f"Unsupported file type: {file_type}"}), 400
        
        if not extraction_result.get("success"):
            return jsonify({
                "success": False,
                "step": "extraction",
                "error": extraction_result.get("error")
            })
        
        formatted_data = pdf_extractor.format_for_odoo_apis(extraction_result["extracted_data"])
        results = {
            "success": True,
            "extraction": extraction_result,
            "vendor_creation": None,
            "company_creation": None,
            "bill_creation": None,
            "processing_summary": {
                "file_name": file_name,
                "extraction_method": extraction_result.get("extraction_method"),
                "records_created": []
            }
        }
        
        # Step 2: Create vendor if vendor data exists
        vendor_data = formatted_data.get("vendor_data", {})
        if vendor_data.get("name"):
            try:
                vendor_result = createvendor.main(vendor_data)
                results["vendor_creation"] = vendor_result
                if vendor_result.get("success"):
                    results["processing_summary"]["records_created"].append("vendor")
                    vendor_id = vendor_result.get("vendor_id")
                else:
                    logger.warning(f"Vendor creation failed: {vendor_result.get('error')}")
            except Exception as e:
                logger.error(f"Vendor creation error: {str(e)}")
                results["vendor_creation"] = {"success": False, "error": str(e)}
        
        # Step 3: Create company if customer data exists
        company_data = formatted_data.get("company_data", {})
        if company_data.get("name"):
            try:
                company_result = createcompany.main(company_data)
                results["company_creation"] = company_result
                if company_result.get("success"):
                    results["processing_summary"]["records_created"].append("company")
            except Exception as e:
                logger.error(f"Company creation error: {str(e)}")
                results["company_creation"] = {"success": False, "error": str(e)}
        
        # Step 4: Create bill if we have vendor and bill data
        bill_data = formatted_data.get("bill_data", {})
        vendor_result = results.get("vendor_creation", {})
        
        if bill_data and vendor_result and vendor_result.get("success"):
            # Add vendor_id to bill data
            bill_data["vendor_id"] = vendor_result.get("vendor_id")
            
            try:
                bill_result = createbill.main(bill_data)
                results["bill_creation"] = bill_result
                if bill_result.get("success"):
                    results["processing_summary"]["records_created"].append("bill")
            except Exception as e:
                logger.error(f"Bill creation error: {str(e)}")
                results["bill_creation"] = {"success": False, "error": str(e)}
        
        # Generate summary
        total_created = len(results["processing_summary"]["records_created"])
        results["processing_summary"]["total_records_created"] = total_created
        results["processing_summary"]["status"] = "completed" if total_created > 0 else "partial"
        
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"Document processing error: {str(e)}")
        return jsonify({
            "success": False,
            "step": "processing",
            "error": f"Processing failed: {str(e)}"
        }), 500

@app.route('/api/extract-from-url', methods=['POST'])
def extract_from_url():
    """
    Extract data from a file URL (for Google Drive files)
    """
    if not PDF_EXTRACTION_AVAILABLE:
        return jsonify({"success": False, "error": "PDF extraction not available"}), 500
    
    try:
        data = request.get_json()
        file_url = data.get('file_url')
        
        if not file_url:
            return jsonify({"success": False, "error": "file_url is required"}), 400
        
        # Download file from URL
        import requests
        response = requests.get(file_url)
        response.raise_for_status()
        
        file_content = response.content
        file_name = data.get('file_name', 'document.pdf')
        file_type = response.headers.get('content-type', 'application/pdf')
        
        # Process the downloaded file
        if file_type == 'application/pdf':
            result = pdf_extractor.extract_from_pdf(file_content, file_name)
        elif file_type.startswith('image/'):
            file_content_b64 = base64.b64encode(file_content).decode()
            image_data = f"data:{file_type};base64,{file_content_b64}"
            result = pdf_extractor.extract_from_image(image_data, file_name)
        else:
            return jsonify({"success": False, "error": f"Unsupported file type: {file_type}"}), 400
        
        if result["success"]:
            formatted_data = pdf_extractor.format_for_odoo_apis(result["extracted_data"])
            result["formatted_for_odoo"] = formatted_data
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"URL extraction error: {str(e)}")
        return jsonify({"success": False, "error": f"Internal server error: {str(e)}"}), 500

@app.route('/api/extraction-status', methods=['GET'])
def extraction_status():
    """
    Check extraction service status
    """
    return jsonify({
        "success": True,
        "pdf_extraction_available": PDF_EXTRACTION_AVAILABLE,
        "supported_formats": ["application/pdf", "image/jpeg", "image/png", "image/jpg"] if PDF_EXTRACTION_AVAILABLE else [],
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "version": "4.0"
    })

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
        result = createjournal.list_accounts()
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
    
@app.route('/api/openaipdf', methods=['POST'])
def openaipdf():
    """openaipdf"""
    try:
        data = request.files['file'] or {}
        result = openaipdf.main({'file': data})
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
    port = int(os.environ.get('PORT', 8080))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)  # 0.0.0.0 allows external access