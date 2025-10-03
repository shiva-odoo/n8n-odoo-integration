import boto3
from datetime import datetime
from botocore.exceptions import ClientError
from decimal import Decimal

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='eu-north-1')
transactions_table = dynamodb.Table('transactions')

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

def extract_line_items(line_items_data):
    """Extract and format line items from input data"""
    line_items = []
    
    # Handle DynamoDB format with 'L' wrapper
    if isinstance(line_items_data, dict) and 'L' in line_items_data:
        items_list = line_items_data['L']
    else:
        items_list = line_items_data
    
    for item in items_list:
        # Handle DynamoDB format with 'M' wrapper
        if isinstance(item, dict) and 'M' in item:
            item_data = item['M']
        else:
            item_data = item
        
        # Extract values, handling DynamoDB type descriptors
        line_item = {}
        for key, value in item_data.items():
            if isinstance(value, dict):
                # Handle DynamoDB type descriptors (S, N, etc.)
                if 'S' in value:
                    line_item[key] = value['S']
                elif 'N' in value:
                    line_item[key] = Decimal(value['N'])
                else:
                    line_item[key] = value
            else:
                line_item[key] = value
        
        line_items.append(line_item)
    
    return line_items

def extract_journal(journal_data):
    """Extract and format journal from input data"""
    # Handle DynamoDB format with 'M' wrapper
    if isinstance(journal_data, dict) and 'M' in journal_data:
        journal_dict = journal_data['M']
    else:
        journal_dict = journal_data
    
    journal = {}
    for key, value in journal_dict.items():
        if isinstance(value, dict):
            # Handle DynamoDB type descriptors
            if 'S' in value:
                journal[key] = value['S']
            elif 'N' in value:
                journal[key] = int(value['N'])
            else:
                journal[key] = value
        else:
            journal[key] = value
    
    return journal

def extract_description(line_items):
    """Extract unique labels from line items to create description"""
    labels = []
    for item in line_items:
        label = item.get('label', '')
        if label and label not in labels:
            labels.append(label)
    
    # Join all unique labels
    return ' | '.join(labels) if labels else ''

def generate_transaction_id(index):
    """Generate unique transaction ID"""
    now = datetime.utcnow()
    timestamp = now.strftime('%Y_%m_%d_%H_%M_%S')
    return f"TXN_{timestamp}_{index}"

def process_transactions(transactions_list):
    """
    Process all transactions and create entries in DynamoDB
    
    Args:
        transactions_list: List of transaction data from the input JSON
    """
    results = {
        "success": True,
        "total": len(transactions_list),
        "created": 0,
        "failed": 0,
        "transactions": []
    }
    
    for idx, transaction_data in enumerate(transactions_list):
        try:
            # Extract and process line items
            line_items = extract_line_items(transaction_data.get('line_items', {}))
            
            # Extract and process journal
            journal = extract_journal(transaction_data.get('journal', {}))
            
            # Generate description from line items
            description = extract_description(line_items)
            
            # Generate unique transaction ID
            transaction_id = generate_transaction_id(idx + 1)
            
            # Prepare transaction item for DynamoDB
            transaction_item = {
                'transaction_id': transaction_id,
                'amount': convert_to_decimal(transaction_data.get('amount', 0)),
                'company_name': transaction_data.get('company_name', ''),
                'reference': transaction_data.get('reference', ''),
                'date': transaction_data.get('date', ''),
                'partner': transaction_data.get('transaction_partner', ''),
                'odoo_id': transaction_data.get('journal_entry_id', 0),
                'description': description,
                'line_items': convert_to_decimal(line_items),
                'journal': convert_to_decimal(journal),
                'created_at': datetime.utcnow().isoformat()
            }
            
            # Save to DynamoDB
            transactions_table.put_item(Item=transaction_item)
            
            results["created"] += 1
            results["transactions"].append({
                "index": idx + 1,
                "transaction_id": transaction_id,
                "journal_entry_id": transaction_data.get('journal_entry_id'),
                "amount": transaction_data.get('amount'),
                "status": "created"
            })
            
            print(f"✅ Transaction {idx + 1} created: {transaction_id}")
            
        except Exception as e:
            results["failed"] += 1
            results["success"] = False
            results["transactions"].append({
                "index": idx + 1,
                "journal_entry_id": transaction_data.get('journal_entry_id'),
                "status": "failed",
                "error": str(e)
            })
            print(f"❌ Transaction {idx + 1} failed: {e}")
    
    results["message"] = f"Processed {results['total']} transactions: {results['created']} created, {results['failed']} failed"
    
    return results