# bank_reconciliation.py
import boto3
from datetime import datetime
from botocore.exceptions import ClientError
from decimal import Decimal
import os

# Configuration
AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
transactions_table = dynamodb.Table('transactions')
bank_accounts_table = dynamodb.Table('bank_accounts')

def convert_decimal(obj):
    """Convert DynamoDB Decimal objects to regular Python numbers"""
    if isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal(v) for v in obj]
    elif isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    else:
        return obj

def get_bank_transactions(business_company_id, bank_account_id=None, date_from=None, date_to=None, status=None):
    """Get bank transactions for reconciliation using business_company_id"""
    try:
        # IMPORTANT: Filter by business_company_id (from DynamoDB onboarding_submissions)
        # This ensures we only get transactions for the specific company (e.g., 139, 124, 125, etc.)
        filter_expression = 'business_company_id = :business_company_id'
        expression_values = {':business_company_id': str(business_company_id)}
        
        if bank_account_id:
            filter_expression += ' AND bank_account_id = :bank_account_id'
            expression_values[':bank_account_id'] = bank_account_id
        
        if status:
            filter_expression += ' AND reconciliation_status = :status'
            expression_values[':status'] = status
        
        # Scan transactions table with filter
        response = transactions_table.scan(
            FilterExpression=filter_expression,
            ExpressionAttributeValues=expression_values
        )
        
        transactions = convert_decimal(response.get('Items', []))
        
        # Filter by date range if provided
        if date_from or date_to:
            filtered_transactions = []
            for txn in transactions:
                txn_date = txn.get('transaction_date', '')
                
                if date_from and txn_date < date_from:
                    continue
                if date_to and txn_date > date_to:
                    continue
                
                filtered_transactions.append(txn)
            
            transactions = filtered_transactions
        
        # Sort by transaction date (newest first)
        transactions.sort(key=lambda x: x.get('transaction_date', ''), reverse=True)
        
        # Format transactions for frontend
        formatted_transactions = []
        for txn in transactions:
            formatted_transactions.append({
                'transaction_id': txn.get('transaction_id', ''),
                'bank_account_id': txn.get('bank_account_id', ''),
                'transaction_date': txn.get('transaction_date', ''),
                'description': txn.get('description', ''),
                'reference': txn.get('reference', ''),
                'amount': txn.get('amount', 0),
                'type': txn.get('type', 'debit'),  # credit or debit
                'balance': txn.get('balance', 0),
                'reconciliation_status': txn.get('reconciliation_status', 'unreconciled'),
                'matched_invoice_id': txn.get('matched_invoice_id'),
                'matched_bill_id': txn.get('matched_bill_id'),
                'matched_at': txn.get('matched_at'),
                'created_at': txn.get('created_at', '')
            })
        
        return {
            "success": True,
            "transactions": formatted_transactions,
            "total_count": len(formatted_transactions)
        }
        
    except ClientError as e:
        print(f"DynamoDB error getting bank transactions: {e}")
        return {
            "success": False,
            "error": "Failed to retrieve bank transactions"
        }
    except Exception as e:
        print(f"Error getting bank transactions: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def get_bank_accounts(business_company_id):
    """Get all bank accounts for a company using business_company_id"""
    try:
        try:
            # IMPORTANT: Filter by business_company_id (from DynamoDB onboarding_submissions)
            response = bank_accounts_table.scan(
                FilterExpression='business_company_id = :business_company_id',
                ExpressionAttributeValues={
                    ':business_company_id': str(business_company_id)
                }
            )
            accounts = convert_decimal(response.get('Items', []))
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Table doesn't exist yet, return empty list
                print(f"⚠️ bank_accounts table not found, returning empty list")
                accounts = []
            else:
                raise
        
        # Format accounts for frontend
        formatted_accounts = []
        for account in accounts:
            formatted_accounts.append({
                'bank_account_id': account.get('bank_account_id', ''),
                'account_name': account.get('account_name', ''),
                'account_number': account.get('account_number', ''),
                'bank_name': account.get('bank_name', ''),
                'currency': account.get('currency', 'USD'),
                'current_balance': account.get('current_balance', 0),
                'account_type': account.get('account_type', 'checking'),
                'status': account.get('status', 'active'),
                'created_at': account.get('created_at', '')
            })
        
        return {
            "success": True,
            "accounts": formatted_accounts,
            "total_count": len(formatted_accounts)
        }
        
    except ClientError as e:
        print(f"DynamoDB error getting bank accounts: {e}")
        return {
            "success": False,
            "error": "Failed to retrieve bank accounts"
        }
    except Exception as e:
        print(f"Error getting bank accounts: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def reconcile_transaction(transaction_id, business_company_id, matched_record_type, matched_record_id, reconciled_by):
    """Mark a transaction as reconciled and link to accounting record"""
    try:
        # Validate that transaction belongs to the company (security check)
        response = transactions_table.get_item(Key={'transaction_id': transaction_id})
        transaction = response.get('Item')
        
        if not transaction:
            return {
                "success": False,
                "error": "Transaction not found"
            }
        
        # Verify the transaction belongs to this business_company_id
        if transaction.get('business_company_id') != str(business_company_id):
            return {
                "success": False,
                "error": "Transaction does not belong to this company"
            }
        
        # Now proceed with reconciliation
        # Update transaction with reconciliation info
        transactions_table.update_item(
            Key={'transaction_id': transaction_id},
            UpdateExpression='SET reconciliation_status = :status, matched_at = :matched_at, reconciled_by = :reconciled_by',
            ExpressionAttributeValues={
                ':status': 'reconciled',
                ':matched_at': datetime.utcnow().isoformat(),
                ':reconciled_by': reconciled_by
            }
        )
        
        # Update matched field based on record type
        if matched_record_type == 'invoice':
            transactions_table.update_item(
                Key={'transaction_id': transaction_id},
                UpdateExpression='SET matched_invoice_id = :matched_id',
                ExpressionAttributeValues={':matched_id': matched_record_id}
            )
        elif matched_record_type == 'bill':
            transactions_table.update_item(
                Key={'transaction_id': transaction_id},
                UpdateExpression='SET matched_bill_id = :matched_id',
                ExpressionAttributeValues={':matched_id': matched_record_id}
            )
        
        print(f"Transaction {transaction_id} reconciled with {matched_record_type} {matched_record_id}")
        
        return {
            "success": True,
            "message": "Transaction reconciled successfully"
        }
        
    except ClientError as e:
        print(f"DynamoDB error reconciling transaction: {e}")
        return {
            "success": False,
            "error": "Failed to reconcile transaction"
        }
    except Exception as e:
        print(f"Error reconciling transaction: {e}")
        return {
            "success": False,
            "error": str(e)
        }

