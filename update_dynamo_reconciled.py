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
    Expects input format:
    {
        "bills": [{ "bill_id": ... }],
        "invoices": [{ "invoice_id": ... }],
        "shares": [{ "share_transaction_id": ... }],
        "payroll": [{ "payroll_transaction_id": ... }],
        "bank_transactions": [{ "transaction_id": ... }]
    }
    """

    # ---------------- Bills ----------------
    for item in input_data.get("bills", []):
        bill_id = item.get("bill_id")
        if bill_id:
            mark_reconciled(bills_table, "bill_id", bill_id)

    # ---------------- Invoices ----------------
    for item in input_data.get("invoices", []):
        invoice_id = item.get("invoice_id")
        if invoice_id:
            mark_reconciled(invoices_table, "invoice_id", invoice_id)

    # ---------------- Share Transactions ----------------
    for item in input_data.get("shares", []):
        share_id = item.get("share_transaction_id")
        if share_id:
            mark_reconciled(shares_table, "share_transaction_id", share_id)

    # ---------------- Payroll ----------------
    for item in input_data.get("payroll", []):
        payroll_id = item.get("payroll_transaction_id")
        if payroll_id:
            mark_reconciled(payroll_table, "payroll_transaction_id", payroll_id)

    # ---------------- Bank Transactions ----------------
    for item in input_data.get("bank_transactions", []):
        txn_id = item.get("transaction_id")
        if txn_id:
            mark_reconciled(transactions_table, "transaction_id", txn_id)

    print("Reconciliation updates completed.")
    return {"success": True}
