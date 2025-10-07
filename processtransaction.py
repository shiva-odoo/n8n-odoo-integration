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

def get_bank_statement_extraction_prompt(company_name, company_context=None):
    """Create bank statement transaction extraction prompt with company context"""
    
    # Get company context section
    company_context_section = get_company_context_section(company_context)
    
    # Get primary bank name for partner assignment
    primary_bank = "Bank of Cyprus"  # default
    if company_context and company_context.get('banking_information'):
        primary_bank = company_context['banking_information'].get('primary_bank', 'Bank of Cyprus')
    
    return f"""# Bank Statement Transaction Extraction

## Task
Extract ALL transactions from bank statement text and convert each transaction into the exact JSON format required for double-entry accounting. Process every single transaction found in the statement.

**COMPANY:** {company_name} (the company whose bank statement this is)

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

**Income:**
• 4000 - Sales
• 4906 - Bank interest received

**Common Expenses:**
• 7000 - Gross wages
• 7100 - Rent
• 7190 - Utilities
• 7200 - Electricity
• 7300 - Car fuel & oil
• 7301 - Repairs and servicing
• 7302 - Licenses & mot's
• 7303 - Vehicle insurance
• 7400 - Traveling
• 7401 - Car hire
• 7402 - Hotels
• 7403 - Entertainment
• 7500 - Printing
• 7501 - Postage
• 7502 - Telephone
• 7503 - Internet
• 7600 - Legal fees
• 7601 - Audit and accountancy fees
• 7602 - Consultancy fees
• 7800 - Repairs and renewals
• 7900 - Bank interest paid
• 7901 - Bank charges
• 6900 - Miscellaneous expenses

## TRANSACTION PROCESSING RULES

### FOR CREDIT CARD STATEMENTS:

**CRITICAL STRUCTURAL RULE FOR CREDIT CARD STATEMENTS:**
Credit card statements have two distinct sections that determine the accounting treatment:

1. **DEBIT SECTION** (reduces credit card balance/liability):
   - **CRITICAL OVERRIDE RULE**: ALL transactions positioned in the debit section alongside other payment transactions MUST be classified as credit card payments
   - If you see one transaction labeled "DIRECT DEBIT PAYMENT" and another transaction with just a reference number (e.g., "252370212") in the same section, they are BOTH credit card payments
   - **DO NOT** let description content override structural position - a reference number in the debit section is still a payment
   - **EXCEPTIONS** - Check description for these keywords (these are NOT payments):
     - "Interest" or "Total Interest" → Interest received (DEBIT 1201 Bank, CREDIT 4906)
     - "Refund" or "Credit" or "Reversal" → Income/credit adjustment (DEBIT 1201 Bank, CREDIT appropriate income account)
     - "Cashback" or "Reward" → Income (DEBIT 1201 Bank, CREDIT appropriate income account)
   - ALL OTHER transactions in debit section → Credit card payment (DEBIT 1240 Credit card, CREDIT 1201 Bank)
   - For non-payment exceptions, use account 4906 Bank interest received or 8200 Other income depending on nature

2. **CREDIT SECTION or Transaction List** (increases credit card balance/liability):
   - These are merchant purchases → DEBIT expense account, CREDIT 1240 Credit card

**Individual Credit Card Purchases (merchant transactions):**
- DEBIT: Appropriate expense account (based on merchant/description)
- CREDIT: 1240 Credit card
- Partner: Extract from transaction description (merchant name)

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
- DEBIT: 7000 Gross wages
- CREDIT: 1201 Bank
- **PRIVACY RULE**: Remove full employee names from accounting entries
- Extract ONLY initials if visible in description (e.g., "John Smith" → "J.S.")
- Partner for 7000: "Employee - [Initials]" (NOT full name)
- Partner for 1201: "{primary_bank} - Current A/c"
- Narration can include more context but keep partner field anonymized
- Indicators: "SALARY", "WAGE", "PAYROLL", employee names, regular monthly transfers
- Use company payroll context: {company_context.get('payroll_information', {}).get('num_employees', 0)} employees, {company_context.get('payroll_information', {}).get('payroll_frequency', 'unknown')} frequency

**Payroll Tax/Social Insurance Payments (money going out - DEBIT column in bank statement):**
- DEBIT: 2210 PAYE/NIC
- CREDIT: 1201 Bank
- Indicators: "Social Insurance", "PAYE", "GHS", "National Insurance"
- Partner for 2210: Extract from description (e.g., "Social Insurance Services")
- Partner for 1201: "{primary_bank} - Current A/c"

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

**Ambiguous/Unclear Transactions:**
- For money OUT (DEBIT column): DEBIT 1260 Suspense account, CREDIT 1201 Bank
- For money IN (CREDIT column): DEBIT 1201 Bank, CREDIT 1260 Suspense account
- Partner for 1260: "Suspense - " + brief description
- Partner for 1201: "{primary_bank} - Current A/c"
- Use suspense account when transaction purpose is unclear or cannot be properly classified

## EXPENSE ACCOUNT MAPPING GUIDE

**Fuel/Petrol Stations:** 7300 Car fuel & oil
**Restaurants/Food:** 7403 Entertainment
**Travel/Airlines:** 7400 Traveling
**Hotels:** 7402 Hotels
**Car Services:** 7301 Repairs and servicing
**Telecommunications:** 7502 Telephone or 7503 Internet
**Office Supplies:** 7500 Printing
**Professional Services:** 7602 Consultancy fees
**Utilities:** 7190 Utilities or 7200 Electricity
**DIY/Hardware Stores:** 7800 Repairs and renewals
**Unknown/Other:** 6900 Miscellaneous expenses

## PARTNER NAME RULES

**Fixed Partner Names:**
- 1201 Bank: "{primary_bank} - Current A/c"
- 1240 Credit card: "{primary_bank} - Credit card"

**Extracted Partner Names:**
- For all other accounts: Extract meaningful partner name from transaction description
- **CRITICAL FOR PAYROLL**: For wage payments, use "Employee - [Initials]" format (e.g., "Employee - J.S.")
- Remove reference numbers, codes, and bank-specific formatting
- Examples:
  - "RAMOIL AYIOS ATHANASIOS CYP" → "RAMOIL AYIOS ATHANASIOS"
  - "SUPERHOME CENTER (DIY)LTD CYP" → "SUPERHOME CENTER"
  - "TAX PAYMENT" → "Tax Authority"
  - "SALARY JOHN SMITH" → "Employee - J.S." (extract initials only)

## CRITICAL OUTPUT REQUIREMENTS
- Return ONLY a valid JSON array
- No markdown code blocks (no ```json```)
- No explanatory text before or after the JSON
- Start response with [ and end with ]
- Each transaction must have "partner" field in line_items
- Anonymize employee names in payroll transactions (use initials only)

## Required Output Format
For EACH transaction found, create a JSON object with this EXACT structure:

[
  {{
    "company_id": "{company_name}",
    "date": "YYYY-MM-DD",
    "ref": "string",
    "narration": "string", 
    "partner": "string",
    "accounting_assignment": {{
      "debit_account": "1201",
      "debit_account_name": "Bank",
      "credit_account": "1100",
      "credit_account_name": "Accounts receivable",
      "transaction_type": "customer_payment",
      "requires_vat": false,
      "additional_entries": []
    }},
    "line_items": [
      {{
        "name": "Bank",
        "debit": 15000.00,
        "credit": 0.00,
        "partner": "{primary_bank} - Current A/c"
      }},
      {{
        "name": "Accounts receivable",
        "debit": 0.00,
        "credit": 15000.00,
        "partner": "Customer Name"
      }}
    ]
  }}
]

## Transaction Type Classification:

1. **customer_payment**: Payments received from customers
2. **supplier_payment**: Payments made to vendors/suppliers
3. **wage_payment**: Salary/wage payments to employees (REMEMBER: anonymize names)
4. **payroll_tax_payment**: Social insurance, PAYE, GHS, and payroll-related tax payments
5. **vat_payment**: VAT payments to tax authority (net VAT payable)
6. **vat_refund**: VAT refunds from tax authority (net VAT receivable)
7. **bank_charges**: Bank fees and charges
8. **credit_card_purchase**: Individual credit card transactions
9. **credit_card_payment**: Payment from bank to credit card
10. **interest_received**: Interest income
11. **credit_adjustment**: Refunds, reversals, cashback, rewards received
12. **suspense_entry**: Unclear/ambiguous transactions
13. **other_expense**: Direct expenses
14. **other_income**: Miscellaneous income

## Processing Instructions

1. **STEP 1: Use company context** to understand expected transaction patterns
2. **STEP 2: Determine document type** (Credit Card vs Bank Account)
3. **STEP 3: Identify statement structure** and group related transactions
4. **STEP 4: For CREDIT CARD statements** - Apply structural grouping rules with exceptions
5. **STEP 5: For BANK ACCOUNT statements** - Determine money flow from columns
6. **STEP 6: Identify payroll transactions** using company payroll context (frequency, employee count)
7. **STEP 7: Anonymize employee names** - Extract initials only for payroll entries
8. **STEP 8: Map to specific expense accounts** where possible
9. **STEP 9: Use suspense account** ONLY for truly unclear bank transactions
10. **STEP 10: Assign correct partner names** (anonymized for employees)
11. **STEP 11: Create balanced line_items** ensuring debits = credits
12. **STEP 12: Set company_id** to company name for every transaction
13. **STEP 13: Ensure all numeric values are numbers, not strings**

## Example Payroll Transaction:

### Wage Payment (ANONYMIZED):
```json
{{
  "company_id": "{company_name}",
  "date": "2025-06-30",
  "ref": "payroll_300625",
  "narration": "Monthly salary payment",
  "partner": "Employee - J.S.",
  "accounting_assignment": {{
    "debit_account": "7000",
    "debit_account_name": "Gross wages",
    "credit_account": "1201",
    "credit_account_name": "Bank",
    "transaction_type": "wage_payment",
    "requires_vat": false,
    "additional_entries": []
  }},
  "line_items": [
    {{
      "name": "Gross wages",
      "debit": 2500.00,
      "credit": 0.00,
      "partner": "Employee - J.S."
    }},
    {{
      "name": "Bank",
      "debit": 0.00,
      "credit": 2500.00,
      "partner": "{primary_bank} - Current A/c"
    }}
  ]
}}
```

**CRITICAL: Return ONLY the JSON array. No markdown formatting, no code blocks, no explanatory text. The response must start with '[' and end with ']'. Every line_item must include a "partner" field. Anonymize employee names in payroll transactions.**
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
            "2100", "2200", "2210",          # Liabilities  
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

def process_bank_statement_extraction(pdf_content, company_name, company_context=None):
    """Process bank statement with Claude for transaction extraction with accounting assignment and company context"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get bank statement extraction prompt with company context
        prompt = get_bank_statement_extraction_prompt(company_name, company_context)
        
        # Build enhanced system prompt with company awareness
        payroll_context_note = ""
        if company_context:
            payroll_info = company_context.get('payroll_information', {})
            num_employees = payroll_info.get('num_employees', 0)
            if num_employees > 0:
                payroll_context_note = f"\n- Company has {num_employees} employee(s), expect payroll transactions"
                payroll_context_note += "\n- CRITICAL: Anonymize employee names - use initials only (e.g., 'Employee - J.S.')"
        
        # Send to Claude with parameters optimized for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=12000,
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
  - Usually appear in a separate list with merchant names and trace numbers
  - Individual purchases: DEBIT expense account, CREDIT 1240 Credit card

**FOR BANK ACCOUNT STATEMENTS - USE COLUMN ANALYSIS:**
• **CRITICAL**: Analyze DEBIT vs CREDIT columns to determine money flow
• CREDIT column (money IN):
  - Customer payments: DEBIT 1201 Bank, CREDIT 1100 Accounts receivable
  - VAT refunds: DEBIT 1201 Bank, CREDIT 2200 VAT control account
• DEBIT column (money OUT):
  - **PAYROLL/WAGES (CRITICAL PRIVACY RULES)**:
    - Keywords: "SALARY", "WAGE", "PAYROLL", employee names, regular scheduled transfers
    - DEBIT 7000 Gross wages, CREDIT 1201 Bank
    - **NEVER use full employee names in partner field**
    - Extract ONLY initials from description (e.g., "John Smith" → "J.S.")
    - Partner format: "Employee - [Initials]" (e.g., "Employee - J.S.")
    - Narration can be more descriptive, but partner field MUST be anonymized
    - Use company payroll context to identify wage transactions
  - Payroll taxes (Social Insurance, PAYE, GHS): DEBIT 2210 PAYE/NIC, CREDIT 1201 Bank
  - VAT payments: DEBIT 2200 VAT control account, CREDIT 1201 Bank
  - Supplier payments: DEBIT 2100 Accounts payable, CREDIT 1201 Bank
  - Bank charges: DEBIT 7901 Bank charges, CREDIT 1201 Bank
• Use 1260 Suspense only when truly unclear

EXPENSE ACCOUNT MAPPING:
• Fuel stations → 7300 Car fuel & oil
• Restaurants → 7403 Entertainment
• Travel/Airlines → 7400 Traveling
• Hotels → 7402 Hotels
• Telecommunications → 7502 Telephone or 7503 Internet
• Professional services → 7602 Consultancy fees
• Unknown merchants → 6900 Miscellaneous expenses

TRANSACTION IDENTIFICATION KEYWORDS:
• **Payroll/Wages**: "SALARY", "WAGE", "PAYROLL", employee names, scheduled monthly transfers → Use 7000 Gross wages (ANONYMIZE NAMES)
• **Payroll taxes**: "Social Insurance", "PAYE", "GHS", "National Insurance", "NIC" → Use 2210 PAYE/NIC
• **VAT payments/refunds**: "TAX PAYMENT" with "VAT" context → Use 2200 VAT control account (check money flow direction)
• **Regular supplier payments**: Everything else with vendor names → Use 2100 Accounts payable

PARTNER NAME ASSIGNMENT:
• 1201 Bank: Always use company's primary bank name + "- Current A/c"
• 1240 Credit card: Always use company's primary bank name + "- Credit card"
• **CRITICAL FOR PAYROLL**: Format as "Employee - [Initials]" (e.g., "Employee - J.S.", "Employee - M.A.")
• Other accounts: Extract from transaction description, clean format

OUTPUT REQUIREMENTS:
• Return ONLY valid JSON array
• Every line_item must include "partner" field
• Ensure proper double-entry balancing
• Use exact account codes and names from chart of accounts
• Apply appropriate transaction types
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
            - company_name (str): Name of the company for context lookup
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Processing result with success status and extracted data
    """
    try:
        # Validate required fields
        required_fields = ['s3_key', 'company_name']
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            return {
                "success": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }
        
        s3_key = data['s3_key']
        company_name = data['company_name']
        bucket_name = data.get('bucket_name')
        
        print(f"Processing bank statement for company: {company_name}, S3 key: {s3_key}")
        
        # Fetch comprehensive company context from DynamoDB
        company_context = get_company_context(company_name)
        
        if not company_context:
            print(f"⚠️  Warning: No company context found for {company_name}")
            print(f"   Proceeding with generic transaction processing")
        else:
            print(f"✅ Company context loaded successfully")
        
        # Download PDF from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded PDF, size: {len(pdf_content)} bytes")
        
        # Process bank statement for transaction extraction with company context
        result = process_bank_statement_extraction(pdf_content, company_name, company_context)
        
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
                    "company_name": company_name,
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