import boto3
import base64
import anthropic
import os
import json
import re

# AWS DynamoDB configuration
AWS_REGION = os.getenv('AWS_REGION', 'eu-north-1')
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
users_table = dynamodb.Table('users')

def get_company_context(company_name):
    """
    Fetch comprehensive company details from DynamoDB users table
    
    Args:
        company_name (str): Company name to lookup
    
    Returns:
        dict: Company context or None if not found
    """
    try:
        # Scan table to find matching company (case-sensitive exact match)
        response = users_table.scan(
            FilterExpression='company_name = :name',
            ExpressionAttributeValues={':name': company_name}
        )
        
        if response.get('Items'):
            company_data = response['Items'][0]
            
            # Extract basic company information
            context = {
                'company_name': company_data.get('company_name', ''),
                'is_vat_registered': company_data.get('is_vat_registered', 'unknown'),
                'primary_industry': company_data.get('primary_industry', ''),
                'business_description': company_data.get('business_description', ''),
                'business_model': company_data.get('business_model', ''),
                'main_products': company_data.get('main_products', ''),
                'business_address': company_data.get('business_address', ''),
                'registration_no': company_data.get('registration_no', ''),
                'vat_no': company_data.get('vat_no', ''),
                'tax_registration_no': company_data.get('tax_registration_no', ''),
                'trading_name': company_data.get('trading_name', '')
            }
            
            # Extract tax information
            tax_info = company_data.get('tax_information', {})
            context['tax_information'] = {
                'reverse_charge': tax_info.get('reverse_charge', []),
                'reverse_charge_other': tax_info.get('reverse_charge_other', ''),
                'vat_exemptions': tax_info.get('vat_exemptions', ''),
                'vat_period_category': tax_info.get('vat_period_category', ''),
                'vat_rates': tax_info.get('vat_rates', [])
            }
            
            # Extract payroll information
            payroll_info = company_data.get('payroll_information', {})
            context['payroll_information'] = {
                'num_employees': payroll_info.get('num_employees', 0),
                'payroll_frequency': payroll_info.get('payroll_frequency', ''),
                'social_insurance': payroll_info.get('social_insurance', ''),
                'uses_ghs': payroll_info.get('uses_ghs', False)
            }
            
            # Extract business operations
            business_ops = company_data.get('business_operations', {})
            context['business_operations'] = {
                'international': business_ops.get('international', False),
                'inventory_management': business_ops.get('inventory_management', ''),
                'multi_location': business_ops.get('multi_location', False),
                'seasonal_business': business_ops.get('seasonal_business', False),
                'peak_seasons': business_ops.get('peak_seasons', '')
            }
            
            # Extract special circumstances
            special_circumstances = company_data.get('special_circumstances', {})
            context['special_circumstances'] = {}
            
            # Construction circumstances
            construction = special_circumstances.get('construction', {})
            if construction.get('enabled', False):
                context['special_circumstances']['construction'] = {
                    'enabled': True,
                    'project_duration': construction.get('project_duration', '')
                }
            
            # Retail/E-commerce circumstances
            retail_ecommerce = special_circumstances.get('retail_ecommerce', {})
            if retail_ecommerce.get('enabled', False):
                context['special_circumstances']['retail_ecommerce'] = {
                    'enabled': True,
                    'platform_type': retail_ecommerce.get('platform_type', '')
                }
            
            # Banking information
            banking_info = company_data.get('banking_information', {})
            context['banking_information'] = {
                'primary_bank': banking_info.get('primary_bank', ''),
                'primary_currency': banking_info.get('primary_currency', ''),
                'multi_currency': banking_info.get('multi_currency', False),
                'currencies_list': banking_info.get('currencies_list', [])
            }
            
            # Extract metadata
            metadata = company_data.get('metadata', {})
            context['metadata'] = {
                'rep_name': metadata.get('rep_name', ''),
                'rep_email': metadata.get('rep_email', ''),
                'vat_no': metadata.get('vat_no', '')
            }
            
            print(f"✅ Company context loaded for: {company_name}")
            print(f"   VAT Registered: {context['is_vat_registered']}")
            print(f"   Industry: {context['primary_industry']}")
            print(f"   Number of Employees: {context['payroll_information']['num_employees']}")
            print(f"   Payroll Frequency: {context['payroll_information']['payroll_frequency']}")
            print(f"   Primary Bank: {context['banking_information']['primary_bank']}")
            
            return context
        else:
            print(f"⚠️  No company context found for: {company_name}")
            return None
            
    except Exception as e:
        print(f"❌ Error fetching company context: {e}")
        return None

def get_company_context_section(company_context):
    """Generate company context section for prompt"""
    
    if not company_context:
        return """
**COMPANY CONTEXT:** Not available - proceed with standard processing
"""
    
    # Build context sections
    basic_info = f"""
**Company:** {company_context.get('company_name', 'N/A')}
**VAT Status:** {'✅ VAT Registered' if company_context.get('is_vat_registered') == 'yes' else '❌ NOT VAT Registered' if company_context.get('is_vat_registered') == 'no' else '⚠️ Unknown'}
**Primary Industry:** {company_context.get('primary_industry', 'N/A')}
**Business Description:** {company_context.get('business_description', 'N/A')}
**Business Model:** {company_context.get('business_model', 'N/A')}
**Main Products/Services:** {company_context.get('main_products', 'N/A')}
**Business Address:** {company_context.get('business_address', 'N/A')}
**Registration No:** {company_context.get('registration_no', 'N/A')}
**VAT No:** {company_context.get('vat_no', 'N/A')}"""

    # Tax information section
    tax_info = company_context.get('tax_information', {})
    tax_section = f"""
**TAX INFORMATION:**
- VAT Exemptions: {tax_info.get('vat_exemptions', 'N/A')}
- VAT Period Category: {tax_info.get('vat_period_category', 'N/A')}
- VAT Rates: {', '.join(map(str, tax_info.get('vat_rates', [])))}%"""

    # Payroll information section
    payroll_info = company_context.get('payroll_information', {})
    payroll_section = f"""
**PAYROLL INFORMATION:**
- Number of Employees: {payroll_info.get('num_employees', 0)}
- Payroll Frequency: {payroll_info.get('payroll_frequency', 'N/A')}
- Social Insurance: {payroll_info.get('social_insurance', 'N/A')}
- Uses GHS: {'Yes' if payroll_info.get('uses_ghs', False) else 'No'}"""

    # Business operations section
    business_ops = company_context.get('business_operations', {})
    operations_section = f"""
**BUSINESS OPERATIONS:**
- International Operations: {'Yes' if business_ops.get('international', False) else 'No'}
- Inventory Management: {business_ops.get('inventory_management', 'N/A')}
- Multi-Location: {'Yes' if business_ops.get('multi_location', False) else 'No'}
- Seasonal Business: {'Yes' if business_ops.get('seasonal_business', False) else 'No'}
- Peak Seasons: {business_ops.get('peak_seasons', 'N/A')}"""

    # Special circumstances section
    special_circumstances = company_context.get('special_circumstances', {})
    special_section = "**SPECIAL CIRCUMSTANCES:**"
    if special_circumstances:
        if 'construction' in special_circumstances:
            construction = special_circumstances['construction']
            special_section += f"\n- Construction Project: Active (Duration: {construction.get('project_duration', 'N/A')})"
        if 'retail_ecommerce' in special_circumstances:
            retail = special_circumstances['retail_ecommerce']
            special_section += f"\n- Retail/E-commerce: Active (Platform: {retail.get('platform_type', 'N/A')})"
    else:
        special_section += "\n- None specified"

    # Banking information section
    banking_info = company_context.get('banking_information', {})
    banking_section = f"""
**BANKING INFORMATION:**
- Primary Bank: {banking_info.get('primary_bank', 'N/A')}
- Primary Currency: {banking_info.get('primary_currency', 'N/A')}
- Multi-Currency: {'Yes' if banking_info.get('multi_currency', False) else 'No'}
- Supported Currencies: {', '.join(banking_info.get('currencies_list', []))}"""

    return f"""
**COMPANY CONTEXT - USE THIS TO IMPROVE ACCURACY:**

{basic_info}

{tax_section}

{payroll_section}

{operations_section}

{special_section}

{banking_section}

**USE THIS CONTEXT TO:**
1. ✅ Validate transaction types align with company's industry and business model
2. ✅ Identify expected transaction patterns (e.g., payroll frequency, typical vendor types)
3. ✅ Flag unusual transactions that don't match business description for review
4. ✅ Apply correct partner names based on primary bank information
5. ✅ Consider employee count when processing payroll transactions
6. ✅ Use payroll frequency to identify wage payments accurately
7. ✅ Apply industry-specific transaction categorization
8. ✅ Handle international transactions appropriately if company has international operations

**INDUSTRY-SPECIFIC GUIDANCE:**
{get_industry_specific_guidance(company_context)}

**PAYROLL TRANSACTION GUIDANCE:**
{get_payroll_transaction_guidance(company_context)}
"""

def get_industry_specific_guidance(company_context):
    """Provide industry-specific transaction guidance"""
    
    industry = company_context.get('primary_industry', '').lower()
    business_desc = company_context.get('business_description', '').lower()
    
    # Property/Real Estate/Construction industries
    if any(keyword in industry or keyword in business_desc for keyword in 
           ['property', 'real estate', 'construction', 'development', 'rental']):
        return """
- Expect frequent property-related transactions (rent, management fees, maintenance)
- Payments to architects, surveyors, engineers should be common
- Legal fees for property transactions are expected
- Utility payments for multiple properties possible"""
    
    # Investment/Portfolio Management
    elif any(keyword in industry for keyword in ['investment', 'portfolio', 'fund', 'holding']):
        return """
- Expect portfolio management fees, investment advisory payments
- Bank charges and financial service fees are common
- Professional fees for accounting and legal services expected
- International transactions likely if managing foreign investments"""
    
    # Tech/Software companies
    elif any(keyword in industry for keyword in ['technology', 'software', 'IT', 'saas']):
        return """
- Software subscriptions and SaaS payments are expected
- Cloud services and hosting fees common
- Tech equipment purchases likely
- Remote work expenses possible (coworking spaces, internet)"""
    
    # Retail/E-commerce
    elif any(keyword in industry for keyword in ['retail', 'e-commerce', 'ecommerce', 'shop']):
        return """
- Point of sale transactions expected
- Inventory and supplier payments common
- Shipping and logistics costs typical
- Platform fees if using e-commerce platforms"""
    
    else:
        return """
- Match transactions to industry-standard patterns
- Flag unusual expense types for this industry"""

def get_payroll_transaction_guidance(company_context):
    """Provide payroll-specific transaction guidance"""
    
    payroll_info = company_context.get('payroll_information', {})
    num_employees = payroll_info.get('num_employees', 0)
    payroll_frequency = payroll_info.get('payroll_frequency', '').lower()
    uses_ghs = payroll_info.get('uses_ghs', False)
    
    if num_employees == 0:
        return "- No employees registered - payroll transactions should be rare or non-existent"
    
    guidance = f"""
- Company has {num_employees} employee(s)
- Payroll frequency: {payroll_frequency if payroll_frequency else 'Not specified'}
- GHS contributions: {'Expected' if uses_ghs else 'Not applicable'}

**CRITICAL PAYROLL PRIVACY RULES:**
- When identifying wage/payroll transactions, NEVER include full employee names in accounting entries
- Extract and use ONLY initials if visible in bank description (e.g., "J.S." from "John Smith")
- Use generic labels like "Payroll - [Initials]" or "Wages - [Initials]"
- For bank narration field, you can include more detail, but accounting entry labels must be anonymized
- Example: Bank shows "SALARY PAYMENT JOHN SMITH" → narration: "Salary payment", partner: "Employee - J.S."

**PAYROLL TRANSACTION IDENTIFICATION:**
"""
    
    if payroll_frequency == 'monthly':
        guidance += "- Expect monthly salary payments (typically end of month or first few days)\n"
    elif payroll_frequency == 'bi-weekly':
        guidance += "- Expect bi-weekly salary payments (every 2 weeks)\n"
    elif payroll_frequency == 'weekly':
        guidance += "- Expect weekly salary payments\n"
    
    if uses_ghs:
        guidance += "- Social Insurance and GHS payments expected monthly\n"
    else:
        guidance += "- Social Insurance payments expected monthly (no GHS)\n"
    
    guidance += f"""
- For {num_employees} employee(s), expect corresponding number of individual salary transfers
- PAYE/NIC payments to tax authority expected monthly
- Social insurance payments expected monthly"""
    
    return guidance

def get_bank_statement_extraction_prompt(company_id, company_context=None):
    """Create bank statement transaction extraction prompt with company context"""
    
    # Get company context section
    company_context_section = get_company_context_section(company_context)
    
    # Get primary bank name for partner assignment
    primary_bank = "Bank of Cyprus"  # default
    if company_context and company_context.get('banking_information'):
        primary_bank = company_context['banking_information'].get('primary_bank', 'Bank of Cyprus')
    
    # Get company display name
    company_display = company_context.get('company_name') if company_context else str(company_id)
    
    return f"""# Bank Statement Transaction Extraction

## Task
Extract ALL transactions from bank statement text and convert each transaction into the exact JSON format required for double-entry accounting. Process every single transaction found in the statement.

**COMPANY ID:** {company_id}
**COMPANY:** {company_display} (the company whose bank statement this is)

{company_context_section}

## DOCUMENT TYPE DETECTION (CRITICAL FIRST STEP)
Before processing any transactions, you MUST determine the document type:

**CREDIT CARD STATEMENT**: Contains keywords like "VISA", "CREDIT CARD", "CREDIT LIMIT", trace numbers, merchant names
**BANK ACCOUNT STATEMENT**: Contains keywords like "SIGHT ACCOUNT", "CURRENT ACCOUNT", direct debits, transfers, account balances

## CHART OF ACCOUNTS (EXACT CODES AND NAMES):
**Assets:**
• 1201 - Bank (Current Account)
• 1240 - Credit card  
• 1100 - Accounts receivable
• 1260 - Suspense account

**Liabilities:**
• 2100 - Accounts payable
• 2200 - VAT control account
• 2210 - PAYE/NIC (payroll deductions)
• 2250 - Net wages (net salary payable to employees)

**Income:**
• 4000 - Sales
• 4906 - Bank interest received

**Common Expenses:**
• 7900 - Bank interest paid
• 7901 - Bank charges

## TRANSACTION PROCESSING RULES

### FOR CREDIT CARD STATEMENTS:

**CRITICAL STRUCTURAL RULE FOR CREDIT CARD STATEMENTS:**
Credit card statements have two distinct sections that determine the accounting treatment:

1. **DEBIT SECTION** (reduces credit card balance):
   - **CRITICAL OVERRIDE RULE**: ALL transactions positioned in the debit section alongside other payment transactions MUST be classified as credit card payments
   - If you see one transaction labeled "DIRECT DEBIT PAYMENT" and another transaction with just a reference number (e.g., "252370212") in the same section, they are BOTH credit card payments
   - **DO NOT** let description content override structural position - a reference number in the debit section is still a payment
   - **EXCEPTIONS** - Check description for these keywords (these are NOT payments):
     - "Interest" or "Total Interest" → Interest received (DEBIT 1201 Bank, CREDIT 4906)
     - "Refund" or "Credit" or "Reversal" → Income/credit adjustment (DEBIT 1201 Bank, CREDIT appropriate income account)
     - "Cashback" or "Reward" → Income (DEBIT 1201 Bank, CREDIT appropriate income account)
   - ALL OTHER transactions in debit section → Credit card payment (DEBIT 1240 Credit card, CREDIT 1201 Bank)
   - **CRITICAL**: Reference numbers, unclear descriptions, or missing keywords DO NOT matter - position determines treatment
   - **DO NOT** use suspense account for transactions in the debit section alongside identified payments
   - For non-payment exceptions, use account 4906 Bank interest received or 8200 Other income depending on nature

2. **CREDIT SECTION or Transaction List** (increases credit card balance):
   - **CRITICAL ACCOUNTING RULE**: These are merchant purchases that create payables
   - **DO NOT** attempt to classify expense type or guess expense accounts
   - **CORRECT METHOD**: ALL merchant purchases post to Accounts Payable
   - Individual purchases: DEBIT 2100 Accounts payable, CREDIT 1240 Credit card
   - Partner: Extract merchant name from transaction description
   - Note: A separate matching process will later match these to actual invoices/bills for proper VAT treatment and expense allocation

**Individual Credit Card Purchases (merchant transactions):**
- **CRITICAL**: Do NOT classify or guess expense types
- DEBIT: 2100 Accounts payable (creates a payable for invoice matching)
- CREDIT: 1240 Credit card
- Partner for 2100: Extract merchant name from transaction description
- Partner for 1240: "{primary_bank} - Credit card"
- Narration: Include merchant name and transaction details
- Note: Later workflow will match to invoices and properly allocate expenses with VAT

**Credit Card Payments (ANY transaction in debit section except interest):**
- DEBIT: 1240 Credit card
- CREDIT: 1201 Bank
- Partner for 1240: "{primary_bank} - Credit card"
- Partner for 1201: "{primary_bank} - Current A/c"
- Apply this rule even if description is just a reference number

**Interest Received (in debit section with "Interest" in description):**
- DEBIT: 1201 Bank
- CREDIT: 4906 Bank interest received
- Partner for 1201: "{primary_bank} - Current A/c"
- Partner for 4906: Extract from description or "Bank interest"

**Credit Adjustments/Refunds (in debit section with "Refund", "Credit", "Reversal", "Cashback", "Reward"):**
- DEBIT: 1201 Bank
- CREDIT: 4906 Bank interest received (for interest-like items) OR 8200 Other non-operating income (for refunds/cashback)
- Partner for 1201: "{primary_bank} - Current A/c"
- Partner for income account: Extract from description

### FOR BANK ACCOUNT STATEMENTS:

**CRITICAL MONEY FLOW ANALYSIS:**
Bank account statements show transactions in DEBIT and CREDIT columns that indicate money movement:
- **DEBIT column** = Money leaving the bank account (reduces balance)
- **CREDIT column** = Money entering the bank account (increases balance)

Always analyze the statement structure to determine which column the transaction appears in, then apply the appropriate accounting treatment.

**Customer Payments (money coming in - CREDIT column in bank statement):**
- DEBIT: 1201 Bank
- CREDIT: 1100 Accounts receivable
- Partner for 1201: "{primary_bank} - Current A/c"
- Partner for 1100: Extract from description

**Supplier Payments (money going out to vendors - DEBIT column in bank statement):**
- DEBIT: 2100 Accounts payable
- CREDIT: 1201 Bank
- Partner for 2100: Extract from description
- Partner for 1201: "{primary_bank} - Current A/c"

**CRITICAL: Payroll/Wage Payments (money going out to employees - DEBIT column in bank statement):**
- **IMPORTANT**: Payroll payments clear the Net Wages liability created during payroll processing
- DEBIT: 2250 Net wages (clearing the payable from payroll journal entry)
- CREDIT: 1201 Bank
- **PRIVACY RULE**: Remove full employee names from ALL fields (partner, narration, description)
- Extract ONLY initials if visible in description (e.g., "John Smith" → "J.S.")
- Partner for 2250: "Employee - [Initials]" (NOT full name)
- Partner for 1201: "{primary_bank} - Current A/c"
- **Narration/Description format**: Use initials only - "J.S. wage payment" or "Net salary payment - J.S." (NOT "John Smith wage payment")
- Indicators: "SALARY", "WAGE", "PAYROLL", employee names, regular monthly transfers
- Use company payroll context: {company_context.get('payroll_information', {}).get('num_employees', 0)} employees, {company_context.get('payroll_information', {}).get('payroll_frequency', 'unknown')} frequency
- **NOTE**: The gross wages expense (7000) is already recorded in the payroll journal entry; this transaction only clears the net wages payable

**Payroll Tax/Social Insurance Payments (money going out - DEBIT column in bank statement):**
- DEBIT: 2210 PAYE/NIC (clearing the payable from payroll journal entry)
- CREDIT: 1201 Bank
- Indicators: "Social Insurance", "PAYE", "GHS", "National Insurance"
- Partner for 2210: Extract from description (e.g., "Social Insurance Services")
- Partner for 1201: "{primary_bank} - Current A/c"
- **NOTE**: The employer contributions expense (7006) is already recorded in the payroll journal entry; this transaction only clears the tax liability

**VAT Payments (money going OUT to tax authority - DEBIT column in bank statement):**
- DEBIT: 2200 VAT control account
- CREDIT: 1201 Bank
- Indicators: "TAX PAYMENT", "VAT payment"
- Partner for 2200: Extract from description (tax authority)
- Partner for 1201: "{primary_bank} - Current A/c"

**VAT Refunds (money coming IN from tax authority - CREDIT column in bank statement):**
- DEBIT: 1201 Bank
- CREDIT: 2200 VAT control account
- Indicators: "TAX PAYMENT" or "VAT" with CREDIT to bank account
- Partner for 1201: "{primary_bank} - Current A/c"
- Partner for 2200: Extract from description (tax authority)

**Bank Charges (money going out - DEBIT column):**
- DEBIT: 7901 Bank charges
- CREDIT: 1201 Bank
- Partner for 7901: Extract from description
- Partner for 1201: "{primary_bank} - Current A/c"

**Bank Interest Paid (money going out - DEBIT column):**
- DEBIT: 7900 Bank interest paid
- CREDIT: 1201 Bank
- Partner for 7900: Extract from description
- Partner for 1201: "{primary_bank} - Current A/c"

**Ambiguous/Unclear Transactions:**
- For money OUT (DEBIT column): DEBIT 1260 Suspense account, CREDIT 1201 Bank
- For money IN (CREDIT column): DEBIT 1201 Bank, CREDIT 1260 Suspense account
- Partner for 1260: "Suspense - " + brief description
- Partner for 1201: "{primary_bank} - Current A/c"
- Use suspense account when transaction purpose is unclear or cannot be properly classified

## PARTNER NAME RULES

**Fixed Partner Names:**
- 1201 Bank: "{primary_bank} - Current A/c"
- 1240 Credit card: "{primary_bank} - Credit card"

**Extracted Partner Names:**
- For 2100 Accounts payable: Extract meaningful merchant/vendor name from transaction description
- For 2250 Net wages: Use "Employee - [Initials]" format (e.g., "Employee - J.S.")
- For 2210 PAYE/NIC: Extract authority name (e.g., "Social Insurance Services")
- **CRITICAL FOR PAYROLL**: For wage payments, use "Employee - [Initials]" format (e.g., "Employee - J.S.")
- Remove reference numbers, codes, and bank-specific formatting
- Examples:
  - "RAMOIL AYIOS ATHANASIOS CYP" → "RAMOIL AYIOS ATHANASIOS"
  - "SUPERHOME CENTER (DIY)LTD CYP" → "SUPERHOME CENTER"
  - "TAX PAYMENT" → "Tax Authority"
  - "SALARY JOHN SMITH" → "Employee - J.S." (extract initials only)
  - "Social Insurance Services" → "Social Insurance Services"

## CRITICAL OUTPUT REQUIREMENTS
- Return ONLY a valid JSON array
- No markdown code blocks (no ```json```)
- No explanatory text before or after the JSON
- Start response with [ and end with ]
- Each transaction must have "partner" field in line_items
- Anonymize employee names in payroll transactions (use initials only)
- For credit card purchases: Always use 2100 Accounts payable
- For wage payments: Always use 2250 Net wages (NOT 7000 Gross wages)
- For payroll tax payments: Always use 2210 PAYE/NIC

## Required Output Format
For EACH transaction found, create a JSON object with this EXACT structure:

[
  {{
    "company_id": {company_id},
    "date": "YYYY-MM-DD",
    "ref": "string",
    "narration": "string", 
    "partner": "string",
    "accounting_assignment": {{
      "debit_account": "2100",
      "debit_account_name": "Accounts payable",
      "credit_account": "1240",
      "credit_account_name": "Credit card",
      "transaction_type": "credit_card_purchase",
      "requires_vat": false,
      "additional_entries": []
    }},
    "line_items": [
      {{
        "name": "Accounts payable",
        "debit": 50.00,
        "credit": 0.00,
        "partner": "Merchant Name"
      }},
      {{
        "name": "Credit card",
        "debit": 0.00,
        "credit": 50.00,
        "partner": "{primary_bank} - Credit card"
      }}
    ]
  }}
]

## Transaction Type Classification:

1. **customer_payment**: Payments received from customers
2. **supplier_payment**: Payments made to vendors/suppliers
3. **wage_payment**: Net salary payments to employees (clears Account 2250 Net wages payable)
4. **payroll_tax_payment**: Social insurance, PAYE, GHS payments (clears Account 2210 PAYE/NIC)
5. **vat_payment**: VAT payments to tax authority (net VAT payable)
6. **vat_refund**: VAT refunds from tax authority (net VAT receivable)
7. **bank_charges**: Bank fees and charges (direct expense)
8. **bank_interest_paid**: Bank interest expense (direct expense)
9. **credit_card_purchase**: Individual credit card transactions (creates Account 2100 Accounts payable)
10. **credit_card_payment**: Payment from bank to credit card
11. **interest_received**: Interest income
12. **credit_adjustment**: Refunds, reversals, cashback, rewards received
13. **suspense_entry**: Unclear/ambiguous transactions

## Processing Instructions

1. **STEP 1: Use company context** to understand expected transaction patterns
2. **STEP 2: Determine document type** (Credit Card vs Bank Account)
3. **STEP 3: Identify statement structure** and group related transactions
4. **STEP 4: For CREDIT CARD statements** - Apply structural grouping rules with exceptions
5. **STEP 5: For CREDIT CARD PURCHASES** - ALWAYS use 2100 Accounts payable (do NOT classify expense types)
6. **STEP 6: For BANK ACCOUNT statements** - Determine money flow from columns
7. **STEP 7: Identify payroll transactions** using company payroll context (frequency, employee count)
8. **STEP 8: For WAGE PAYMENTS** - Use 2250 Net wages (NOT 7000 Gross wages)
9. **STEP 9: For PAYROLL TAX PAYMENTS** - Use 2210 PAYE/NIC (clearing liability)
10. **STEP 10: Anonymize employee names** - Extract initials only for payroll entries
11. **STEP 11: Use suspense account** ONLY for truly unclear bank transactions
12. **STEP 12: Assign correct partner names** (merchant names for payables, anonymized for employees)
13. **STEP 13: Create balanced line_items** ensuring debits = credits
14. **STEP 14: Set company_id** to the numeric ID provided ({company_id}) for every transaction
15. **STEP 15: Ensure all numeric values are numbers, not strings**

## Example Credit Card Purchase Transaction:

```json
{{
  "company_id": {company_id},
  "date": "2025-10-10",
  "ref": "cc_purchase_101025",
  "narration": "Purchase at Shell Petrol Station",
  "partner": "Shell",
  "accounting_assignment": {{
    "debit_account": "2100",
    "debit_account_name": "Accounts payable",
    "credit_account": "1240",
    "credit_account_name": "Credit card",
    "transaction_type": "credit_card_purchase",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "Accounts payable",
      "debit": 50.00,
      "credit": 0.00,
      "partner": "Shell"
    }},
    {{
      "name": "Credit card",
      "debit": 0.00,
      "credit": 50.00,
      "partner": "{primary_bank} - Credit card"
    }}
  ]
}}
```

## Example Wage Payment Transaction (CLEARING NET WAGES PAYABLE):

```json
{{
  "company_id": {company_id},
  "date": "2025-06-30",
  "ref": "payroll_300625",
  "narration": "Net salary payment - J.S.",
  "partner": "Employee - J.S.",
  "accounting_assignment": {{
    "debit_account": "2250",
    "debit_account_name": "Net wages",
    "credit_account": "1201",
    "credit_account_name": "Bank",
    "transaction_type": "wage_payment",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "Net wages",
      "debit": 929.77,
      "credit": 0.00,
      "partner": "Employee - J.S."
    }},
    {{
      "name": "Bank",
      "debit": 0.00,
      "credit": 929.77,
      "partner": "{primary_bank} - Current A/c"
    }}
  ]
}}
```

## Example Payroll Tax Payment Transaction (CLEARING PAYE/NIC LIABILITY):

```json
{{
  "company_id": {company_id},
  "date": "2025-07-15",
  "ref": "social_insurance_150725",
  "narration": "Social insurance payment - clearing payroll tax liability",
  "partner": "Social Insurance Services",
  "accounting_assignment": {{
    "debit_account": "2210",
    "debit_account_name": "PAYE/NIC",
    "credit_account": "1201",
    "credit_account_name": "Bank",
    "transaction_type": "payroll_tax_payment",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "PAYE/NIC",
      "debit": 158.40,
      "credit": 0.00,
      "partner": "Social Insurance Services"
    }},
    {{
      "name": "Bank",
      "debit": 0.00,
      "credit": 158.40,
      "partner": "{primary_bank} - Current A/c"
    }}
  ]
}}
```

**CRITICAL: Return ONLY the JSON array. No markdown formatting, no code blocks, no explanatory text. The response must start with '[' and end with ']'. Every line_item must include a "partner" field. Anonymize employee names in payroll transactions. Set company_id to {company_id} (numeric) for all transactions. For credit card purchases, ALWAYS use 2100 Accounts payable. For wage payments, ALWAYS use 2250 Net wages (this clears the payable created in payroll processing). For payroll tax payments, ALWAYS use 2210 PAYE/NIC (this clears the liability created in payroll processing).**
"""

def extract_json_from_response(response_text):
    """Extract JSON from Claude's response, handling various formats"""
    try:
        # Remove any leading/trailing whitespace
        response_text = response_text.strip()
        
        # Try to parse directly first
        try:
            parsed = json.loads(response_text)
            return parsed
        except json.JSONDecodeError:
            pass
        
        # Look for JSON wrapped in markdown code blocks
        json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        matches = re.findall(json_pattern, response_text, re.IGNORECASE)
        
        if matches:
            # Try each match
            for match in matches:
                try:
                    parsed = json.loads(match.strip())
                    return parsed
                except json.JSONDecodeError:
                    continue
        
        # Look for JSON arrays/objects without code blocks
        # Find content between first '[' and last ']'
        if '[' in response_text and ']' in response_text:
            start_idx = response_text.find('[')
            
            # Find matching closing bracket
            bracket_count = 0
            end_idx = -1
            
            for i in range(start_idx, len(response_text)):
                char = response_text[i]
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                try:
                    parsed = json.loads(json_str)
                    return parsed
                except json.JSONDecodeError:
                    pass
        
        # Look for JSON objects if no arrays found
        if '{' in response_text and '}' in response_text:
            start_idx = response_text.find('{')
            
            # Find matching closing brace
            brace_count = 0
            end_idx = -1
            
            for i in range(start_idx, len(response_text)):
                char = response_text[i]
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                try:
                    parsed = json.loads(json_str)
                    # If it's a single object, wrap it in an array
                    if isinstance(parsed, dict):
                        return [parsed]
                    return parsed
                except json.JSONDecodeError:
                    pass
        
        # If all else fails, raise an error with the raw response
        raise json.JSONDecodeError(f"Could not extract valid JSON from response. Response starts with: {response_text[:200]}...")
        
    except Exception as e:
        raise Exception(f"JSON extraction failed: {str(e)}")

def validate_transaction_json(transactions):
    """Validate the extracted transaction JSON structure including accounting assignment"""
    try:
        if not isinstance(transactions, list):
            raise ValueError("Expected JSON array of transactions")
        
        # Validate account codes - Updated with new accounts
        valid_accounts = [
            "1201", "1240", "1100", "1260",  # Assets
            "2100", "2200", "2210", "2250",         # Liabilities  
            "4000", "4906",                  # Income
            "7000", "7100", "7190", "7200", "7300", "7301", "7302", "7303",  # Expenses
            "7400", "7401", "7402", "7403", "7500", "7501", "7502", "7503",
            "7600", "7601", "7602", "7800", "7900", "7901", "6900"
        ]
        
        for i, transaction in enumerate(transactions):
            if not isinstance(transaction, dict):
                raise ValueError(f"Transaction {i} is not a JSON object")
            
            # Check required fields
            required_fields = ['company_id', 'date', 'ref', 'narration', 'partner', 'accounting_assignment', 'line_items']
            for field in required_fields:
                if field not in transaction:
                    raise ValueError(f"Transaction {i} missing required field: {field}")
            
            # Validate accounting_assignment structure
            accounting = transaction['accounting_assignment']
            required_accounting_fields = ['debit_account', 'debit_account_name', 'credit_account', 'credit_account_name', 'transaction_type', 'requires_vat', 'additional_entries']
            for field in required_accounting_fields:
                if field not in accounting:
                    raise ValueError(f"Transaction {i} accounting_assignment missing field: {field}")
            
            # Validate account codes
            debit_account = accounting['debit_account']
            credit_account = accounting['credit_account']
            
            if debit_account not in valid_accounts:
                raise ValueError(f"Transaction {i} invalid debit_account: {debit_account}")
            
            if credit_account not in valid_accounts:
                raise ValueError(f"Transaction {i} invalid credit_account: {credit_account}")
            
            # Validate line_items
            line_items = transaction['line_items']
            if not isinstance(line_items, list) or len(line_items) < 2:
                raise ValueError(f"Transaction {i} must have at least 2 line items")
            
            # Validate that each line item has partner field
            for j, line_item in enumerate(line_items):
                if 'partner' not in line_item:
                    raise ValueError(f"Transaction {i}, line item {j} missing 'partner' field")
            
            # Validate double-entry balancing
            total_debits = sum(item.get('debit', 0) for item in line_items)
            total_credits = sum(item.get('credit', 0) for item in line_items)
            
            if abs(total_debits - total_credits) > 0.01:  # Allow small rounding differences
                raise ValueError(f"Transaction {i} debits ({total_debits}) don't balance with credits ({total_credits})")
        
        return True
        
    except Exception as e:
        raise Exception(f"Transaction validation failed: {str(e)}")

def ensure_transaction_structure(transaction):
    """Ensure each transaction has the complete required structure with default values"""
    
    # Define the complete structure with default values
    default_transaction = {
        "company_id": "",
        "date": "",
        "ref": "",
        "narration": "",
        "partner": "unknown",
        "accounting_assignment": {
            "debit_account": "",
            "debit_account_name": "",
            "credit_account": "",
            "credit_account_name": "",
            "transaction_type": "",
            "requires_vat": False,
            "additional_entries": []
        },
        "line_items": []
    }
    
    def merge_with_defaults(source, defaults):
        """Recursively merge source with defaults, ensuring all fields are present"""
        if isinstance(defaults, dict):
            result = {}
            for key, default_value in defaults.items():
                if key in source and source[key] is not None:
                    if isinstance(default_value, dict):
                        result[key] = merge_with_defaults(source[key], default_value)
                    elif isinstance(default_value, list):
                        result[key] = source[key] if isinstance(source[key], list) else default_value
                    else:
                        result[key] = source[key]
                else:
                    result[key] = default_value
            return result
        else:
            return source if source is not None else defaults
    
    return merge_with_defaults(transaction, default_transaction)

def download_from_s3(s3_key, bucket_name=None):
    """Download file from S3 using key"""
    try:
        if not bucket_name:
            bucket_name = os.getenv('S3_BUCKET_NAME', 'company-documents-2025')
        
        # Initialize S3 client
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION', 'eu-north-1')
        
        if aws_access_key and aws_secret_key:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=aws_region
            )
        else:
            s3_client = boto3.client('s3', region_name=aws_region)
        
        print(f"Downloading from bucket: {bucket_name}, key: {s3_key}")
        
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        return response['Body'].read()
        
    except Exception as e:
        raise Exception(f"Error downloading from S3: {str(e)}")

def process_bank_statement_extraction(pdf_content, company_id, company_context=None):
    """Process bank statement with Claude for transaction extraction with accounting assignment and company context"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get bank statement extraction prompt with company context
        prompt = get_bank_statement_extraction_prompt(company_id, company_context)
        
        # Build enhanced system prompt with company awareness
        payroll_context_note = ""
        if company_context:
            payroll_info = company_context.get('payroll_information', {})
            num_employees = payroll_info.get('num_employees', 0)
            if num_employees > 0:
                payroll_context_note = f"\n- Company has {num_employees} employee(s), expect payroll transactions"
                payroll_context_note += "\n- CRITICAL: Anonymize employee names - use initials only (e.g., 'Employee - J.S.')"
                payroll_context_note += "\n- CRITICAL: Wage payments clear Account 2250 Net wages (NOT 7000 Gross wages)"
                payroll_context_note += "\n- CRITICAL: Payroll tax payments clear Account 2210 PAYE/NIC"
        
        # Send to Claude with parameters optimized for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            temperature=0.0,  # Maximum determinism for consistent parsing
            system=f"""You are an expert accountant specializing in bank statement analysis and double-entry bookkeeping. Your core behavior is to think and act like a professional accountant who understands document types, transaction flows, proper account classification, and privacy requirements.

CRITICAL DOCUMENT TYPE DETECTION:
Before processing any transactions, you MUST first determine whether this is:
1. **CREDIT CARD STATEMENT**: Look for "VISA", "MASTERCARD", "CREDIT CARD", "CREDIT LIMIT", merchant names, trace numbers
2. **BANK ACCOUNT STATEMENT**: Look for "SIGHT ACCOUNT", "CURRENT ACCOUNT", direct debits, transfers, IBANs

CORE ACCOUNTING PRINCIPLES:
• Always maintain double-entry bookkeeping: debits must equal credits
• Use appropriate account codes from the provided chart of accounts
• Apply correct transaction types based on document type and transaction nature
• Extract meaningful partner names from transaction descriptions
• Use suspense accounts ONLY for truly unclear bank transactions
• CRITICAL: Protect employee privacy by anonymizing names in payroll transactions{payroll_context_note}

COMPANY CONTEXT AWARENESS:
• Use provided company context to identify expected transaction patterns
• Match transaction frequency to company's payroll schedule
• Validate transaction types against company's industry and business model
• Flag unusual transactions that don't match company profile
• Use company's primary bank name for partner assignments

DOCUMENT-SPECIFIC PROCESSING:

**FOR CREDIT CARD STATEMENTS - USE STRUCTURAL POSITION RULES:**
• **CRITICAL**: Credit card statements have DEBIT and CREDIT sections with specific meanings
• **STRUCTURAL POSITION OVERRIDE**: When you identify transactions grouped together in the same section, treat them identically
• **DEBIT section** (reduces card balance):
  - Look for transactions positioned together at the top of the statement or in a summary section
  - If ONE transaction says "DIRECT DEBIT PAYMENT" and ANOTHER shows only a reference number like "252370212", they are in the SAME section
  - **CHECK FOR EXCEPTIONS FIRST** - these are NOT payments:
    - "Interest", "Total Interest" → Interest received: DEBIT 1201 Bank, CREDIT 4906
    - "Refund", "Credit", "Reversal" → Income/adjustment: DEBIT 1201 Bank, CREDIT 4906 or 8200
    - "Cashback", "Reward" → Income: DEBIT 1201 Bank, CREDIT 4906 or 8200
  - ALL OTHER transactions in debit section → Credit card payment: DEBIT 1240 Credit card, CREDIT 1201 Bank
  - **CRITICAL**: Reference numbers, unclear descriptions, or missing keywords DO NOT matter - position determines treatment
  - **DO NOT** use suspense account for transactions in the debit section alongside identified payments
• **Merchant transactions** (increases card balance):
  - **CRITICAL NEW RULE**: DO NOT classify expense types or attempt to determine merchant category
  - **CORRECT METHOD**: Post ALL merchant purchases to Accounts Payable
  - Individual purchases: DEBIT 2100 Accounts payable, CREDIT 1240 Credit card
  - Extract merchant name for partner field
  - **REASON**: Direct posting causes VAT issues. A separate matching process will later match these payables to actual invoices/bills for proper expense allocation and VAT treatment

**FOR BANK ACCOUNT STATEMENTS - CRITICAL PAYROLL RULES:**
• **PAYROLL/WAGES (CLEARING LIABILITY CREATED IN PAYROLL PROCESSING)**:
  - Keywords: "SALARY", "WAGE", "PAYROLL", employee names, regular scheduled transfers
  - **CRITICAL ACCOUNT SELECTION**: DEBIT 2250 Net wages, CREDIT 1201 Bank
  - **DO NOT USE 7000 Gross wages** - that expense is already recorded in the payroll journal entry
  - This transaction ONLY clears the net wages payable liability
  - **CRITICAL PRIVACY RULE - ANONYMIZE ALL FIELDS**:
    - Partner field: "Employee - [Initials]" (e.g., "Employee - J.S.")
    - Narration field: Use initials only - "Net salary payment - J.S." or "J.S. wage payment"
    - Description field: Use initials only - "J.S. wage payment" (NOT "John Smith wage payment")
    - Extract ONLY initials from full names (e.g., "John Smith" → "J.S.", "Maria Costa" → "M.C.")
  - Use company payroll context to identify wage transactions
• **PAYROLL TAXES (CLEARING LIABILITY CREATED IN PAYROLL PROCESSING)**:
  - Keywords: "Social Insurance", "PAYE", "GHS", "National Insurance", "NIC"
  - **CRITICAL ACCOUNT SELECTION**: DEBIT 2210 PAYE/NIC, CREDIT 1201 Bank
  - **DO NOT USE 7006 Employers n.i.** - that expense is already recorded in the payroll journal entry
  - This transaction ONLY clears the payroll tax liability
  - Partner: Extract authority name (e.g., "Social Insurance Services")
• **OTHER BANK TRANSACTIONS**:
  - Customer payments: DEBIT 1201 Bank, CREDIT 1100 Accounts receivable
  - Supplier payments: DEBIT 2100 Accounts payable, CREDIT 1201 Bank
  - VAT payments: DEBIT 2200 VAT control account, CREDIT 1201 Bank
  - VAT refunds: DEBIT 1201 Bank, CREDIT 2200 VAT control account
  - Bank charges: DEBIT 7901 Bank charges, CREDIT 1201 Bank
  - Bank interest paid: DEBIT 7900 Bank interest paid, CREDIT 1201 Bank
• Use 1260 Suspense only when truly unclear

CRITICAL CREDIT CARD PURCHASE RULE:
• **NEVER** classify or guess expense types for credit card purchases
• **ALWAYS** post to 2100 Accounts payable
• This prevents VAT issues and allows proper invoice matching downstream
• Expense allocation happens later when matched to actual invoices/bills

CRITICAL PAYROLL PAYMENT RULES:
• **Wage payments from bank**: Use 2250 Net wages (clears payroll liability), NOT 7000 Gross wages
• **Payroll tax payments from bank**: Use 2210 PAYE/NIC (clears tax liability), NOT 7006 Employers n.i.
• **EMPLOYEE NAME ANONYMIZATION**: For wage payments, use ONLY initials in ALL fields:
  - Partner: "Employee - J.S."
  - Narration: "Net salary payment - J.S." or "J.S. wage payment"
  - Description: "J.S. wage payment" (NOT "John Smith wage payment")
  - Never use full employee names anywhere in wage payment transactions
• **REASONING**: The payroll journal entry already recorded expenses (7000, 7006) and created liabilities (2250, 2210). Bank payments only clear these liabilities.

TRANSACTION IDENTIFICATION KEYWORDS:
• **Payroll/Wages**: "SALARY", "WAGE", "PAYROLL", employee names → Use 2250 Net wages (ANONYMIZE ALL FIELDS - use initials only)
• **Payroll taxes**: "Social Insurance", "PAYE", "GHS", "NIC" → Use 2210 PAYE/NIC
• **VAT payments/refunds**: "TAX PAYMENT" with "VAT" context → Use 2200 VAT control account
• **Credit card purchases**: ANY merchant transaction → Use 2100 Accounts payable
• **Supplier payments**: Vendor names in bank statement → Use 2100 Accounts payable

PARTNER NAME ASSIGNMENT:
• 1201 Bank: Always use company's primary bank name + "- Current A/c"
• 1240 Credit card: Always use company's primary bank name + "- Credit card"
• 2100 Accounts payable: Extract merchant/vendor name from transaction description
• 2250 Net wages: Format as "Employee - [Initials]" (e.g., "Employee - J.S.")
• 2210 PAYE/NIC: Extract authority name (e.g., "Social Insurance Services")

OUTPUT REQUIREMENTS:
• Return ONLY valid JSON array
• Every line_item must include "partner" field
• Ensure proper double-entry balancing
• Use exact account codes and names from chart of accounts
• Apply appropriate transaction types
• **CRITICAL FOR CREDIT CARDS**: Use 2100 Accounts payable for ALL merchant purchases
• **CRITICAL FOR PAYROLL**: Use 2250 Net wages for wage payments (NOT 7000)
• **CRITICAL FOR PAYROLL TAXES**: Use 2210 PAYE/NIC for tax payments (NOT 7006)
• **CRITICAL**: Anonymize all employee names in payroll transactions""",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )
        
        # Extract response
        response_text = message.content[0].text.strip()
        
        # Log the raw response for debugging (first 500 chars)
        print(f"Raw Claude response (first 500 chars): {response_text[:500]}...")
        
        # Extract and parse JSON
        try:
            extracted_json = extract_json_from_response(response_text)
            
            # Ensure each transaction has complete structure
            validated_transactions = []
            for transaction in extracted_json:
                validated_transaction = ensure_transaction_structure(transaction)
                validated_transactions.append(validated_transaction)
            
            # Validate the JSON structure
            validate_transaction_json(validated_transactions)
            
            # Log token usage for monitoring
            print(f"Token usage - Input: {message.usage.input_tokens}, Output: {message.usage.output_tokens}")
            print(f"Successfully extracted and validated {len(validated_transactions)} transactions")
            
            return {
                "success": True,
                "extraction_result": validated_transactions,
                "raw_response": response_text,
                "token_usage": {
                    "input_tokens": message.usage.input_tokens,
                    "output_tokens": message.usage.output_tokens
                },
                "transaction_count": len(validated_transactions)
            }
            
        except Exception as json_error:
            print(f"JSON processing failed: {str(json_error)}")
            return {
                "success": False,
                "error": f"JSON processing failed: {str(json_error)}",
                "raw_response": response_text
            }
        
    except Exception as e:
        print(f"Claude API error: {str(e)}")
        return {
            "success": False,
            "error": f"Claude API error: {str(e)}"
        }

def validate_accounting_assignments(transactions, company_context=None):
    """Validate accounting assignments for extracted transactions with company context awareness"""
    validation_results = []
    
    for i, transaction in enumerate(transactions):
        transaction_validation = {
            "transaction_index": i + 1,
            "issues": [],
            "warnings": [],
            "accounting_valid": True
        }
        
        accounting = transaction.get("accounting_assignment", {})
        transaction_type = accounting.get("transaction_type", "")
        
        # Check for proper account assignment
        debit_account = accounting.get("debit_account", "")
        credit_account = accounting.get("credit_account", "")
        
        # Validate account codes
        valid_accounts = [
            "1201", "1240", "1100", "1260",  # Assets
            "2100", "2200", "2210",          # Liabilities  
            "4000", "4906",                  # Income
            "7000", "7100", "7190", "7200", "7300", "7301", "7302", "7303",  # Expenses
            "7400", "7401", "7402", "7403", "7500", "7501", "7502", "7503",
            "7600", "7601", "7602", "7800", "7900", "7901", "6900"
        ]
        
        if debit_account not in valid_accounts:
            transaction_validation["issues"].append(f"Invalid debit account code: {debit_account}")
            transaction_validation["accounting_valid"] = False
        
        if credit_account not in valid_accounts:
            transaction_validation["issues"].append(f"Invalid credit account code: {credit_account}")
            transaction_validation["accounting_valid"] = False
        
        # Check transaction type consistency
        if not transaction_type:
            transaction_validation["warnings"].append("Missing transaction type classification")
        
        # CRITICAL: Validate payroll transaction anonymization
        if transaction_type == "wage_payment" or debit_account == "7000":
            line_items = transaction.get("line_items", [])
            for j, line_item in enumerate(line_items):
                partner = line_item.get('partner', '')
                # Check if partner contains full names (more than just initials)
                if partner and len(partner.split()) > 2:  # Likely contains full name
                    # Check if it's not the standard bank partner format
                    if "Current A/c" not in partner and "Credit card" not in partner:
                        transaction_validation["warnings"].append(
                            f"Payroll transaction may contain full employee name in partner field: '{partner}'. "
                            f"Should use format 'Employee - [Initials]'"
                        )
        
        # Validate against company context if available
        if company_context:
            # Check payroll frequency alignment
            payroll_info = company_context.get('payroll_information', {})
            payroll_frequency = payroll_info.get('payroll_frequency', '').lower()
            num_employees = payroll_info.get('num_employees', 0)
            
            if transaction_type == "wage_payment":
                # Check if number of wage transactions aligns with employee count
                if num_employees == 0:
                    transaction_validation["warnings"].append(
                        "Wage payment detected but company has 0 registered employees"
                    )
            
            # Check for unusual transactions based on industry
            industry = company_context.get('primary_industry', '').lower()
            if 'technology' in industry or 'software' in industry:
                # Tech companies shouldn't have many fuel expenses
                if debit_account == "7300":  # Car fuel & oil
                    transaction_validation["warnings"].append(
                        "Fuel expense unusual for technology/software company"
                    )
        
        # Check line items consistency with accounting assignment
        line_items = transaction.get("line_items", [])
        if len(line_items) >= 2:
            # Check if line items match accounting assignment
            debit_items = [item for item in line_items if item.get('debit', 0) > 0]
            credit_items = [item for item in line_items if item.get('credit', 0) > 0]
            
            if len(debit_items) == 0 or len(credit_items) == 0:
                transaction_validation["issues"].append("Line items don't follow double-entry principles")
            
            # Check if partner field exists in all line items
            for j, line_item in enumerate(line_items):
                if 'partner' not in line_item:
                    transaction_validation["issues"].append(f"Line item {j} missing 'partner' field")
                    transaction_validation["accounting_valid"] = False
        
        validation_results.append(transaction_validation)
    
    return validation_results

def main(data):
    """
    Main function for bank statement transaction extraction with accounting assignment and company context
    
    Args:
        data (dict): Request data containing:
            - s3_key (str): S3 key path to the document
            - company_id (str/int): Company ID for transaction extraction (REQUIRED - numeric ID)
            - company_name (str, optional): Company name for context lookup
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Processing result with success status and extracted data
    """
    try:
        # Validate required fields
        required_fields = ['s3_key', 'company_id']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return {
                "success": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }
        
        s3_key = data['s3_key']
        company_id = data['company_id']  # This should be the numeric ID
        company_name = data.get('company_name')  # Optional - for context lookup
        bucket_name = data.get('bucket_name')
        
        # Ensure company_id is numeric
        try:
            company_id_numeric = int(company_id)
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": f"company_id must be a number, received: {company_id} ({type(company_id).__name__})"
            }
        
        print(f"Processing bank statement for company_id: {company_id_numeric}, S3 key: {s3_key}")
        
        # Fetch comprehensive company context from DynamoDB (if company_name provided)
        company_context = None
        if company_name:
            print(f"Looking up company context for: {company_name}")
            company_context = get_company_context(company_name)
            
            if not company_context:
                print(f"⚠️  Warning: No company context found for {company_name}")
                print(f"   Proceeding with generic transaction processing")
            else:
                print(f"✅ Company context loaded successfully")
        else:
            print(f"⚠️  No company_name provided - proceeding without company context")
            print(f"   To enable context-aware processing, include 'company_name' in request")
        
        # Download PDF from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded PDF, size: {len(pdf_content)} bytes")
        
        # Process bank statement for transaction extraction with company context
        # Pass the NUMERIC company_id to the extraction function
        result = process_bank_statement_extraction(pdf_content, company_id_numeric, company_context)
        
        if result["success"]:
            transactions = result["extraction_result"]
            
            # Validate accounting assignments with company context
            validation_results = validate_accounting_assignments(transactions, company_context)
            
            # Count transactions with issues
            transactions_with_issues = sum(1 for v in validation_results if not v["accounting_valid"])
            total_transactions = len(transactions)
            
            return {
                "success": True,
                "total_transactions": total_transactions,
                "transactions": transactions,
                "processing_summary": {
                    "transactions_processed": total_transactions,
                    "transactions_with_issues": transactions_with_issues,
                    "success_rate": f"{((total_transactions - transactions_with_issues) / total_transactions * 100):.1f}%" if total_transactions > 0 else "0%"
                },
                "validation_results": validation_results,
                "metadata": {
                    "company_id": company_id_numeric,  # Always return numeric ID
                    "company_name": company_context.get('company_name') if company_context else company_name,
                    "company_context_loaded": company_context is not None,
                    "num_employees": company_context.get('payroll_information', {}).get('num_employees', 0) if company_context else 0,
                    "payroll_frequency": company_context.get('payroll_information', {}).get('payroll_frequency', 'unknown') if company_context else 'unknown',
                    "primary_bank": company_context.get('banking_information', {}).get('primary_bank', 'unknown') if company_context else 'unknown',
                    "s3_key": s3_key,
                    "token_usage": result["token_usage"]
                }
            }
        else:
            return {
                "success": False,
                "error": result["error"],
                "raw_response": result.get("raw_response")
            }
            
    except Exception as e:
        print(f"Bank statement processing error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }

def health_check():
    """Health check for the bank statement processing service"""
    try:
        # Check if required environment variables are set
        required_vars = ['ANTHROPIC_API_KEY']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            return {
                "healthy": False,
                "error": f"Missing environment variables: {', '.join(missing_vars)}"
            }
        
        return {
            "healthy": True,
            "service": "claude-bank-statement-extraction",
            "version": "3.0",
            "capabilities": [
                "document_type_detection",
                "credit_card_transaction_processing",
                "bank_account_transaction_processing",
                "transaction_extraction",
                "accounting_assignment",
                "double_entry_validation",
                "transaction_classification",
                "partner_name_extraction",
                "suspense_account_handling",
                "structured_json_output",
                "company_context_integration",
                "payroll_anonymization",
                "employee_privacy_protection",
                "industry_specific_validation",
                "dynamodb_company_lookup",
                "payroll_pattern_recognition"
            ],
            "supported_document_types": [
                "credit_card_statements",
                "bank_account_statements"
            ],
            "account_types": [
                "1201_bank_current",
                "1240_credit_card",
                "1100_accounts_receivable",
                "1260_suspense_account",
                "2100_accounts_payable",
                "2200_vat_control_account",
                "2210_paye_nic",
                "7000_gross_wages",
                "expense_accounts_7xxx",
                "income_accounts_4xxx"
            ],
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025'),
            "dynamodb_table": "users",
            "new_features": [
                "Comprehensive company context from DynamoDB",
                "Payroll information and frequency awareness",
                "Employee name anonymization (initials only)",
                "Industry-specific transaction validation",
                "Business operations context integration",
                "Banking information awareness",
                "Privacy protection for employee data"
            ]
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }

# Example usage for testing
if __name__ == "__main__":
    # Test the JSON extraction function with payroll anonymization
    test_response = '''[
  {
    "company_id": "Test Company Ltd",
    "date": "2025-06-30",
    "ref": "payroll_300625",
    "narration": "Monthly salary payment",
    "partner": "Employee - J.S.",
    "accounting_assignment": {
      "debit_account": "7000",
      "debit_account_name": "Gross wages",
      "credit_account": "1201",
      "credit_account_name": "Bank",
      "transaction_type": "wage_payment",
      "requires_vat": false,
      "additional_entries": []
    },
    "line_items": [
      {
        "name": "Gross wages",
        "debit": 2500.00,
        "credit": 0.00,
        "partner": "Employee - J.S."
      },
      {
        "name": "Bank",
        "debit": 0.00,
        "credit": 2500.00,
        "partner": "Bank of Cyprus - Current A/c"
      }
    ]
  }
]'''
    
    try:
        result = extract_json_from_response(test_response)
        print("JSON extraction test successful:")
        print(json.dumps(result, indent=2))
        
        validate_transaction_json(result)
        print("Validation test successful!")
        
        # Test accounting validation
        validation_results = validate_accounting_assignments(result)
        print("Accounting validation results:")
        for validation in validation_results:
            print(f"Transaction {validation['transaction_index']}: {'Valid' if validation['accounting_valid'] else 'Invalid'}")
            if validation['issues']:
                print(f"  Issues: {validation['issues']}")
            if validation['warnings']:
                print(f"  Warnings: {validation['warnings']}")
        
    except Exception as e:
        print(f"Test failed: {str(e)}")