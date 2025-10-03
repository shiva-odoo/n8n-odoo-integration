"""
Odoo Accounting Logic Module - Streamlined Tiered Approach

This module provides practical tiered accounting rules focused on actually used accounts.
Common functions: 80% usage frequency
Rare functions: 20% usage frequency
Updated VAT rules: Normal companies vs Construction/Property reverse charge
IAS 40 Property Capitalization: Added 0060 account with comprehensive guidance
"""

def bill_common_accounts_logic():
    """
    Returns common account logic for vendor bills (covers 80% of typical bills)
    """
    return """
**COMMON BILL ACCOUNTS (Use First - Covers 80% of Bills):**

**CORE PRINCIPLE:**
- ALWAYS CREDIT: 2100 (Accounts Payable) - What we owe to vendors
- DEBIT: One of these common expense accounts based on bill type

**COMMON EXPENSE ACCOUNTS (80% Usage):**

1. **7602 - Consultancy fees** - Business consulting, advisory services (NOT legal or accounting)
2. **7600 - Legal fees** - Law firm bills, legal services ONLY
3. **7601 - Audit and accountancy fees** - Accountant fees, bookkeeping, tax preparation ONLY
4. **7100 - Rent** - Office/warehouse rent (NOT equipment rental)
5. **7190 - Utilities** - Mixed utility bills, combined services
6. **7200 - Electricity** - Pure electricity bills ONLY
7. **7201 - Gas** - Pure gas bills ONLY (NOT vehicle fuel)
8. **7508 - Computer software** - Software subscriptions, SaaS (NOT hardware or internet)
9. **7503 - Internet** - ISP bills, broadband (NOT software or phones)
10. **7502 - Telephone** - Phone bills, mobile plans (NOT internet)
11. **7400 - Traveling** - Transport tickets, business travel (NOT hotels or meals)
12. **7800 - Repairs and renewals** - Equipment repairs, maintenance (NOT purchases)
13. **5100 - Carriage** - Shipping, freight, courier services (NOT travel)
14. **8200 - Other non-operating income or expenses** - Government fees, misc expenses

**STANDARD BILL JOURNAL ENTRY:**
Dr. [Common Expense Account]    €X,XXX
    Cr. 2100 (Accounts Payable)    €X,XXX
"""

def bill_rare_accounts_logic():
    """
    Returns rare account logic for vendor bills (covers remaining 20%)
    """
    return """
**RARE BILL ACCOUNTS (Use Only When Common Accounts Don't Fit - 20% Usage):**

**PROPERTY DEVELOPMENT & INVESTMENT PROPERTY (IAS 40):**
- 0060 - Freehold property / Property Development in Progress
  Use for capitalizing pre-construction and development costs when directly attributable to property acquisition/development:
  
  CAPITALIZE to 0060 when:
  • Initial acquisition costs (option payments, earnest money, acquisition legal fees)
  • Valuation expenses (professional appraisals, market analysis, valuation reports)
  • Architect fees - pre-construction phase (feasibility studies, conceptual design, planning drawings)
  • Property due diligence (site investigations, geotechnical studies, environmental assessments, archaeological surveys)
  • Surveyor fees (boundary surveys, topographical surveys, land measurement, mechanical/electrical studies for property)
  • Planning permission and building permit application fees
  • Zoning and compliance costs
  • Transfer taxes and stamp duty on property acquisition
  • Engineering studies directly related to property development
  
  DO NOT capitalize to 0060 (expense normally):
  • General market research not specific to a property (→ 7602)
  • Costs before property acquisition becomes probable
  • Routine maintenance of existing structures (→ 7800)
  • Ongoing property management fees (→ 7100)
  • General administrative overhead
  • Speculative costs without specific development plan
  
  INDICATORS for 0060:
  • Vendor is: surveyor, architect, engineer, valuation company, planning consultant
  • Description contains: property address, building project name, land survey, plot number
  • Services are: structural studies, topographical work, architectural design, property valuation

**ASSET PURCHASES:**
- 0080 - Plant and machinery
- 0090 - Office equipment  
- 0100 - Computers (hardware purchases)
- 0110 - Furniture and fixtures
- 0130 - Motor vehicles
- 0040 - Software (when purchased as asset, not subscription)
- 0030 - Licenses (when purchased as asset)

**DETAILED PREMISES:**
- 7102 - Water rates
- 7104 - Premises & liability insurance
- 7700 - Equipment hire

**DETAILED SERVICES:**
- 7603 - Professional fees (other professional services)
- 7506 - Training costs
- 7005 - Recruitment fees

**SALES & MARKETING:**
- 6201 - Advertising
- 6100 - Sales commissions

**INVENTORY (for businesses with stock):**
- 1000 - Stock
- 1020 - Raw materials
- 5000 - Cost of goods
- 6002 - Sub-contractors

**DETAILED TRAVEL:**
- 7402 - Hotels
- 7401 - Car hire
- 7406 - Subsistence & refreshments

**OFFICE & ADMIN:**
- 7500 - Printing
- 7501 - Postage
- 7504 - Office stationery

**VEHICLE (for companies with vehicles):**
- 7300 - Car fuel & oil
- 7301 - Repairs and servicing
- 7303 - Vehicle insurance

**ADVANCED:**
- 1090 - Advance payments (deposits to suppliers)
- 1160 - Prepaid expenses (advance payments for services)
"""

def invoice_common_accounts_logic():
    """
    Returns common account logic for customer invoices (covers 80% of invoices)
    """
    return """
**COMMON INVOICE ACCOUNTS (Use First - Covers 80% of Invoices):**

**CORE PRINCIPLE:**
- ALWAYS DEBIT: 1100 (Accounts Receivable) - What customers owe us
- CREDIT: Revenue account based on service type

**PRIMARY REVENUE ACCOUNTS (80% Usage):**

1. **4000 - Sales** - ALL main business revenue (DEFAULT: use for 80% of invoices)
2. **4900 - Other sales** - Secondary/non-core business services only

**STANDARD INVOICE JOURNAL ENTRY:**
Dr. 1100 (Accounts Receivable)    €X,XXX
    Cr. 4000 (Sales)                €X,XXX

**RULE: Use 4000 (Sales) for ALL invoices unless document clearly states it's secondary/ancillary services**
"""

def invoice_rare_accounts_logic():
    """
    Returns rare account logic for customer invoices (covers remaining 20%)
    """
    return """
**RARE INVOICE ACCOUNTS (Use Only for Specialized Revenue - 20% Usage):**

**PASSIVE INCOME:**
- 4901 - Royalties received (licensing income, IP royalties)
- 4902 - Commissions received (partnership commissions)
- 4904 - Rent income (if subletting space/equipment)

**ASSET SALES:**
- 4200 - Sales of assets (equipment, property sales)

**REIMBURSEMENTS:**
- 4905 - Distribution and carriage (shipping charges to customers)
- 4903 - Insurance claims (insurance reimbursements)

**FINANCIAL:**
- 4906 - Bank interest received (interest income)

**CUSTOMER ADVANCES (Liability, not revenue):**
- 2160 - Deposit received (customer deposits for future work)

**ADJUSTMENTS:**
- 4090 - Discounts allowed (customer discounts - reduces revenue)

**UNUSUAL:**
- 8200 - Other non-operating income or expenses (miscellaneous income)
"""

def share_common_accounts_logic():
    """
    Returns account logic for share capital transactions (standard pattern)
    """
    return """
**SHARE CAPITAL TRANSACTION ACCOUNTS (Standard Pattern):**

**SHARE CAPITAL PATTERN (95% of cases):**
- DEBIT: 1100 (Accounts Receivable) - Amount shareholder owes
- CREDIT: 3000 (Share Capital) - Nominal value × number of shares

**Extract from document:** Number of shares, nominal value per share, shareholder name
**Calculate:** Total amount = shares × nominal value (goes to both accounts)
**Example:** 10,000 shares at €1.50 = €15,000 to both 1100 and 3000

**KEY EXTRACTION:**
- Number of shares + nominal value per share + shareholder name
- Total = shares × nominal value (same amount for both accounts)

**VAT TREATMENT:**
- Share capital transactions are VAT-EXEMPT
- No VAT entries needed

**DESCRIPTION FORMAT:**
"Allotment of [number] shares at €[nominal value] each to [Shareholder Name]"
"""

def share_rare_accounts_logic():
    """
    Returns rare account logic for share transactions (complex scenarios)
    """
    return """
**RARE SHARE TRANSACTION ACCOUNTS (Complex Scenarios Only):**

**SHARE PREMIUM (When shares issued above nominal value):**
- 3100 - Reserves
  - Share premium above nominal value
  - Example: €1 nominal shares issued at €5 = €1 to Share Capital, €4 to Reserves

**COMPLEX JOURNAL ENTRY FOR PREMIUM:**
Dr. 1100 (Accounts Receivable)    €50,000
    Cr. 3000 (Share Capital)          €10,000 [nominal value]
    Cr. 3100 (Reserves)              €40,000 [premium]

**TRANSACTION COSTS (if charged to company):**
- 7600 - Legal fees (legal costs for share issuance)
- 7601 - Audit and accountancy fees (accounting fees for capital changes)

**EMPLOYEE SHARES:**
- 1150 - Employee advances (if shares allocated to employees)

**USAGE:**
- 95% of share transactions only need 1100 + 3000
- Only use premium/reserves when explicitly mentioned
- Only use transaction costs if separately detailed
"""

def get_vat_rules():
    """
    Updated VAT handling rules - Normal companies vs Construction/Property reverse charge
    """
    return """
**VAT HANDLING RULES - Two Different Approaches:**

**VAT ACCOUNTS:**
- 2201 - Output VAT (Sales) - VAT owed to tax authorities
- 2202 - Input VAT (Purchases) - VAT reclaimable from authorities

**COMPANY TYPE DETECTION:**
- **Normal Companies**: Standard VAT treatment
- **Construction/Property Companies**: Reverse charge mechanism

**=== FOR BILLS (Purchases) ===**

**NORMAL COMPANIES (Standard VAT):**
Main transaction uses GROSS amount (net + VAT)
```
Example: €100 net + €19 VAT = €119 total bill
Dr. [Expense Account]           €100
Dr. 2202 (Input VAT)           €19    [Reclaimable]
    Cr. 2100 (Accounts Payable)   €119
```

**CONSTRUCTION/PROPERTY COMPANIES (Reverse Charge):**
Main transaction uses NET amount only
```
Example: €100 net (reverse charge - we handle VAT)
Dr. [Expense Account]           €100
Dr. 2202 (Input VAT)           €19    [Reclaimable]
    Cr. 2201 (Output VAT)          €19    [Owed to authorities]
    Cr. 2100 (Accounts Payable)   €100   [Net only]

Additional entries needed:
{
  "account_code": "2202",
  "account_name": "Input VAT (Purchases)",
  "debit_amount": [vat_amount],
  "credit_amount": 0,
  "description": "Reverse charge Input VAT"
},
{
  "account_code": "2201",
  "account_name": "Output VAT (Sales)", 
  "debit_amount": 0,
  "credit_amount": [vat_amount],
  "description": "Reverse charge Output VAT"
}
```

**=== FOR INVOICES (Sales) ===**

**NORMAL COMPANIES (Standard VAT):**
Main transaction uses GROSS amount (net + VAT)
```
Example: €100 net + €19 VAT = €119 total invoice
Dr. 1100 (Accounts Receivable) €119
    Cr. [Revenue Account]          €100
    Cr. 2201 (Output VAT)         €19    [Owed to authorities]
```

**CONSTRUCTION/PROPERTY COMPANIES (Reverse Charge):**
Main transaction uses NET amount only (customer handles VAT)
```
Example: €100 net (reverse charge - customer handles VAT)
Dr. 1100 (Accounts Receivable) €100   [Net only]
    Cr. [Revenue Account]          €100
No VAT entries needed - customer handles all VAT
```

**CONSTRUCTION/PROPERTY INDICATORS:**
Look for these keywords in documents:
- "Construction services"
- "Building work"
- "Property management" 
- "Real estate services"
- "Reverse charge applicable"
- "Customer to account for VAT"

**PROPERTY DEVELOPMENT VAT (Cyprus-Specific):**
- 19% VAT on professional services (architects, surveyors, valuers) may be recoverable
- Property transfer taxes (3-8% tiered) are capitalized as part of land cost, not VAT
- Construction services may be subject to reverse charge mechanism

**VAT EXEMPTIONS (No VAT entries needed):**
- Share capital transactions
- Bank interest and charges
- Insurance premiums (usually)
- Some government fees

**DEFAULT VAT RATE:** 
Extract from document or use jurisdiction standard (e.g., 19% in Cyprus/Germany)
"""

# Main function
def main(document_type):
    """
    Returns account logic for a document type
    
    Args:
        document_type (str): "bill", "invoice", "share"
    
    Returns:
        str: Combined common + rare account logic with VAT rules
    """
    if document_type.lower() == "bill":
        base_logic = bill_common_accounts_logic() + "\n\n" + bill_rare_accounts_logic()
    elif document_type.lower() == "invoice":
        base_logic = invoice_common_accounts_logic() + "\n\n" + invoice_rare_accounts_logic()  
    elif document_type.lower() == "share":
        base_logic = share_common_accounts_logic() + "\n\n" + share_rare_accounts_logic()
    else:
        return "Invalid document type. Use: bill, invoice, or share"
    
    return base_logic + "\n\n" + get_vat_rules()

# Test the functions
if __name__ == "__main__":
    print("=== BILL ACCOUNTS ===")
    print(main("bill"))
    print("\n" + "="*50 + "\n")
    print("=== INVOICE ACCOUNTS ===")
    print(main("invoice"))
    print("\n" + "="*50 + "\n")
    print("=== SHARE ACCOUNTS ===")
    print(main("share"))