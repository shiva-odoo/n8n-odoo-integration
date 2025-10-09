import boto3
from datetime import datetime
from botocore.exceptions import ClientError
from decimal import Decimal

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='eu-north-1')
bills_table = dynamodb.Table('bills')

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

def generate_bill_id():
    """Generate unique bill ID"""
    now = datetime.utcnow()
    timestamp = now.strftime('%Y_%m_%d_%H_%M_%S')
    return f"BILL_{timestamp}"

def safe_get_nested(data, *keys, default=''):
    """Safely extract nested values from dictionaries"""
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key, default)
        else:
            return default
    return result if result is not None else default

def process_bill(bill_data):
    """
    Process a single bill and create entry in DynamoDB
    
    Args:
        bill_data: Dictionary containing bill data from the input JSON
        
    Returns:
        Dictionary with processing result
    """
    result = {
        "success": False,
        "bill_id": None,
        "odoo_bill_id": bill_data.get('bill_id'),
        "message": ""
    }
    
    try:
        # Generate unique bill ID
        bill_id = generate_bill_id()
        
        # Extract line items for description
        line_items = bill_data.get('line_items', [])
        if not isinstance(line_items, list):
            line_items = []
        
        # Generate description from line items
        description = extract_description(line_items)
        
        # Extract company details safely
        company = bill_data.get('company', {})
        if not isinstance(company, dict):
            company = {}
        company_name = company.get('name', '')
        
        # Extract journal details safely
        journal = bill_data.get('journal', {})
        if not isinstance(journal, dict):
            journal = {}
        journal_name = journal.get('name', '')
        
        # Extract vendor details safely
        vendor = bill_data.get('vendor', {})
        if not isinstance(vendor, dict):
            vendor = {}
        vendor_name = vendor.get('name', '')
        
        # Extract journal entries detailed safely
        journal_entries_detailed = bill_data.get('journal_entries_detailed', [])
        if not isinstance(journal_entries_detailed, list):
            journal_entries_detailed = []
        
        # Handle payment_reference (could be False, None, or string)
        payment_ref = bill_data.get('payment_reference')
        if payment_ref is False or payment_ref is None:
            payment_ref = ''
        else:
            payment_ref = str(payment_ref) if payment_ref else ''
        
        # Handle vendor_reference (could be False, None, or string)
        vendor_ref = bill_data.get('vendor_reference')
        if vendor_ref is False or vendor_ref is None:
            vendor_ref = ''
        else:
            vendor_ref = str(vendor_ref) if vendor_ref else ''
        
        # Prepare bill item for DynamoDB
        bill_item = {
            # Existing fields
            'bill_id': bill_id,
            'amount': convert_to_decimal(bill_data.get('total_amount', 0)),
            'company_name': str(company_name) if company_name else '',
            'date': str(bill_data.get('invoice_date', '')),
            'description': str(description) if description else '',
            'journal': str(journal_name) if journal_name else '',
            'partners': str(vendor_name) if vendor_name else '',
            'reference': vendor_ref,
            
            # New fields
            'due_date': str(bill_data.get('due_date', '')),
            'journal_details': convert_to_decimal(journal) if journal else {},
            'vendor_details': convert_to_decimal(vendor) if vendor else {},
            'vendor_reference': vendor_ref,
            'tax_amount': convert_to_decimal(bill_data.get('tax_amount', 0)),
            'subtotal': convert_to_decimal(bill_data.get('subtotal', 0)),
            'payment_reference': payment_ref,
            'line_items': convert_to_decimal(line_items) if line_items else [],
            'journal_entries_detailed': convert_to_decimal(journal_entries_detailed) if journal_entries_detailed else [],
            'odoo_bill_id': int(bill_data.get('bill_id', 0)) if bill_data.get('bill_id') else 0,
            'odoo_bill_number': str(bill_data.get('bill_number', '')),
            
            # Metadata
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Save to DynamoDB
        bills_table.put_item(Item=bill_item)
        
        result["success"] = True
        result["bill_id"] = bill_id
        result["message"] = f"Bill created successfully: {bill_id}"
        
        print(f"✅ Bill created: {bill_id}")
        print(f"   Odoo Bill ID: {bill_data.get('bill_id', 'N/A')}")
        print(f"   Odoo Bill Number: {bill_data.get('bill_number', 'N/A')}")
        print(f"   Amount: {bill_data.get('total_amount', 0)}")
        print(f"   Vendor: {vendor_name if vendor_name else 'N/A'}")
        
    except Exception as e:
        result["success"] = False
        result["message"] = f"Failed to create bill: {str(e)}"
        print(f"❌ Bill creation failed: {e}")
    
    return result


# Example usage
if __name__ == "__main__":
    # Example bill data (replace with actual input)
    sample_bill = {
        "bill_id": 1803,
        "bill_number": "BILL/2025/07/0004",
        "total_amount": 3035.0,
        "invoice_date": "2025-07-30",
        "due_date": "2025-10-09",
        "vendor_reference": "406",
        "tax_amount": 0.0,
        "subtotal": 3035.0,
        "payment_reference": False,
        "company": {
            "id": 125,
            "name": "KYRASTEL ENTERPRISES LIMITED"
        },
        "journal": {
            "id": 808,
            "code": "BILL",
            "name": "Purchases",
            "type": "purchase"
        },
        "vendor": {
            "id": 564,
            "name": "RNA design studio L.L.C.",
            "email": "info@rnadesignstudio.com",
            "phone": "+357 26818140"
        },
        "line_items": [],
        "journal_entries_detailed": []
    }
    
    # Process the bill
    result = process_bill(sample_bill)
    print(f"\nResult: {result}")