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
    """Create comprehensive payroll processing prompt for journal entry extraction with Cyprus-specific handling"""
    
    # Get company context section
    company_context_section = get_company_context_section(company_context)
    
    return f"""You are an advanced payroll document processing AI specialized in Cyprus payroll accounting. Your task is to analyze a payroll document and extract structured data for creating a consolidated payroll journal entry in Odoo.

**CRITICAL INSTRUCTION: Respond with ONLY the JSON object. Do not include any explanatory text, commentary, analysis, or markdown formatting before or after the JSON. Start your response immediately with the opening curly brace {{.**

**INPUT:** Payroll document (PDF/Excel format)
**COMPANY:** {company_name} (the company processing this payroll)
**OUTPUT:** Raw JSON object only

{company_context_section}

**CRITICAL: PAYROLL DOCUMENT STRUCTURE - READ CAREFULLY**

Payroll documents have TWO types of rows:
1. **Individual employee rows** (UI001, UI002, UI003, etc.) - DO NOT USE THESE
2. **TOTALS row** (usually labeled "TOTALS" or "TOTALS (3)") - USE THIS ONLY

**YOU MUST READ ONLY THE TOTALS ROW, NOT INDIVIDUAL EMPLOYEE ROWS**

The TOTALS row may span TWO lines:
- **First line:** Shows totals for EARNINGS and most DEDUCTIONS
- **Second line:** Shows additional items (often labeled with period like "202506 - JUNE") with more DEDUCTIONS and all CONTRIBUTIONS

**BOTH lines are part of the TOTALS section - read across both lines**

**CYPRUS PAYROLL - COMPLETE ACCOUNTING STRUCTURE:**

**EXPENSE ACCOUNTS (Always DEBIT):**
- **7000 - Gross wages:** Total from SALARY column in EARNINGS (first TOTALS line)
- **7003 - Staff bonus:** Total from BONUS column (may appear in EARNINGS or DEDUCTIONS)
- **7006 - Employers n.i.:** Combined total of ALL employer-only contributions:
  * Employer SI (from SOCIAL INS in CONTRIBUTIONS)
  * Social Cohesion (from SOC COHESION in CONTRIBUTIONS)
  * Redundancy/Unemployment (from UNEMPLOYM ENT in CONTRIBUTIONS)
  * Industrial Training (from INDUSTRIAL in CONTRIBUTIONS)
- **7008 - Employee benefits healthcare:** Employer GESY only (from GESY in CONTRIBUTIONS)
- **7400 - Traveling:** From TRAVELING in EARNINGS (if any)

**LIABILITY ACCOUNTS (Always CREDIT):**
- **2210 - PAYE/NIC:** Sum of ALL these items:
  * Employee SI (from SOCIAL INS in DEDUCTIONS)
  * Employer SI (from SOCIAL INS in CONTRIBUTIONS)
  * Employee GESY (from GESY in DEDUCTIONS, often €0)
  * Employer GESY (from GESY in CONTRIBUTIONS)
  * Social Cohesion (from SOC COHESION in CONTRIBUTIONS)
  * Unemployment/Redundancy (from UNEMPLOYM ENT in CONTRIBUTIONS)
  * Industrial Training (from INDUSTRIAL in CONTRIBUTIONS)
- **2220 - Income Tax:** From INCOME TAX or PAYE in DEDUCTIONS (often €0 in Cyprus if under threshold)
- **2250 - Net wages:** Calculate as: Total Debits - Account 2210 - Account 2220

**CRITICAL RULE 1: COMBINE EMPLOYER CONTRIBUTIONS INTO ONE ACCOUNT 7006 LINE**

```
DO NOT create separate lines:
❌ Account 7006: Employer SI €92.40
❌ Account 7006: Industrial/Cohesion €26.25

Instead create ONE combined line:
✓ Account 7006: Employer n.i. €131.25 (all combined)
```

**CRITICAL RULE 2: ACCOUNT 2210 INCLUDES ALL EMPLOYER CONTRIBUTIONS**

```
Account 2210 must include:
- Employee SI (DEDUCTIONS)
- Employer SI (CONTRIBUTIONS) ← Include this
- Employee GESY (DEDUCTIONS)
- Employer GESY (CONTRIBUTIONS) ← Include this
- Social Cohesion (CONTRIBUTIONS) ← Include this
- Unemployment (CONTRIBUTIONS) ← Include this
- Industrial (CONTRIBUTIONS) ← Include this

These are ALL paid together to Cyprus Social Insurance Services.
```

**CRITICAL RULE 3: BONUS HANDLING**

```
If BONUS appears in DEDUCTIONS section with a value (like €27.83):
- This is still a BONUS EXPENSE to the company
- Create Account 7003 (Staff bonus) line with this amount as DEBIT
- The bonus reduces net wages (it's being recovered or it's pre-paid)
- DO NOT confuse this with Income Tax!

BONUS in DEDUCTIONS = Account 7003 (debit expense)
INCOME TAX in DEDUCTIONS = Account 2220 (credit liability)

These are completely different!
```

**CRITICAL RULE 4: NET WAGES CALCULATION**

```
Net Wages = Total Debits - Account 2210 - Account 2220 - Other Credits

This ensures the entry balances.

Do NOT just copy the "Net Pay" from document - calculate it to balance the entry.

Verification:
If document shows Net Pay = €929.77
And your calculation gives €990.33
Use the CALCULATED amount (€990.33) to ensure accounting balance.

The "Net Pay" in document may exclude some adjustments that appear in accounting.
```

**STEP-BY-STEP EXTRACTION PROCESS:**

**Step 1: Locate the TOTALS Row(s)**

Find the row that says "TOTALS" or "TOTALS (3)" - this may span two lines.
The second line often has a period label like "202506 - JUNE"

**Step 2: Extract EARNINGS (from first TOTALS line)**

```
SALARY column → Note the value for Account 7000
TRAVELING column → Note if non-zero for Account 7400
BONUS column → Check if appears here (usually €0 in Cyprus payrolls)
```

**Step 3: Extract DEDUCTIONS (from BOTH TOTALS lines)**

```
From first TOTALS line:
- SOCIAL INS column in DEDUCTIONS → Employee SI for Account 2210
- GESY column in DEDUCTIONS → Employee GESY for Account 2210 (often €0)
- INCOME TAX column in DEDUCTIONS → For Account 2220 (often €0)

From second TOTALS line (period line):
- BONUS column in DEDUCTIONS → For Account 7003 (if present)
- Note: This is still a company expense even though in deductions!
```

**Step 4: Extract CONTRIBUTIONS (from second TOTALS line)**

```
INDUSTRIAL column → Part of combined Account 7006
GESY column → Account 7008 (separate)
PROV. FUND column → Account 7007 if present (usually €0)
SOCIAL INS column → Part of combined Account 7006
SOC COHESION column → Part of combined Account 7006
UNEMPLOYM ENT column → Part of combined Account 7006
```

**Step 5: Calculate Combined Account 7006**

```
Account 7006 = 
  SOCIAL INS (CONTRIBUTIONS)
  + SOC COHESION (CONTRIBUTIONS)
  + UNEMPLOYM ENT (CONTRIBUTIONS)
  + INDUSTRIAL (CONTRIBUTIONS)

Example from document:
€92.40 + €21.00 + €12.60 + €5.25 = €131.25

Create ONE journal line for Account 7006 with this total.
```

**Step 6: Calculate Account 2210 (PAYE/NIC)**

```
Account 2210 = 
  Employee SI (from DEDUCTIONS, first line)
  + Employer SI (from CONTRIBUTIONS, second line)
  + Employee GESY (from DEDUCTIONS, first line)
  + Employer GESY (from CONTRIBUTIONS, second line)
  + SOC COHESION (from CONTRIBUTIONS, second line)
  + UNEMPLOYM ENT (from CONTRIBUTIONS, second line)
  + INDUSTRIAL (from CONTRIBUTIONS, second line)

Example from document:
€87.50 + €92.40 + €0.00 + €30.45 + €21.00 + €12.60 + €5.25 = €249.20
```

**Step 7: Create Journal Entry Lines**

```json
{{
  "journal_entry_lines": [
    {{
      "account_code": "7000",
      "account_name": "Gross wages",
      "description": "Total gross salaries for [period]",
      "debit_amount": [SALARY from EARNINGS],
      "credit_amount": 0
    }},
    {{
      "account_code": "7003",
      "account_name": "Staff bonus",
      "description": "Staff bonuses for [period]",
      "debit_amount": [BONUS from DEDUCTIONS if present, else 0],
      "credit_amount": 0
    }},
    {{
      "account_code": "7006",
      "account_name": "Employers n.i.",
      "description": "Employer contributions (SI + Cohesion + Unemployment + Industrial combined)",
      "debit_amount": [Sum of SOCIAL INS + SOC COHESION + UNEMPLOYM ENT + INDUSTRIAL from CONTRIBUTIONS],
      "credit_amount": 0
    }},
    {{
      "account_code": "7008",
      "account_name": "Employee benefits healthcare",
      "description": "Employer GESY contribution",
      "debit_amount": [GESY from CONTRIBUTIONS],
      "credit_amount": 0
    }},
    {{
      "account_code": "2210",
      "account_name": "PAYE/NIC",
      "description": "Total payable to authorities (Employee SI + all employer contributions)",
      "debit_amount": 0,
      "credit_amount": [Sum calculated in Step 6]
    }},
    {{
      "account_code": "2220",
      "account_name": "Income Tax",
      "description": "Income tax withheld",
      "debit_amount": 0,
      "credit_amount": [INCOME TAX from DEDUCTIONS, often 0]
    }},
    {{
      "account_code": "2250",
      "account_name": "Net wages",
      "description": "Net wages payable to employees",
      "debit_amount": 0,
      "credit_amount": [CALCULATED to balance: Total Debits - 2210 - 2220]
    }}
  ]
}}
```

**Step 8: Verify Balance**

```
Calculate Total Debits:
= Account 7000 + Account 7003 + Account 7006 + Account 7008

Calculate Total Credits:
= Account 2210 + Account 2220 + Account 2250

IF Total Debits ≠ Total Credits:
Adjust Account 2250 (Net wages) to make them equal.

Account 2250 = Total Debits - Account 2210 - Account 2220

This is the ONLY way to ensure balance.
```

**WORKED EXAMPLE FROM ACTUAL CYPRUS PAYROLL:**

**Document TOTALS rows show:**
```
Line 1 (TOTALS (3)):
SALARY: €1,050.00
SOCIAL INS (DEDUCTIONS): €87.50
All other deductions: €0.00

Line 2 (202506 - JUNE):
BONUS (DEDUCTIONS): €27.83
INDUSTRIAL (CONTRIBUTIONS): €5.25
GESY (CONTRIBUTIONS): €30.45
SOCIAL INS (CONTRIBUTIONS): €92.40
SOC COHESION (CONTRIBUTIONS): €21.00
UNEMPLOYM ENT (CONTRIBUTIONS): €12.60
```

**Step-by-step calculation:**

**1. Account 7000 (Gross wages):**
```
From SALARY in EARNINGS: €1,050.00
```

**2. Account 7003 (Staff bonus):**
```
From BONUS in DEDUCTIONS line 2: €27.83
(Yes, it's in deductions, but it's still a bonus expense!)
```

**3. Account 7006 (Employers n.i.) - COMBINED:**
```
SOCIAL INS (CONTRIBUTIONS): €92.40
+ SOC COHESION: €21.00
+ UNEMPLOYM ENT: €12.60
+ INDUSTRIAL: €5.25
= €131.25 (ONE line only!)
```

**4. Account 7008 (Employer GESY):**
```
GESY from CONTRIBUTIONS: €30.45
```

**5. Total Debits:**
```
€1,050.00 + €27.83 + €131.25 + €30.45 = €1,239.53
```

**6. Account 2210 (PAYE/NIC) - ALL COMBINED:**
```
Employee SI (DEDUCTIONS): €87.50
+ Employer SI (CONTRIBUTIONS): €92.40
+ Employee GESY (DEDUCTIONS): €0.00
+ Employer GESY (CONTRIBUTIONS): €30.45
+ SOC COHESION: €21.00
+ UNEMPLOYM ENT: €12.60
+ INDUSTRIAL: €5.25
= €249.20
```

**7. Account 2220 (Income Tax):**
```
INCOME TAX from DEDUCTIONS: €0.00
(No income tax in this payroll - under Cyprus threshold)
```

**8. Account 2250 (Net wages) - CALCULATED:**
```
Total Debits: €1,239.53
- Account 2210: €249.20
- Account 2220: €0.00
= €990.33

Use €990.33 (NOT the document's €929.77)
This ensures accounting balance.
```

**9. Verify Balance:**
```
Total Debits: €1,239.53
Total Credits: €249.20 + €0.00 + €990.33 = €1,239.53
✓ BALANCED!
```

**COMPLETE JSON OUTPUT:**

```json
{{
  "success": true,
  "payroll_data": {{
    "period": "202506 - JUNE",
    "month": "June",
    "year": "2025",
    "pay_date": null,
    "num_employees": 3,
    "currency_code": "EUR",
    "description": "Payroll for June 2025 - 3 employees: Gross wages €1,050.00, Staff bonus €27.83, Employer contributions €131.25, Employer GESY €30.45, Total PAYE/NIC €249.20, Net wages payable €990.33",
    "total_gross_wages": 1050.00,
    "total_net_wages": 990.33,
    "total_deductions": 87.50,
    "total_employer_contributions": 161.70,
    "journal_entry_lines": [
      {{
        "account_code": "7000",
        "account_name": "Gross wages",
        "description": "Total gross salaries for June 2025",
        "debit_amount": 1050.00,
        "credit_amount": 0
      }},
      {{
        "account_code": "7003",
        "account_name": "Staff bonus",
        "description": "Staff bonuses for June 2025 (from deductions)",
        "debit_amount": 27.83,
        "credit_amount": 0
      }},
      {{
        "account_code": "7006",
        "account_name": "Employers n.i.",
        "description": "Employer contributions (SI €92.40 + Cohesion €21.00 + Unemployment €12.60 + Industrial €5.25)",
        "debit_amount": 131.25,
        "credit_amount": 0
      }},
      {{
        "account_code": "7008",
        "account_name": "Employee benefits healthcare",
        "description": "Employer GESY contribution",
        "debit_amount": 30.45,
        "credit_amount": 0
      }},
      {{
        "account_code": "2210",
        "account_name": "PAYE/NIC",
        "description": "Total payable to authorities (Employee SI €87.50 + Employer SI €92.40 + Employer GESY €30.45 + Cohesion €21.00 + Unemployment €12.60 + Industrial €5.25)",
        "debit_amount": 0,
        "credit_amount": 249.20
      }},
      {{
        "account_code": "2220",
        "account_name": "Income Tax",
        "description": "Income tax withheld",
        "debit_amount": 0,
        "credit_amount": 0
      }},
      {{
        "account_code": "2250",
        "account_name": "Net wages",
        "description": "Net wages payable to employees (calculated to balance entry)",
        "debit_amount": 0,
        "credit_amount": 990.33
      }}
    ]
  }},
  "company_validation": {{
    "expected_company": "{company_name}",
    "found_company": "ENAMI LIMITED",
    "company_match": "exact_match",
    "match_details": "Company name matches"
  }},
  "extraction_confidence": {{
    "period_info": "high",
    "amounts": "high",
    "employee_count": "high",
    "company_validation": "high"
  }},
  "validation_summary": {{
    "debits_equal_credits": true,
    "total_debits": 1239.53,
    "total_credits": 1239.53,
    "balance_difference": 0
  }},
  "missing_fields": []
}}
```

**ABSOLUTE REQUIREMENTS:**

1. ✅ Read ONLY the TOTALS row(s), NOT individual employee rows
2. ✅ TOTALS may span TWO lines - read BOTH lines
3. ✅ Combine ALL employer contributions (except GESY) into ONE Account 7006 line
4. ✅ Account 2210 includes ALL employer contributions + employee portions
5. ✅ BONUS in DEDUCTIONS is still Account 7003 (expense), NOT income tax
6. ✅ Calculate Account 2250 to balance the entry: Total Debits - 2210 - 2220
7. ✅ Verify Total Debits = Total Credits before outputting
8. ✅ Never create multiple lines for same account code

**FINAL REMINDER: Return ONLY the JSON object. No text before or after. Ensure debits equal credits by calculating Account 2250 correctly.**"""

def validate_cyprus_payroll_structure(payroll_data):
    """
    Validate Cyprus-specific payroll structure and calculations
    Returns issues found and potential corrections
    """
    issues = []
    warnings = []
    
    gross_wages = payroll_data.get('total_gross_wages', 0)
    if gross_wages == 0:
        return {
            'issues': ['Cannot validate - gross wages is zero'],
            'warnings': [],
            'corrections': []
        }
    
    # Get journal lines
    lines = payroll_data.get('journal_entry_lines', [])
    
    # Find key accounts
    account_7006 = sum(l.get('debit_amount', 0) for l in lines if l.get('account_code') == '7006')  # Employer SI
    account_7008 = sum(l.get('debit_amount', 0) for l in lines if l.get('account_code') == '7008')  # Employer GESY
    account_2210 = sum(l.get('credit_amount', 0) for l in lines if l.get('account_code') == '2210')  # All SI+GESY
    
    # Expected calculations
    expected_employer_si = gross_wages * 0.083
    expected_employer_gesy = gross_wages * 0.029
    expected_employee_si = gross_wages * 0.083
    expected_employee_gesy = gross_wages * 0.0265
    
    # Account 2210 should include ALL FOUR portions
    expected_account_2210 = expected_employee_si + expected_employer_si + expected_employee_gesy + expected_employer_gesy
    
    # Validate Employer SI (Account 7006)
    if account_7006 > 0:
        si_diff = abs(account_7006 - expected_employer_si)
        si_percent = (account_7006 / gross_wages * 100) if gross_wages > 0 else 0
        if si_diff > (expected_employer_si * 0.15):  # Allow 15% variance
            warnings.append(
                f"Employer SI (€{account_7006:.2f}, {si_percent:.1f}%) differs from expected "
                f"~8.3% (€{expected_employer_si:.2f}). Variance: €{si_diff:.2f}"
            )
    
    # Validate Employer GESY (Account 7008)
    if account_7008 > 0:
        gesy_diff = abs(account_7008 - expected_employer_gesy)
        gesy_percent = (account_7008 / gross_wages * 100) if gross_wages > 0 else 0
        if gesy_diff > (expected_employer_gesy * 0.15):  # Allow 15% variance
            warnings.append(
                f"Employer GESY (€{account_7008:.2f}, {gesy_percent:.1f}%) differs from expected "
                f"~2.9% (€{expected_employer_gesy:.2f}). Variance: €{gesy_diff:.2f}"
            )
    
    # Validate Account 2210 includes all four portions
    if account_2210 > 0:
        paye_diff = abs(account_2210 - expected_account_2210)
        paye_percent = (account_2210 / gross_wages * 100) if gross_wages > 0 else 0
        
        # Check if Account 2210 is approximately 22% of gross (all four portions combined)
        if paye_percent < 18 or paye_percent > 26:  # Allow reasonable range around 22%
            warnings.append(
                f"Account 2210 (€{account_2210:.2f}, {paye_percent:.1f}%) differs from expected "
                f"~22% (€{expected_account_2210:.2f}). Should include Employee SI + Employer SI + Employee GESY + Employer GESY"
            )
        
        # CRITICAL CHECK: Verify Account 2210 includes employer portions
        total_employer = account_7006 + account_7008
        if total_employer > 0:
            # Account 2210 should be at least as large as employer contributions alone
            if account_2210 < total_employer:
                issues.append(
                    f"CRITICAL: Account 2210 (€{account_2210:.2f}) is less than employer contributions "
                    f"(€{total_employer:.2f}). Account 2210 must include BOTH employee and employer portions."
                )
            
            # Account 2210 should be significantly more than just employer contributions
            # (it should include employee portions too)
            if account_2210 < (total_employer * 1.5):
                warnings.append(
                    f"Account 2210 (€{account_2210:.2f}) seems low relative to employer contributions "
                    f"(€{total_employer:.2f}). Verify it includes employee portions too."
                )
    
    # Check if employer contributions exist but Account 2210 is missing
    total_employer = account_7006 + account_7008
    if total_employer > 0 and account_2210 == 0:
        issues.append(
            f"CRITICAL: Employer contributions exist (€{total_employer:.2f}) but Account 2210 is zero. "
            f"Account 2210 must include all SI and GESY portions."
        )
    
    return {
        'issues': issues,
        'warnings': warnings,
        'validation_passed': len(issues) == 0
    }


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
    
    # Validate debits equal credits
    balance_difference = abs(total_debits - total_credits)
    
    if balance_difference < 0.01:  # Tolerance for rounding
        validation_results["accounting_balanced"] = True
    else:
        validation_results["issues"].append(
            f"Debits ({total_debits:.2f}) do not equal Credits ({total_credits:.2f}). "
            f"Difference: {balance_difference:.2f}"
        )
    
    # Cyprus-specific validations
    cyprus_validation = validate_cyprus_payroll_structure(payroll_data)
    validation_results["issues"].extend(cyprus_validation.get('issues', []))
    validation_results["warnings"].extend(cyprus_validation.get('warnings', []))
    
    # Validate Account 2210 includes employer contributions
    paye_nic_lines = [line for line in journal_lines if line.get("account_code") == "2210"]
    employer_ni_lines = [line for line in journal_lines if line.get("account_code") == "7006"]
    employer_gesy_lines = [line for line in journal_lines if line.get("account_code") == "7008"]
    
    if paye_nic_lines:
        paye_nic_amount = sum(line.get("credit_amount", 0) for line in paye_nic_lines)
        employer_ni_amount = sum(line.get("debit_amount", 0) for line in employer_ni_lines)
        employer_gesy_amount = sum(line.get("debit_amount", 0) for line in employer_gesy_lines)
        total_employer = employer_ni_amount + employer_gesy_amount
        
        # CRITICAL: Account 2210 must include employer contributions
        if total_employer > 0:
            if paye_nic_amount < total_employer:
                validation_results["issues"].append(
                    f"CRITICAL: Account 2210 (€{paye_nic_amount:.2f}) is less than employer contributions "
                    f"(€{total_employer:.2f}). Account 2210 must include Employee SI + Employer SI + Employee GESY + Employer GESY"
                )
            elif paye_nic_amount < (total_employer * 1.5):
                validation_results["warnings"].append(
                    f"Account 2210 (€{paye_nic_amount:.2f}) seems low relative to employer contributions "
                    f"(€{total_employer:.2f}). Verify it includes employee portions too."
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