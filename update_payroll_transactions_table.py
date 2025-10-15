import boto3
from datetime import datetime
from botocore.exceptions import ClientError
from decimal import Decimal

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='eu-north-1')
payroll_transactions_table = dynamodb.Table('payroll_transactions')

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

def generate_payroll_transaction_id():
    """Generate unique payroll transaction ID"""
    now = datetime.utcnow()
    timestamp = now.strftime('%Y_%m_%d_%H_%M_%S')
    return f"PAY_{timestamp}"

def safe_get_nested(data, *keys, default=''):
    """Safely extract nested values from dictionaries"""
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key, default)
        else:
            return default
    return result if result is not None else default

def process_payroll_transaction(transaction_data):
    """
    Process a single payroll transaction and create entry in DynamoDB
    
    Args:
        transaction_data: Dictionary containing payroll transaction data from the input JSON
        
    Returns:
        Dictionary with processing result
    """
    result = {
        "success": False,
        "payroll_transaction_id": None,
        "odoo_entry_id": transaction_data.get('entry_id'),
        "message": ""
    }
    
    try:
        # Generate unique payroll transaction ID
        payroll_transaction_id = generate_payroll_transaction_id()
        
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
        company_name = company.get('name', '') or transaction_data.get('company_name', '')
        
        # Extract journal details safely
        journal = transaction_data.get('journal', {})
        if not isinstance(journal, dict):
            journal = {}
        journal_name = journal.get('name', '') or transaction_data.get('journal_name', '')
        
        # Extract partner details safely (usually None for payroll)
        partner = transaction_data.get('partner', {})
        if not isinstance(partner, dict):
            partner = {}
        partner_name = partner.get('name', '') if partner else ''
        
        # Extract journal entries detailed safely
        journal_entries_detailed = transaction_data.get('journal_entries_detailed', [])
        if not isinstance(journal_entries_detailed, list):
            journal_entries_detailed = []
        
        # Handle reference (ref or reference field)
        reference = transaction_data.get('reference') or transaction_data.get('ref')
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
        
        # Handle period and year
        period = transaction_data.get('period', '')
        if period is False or period is None:
            period = ''
        else:
            period = str(period) if period else ''
        
        year = transaction_data.get('year', '')
        if year is False or year is None:
            year = ''
        else:
            year = str(year) if year else ''
        
        # Handle warnings
        warnings = transaction_data.get('warnings', [])
        if not isinstance(warnings, list):
            warnings = []
        
        # Handle missing_accounts
        missing_accounts = transaction_data.get('missing_accounts', [])
        if not isinstance(missing_accounts, list):
            missing_accounts = []
        
        # Prepare payroll transaction item for DynamoDB
        transaction_item = {
            # Core fields matching share transactions table structure
            'payroll_transaction_id': payroll_transaction_id,
            'amount': convert_to_decimal(transaction_data.get('amount_total', 0)),
            'company_name': str(company_name) if company_name else '',
            'date': str(transaction_data.get('transaction_date') or transaction_data.get('date', '')),
            'description': str(description) if description else '',
            'journal': str(journal_name) if journal_name else '',
            'partners': str(partner_name) if partner_name else '',
            'reference': reference,
            
            # Additional payroll transaction specific fields
            'transaction_date': str(transaction_data.get('transaction_date') or transaction_data.get('date', '')),
            'period': period,
            'year': year,
            'narration': narration,
            'journal_details': convert_to_decimal(journal) if journal else {},
            'partner_details': convert_to_decimal(partner) if partner else {},
            'company_details': convert_to_decimal(company) if company else {},
            'total_amount': convert_to_decimal(transaction_data.get('amount_total', 0)),
            'currency': convert_to_decimal(transaction_data.get('currency', [])) if transaction_data.get('currency') else [],
            'line_items': convert_to_decimal(line_items) if line_items else [],
            'journal_entries_detailed': convert_to_decimal(journal_entries_detailed) if journal_entries_detailed else [],
            'line_count': int(transaction_data.get('line_count', 0)),
            
            # Payroll specific fields
            'total_debits': convert_to_decimal(transaction_data.get('total_debits', 0)),
            'total_credits': convert_to_decimal(transaction_data.get('total_credits', 0)),
            'balance_difference': convert_to_decimal(transaction_data.get('balance_difference', 0)),
            'is_balanced': bool(transaction_data.get('is_balanced', True)),
            'auto_balanced': bool(transaction_data.get('auto_balanced', False)),
            'requires_review': bool(transaction_data.get('requires_review', False)),
            'warnings': warnings if warnings else [],
            'missing_accounts': missing_accounts if missing_accounts else [],
            
            # Odoo metadata
            'odoo_entry_id': int(transaction_data.get('entry_id', 0)) if transaction_data.get('entry_id') else 0,
            'odoo_entry_number': str(transaction_data.get('entry_number', '')),
            'move_type': str(transaction_data.get('move_type', 'entry')),
            'state': str(transaction_data.get('state', 'posted')),
            'journal_code': str(transaction_data.get('journal_code', '')),
            
            # Metadata
            'created_at': datetime.utcnow().isoformat(),
            'exists': bool(transaction_data.get('exists', False))
        }
        
        # Save to DynamoDB
        payroll_transactions_table.put_item(Item=transaction_item)
        
        result["success"] = True
        result["payroll_transaction_id"] = payroll_transaction_id
        result["message"] = f"Payroll transaction created successfully: {payroll_transaction_id}"
        
        print(f"✅ Payroll transaction created: {payroll_transaction_id}")
        print(f"   Odoo Entry ID: {transaction_data.get('entry_id', 'N/A')}")
        print(f"   Odoo Entry Number: {transaction_data.get('entry_number', 'N/A')}")
        print(f"   Period: {period if period else 'N/A'}")
        print(f"   Year: {year if year else 'N/A'}")
        print(f"   Amount: {transaction_data.get('amount_total', 0)}")
        print(f"   Company: {company_name if company_name else 'N/A'}")
        print(f"   Total Debits: {transaction_data.get('total_debits', 0)}")
        print(f"   Total Credits: {transaction_data.get('total_credits', 0)}")
        print(f"   Balanced: {transaction_data.get('is_balanced', True)}")
        print(f"   Auto-balanced: {transaction_data.get('auto_balanced', False)}")
        print(f"   Requires Review: {transaction_data.get('requires_review', False)}")
        
    except Exception as e:
        result["success"] = False
        result["message"] = f"Failed to create payroll transaction: {str(e)}"
        print(f"❌ Payroll transaction creation failed: {e}")
    
    return result


# Example usage
if __name__ == "__main__":
    # Example payroll transaction data (from the provided sample)
    sample_transaction = {
        "amount_total": 1239.53,
        "auto_balanced": False,
        "balance_difference": 0.0,
        "company": {
            "country": [55, "Cyprus"],
            "currency": [125, "EUR"],
            "id": 124,
            "name": "ENAMI Limited"
        },
        "company_name": "ENAMI Limited",
        "currency": [125, "EUR"],
        "date": "2025-06-30",
        "entry_id": 1922,
        "entry_number": "SLR/2025/06/0001",
        "exists": False,
        "is_balanced": True,
        "journal": {
            "code": "SLR",
            "id": 801,
            "name": "Salaries",
            "type": "general"
        },
        "journal_code": "SLR",
        "journal_entries_detailed": [
            {
                "account": {
                    "code": False,
                    "id": 17644,
                    "name": "Gross wages",
                    "type": "expense"
                },
                "balance": 1050.0,
                "credit": 0.0,
                "debit": 1050.0,
                "display_type": "product",
                "id": 4759,
                "is_tax_line": False,
                "name": "Total gross salaries for June 2025",
                "price_subtotal": 1050.0,
                "price_total": 1050.0,
                "price_unit": 0.0,
                "quantity": 1.0
            }
        ],
        "journal_name": "Salaries",
        "line_count": 6,
        "line_items": [
            {
                "account_code": False,
                "account_name": "Gross wages",
                "account_type": "expense",
                "balance": 1050.0,
                "credit": 0.0,
                "debit": 1050.0,
                "display_type": "product",
                "id": 4759,
                "is_tax_line": False,
                "label": "Total gross salaries for June 2025",
                "partner": None,
                "price_subtotal": 1050.0,
                "price_total": 1050.0,
                "price_unit": 0.0,
                "quantity": 1.0,
                "tax_tags": None,
                "taxes": None
            }
        ],
        "message": "Payroll journal entry created and posted successfully",
        "missing_accounts": None,
        "move_type": "entry",
        "narration": "<p>Payroll for June 2025...</p>",
        "partner": None,
        "period": "202506 - JUNE",
        "ref": "Payroll - 202506 - JUNE 2025",
        "reference": "Payroll - 202506 - JUNE 2025",
        "requires_review": False,
        "state": "posted",
        "success": True,
        "total_credits": 1239.53,
        "total_debits": 1239.53,
        "transaction_date": "2025-06-30",
        "warnings": None,
        "year": "2025"
    }
    
    # Process the payroll transaction
    result = process_payroll_transaction(sample_transaction)
    print(f"\nResult: {result}")