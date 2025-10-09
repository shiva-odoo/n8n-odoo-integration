import boto3
from datetime import datetime
from botocore.exceptions import ClientError
from decimal import Decimal

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='eu-north-1')
invoices_table = dynamodb.Table('invoices')

def convert_to_decimal(obj):
    """Convert numbers to Decimal for DynamoDB compatibility"""
    if isinstance(obj, dict):
        return {k: convert_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_decimal(v) for v in obj]
    elif isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, int):
        return Decimal(obj)
    else:
        return obj

def extract_description(line_items):
    """Extract labels from line items and concatenate with +"""
    labels = []
    for item in line_items:
        label = item.get('label', '')
        if label:
            labels.append(label)
    
    # Join all labels with +
    return ' + '.join(labels) if labels else ''

def generate_invoice_id():
    """Generate unique invoice ID"""
    now = datetime.utcnow()
    timestamp = now.strftime('%Y_%m_%d_%H_%M_%S')
    return f"INV_{timestamp}"

def safe_get_nested(data, *keys, default=''):
    """Safely extract nested values from dictionaries"""
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key, default)
        else:
            return default
    return result if result is not None else default

def process_invoice(invoice_data):
    """
    Process a single invoice and create entry in DynamoDB
    
    Args:
        invoice_data: Dictionary containing invoice data from the input JSON
        
    Returns:
        Dictionary with processing result
    """
    result = {
        "success": False,
        "invoice_id": None,
        "odoo_invoice_id": invoice_data.get('invoice_id'),
        "message": ""
    }
    
    try:
        # Generate unique invoice ID
        invoice_id = generate_invoice_id()
        
        # Extract line items for description
        line_items = invoice_data.get('line_items', [])
        if not isinstance(line_items, list):
            line_items = []
        
        # Generate description from line items
        description = extract_description(line_items)
        
        # Extract company details safely
        company = invoice_data.get('company', {})
        if not isinstance(company, dict):
            company = {}
        company_name = company.get('name', '')
        
        # Extract journal details safely
        journal = invoice_data.get('journal', {})
        if not isinstance(journal, dict):
            journal = {}
        journal_name = journal.get('name', '')
        
        # Extract customer details safely
        customer = invoice_data.get('customer', {})
        if not isinstance(customer, dict):
            customer = {}
        customer_name = customer.get('name', '')
        
        # Extract journal entries detailed safely
        journal_entries_detailed = invoice_data.get('journal_entries_detailed', [])
        if not isinstance(journal_entries_detailed, list):
            journal_entries_detailed = []
        
        # Handle payment_reference (could be False, None, or string)
        payment_ref = invoice_data.get('payment_reference')
        if payment_ref is False or payment_ref is None:
            payment_ref = ''
        else:
            payment_ref = str(payment_ref) if payment_ref else ''
        
        # Handle customer_reference (could be False, None, or string)
        customer_ref = invoice_data.get('customer_reference')
        if customer_ref is False or customer_ref is None:
            customer_ref = ''
        else:
            customer_ref = str(customer_ref) if customer_ref else ''
        
        # Prepare invoice item for DynamoDB
        invoice_item = {
            # Existing fields
            'invoice_id': invoice_id,
            'amount': convert_to_decimal(invoice_data.get('total_amount', 0)),
            'company_name': str(company_name) if company_name else '',
            'date': str(invoice_data.get('invoice_date', '')),
            'description': str(description) if description else '',
            'journal': str(journal_name) if journal_name else '',
            'partners': str(customer_name) if customer_name else '',
            'reference': customer_ref,
            
            # New fields
            'due_date': str(invoice_data.get('due_date', '')),
            'journal_details': convert_to_decimal(journal) if journal else {},
            'customer_details': convert_to_decimal(customer) if customer else {},
            'customer_reference': customer_ref,
            'tax_amount': convert_to_decimal(invoice_data.get('tax_amount', 0)),
            'subtotal': convert_to_decimal(invoice_data.get('subtotal', 0)),
            'payment_reference': payment_ref,
            'line_items': convert_to_decimal(line_items) if line_items else [],
            'journal_entries_detailed': convert_to_decimal(journal_entries_detailed) if journal_entries_detailed else [],
            'odoo_invoice_id': int(invoice_data.get('invoice_id', 0)) if invoice_data.get('invoice_id') else 0,
            'odoo_invoice_number': str(invoice_data.get('invoice_number', '')),
            
            # Metadata
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Save to DynamoDB
        invoices_table.put_item(Item=invoice_item)
        
        result["success"] = True
        result["invoice_id"] = invoice_id
        result["message"] = f"Invoice created successfully: {invoice_id}"
        
        print(f"✅ Invoice created: {invoice_id}")
        print(f"   Odoo Invoice ID: {invoice_data.get('invoice_id', 'N/A')}")
        print(f"   Odoo Invoice Number: {invoice_data.get('invoice_number', 'N/A')}")
        print(f"   Amount: {invoice_data.get('total_amount', 0)}")
        print(f"   Customer: {customer_name if customer_name else 'N/A'}")
        
    except Exception as e:
        result["success"] = False
        result["message"] = f"Failed to create invoice: {str(e)}"
        print(f"❌ Invoice creation failed: {e}")
    
    return result


# Example usage
if __name__ == "__main__":
    # Example invoice data (replace with actual input)
    sample_invoice = {
        "invoice_id": 1804,
        "invoice_number": "INV/2025/00001",
        "total_amount": 3035.0,
        "invoice_date": "2025-07-30",
        "due_date": "2025-10-09",
        "customer_reference": False,
        "tax_amount": 0.0,
        "subtotal": 3035.0,
        "payment_reference": "INV/2025/00001",
        "company": {
            "id": 125,
            "name": "KYRASTEL ENTERPRISES LIMITED"
        },
        "journal": {
            "id": 807,
            "code": "INV",
            "name": "Sales",
            "type": "sale"
        },
        "customer": {
            "id": 569,
            "name": "invoice creation test",
            "email": False,
            "phone": False
        },
        "line_items": [],
        "journal_entries_detailed": []
    }
    
    # Process the invoice
    result = process_invoice(sample_invoice)
    print(f"\nResult: {result}")