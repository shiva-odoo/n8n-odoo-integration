import boto3
from datetime import datetime
from botocore.exceptions import ClientError
from decimal import Decimal

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='eu-north-1')
share_transactions_table = dynamodb.Table('share_transactions')

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
    seen_labels = set()  # Track unique labels
    
    for item in line_items:
        label = item.get('label', '')
        if label and label not in seen_labels:
            labels.append(label)
            seen_labels.add(label)
    
    # Join all unique labels with +
    return ' + '.join(labels) if labels else ''

def generate_share_transaction_id():
    """Generate unique share transaction ID"""
    now = datetime.utcnow()
    timestamp = now.strftime('%Y_%m_%d_%H_%M_%S')
    return f"SHR_{timestamp}"

def safe_get_nested(data, *keys, default=''):
    """Safely extract nested values from dictionaries"""
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key, default)
        else:
            return default
    return result if result is not None else default

def process_share_transaction(transaction_data):
    """
    Process a single share transaction and create entry in DynamoDB
    
    Args:
        transaction_data: Dictionary containing share transaction data from the input JSON
        
    Returns:
        Dictionary with processing result
    """
    result = {
        "success": False,
        "share_transaction_id": None,
        "odoo_transaction_id": transaction_data.get('transaction_id'),
        "message": ""
    }
    
    try:
        # Generate unique share transaction ID
        share_transaction_id = generate_share_transaction_id()
        
        # Extract line items for description
        line_items = transaction_data.get('line_items', [])
        if not isinstance(line_items, list):
            line_items = []
        
        # Generate description from line items
        description = extract_description(line_items)
        
        # Extract company details safely
        company = transaction_data.get('company', {})
        if not isinstance(company, dict):
            company = {}
        company_name = company.get('name', '')
        
        # Extract journal details safely
        journal = transaction_data.get('journal', {})
        if not isinstance(journal, dict):
            journal = {}
        journal_name = journal.get('name', '')
        
        # Extract partner details safely
        partner = transaction_data.get('partner', {})
        if not isinstance(partner, dict):
            partner = {}
        partner_name = partner.get('name', '')
        
        # Extract journal entries detailed safely
        journal_entries_detailed = transaction_data.get('journal_entries_detailed', [])
        if not isinstance(journal_entries_detailed, list):
            journal_entries_detailed = []
        
        # Handle reference (customer_ref or reference field)
        reference = transaction_data.get('reference') or transaction_data.get('customer_ref')
        if reference is False or reference is None:
            reference = ''
        else:
            reference = str(reference) if reference else ''
        
        # Handle narration (could be False, None, or string)
        narration = transaction_data.get('narration')
        if narration is False or narration is None:
            narration = ''
        else:
            narration = str(narration) if narration else ''
        
        # Prepare share transaction item for DynamoDB
        transaction_item = {
            # Core fields matching bills table structure
            'share_transaction_id': share_transaction_id,
            'amount': convert_to_decimal(transaction_data.get('total_amount', 0)),
            'company_name': str(company_name) if company_name else '',
            'date': str(transaction_data.get('transaction_date') or transaction_data.get('date', '')),
            'description': str(description) if description else '',
            'journal': str(journal_name) if journal_name else '',
            'partners': str(partner_name) if partner_name else '',
            'reference': reference,
            
            # Additional share transaction specific fields
            'transaction_date': str(transaction_data.get('transaction_date') or transaction_data.get('date', '')),
            'narration': narration,
            'journal_details': convert_to_decimal(journal) if journal else {},
            'partner_details': convert_to_decimal(partner) if partner else {},
            'company_details': convert_to_decimal(company) if company else {},
            'transaction_amount': convert_to_decimal(transaction_data.get('transaction_amount', 0)),
            'total_amount': convert_to_decimal(transaction_data.get('total_amount', 0)),
            'currency': convert_to_decimal(transaction_data.get('currency', [])) if transaction_data.get('currency') else [],
            'line_items': convert_to_decimal(line_items) if line_items else [],
            'journal_entries_detailed': convert_to_decimal(journal_entries_detailed) if journal_entries_detailed else [],
            'line_count': int(transaction_data.get('line_count', 0)),
            
            # Odoo metadata
            'odoo_transaction_id': int(transaction_data.get('transaction_id', 0)) if transaction_data.get('transaction_id') else 0,
            'odoo_entry_number': str(transaction_data.get('entry_number', '')),
            'move_type': str(transaction_data.get('move_type', 'entry')),
            'state': str(transaction_data.get('state', 'posted')),
            
            # Metadata
            'created_at': datetime.utcnow().isoformat(),
            'exists': bool(transaction_data.get('exists', False))
        }
        
        # Save to DynamoDB
        share_transactions_table.put_item(Item=transaction_item)
        
        result["success"] = True
        result["share_transaction_id"] = share_transaction_id
        result["message"] = f"Share transaction created successfully: {share_transaction_id}"
        
        print(f"✅ Share transaction created: {share_transaction_id}")
        print(f"   Odoo Transaction ID: {transaction_data.get('transaction_id', 'N/A')}")
        print(f"   Odoo Entry Number: {transaction_data.get('entry_number', 'N/A')}")
        print(f"   Amount: {transaction_data.get('total_amount', 0)}")
        print(f"   Partner: {partner_name if partner_name else 'N/A'}")
        print(f"   Company: {company_name if company_name else 'N/A'}")
        
    except Exception as e:
        result["success"] = False
        result["message"] = f"Failed to create share transaction: {str(e)}"
        print(f"❌ Share transaction creation failed: {e}")
    
    return result


# Example usage
if __name__ == "__main__":
    # Example share transaction data (replace with actual input from createsharetransaction.py)
    sample_transaction = {
        "company": {
            "country": [55, "Cyprus"],
            "currency": [125, "EUR"],
            "id": 125,
            "name": "KYRASTEL ENTERPRISES LIMITED"
        },
        "currency": [125, "EUR"],
        "customer_ref": "Director's Resolution dated 15/01/2025 - Share Allotment",
        "date": "2025-01-15",
        "entry_number": "JV/2025/01/0001",
        "exists": False,
        "journal": {
            "code": "JV",
            "id": 818,
            "name": "Journal Voucher",
            "type": "general"
        },
        "journal_entries_detailed": [
            {
                "account": {
                    "code": False,
                    "id": 17762,
                    "name": "Accounts receivable",
                    "type": "asset_receivable"
                },
                "balance": 10000.0,
                "credit": 0.0,
                "debit": 10000.0,
                "display_type": "product",
                "id": 4723,
                "is_tax_line": False,
                "name": "10,000 ordinary shares of nominal value €1 each (Qty: 10,000 @ 1.00)",
                "partner": {
                    "id": 438,
                    "name": "STELIOS KYRANIDES"
                },
                "price_subtotal": 10000.0,
                "price_total": 10000.0,
                "price_unit": 0.0,
                "quantity": 1.0
            },
            {
                "account": {
                    "code": False,
                    "id": 17795,
                    "name": "Share capital",
                    "type": "equity"
                },
                "balance": -10000.0,
                "credit": 10000.0,
                "debit": 0.0,
                "display_type": "product",
                "id": 4724,
                "is_tax_line": False,
                "name": "10,000 ordinary shares of nominal value €1 each (Qty: 10,000 @ 1.00)",
                "partner": {
                    "id": 438,
                    "name": "STELIOS KYRANIDES"
                },
                "price_subtotal": -10000.0,
                "price_total": -10000.0,
                "price_unit": 0.0,
                "quantity": 1.0
            }
        ],
        "line_count": 2,
        "line_items": [
            {
                "account_code": False,
                "account_name": "Accounts receivable",
                "account_type": "asset_receivable",
                "balance": 10000.0,
                "credit": 0.0,
                "debit": 10000.0,
                "display_type": "product",
                "id": 4723,
                "is_tax_line": False,
                "label": "10,000 ordinary shares of nominal value €1 each (Qty: 10,000 @ 1.00)",
                "partner": "STELIOS KYRANIDES",
                "price_subtotal": 10000.0,
                "price_total": 10000.0,
                "price_unit": 0.0,
                "quantity": 1.0,
                "tax_tags": None,
                "taxes": None
            },
            {
                "account_code": False,
                "account_name": "Share capital",
                "account_type": "equity",
                "balance": -10000.0,
                "credit": 10000.0,
                "debit": 0.0,
                "display_type": "product",
                "id": 4724,
                "is_tax_line": False,
                "label": "10,000 ordinary shares of nominal value €1 each (Qty: 10,000 @ 1.00)",
                "partner": "STELIOS KYRANIDES",
                "price_subtotal": -10000.0,
                "price_total": -10000.0,
                "price_unit": 0.0,
                "quantity": 1.0,
                "tax_tags": None,
                "taxes": None
            }
        ],
        "message": "Share capital transaction created and posted successfully",
        "move_type": "entry",
        "narration": "<p>Payment Reference: SHARE-2025-001</p>",
        "partner": {
            "address": {
                "city": False,
                "country": False,
                "street": False
            },
            "email": False,
            "id": 438,
            "name": "STELIOS KYRANIDES",
            "phone": False,
            "vat": False
        },
        "reference": "Director's Resolution dated 15/01/2025 - Share Allotment",
        "state": "posted",
        "success": True,
        "total_amount": 10000.0,
        "transaction_amount": 10000.0,
        "transaction_date": "2025-01-15",
        "transaction_id": 1915
    }
    
    # Process the share transaction
    result = process_share_transaction(sample_transaction)
    print(f"\nResult: {result}")