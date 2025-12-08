import boto3
from botocore.exceptions import ClientError

# ----------------------------------------------------
# DynamoDB setup
# ----------------------------------------------------
dynamodb = boto3.resource('dynamodb', region_name='eu-north-1')

bills_table = dynamodb.Table('bills')
invoices_table = dynamodb.Table('invoices')
shares_table = dynamodb.Table('share_transactions')
payroll_table = dynamodb.Table('payroll_transactions')
transactions_table = dynamodb.Table('transactions')


# ----------------------------------------------------
# Helper function to mark a record as reconciled
# ----------------------------------------------------
def mark_reconciled(table, key_name, key_value):
    """
    Updates a single record in a DynamoDB table:
    Sets reconciled = "true"
    """
    try:
        table.update_item(
            Key={key_name: key_value},
            UpdateExpression="SET reconciled = :val",
            ExpressionAttributeValues={":val": "true"}
        )
        print(f"Updated {table.name}: {key_name}={key_value}")
        return True

    except ClientError as e:
        print(f"Failed updating {table.name} for {key_value}: {e}")
        return False


# ----------------------------------------------------
# Main function the endpoint will call
# ----------------------------------------------------
def process_reconciliation(input_data):
    """
    Accepts BOTH formats:
    - ["ID1", "ID2", ...]
    - [{ "bill_id": "ID1" }, ...]
    """

    def extract_id(item, key):
        """Return ID from either a string or a dict."""
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            return item.get(key)
        return None

    # ---------------- Bills ----------------
    for item in input_data.get("bills", []):
        bill_id = extract_id(item, "bill_id")
        if bill_id:
            mark_reconciled(bills_table, "bill_id", bill_id)

    # ---------------- Invoices ----------------
    for item in input_data.get("invoices", []):
        invoice_id = extract_id(item, "invoice_id")
        if invoice_id:
            mark_reconciled(invoices_table, "invoice_id", invoice_id)

    # ---------------- Share Transactions ----------------
    for item in input_data.get("shares", []):
        share_id = extract_id(item, "share_transaction_id")
        if share_id:
            mark_reconciled(shares_table, "share_transaction_id", share_id)

    # ---------------- Payroll ----------------
    for item in input_data.get("payroll", []):
        payroll_id = extract_id(item, "payroll_transaction_id")
        if payroll_id:
            mark_reconciled(payroll_table, "payroll_transaction_id", payroll_id)

    # ---------------- Bank Transactions ----------------
    for item in input_data.get("bank_transactions", []):
        txn_id = extract_id(item, "transaction_id")
        if txn_id:
            mark_reconciled(transactions_table, "transaction_id", txn_id)

    print("Reconciliation updates completed.")
    return {"success": True}

