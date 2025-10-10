import boto3
import base64
import anthropic
import os
import json
from decimal import Decimal

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
                'business_address': company_data.get('business_address', ''),
                'registration_no': company_data.get('registration_no', ''),
                'vat_no': company_data.get('vat_no', ''),
                'trading_name': company_data.get('trading_name', '')
            }
            
            # Extract payroll information
            payroll_info = company_data.get('payroll_information', {})
            context['payroll_information'] = {
                'num_employees': payroll_info.get('num_employees', 0),
                'payroll_frequency': payroll_info.get('payroll_frequency', ''),
                'social_insurance': payroll_info.get('social_insurance', ''),
                'uses_ghs': payroll_info.get('uses_ghs', False)
            }
            
            # Extract banking information
            banking_info = company_data.get('banking_information', {})
            context['banking_information'] = {
                'primary_currency': banking_info.get('primary_currency', ''),
                'multi_currency': banking_info.get('multi_currency', False)
            }
            
            print(f"✅ Company context loaded for: {company_name}")
            print(f"  Number of Employees: {context['payroll_information']['num_employees']}")
            print(f"  Payroll Frequency: {context['payroll_information']['payroll_frequency']}")
            print(f"  Social Insurance: {context['payroll_information']['social_insurance']}")
            
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
**COMPANY CONTEXT:** Not available - proceed with standard payroll processing
"""
    
    # Build context sections
    basic_info = f"""
**Company:** {company_context.get('company_name', 'N/A')}
**Business Address:** {company_context.get('business_address', 'N/A')}
**Registration No:** {company_context.get('registration_no', 'N/A')}
**VAT No:** {company_context.get('vat_no', 'N/A')}"""

    # Payroll information section
    payroll_info = company_context.get('payroll_information', {})
    payroll_section = f"""
**PAYROLL INFORMATION:**
- Number of Employees: {payroll_info.get('num_employees', 0)}
- Payroll Frequency: {payroll_info.get('payroll_frequency', 'N/A')}
- Social Insurance: {payroll_info.get('social_insurance', 'N/A')}
- Uses GHS: {'Yes' if payroll_info.get('uses_ghs', False) else 'No'}"""

    # Banking information section
    banking_info = company_context.get('banking_information', {})
    banking_section = f"""
**BANKING INFORMATION:**
- Primary Currency: {banking_info.get('primary_currency', 'N/A')}
- Multi-Currency: {'Yes' if banking_info.get('multi_currency', False) else 'No'}"""

    return f"""
**COMPANY CONTEXT - USE THIS TO IMPROVE ACCURACY:**

{basic_info}

{payroll_section}

{banking_section}

**USE THIS CONTEXT TO:**
1. ✅ Validate payroll data aligns with expected employee count
2. ✅ Verify payroll frequency matches document period
3. ✅ Apply correct social insurance calculations based on company setup
4. ✅ Use correct currency for all monetary amounts
5. ✅ Flag discrepancies between expected and actual employee counts
"""

def get_payroll_processing_prompt(company_name, company_context=None):
    """Create comprehensive payroll processing prompt for journal entry extraction"""
    
    # Get company context section
    company_context_section = get_company_context_section(company_context)
    
    return f"""You are an advanced payroll document processing AI specialized in Cyprus payroll accounting. Your task is to analyze a payroll document and extract structured data for creating a consolidated payroll journal entry in Odoo.

**CRITICAL INSTRUCTION: Respond with ONLY the JSON object. Do not include any explanatory text, commentary, analysis, or markdown formatting before or after the JSON. Start your response immediately with the opening curly brace {{.**

**INPUT:** Payroll document (PDF/Excel format)
**COMPANY:** {company_name} (the company processing this payroll)
**OUTPUT:** Raw JSON object only

{company_context_section}

**PAYROLL DOCUMENT STRUCTURE:**
Payroll documents typically contain:
- Individual employee rows with earnings, deductions, and net pay
- A totals/summary row at the bottom
- Sections for EARNINGS, DEDUCTIONS, EMPLOYER CONTRIBUTIONS
- Period information (month, year, pay date)

**YOUR TASK:**
Extract data from the TOTALS/SUMMARY row (not individual employee rows) to create ONE consolidated journal entry for the entire payroll run.

**CRITICAL PAYROLL ACCOUNTING PRINCIPLES:**

**1. ONE CONSOLIDATED JOURNAL ENTRY:**
- Create ONLY ONE journal entry for the entire payroll period
- Aggregate all amounts by account type across all employees
- Do NOT create separate entries per employee
- Individual employee details are in payslips; accounting is consolidated

**2. ACCRUAL ACCOUNTING:**
- Recognize expenses when incurred (when employees work), not when paid
- All expenses are DEBITED (gross wages, bonuses, employer contributions)
- All liabilities are CREDITED (net wages payable, taxes payable, social insurance payable)
- NO bank or cash accounts in the payroll journal entry

**3. CYPRUS SOCIAL INSURANCE - TWO COMPONENTS:**
- **Employee Contribution (~8.8% of gross):** Deducted FROM employee salary, reduces net pay
- **Employer Contribution (~8.3% of gross):** Company expense, does NOT reduce employee net pay
- **Both go to Account 2210 (PAYE/NIC):** Employee portion + Employer portion = Total liability to authorities

**CHART OF ACCOUNTS FOR PAYROLL:**

**EXPENSE ACCOUNTS (Always DEBIT):**
- **7000 - Gross wages:** Total salary expense before deductions
- **7003 - Staff bonus:** Bonus payments (annual, performance, etc.)
- **7006 - Employers n.i.:** Employer's National Insurance/Social Insurance contribution (~8.3%)
- **7400 - Traveling:** Employee traveling allowances/reimbursements
- **7007 - Employers pensions:** Employer's provident fund/pension contribution (if applicable)
- **7008 - Employee benefits healthcare:** Company-paid healthcare benefits (if applicable)
- **7009 - Employee benefits phi life assurance:** Company-paid life insurance (if applicable)

**LIABILITY ACCOUNTS (Always CREDIT):**
- **2210 - PAYE/NIC:** BOTH employee AND employer social insurance combined (total liability to authorities)
- **2250 - Net wages:** Net salary payable to employees after all deductions
- **2220 - Income Tax:** Income tax withheld from employee salaries (PAYE) (if applicable)
- **1150 - Employee advances:** Employee advances recovered from salary (if applicable) (CREDIT when deducted)

**JOURNAL ENTRY STRUCTURE:**

**DEBITS (Expenses recognized):**
- Account 7000: Total gross salaries
- Account 7003: Total bonuses (if any)
- Account 7006: Total employer social insurance contribution
- Account 7400: Total traveling allowances (if any)
- Account 7007: Employer pension contributions (if any)
- Account 7008: Healthcare benefits (if any)
- Account 7009: Life insurance benefits (if any)

**CREDITS (Liabilities created):**
- Account 2210: Employee social insurance + Employer social insurance (BOTH combined)
- Account 2250: Total net wages payable to all employees
- Account 2220: Total income tax withheld (if any)
- Account 1150: Employee advances deducted (if any)

**CRITICAL CALCULATIONS:**

**1. Account 2210 (PAYE/NIC) Calculation:**
```
Account 2210 = Employee Social Insurance (deducted) + Employer Social Insurance (expense)
```
Example: Employee contribution 92.40 + Employer contribution 66.00 = 158.40 credited to 2210

**2. Net Wages Calculation:**
```
Net Wages = Gross Wages + Allowances/Bonuses - All Employee Deductions
```
Employee deductions include: social insurance, income tax, pension contributions, advances
Employer contributions do NOT reduce net wages

**3. Validation Check:**
```
Total Debits MUST EQUAL Total Credits
Sum of all debits = Sum of all credits
```

**DOCUMENT READING INSTRUCTIONS:**

**Step 1: Identify Document Structure**
- Look for totals/summary row (usually at bottom)
- Identify sections: EARNINGS, DEDUCTIONS, CONTRIBUTIONS/EMPLOYER
- Find period information (month, year)

**Step 2: Extract from TOTALS Row**
- Extract total gross salaries
- Extract total bonuses
- Extract total allowances (traveling, etc.)
- Extract total employee deductions (social insurance, income tax, etc.)
- Extract total employer contributions (employer social insurance, pension, etc.)
- Extract total net wages

**Step 3: Map to Accounts**
- Gross salary totals → Account 7000
- Bonus totals → Account 7003
- Traveling allowance totals → Account 7400
- Employer social insurance totals → Account 7006
- Employee social insurance + Employer social insurance → Account 2210
- Net wages totals → Account 2250
- Income tax totals → Account 2220

**Step 4: Create Line Items**
Each line item represents one account in the journal entry with:
- Account code and name
- Debit amount (if expense) or 0
- Credit amount (if liability) or 0
- Description explaining the line

**HANDLING DIFFERENT DOCUMENT FORMATS:**

**Common Column Names for Earnings:**
- "Salary", "Wages", "Basic Pay", "Gross Salary" → Account 7000
- "Bonus", "Annual Bonus", "Performance Bonus" → Account 7003
- "Travel Allowance", "Traveling", "Travel Pay" → Account 7400

**Common Column Names for Deductions:**
- "Social Insurance", "NI", "Social Ins", "Employee SI" → Employee portion for Account 2210
- "Income Tax", "PAYE", "Tax", "Withholding Tax" → Account 2220
- "Pension", "Provident Fund", "Employee Pension" → Part of employee deductions
- "Advance", "Loan Recovery", "Employee Advance" → Account 1150

**Common Column Names for Employer Contributions:**
- "Employer Social Insurance", "Employer NI", "Company SI" → Account 7006
- "Employer Pension", "Company Pension" → Account 7007
- "Healthcare", "Health Insurance", "GHS" → Account 7008
- "Life Insurance", "Life Assurance" → Account 7009

**Net Pay Identification:**
- "Net Pay", "Net Wages", "Net Salary", "Take Home" → Account 2250

**STRICT FORMATTING RULES:**
- Text fields: Use empty string "" if not found
- Date fields: Use null if not found
- Number fields: Use 0 if not found (never use null)
- Array fields: Use empty array [] if no items found
- Currency codes: Use standard 3-letter codes: EUR, USD, GBP, or "" if unknown
- All monetary amounts must be numbers (not strings)

**REQUIRED JSON STRUCTURE - ALL FIELDS MUST BE PRESENT:**

{{
  "success": true,
  "payroll_data": {{
    "period": "",
    "month": "",
    "year": "",
    "pay_date": null,
    "num_employees": 0,
    "currency_code": "",
    "description": "",
    "total_gross_wages": 0,
    "total_net_wages": 0,
    "total_deductions": 0,
    "total_employer_contributions": 0,
    "journal_entry_lines": []
  }},
  "company_validation": {{
    "expected_company": "{company_name}",
    "found_company": "",
    "company_match": "no_match",
    "match_details": ""
  }},
  "extraction_confidence": {{
    "period_info": "low",
    "amounts": "low",
    "employee_count": "low",
    "company_validation": "low"
  }},
  "validation_summary": {{
    "debits_equal_credits": false,
    "total_debits": 0,
    "total_credits": 0,
    "balance_difference": 0
  }},
  "missing_fields": []
}}

**JOURNAL ENTRY LINES STRUCTURE:**
Each line in the journal_entry_lines array must have this exact structure:
{{
  "account_code": "",
  "account_name": "",
  "description": "",
  "debit_amount": 0,
  "credit_amount": 0
}}

**JOURNAL ENTRY LINE EXAMPLES:**

**Expense Lines (Debits):**
{{
  "account_code": "7000",
  "account_name": "Gross wages",
  "description": "Total gross salaries for June 2025",
  "debit_amount": 1050.00,
  "credit_amount": 0
}}

{{
  "account_code": "7003",
  "account_name": "Staff bonus",
  "description": "Total staff bonuses for June 2025",
  "debit_amount": 27.83,
  "credit_amount": 0
}}

{{
  "account_code": "7006",
  "account_name": "Employers n.i.",
  "description": "Employer social insurance contribution (~8.3%)",
  "debit_amount": 66.00,
  "credit_amount": 0
}}

**Liability Lines (Credits):**
{{
  "account_code": "2210",
  "account_name": "PAYE/NIC",
  "description": "Total social insurance payable (employee 92.40 + employer 66.00)",
  "debit_amount": 0,
  "credit_amount": 158.40
}}

{{
  "account_code": "2250",
  "account_name": "Net wages",
  "description": "Total net wages payable to all employees",
  "debit_amount": 0,
  "credit_amount": 929.77
}}

{{
  "account_code": "2220",
  "account_name": "Income Tax",
  "description": "Total income tax withheld (PAYE)",
  "debit_amount": 0,
  "credit_amount": 50.00
}}

**VALIDATION REQUIREMENTS:**

**1. Balance Check:**
- Sum of all debit_amount must equal sum of all credit_amount
- Calculate and report any difference
- Set debits_equal_credits to true only if difference is 0.00 or within 0.01 tolerance

**2. Account 2210 Verification:**
- Must include BOTH employee and employer social insurance
- Verify the sum makes sense relative to gross wages (typically ~17% combined)

**3. Net Wages Verification:**
- Net wages should be less than gross wages
- Difference should roughly equal total deductions
- Verify calculation: Gross + Allowances - Deductions = Net

**4. Mandatory Lines:**
- Must have at least Account 7000 (Gross wages) as debit
- Must have at least Account 2250 (Net wages) as credit
- Should have Account 2210 (PAYE/NIC) unless no social insurance applies

**DESCRIPTION FIELD:**
Create a comprehensive description of the payroll run including:
- Payroll period (month and year)
- Number of employees
- Key components (gross wages, bonuses, deductions, net pay)
- Example: "Payroll for June 2025 - 3 employees: Gross wages €1,050.00, Staff bonus €27.83, Net wages payable €929.77"

**COMPANY VALIDATION:**
- Identify company name in the document
- Check if it matches "{company_name}" (case-insensitive, fuzzy matching)
- Set company_match: "exact_match", "close_match", "no_match", or "unclear"

**CONFIDENCE LEVELS:**
Assess extraction confidence for each category:
- "high": Data clearly visible and extracted with certainty
- "medium": Data visible but some ambiguity
- "low": Data not found, unclear, or estimated

**ABSOLUTE REQUIREMENTS:**
1. Every field must be present with appropriate default values
2. All monetary amounts must be numbers, not strings
3. Debit amounts go to expense accounts (7xxx)
4. Credit amounts go to liability accounts (2xxx) or asset reduction (1150)
5. Total debits must equal total credits
6. Account 2210 must include both employee and employer contributions
7. Create exactly ONE consolidated journal entry, not per-employee entries
8. Never include bank/cash accounts in the payroll journal entry
9. String fields default to ""
10. Number fields default to 0
11. Date fields default to null
12. Array fields default to []

**FINAL REMINDER: Return ONLY the JSON object with ALL fields present. No explanatory text. Start with {{ and end with }}.**"""

def validate_payroll_data(payroll_data, company_context=None):
    """Validate extracted payroll data for completeness and accuracy"""
    validation_results = {
        "issues": [],
        "warnings": [],
        "data_complete": True,
        "accounting_balanced": False
    }
    
    # Check mandatory fields
    if not payroll_data.get("period"):
        validation_results["issues"].append("Missing payroll period")
        validation_results["data_complete"] = False
    
    if payroll_data.get("total_gross_wages", 0) == 0:
        validation_results["issues"].append("Total gross wages is zero")
        validation_results["data_complete"] = False
    
    if payroll_data.get("total_net_wages", 0) == 0:
        validation_results["issues"].append("Total net wages is zero")
        validation_results["data_complete"] = False
    
    # Check journal entry lines
    journal_lines = payroll_data.get("journal_entry_lines", [])
    
    if not journal_lines:
        validation_results["issues"].append("No journal entry lines found")
        validation_results["data_complete"] = False
        return validation_results
    
    # Validate account structure
    debit_accounts = []
    credit_accounts = []
    total_debits = 0
    total_credits = 0
    
    for line in journal_lines:
        account_code = line.get("account_code", "")
        debit_amount = line.get("debit_amount", 0)
        credit_amount = line.get("credit_amount", 0)
        
        if not account_code:
            validation_results["issues"].append("Journal line missing account_code")
            continue
        
        if debit_amount > 0:
            debit_accounts.append(account_code)
            total_debits += debit_amount
        
        if credit_amount > 0:
            credit_accounts.append(account_code)
            total_credits += credit_amount
        
        # Validate that line has either debit or credit, not both
        if debit_amount > 0 and credit_amount > 0:
            validation_results["warnings"].append(
                f"Account {account_code} has both debit and credit amounts"
            )
    
    # Check for mandatory accounts
    if "7000" not in debit_accounts:
        validation_results["issues"].append("Missing Account 7000 (Gross wages) - mandatory debit")
    
    if "2250" not in credit_accounts:
        validation_results["issues"].append("Missing Account 2250 (Net wages) - mandatory credit")
    
    if "2210" not in credit_accounts:
        validation_results["warnings"].append(
            "Missing Account 2210 (PAYE/NIC) - expected for most payrolls"
        )
    
    # Validate debits equal credits
    balance_difference = abs(total_debits - total_credits)
    
    if balance_difference < 0.01:  # Tolerance for rounding
        validation_results["accounting_balanced"] = True
    else:
        validation_results["issues"].append(
            f"Debits ({total_debits:.2f}) do not equal Credits ({total_credits:.2f}). "
            f"Difference: {balance_difference:.2f}"
        )
    
    # Validate social insurance logic (Account 2210)
    paye_nic_lines = [line for line in journal_lines if line.get("account_code") == "2210"]
    employer_ni_lines = [line for line in journal_lines if line.get("account_code") == "7006"]
    
    if paye_nic_lines and employer_ni_lines:
        paye_nic_amount = sum(line.get("credit_amount", 0) for line in paye_nic_lines)
        employer_ni_amount = sum(line.get("debit_amount", 0) for line in employer_ni_lines)
        
        # Account 2210 should include employer contribution
        if paye_nic_amount < employer_ni_amount:
            validation_results["warnings"].append(
                f"Account 2210 ({paye_nic_amount:.2f}) seems low - should include employer NI ({employer_ni_amount:.2f})"
            )
    
    # Validate net wages calculation
    gross_wages = payroll_data.get("total_gross_wages", 0)
    net_wages = payroll_data.get("total_net_wages", 0)
    
    if gross_wages > 0 and net_wages >= gross_wages:
        validation_results["warnings"].append(
            "Net wages equal or exceed gross wages - unusual, verify deductions"
        )
    
    # Company context validations
    if company_context:
        expected_employees = company_context.get('payroll_information', {}).get('num_employees', 0)
        actual_employees = payroll_data.get("num_employees", 0)
        
        if expected_employees > 0 and actual_employees > 0:
            if actual_employees != expected_employees:
                validation_results["warnings"].append(
                    f"Employee count mismatch: Expected {expected_employees}, Found {actual_employees}"
                )
    
    # Check confidence levels
    confidence = payroll_data.get("extraction_confidence", {})
    low_confidence_fields = [
        field for field, conf in confidence.items() 
        if conf == "low"
    ]
    
    if low_confidence_fields:
        validation_results["warnings"].append(
            f"Low confidence fields: {', '.join(low_confidence_fields)}"
        )
    
    return validation_results

def process_payroll_with_claude(pdf_content, company_name, company_context=None):
    """Process payroll document with Claude for data extraction"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get comprehensive prompt with company context
        prompt = get_payroll_processing_prompt(company_name, company_context)
        
        # Build system prompt with payroll expertise
        system_prompt = """You are an expert accountant and payroll processing specialist with deep expertise in Cyprus payroll accounting, double-entry bookkeeping for salary expenses, and Odoo ERP payroll journal entries.

**CORE PAYROLL ACCOUNTING EXPERTISE:**

**Cyprus Social Insurance Structure:**
- Employee contribution: ~8.8% of gross salary (deducted from employee)
- Employer contribution: ~8.3% of gross salary (company expense)
- Both portions go to Account 2210 (PAYE/NIC) as total liability
- Employee portion reduces net pay; employer portion does not

**Payroll Journal Entry Principles:**
- ONE consolidated entry per payroll period (not per employee)
- Accrual accounting: recognize expenses when incurred, not when paid
- Expense accounts (7xxx) are always DEBITED
- Liability accounts (2xxx) are always CREDITED
- Never include bank/cash accounts in payroll journal entry
- Total debits must equal total credits

**Account Assignment Rules:**
- Gross salaries → 7000 (Gross wages) [DEBIT]
- Bonuses → 7003 (Staff bonus) [DEBIT]
- Traveling allowances → 7400 (Traveling) [DEBIT]
- Employer social insurance → 7006 (Employers n.i.) [DEBIT]
- Employer pension → 7007 (Employers pensions) [DEBIT]
- Employee + Employer social insurance → 2210 (PAYE/NIC) [CREDIT]
- Net wages payable → 2250 (Net wages) [CREDIT]
- Income tax withheld → 2220 (Income Tax) [CREDIT]

**Document Reading Strategy:**
- Focus on TOTALS/SUMMARY row (bottom of document)
- Aggregate amounts by account type, not per employee
- Identify sections: EARNINGS, DEDUCTIONS, EMPLOYER CONTRIBUTIONS
- Map column names to account codes
- Extract period information (month, year)
- Count number of employees

**Critical Validation:**
- Verify debits equal credits
- Check Account 2210 includes both employee and employer contributions
- Validate net wages = gross wages + allowances - deductions
- Ensure all mandatory accounts are present (7000, 2250)

**Output Format:**
Respond ONLY with valid JSON. No explanatory text, analysis, or commentary. Include ALL required fields with default values when data is missing. Apply accounting expertise to ensure balanced journal entries."""
        
        # Send to Claude with optimized parameters
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16000,
            temperature=0.0,
            system=system_prompt,
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
        
        # Log token usage
        print(f"Token usage - Input: {message.usage.input_tokens}, Output: {message.usage.output_tokens}")
        print(f"Response preview: {response_text[:200]}...")
        
        return {
            "success": True,
            "raw_response": response_text,
            "token_usage": {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

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

def ensure_payroll_structure(payroll_data):
    """Ensure payroll data has the complete required structure with default values"""
    
    default_structure = {
        "success": True,
        "payroll_data": {
            "period": "",
            "month": "",
            "year": "",
            "pay_date": None,
            "num_employees": 0,
            "currency_code": "",
            "description": "",
            "total_gross_wages": 0,
            "total_net_wages": 0,
            "total_deductions": 0,
            "total_employer_contributions": 0,
            "journal_entry_lines": []
        },
        "company_validation": {
            "expected_company": "",
            "found_company": "",
            "company_match": "no_match",
            "match_details": ""
        },
        "extraction_confidence": {
            "period_info": "low",
            "amounts": "low",
            "employee_count": "low",
            "company_validation": "low"
        },
        "validation_summary": {
            "debits_equal_credits": False,
            "total_debits": 0,
            "total_credits": 0,
            "balance_difference": 0
        },
        "missing_fields": []
    }
    
    def merge_with_defaults(source, defaults):
        """Recursively merge source with defaults"""
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
    
    return merge_with_defaults(payroll_data, default_structure)

def parse_payroll_response(raw_response):
    """Parse the raw response into structured payroll data with error handling"""
    try:
        # Clean the response
        cleaned_response = raw_response.strip()
        
        # Remove markdown formatting if present
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]
        elif cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]
            
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]
            
        cleaned_response = cleaned_response.strip()
        
        # Handle text before JSON
        json_start = cleaned_response.find('{')
        if json_start > 0:
            print(f"Warning: Found text before JSON, removing: {cleaned_response[:json_start][:100]}...")
            cleaned_response = cleaned_response[json_start:]
        
        # Handle text after JSON
        json_end = cleaned_response.rfind('}')
        if json_end > 0 and json_end < len(cleaned_response) - 1:
            print(f"Warning: Found text after JSON, removing: {cleaned_response[json_end+1:][:100]}...")
            cleaned_response = cleaned_response[:json_end + 1]
        
        cleaned_response = cleaned_response.strip()
        
        # Parse JSON response
        try:
            result = json.loads(cleaned_response)
            
            # Validate basic structure
            if not isinstance(result, dict):
                raise ValueError("Response is not a JSON object")
            
            # Ensure complete structure
            validated_result = ensure_payroll_structure(result)
            
            # Calculate validation summary
            journal_lines = validated_result.get("payroll_data", {}).get("journal_entry_lines", [])
            total_debits = sum(line.get("debit_amount", 0) for line in journal_lines)
            total_credits = sum(line.get("credit_amount", 0) for line in journal_lines)
            balance_difference = abs(total_debits - total_credits)
            
            validated_result["validation_summary"] = {
                "debits_equal_credits": balance_difference < 0.01,
                "total_debits": total_debits,
                "total_credits": total_credits,
                "balance_difference": balance_difference
            }
            
            print(f"Successfully parsed payroll response")
            print(f"  Period: {validated_result['payroll_data'].get('period', 'Unknown')}")
            print(f"  Employees: {validated_result['payroll_data'].get('num_employees', 0)}")
            print(f"  Total Debits: {total_debits:.2f}, Total Credits: {total_credits:.2f}")
            print(f"  Balanced: {validated_result['validation_summary']['debits_equal_credits']}")
            
            return {
                "success": True,
                "result": validated_result
            }
            
        except json.JSONDecodeError as e:
            error_position = getattr(e, 'pos', 0)
            context_start = max(0, error_position - 50)
            context_end = min(len(cleaned_response), error_position + 50)
            context = cleaned_response[context_start:context_end]
            
            return {
                "success": False,
                "error": f"Invalid JSON response at position {error_position}: {str(e)}",
                "context": context,
                "raw_response": cleaned_response[:1000]
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Error parsing response: {str(e)}",
            "raw_response": raw_response[:500] if raw_response else "No response"
        }

def main(data):
    """
    Main function for payroll document processing
    
    Args:
        data (dict): Request data containing:
            - s3_key (str): S3 key path to the payroll document
            - company_name (str): Name of the company processing payroll
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Processing result with structured payroll data
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
        
        print(f"Processing payroll for company: {company_name}, S3 key: {s3_key}")
        
        # Fetch company context from DynamoDB
        company_context = get_company_context(company_name)
        
        if not company_context:
            print(f"⚠️  Warning: No company context found for {company_name}")
            print(f"  Proceeding with standard payroll processing")
        else:
            print(f"✅ Company context loaded successfully")
        
        # Download document from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded document, size: {len(pdf_content)} bytes")
        
        # Process with Claude for payroll data extraction
        claude_result = process_payroll_with_claude(pdf_content, company_name, company_context)
        
        if not claude_result["success"]:
            return {
                "success": False,
                "error": f"Claude processing failed: {claude_result['error']}"
            }
        
        # Parse the structured response
        parse_result = parse_payroll_response(claude_result["raw_response"])
        
        if not parse_result["success"]:
            return {
                "success": False,
                "error": f"Response parsing failed: {parse_result['error']}",
                "raw_response": claude_result["raw_response"],
                "parse_details": parse_result
            }
        
        result_data = parse_result["result"]
        payroll_data = result_data.get("payroll_data", {})
        
        # Validate extracted payroll data
        validation_results = validate_payroll_data(payroll_data, company_context)
        
        # Determine overall success
        processing_success = (
            validation_results["data_complete"] and 
            validation_results["accounting_balanced"] and
            len(validation_results["issues"]) == 0
        )
        
        return {
            "success": True,
            "payroll_data": payroll_data,
            "company_validation": result_data.get("company_validation", {}),
            "extraction_confidence": result_data.get("extraction_confidence", {}),
            "validation_summary": result_data.get("validation_summary", {}),
            "validation_results": validation_results,
            "processing_summary": {
                "data_complete": validation_results["data_complete"],
                "accounting_balanced": validation_results["accounting_balanced"],
                "issues_count": len(validation_results["issues"]),
                "warnings_count": len(validation_results["warnings"]),
                "processing_success": processing_success
            },
            "metadata": {
                "company_name": company_name,
                "company_context_loaded": company_context is not None,
                "expected_employees": company_context.get('payroll_information', {}).get('num_employees', 0) if company_context else 0,
                "payroll_frequency": company_context.get('payroll_information', {}).get('payroll_frequency', 'Unknown') if company_context else 'Unknown',
                "s3_key": s3_key,
                "token_usage": claude_result["token_usage"]
            }
        }
        
    except Exception as e:
        print(f"Payroll processing error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }

def health_check():
    """Health check for the payroll processing service"""
    try:
        # Check required environment variables
        required_vars = ['ANTHROPIC_API_KEY']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            return {
                "healthy": False,
                "error": f"Missing environment variables: {', '.join(missing_vars)}"
            }
        
        return {
            "healthy": True,
            "service": "claude-payroll-processing",
            "version": "1.0",
            "capabilities": [
                "payroll_document_processing",
                "journal_entry_extraction",
                "consolidated_accounting",
                "cyprus_social_insurance_handling",
                "double_entry_validation",
                "company_context_integration",
                "dynamodb_company_lookup",
                "accrual_accounting",
                "employee_aggregation",
                "debit_credit_balancing",
                "odoo_erp_integration",
                "salary_journal_entries"
            ],
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025'),
            "dynamodb_table": "users",
            "accounting_standard": "Cyprus Payroll Accounting",
            "journal_type": "SALARY",
            "supported_accounts": {
                "expense_accounts": [
                    "7000 - Gross wages",
                    "7003 - Staff bonus",
                    "7006 - Employers n.i.",
                    "7400 - Traveling",
                    "7007 - Employers pensions",
                    "7008 - Employee benefits healthcare",
                    "7009 - Employee benefits phi life assurance"
                ],
                "liability_accounts": [
                    "2210 - PAYE/NIC",
                    "2250 - Net wages",
                    "2220 - Income Tax",
                    "1150 - Employee advances"
                ]
            },
            "key_features": [
                "One consolidated journal entry per payroll period",
                "Automatic debit/credit balancing validation",
                "Cyprus social insurance calculation (employee + employer)",
                "Net wages calculation verification",
                "Company context awareness for validation",
                "Employee count verification",
                "Payroll frequency matching"
            ]
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }