import boto3
import base64
import anthropic
import os
import json
import re
from odoo_accounting_logic import main as get_accounting_logic

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
            print(f"  VAT Registered: {context['is_vat_registered']}")
            print(f"  Industry: {context['primary_industry']}")
            print(f"  Reverse Charge Categories: {context['tax_information']['reverse_charge']}")
            print(f"  Special Circumstances: {list(context['special_circumstances'].keys())}")
            
            return context
        else:
            print(f"⚠️  No company context found for: {company_name}")
            return None
            
    except Exception as e:
        print(f"❌ Error fetching company context: {e}")
        return None

def get_property_capitalization_rules():
    """Returns IAS 40 property capitalization rules for prompt"""
    return """
**IAS 40 PROPERTY CAPITALIZATION RULES (CRITICAL):**

When processing bills, check if expenses should be CAPITALIZED to 0060 (Freehold property) instead of expensed.

**CAPITALIZATION TRIGGERS - Check vendor type AND service description:**

**Vendor Types Requiring Capitalization Analysis:**
- Architects, design firms, architectural consultants
- Surveyors, land surveyors, topographical survey companies
- Valuation firms, appraisers, property valuers, valuation companies
- Engineering consultants (structural, mechanical, electrical studies for property development)
- Environmental consultants, geotechnical firms, soil testing companies
- Planning consultants, town planning advisors, zoning consultants
- Legal firms (when services specifically relate to property acquisition)
- Archaeological survey firms (Cyprus-specific requirement)

**Service Descriptions Requiring Capitalization:**
- "Property valuation", "appraisal fees", "market valuation", "property appraisal"
- "Architect fees", "architectural design", "feasibility study", "conceptual design", "planning drawings"
- "Surveyor fees", "land survey", "topographical survey", "boundary survey", "mechanical study", "electrical study"
- "Site investigation", "geotechnical study", "soil testing", "ground investigation"
- "Environmental assessment", "environmental impact study", "environmental compliance"
- "Planning permission", "building permit application", "zoning application", "planning approval"
- "Property due diligence", "property acquisition legal fees", "conveyancing fees"
- "Archaeological survey", "heritage assessment" (Cyprus-specific)
- Property-specific identifiers: building names, plot numbers, property addresses, project names

**CAPITALIZATION DECISION LOGIC:**

IF (vendor is property-related professional) 
    AND (service relates to specific property development/acquisition)
    AND (description contains property identifiers OR pre-construction keywords)
THEN:
    → account_code = "0060"
    → account_name = "Freehold property"

ELSE IF (same vendor provides routine/operational services):
    → Use normal expense accounts (7600, 7602, 7800, etc.)

**EXAMPLES:**

✅ CAPITALIZE to 0060:
- "Surveyor Fees - Μηχανολογική μελέτη για το έργο ΔΥΟ ΚΑΤΟΙΚΕΣ ΣΤΗΝ ΠΕΓΕΙΑ" → 0060
- "Surveyor Fees - ΜΗΧΑΝΟΛΟΓΙΚΗ ΜΕΛΕΤΗ ΚΟΛΥΜΒΗΤΙΚΗΣ ΔΕΞΑΜΕΝΗΣ" → 0060
- "Valuation Fees - Bank of Cyprus property appraisal" → 0060
- "Architect fees - Feasibility study for Paphos development" → 0060
- "Legal fees - Property acquisition for Plot 123, Peyia" → 0060
- "Topographical survey - Land parcel 456/789" → 0060
- "Geotechnical investigation - Building site Limassol" → 0060
- "Planning permission application - Residential development Paphos" → 0060

❌ DO NOT CAPITALIZE (Expense normally):
- "Legal consultation - general corporate advice" → 7600 (Legal fees)
- "Routine building maintenance and repairs" → 7800 (Repairs and renewals)
- "Property management monthly fees" → 7100 (Rent)
- "General market research - Cyprus real estate trends" → 7602 (Consultancy fees)
- "Architectural consultation - office redesign" → 7602 (Consultancy fees)

**MIXED BILLS WITH PROPERTY ITEMS:**
If a bill contains BOTH capitalizable property costs AND regular expenses:
- Set debit_account = "MIXED"
- Assign each line item to appropriate account (some to 0060, others to expense accounts)
- Example: Architecture firm billing for property design (0060) AND general office consulting (7602)

**KEY PRINCIPLE:**
Ask yourself: "Is this cost directly attributable to acquiring or developing a a specific property asset?"
- YES → 0060 (Freehold property)
- NO → Normal expense account
"""

def detect_construction_property_reverse_charge(vendor_data, line_items):
    """
    Enhanced detection for Cyprus construction/property reverse charge (Article 11B)
    
    Returns:
        tuple: (is_reverse_charge, reason, confidence_level)
    """
    vendor_name = vendor_data.get("name", "").lower()
    vendor_country = vendor_data.get("country_code", "")
    description = vendor_data.get("description", "").lower()
    all_line_descriptions = " ".join([item.get("description", "").lower() for item in line_items])
    
    # Combined text for searching
    all_text = f"{vendor_name} {description} {all_line_descriptions}"
    
    # Explicit reverse charge indicators (Article 11B references)
    explicit_reverse_charge = [
        "άρθρο 11β", "article 11b", "αρθρο 11β",
        "reverse charge", "αντίστροφη επιβάρυνση",
        "δεν χρεωνεται φπα", "δεν χρεώνεται φπα",
        "δεν χρεωνεται ΦΠΑ", "συμφωνα με το αρθρο 11β"
    ]
    
    # Construction/property professional vendor types
    construction_property_vendors = [
        # Direct construction
        "construction", "builder", "contractor", "building", "κατασκευ",
        
        # Architects
        "architect", "architectural", "αρχιτεκτον", "architecture",
        
        # Engineers (all types)
        "engineer", "engineering", "μηχανικ", "mechenergy",
        "civil engineer", "πολιτικός μηχανικός",
        "mechanical engineer", "μηχανολόγος",
        "electrical engineer", "ηλεκτρολόγος",
        
        # Surveyors
        "surveyor", "topographer", "τοπογραφ", "survey",
        
        # Design professionals
        "design studio", "σχεδιαστικό", "design consultant",
        
        # Planning
        "planning consultant", "πολεοδομ", "town planning",
        
        # Property services
        "property management", "real estate", "ακινητ",
        "demolition", "installation", "κατεδαφ"
    ]
    
    # Construction/property-related services
    construction_property_services = [
        # Design & planning
        "architectural design", "preliminary design", "σχεδιασμός",
        "feasibility study", "μελέτη σκοπιμότητας",
        "planning permit", "planning application", "άδεια δόμησης",
        "building permit", "οικοδομική άδεια",
        
        # Engineering services
        "mechanical study", "μηχανολογική μελέτη", "μηχανολογικ",
        "electrical study", "ηλεκτρολογική μελέτη", "ηλεκτρολογικ",
        "structural study", "στατική μελέτη", "στατικ",
        
        # Surveying
        "topographical work", "τοπογραφικές εργασίες", "τοπογραφικ",
        "land survey", "boundary survey", "αποτύπωση",
        
        # Construction work
        "construction services", "building work", "κατασκευαστικ",
        "installation services", "εγκατάσταση",
        "repair services", "επισκευ",
        
        # Property development
        "property development", "building project", "ανάπτυξη ακινητ"
    ]
    
    # Property project identifiers
    property_project_indicators = [
        "houses", "κατοικίες", "κατοικι",
        "residential development", "οικιστικ",
        "plot", "οικόπεδο", "οικοπεδ",
        "property", "ακινητ",
        "building", "κτίριο", "κτιρι",
        "peyia", "pegeia", "πέγεια", "πεγεια",
        "paphos", "pafos", "πάφος", "παφος",
        "limassol", "λεμεσός", "λεμεσος"
    ]
    
    # Level 1: Explicit Article 11B reference (highest confidence)
    if any(keyword in all_text for keyword in explicit_reverse_charge):
        return True, "Explicit Article 11B reference in document", "high"
    
    # Level 2: Vendor type + Service type (high confidence)
    is_construction_vendor = any(keyword in vendor_name for keyword in construction_property_vendors)
    has_construction_service = any(keyword in all_text for keyword in construction_property_services)
    
    if is_construction_vendor and has_construction_service:
        return True, "Construction/property professional providing related services", "high"
    
    # Level 3: Service type + Property project (medium confidence)
    has_property_project = any(keyword in all_text for keyword in property_project_indicators)
    
    if has_construction_service and has_property_project:
        return True, "Construction services for specific property project", "medium"
    
    # Level 4: Vendor type + Property project (medium-low confidence)
    if is_construction_vendor and has_property_project:
        return True, "Construction professional working on property project", "medium"
    
    return False, "", "low"

def get_vat_instructions(company_context):
    """Generate VAT handling instructions based on company registration status"""
    
    if not company_context:
        return """
**VAT TREATMENT (COMPANY CONTEXT UNAVAILABLE):**
- Company VAT status unknown - use conservative approach
- Default to standard VAT treatment with account 2202 (Input VAT)
- Flag for manual review
"""
    
    is_vat_registered = company_context.get('is_vat_registered', 'unknown')
    
    if is_vat_registered == 'yes':
        return """
**VAT TREATMENT FOR THIS COMPANY (VAT REGISTERED):**
✅ Company IS registered for VAT
✅ VAT is RECOVERABLE - use account 2202 (Input VAT)
✅ Standard VAT accounting applies

**For Normal Vendors (No Reverse Charge):**
Debit: [Expense Account] - Net amount
Debit: 2202 (Input VAT) - VAT amount (RECOVERABLE)
Credit: 2100 (Accounts Payable) - Total amount

**Additional Entry:**
{
  "account_code": "2202",
  "account_name": "Input VAT (Purchases)",
  "debit_amount": [vat_amount],
  "credit_amount": 0,
  "description": "Recoverable Input VAT",
  "tax_grid": "+4"
}

**For Reverse Charge Vendors:**
Still create BOTH 2202 (Input VAT) AND 2201 (Output VAT) entries as per reverse charge rules.
"""
    
    elif is_vat_registered == 'no':
        return """
**🔴 CRITICAL VAT TREATMENT FOR THIS COMPANY (NOT VAT REGISTERED):**
❌ Company is NOT registered for VAT
❌ VAT is NON-RECOVERABLE - MUST use account 7906 (Non Recoverable VAT on expenses)
❌ VAT becomes an EXPENSE, not a recoverable asset
❌ NEVER use account 2202 (Input VAT) for this company

**Accounting Entry for Non-VAT Registered Company:**
Debit: [Expense Account] - Net amount
Debit: 7906 (Non Recoverable VAT on expenses) - VAT amount (EXPENSE)
Credit: 2100 (Accounts Payable) - Total amount

**Additional Entry Structure:**
{
  "account_code": "7906",
  "account_name": "Non Recoverable VAT on expenses",
  "debit_amount": [vat_amount],
  "credit_amount": 0,
  "description": "Non-recoverable VAT - company not VAT registered"
}

**IMPORTANT:** - Even for reverse charge vendors, use 7906 instead of 2202
- No Output VAT (2201) entry needed since company cannot recover VAT
- All VAT amounts are expenses for non-VAT registered companies
"""
    
    else:
        return """
**VAT TREATMENT (COMPANY VAT STATUS UNKNOWN):**
⚠️  Company VAT registration status not specified
- Use conservative approach with standard VAT treatment
- Default to account 2202 (Input VAT) 
- Flag for manual verification
"""

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
- Reverse Charge Categories: {', '.join(tax_info.get('reverse_charge', []))}
- Additional Reverse Charge: {tax_info.get('reverse_charge_other', 'N/A')}
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
1. ✅ Validate expense types align with company's industry and business model
2. ✅ Determine if property-related costs should be capitalized (especially if property development/construction industry)
3. ✅ Assign more accurate account codes based on industry-specific services
4. ✅ Flag unusual expenses that don't match business description for review
5. ✅ Apply correct VAT treatment based on registration status
6. ✅ Apply specific reverse charge rules based on company's registered categories
7. ✅ Handle payroll-related documents appropriately based on employee count and frequency
8. ✅ Consider seasonal patterns and special circumstances for expense classification

**INDUSTRY-SPECIFIC GUIDANCE:**
{get_industry_specific_guidance(company_context)}

**REVERSE CHARGE SPECIFIC GUIDANCE:**
{get_reverse_charge_guidance(company_context)}
"""

def get_reverse_charge_guidance(company_context):
    """Provide specific reverse charge guidance based on company's registered categories"""
    
    tax_info = company_context.get('tax_information', {})
    reverse_charge_categories = tax_info.get('reverse_charge', [])
    
    if not reverse_charge_categories:
        return "- No specific reverse charge categories registered"
    
    guidance = "- Company is registered for reverse charge on: " + ", ".join(reverse_charge_categories)
    
    # Add specific guidance based on categories
    if 'construction' in reverse_charge_categories:
        guidance += "\n- CONSTRUCTION: Pay special attention to construction/property services (Article 11B)"
    
    if 'other' in reverse_charge_categories:
        other_desc = tax_info.get('reverse_charge_other', '')
        if other_desc:
            guidance += f"\n- OTHER: {other_desc}"
    
    return guidance

def get_industry_specific_guidance(company_context):
    """Provide industry-specific account assignment guidance"""
    
    industry = company_context.get('primary_industry', '').lower()
    business_desc = company_context.get('business_description', '').lower()
    special_circumstances = company_context.get('special_circumstances', {})
    business_ops = company_context.get('business_operations', {})
    inventory_management = business_ops.get('inventory_management', '').lower()
    
    # Property/Real Estate/Construction industries
    if any(keyword in industry or keyword in business_desc for keyword in 
           ['property', 'real estate', 'construction', 'development', 'rental']):
        guidance = """
- Property-related professional fees (architects, surveyors, engineers) → Likely 0060 (Freehold property) if for development
- Property management fees → 7100 (Rent) or specific property management account
- Rental property repairs → Check if capitalizable (major improvements) or expense (routine maintenance)
- Legal fees → Check if for property acquisition (0060) or general operations (7600)"""
        
        # Check inventory management approach
        if inventory_management in ['no', 'none', 'project-based', 'on-demand', 'just-in-time', '']:
            guidance += """
- **MATERIALS & SUPPLIES:** Use 5001 (Purchases) for all materials, supplies, and goods purchased on demand for projects
- Company does NOT maintain inventory - purchases are expensed immediately as 5001 (Purchases)
- Items like construction materials, hardware, supplies, tools, consumables → 5001 (Purchases)
- Building materials (cement, steel, timber, etc.) → 5001 (Purchases)
- Hardware and fixtures purchased for projects → 5001 (Purchases)"""
        elif inventory_management in ['yes', 'perpetual', 'periodic']:
            guidance += """
- **MATERIALS & SUPPLIES:** Use 1000 (Stock) or 1020 (Raw materials) for inventory items
- Company maintains inventory - purchases are capitalized to inventory accounts
- Items held in warehouse for future use → 1000 (Stock) or 1020 (Raw materials)"""
        
        # Add construction-specific guidance if active project
        if 'construction' in special_circumstances:
            guidance += "\n- ACTIVE CONSTRUCTION PROJECT: High likelihood of capitalizable costs to 0060"
        
        return guidance
    
    # Investment/Portfolio Management
    elif any(keyword in industry for keyword in ['investment', 'portfolio', 'fund', 'holding']):
        return """
- Portfolio management fees → 7605 (Portfolio management fees)
- Investment advisory → 7602 (Consultancy fees) or 7605
- Fund administration → 7603 (Professional fees)
- Holding company costs → Generally operational expenses unless property-related
"""
    
    # Tech/Software companies
    elif any(keyword in industry for keyword in ['technology', 'software', 'it', 'saas']):
        return """
- Software subscriptions → 7508 (Computer software)
- IT consulting → 7602 (Consultancy fees)
- Cloud services → 7508 (Computer software)
- Development tools → 7508 or capitalize if significant asset
"""
    
    # Manufacturing/Production companies with inventory
    elif any(keyword in industry for keyword in ['manufacturing', 'production', 'factory']):
        if inventory_management in ['yes', 'perpetual', 'periodic']:
            return """
- Raw materials purchases → 1020 (Raw materials)
- Finished goods → 1000 (Stock)
- Production supplies → 1020 (Raw materials)
- Manufacturing overhead → Appropriate expense accounts
"""
        else:
            return """
- Materials and supplies → 5001 (Purchases)
- Production costs → 5001 (Purchases)
- Manufacturing supplies → 5001 (Purchases)
"""
    
    # Retail/Wholesale companies
    elif any(keyword in industry for keyword in ['retail', 'wholesale', 'trading', 'merchant']):
        if inventory_management in ['yes', 'perpetual', 'periodic']:
            return """
- Goods for resale → 1000 (Stock)
- Inventory purchases → 1000 (Stock)
- Cost of goods sold → 5000 (Cost of goods)
"""
        else:
            return """
- Goods for resale → 5001 (Purchases)
- Trading stock → 5001 (Purchases)
"""
    
    else:
        # Generic guidance based on inventory management
        if inventory_management in ['no', 'none', 'project-based', 'on-demand', 'just-in-time', '']:
            return """
- Materials and supplies → 5001 (Purchases) (company does not maintain inventory)
- Goods purchased on demand → 5001 (Purchases)
- Match other expenses to industry-standard account codes
- Flag expenses that seem unusual for this industry
"""
        elif inventory_management in ['yes', 'perpetual', 'periodic']:
            return """
- Inventory items → 1000 (Stock) or 1020 (Raw materials)
- Goods for resale → 1000 (Stock)
- Match other expenses to industry-standard account codes
- Flag expenses that seem unusual for this industry
"""
        else:
            return """
- Match expenses to industry-standard account codes
- Flag expenses that seem unusual for this industry
"""

def get_date_extraction_rules():
    """Returns comprehensive date extraction rules for prompt"""
    return """
**CRITICAL DATE EXTRACTION RULES:**

You MUST extract dates with extreme precision. Dates are CRITICAL for accounting compliance and must be 100% accurate.

**DATE EXTRACTION PRIORITY (CHECK IN THIS ORDER):**

1. **PRIMARY DATE FIELDS - ALWAYS CHECK THESE FIRST:**
   - Look for explicit labels: "ΗΜΕΡΟΜΗΝΙΑ" (Ημερομηνία), "ΗΜΕΡ:" (Ημερ:), "Ημερ.", "Date:", "Invoice Date:", "ΤΙΜΟΛΟΓΙΟΥ" (after ΗΜΕΡΟΜΗΝΙΑ)
   - Look for "Ημερομηνία:" followed by date
   - Check document header area (top 30% of page)
   - Greek format: DD/MM/YYYY or DD.MM.YYYY or DD-MM-YYYY
   - English format: MM/DD/YYYY or YYYY-MM-DD

2. **DATE FORMAT VALIDATION:**
   - Greek documents typically use: DD/MM/YYYY (e.g., 15/04/25 means April 15, 2025)
   - Must have day, month, and year components
   - Year can be 2-digit (25 = 2025) or 4-digit (2025)
   - Valid day range: 01-31
   - Valid month range: 01-12

3. **CONTEXT CLUES FOR DATE IDENTIFICATION:**
   - Date usually appears near: invoice number, vendor name, or "ΤΙΜΟΛΟΓΙΟ/INVOICE" header
   - In Greek documents, look for: "Ημερομηνία:", "Ημερ:", "εκ:" (abbreviation for εκδοτική ημερομηνία)
   - Dates are often in the top-right or top-left corner
   - May appear after invoice number with format like "ΑΡ ΤΙΜΟΛΟΓΙΟΥ: [number] [date]"

4. **MULTIPLE DATE HANDLING:**
   - If multiple dates present, prioritize:
     a. Date explicitly labeled as "invoice date" or "ΗΜΕΡΟΜΗΝΙΑ ΤΙΜΟΛΟΓΙΟΥ"
     b. Date near invoice number
     c. Earliest date in document header
   - NEVER use: receipt date, payment date, or due date as invoice_date
   - Due date goes in separate "due_date" field

5. **DATE CONVERSION TO ISO FORMAT:**
   - ALWAYS convert to ISO 8601 format: "YYYY-MM-DD"
   - Examples:
     * "15/04/25" → "2025-04-15"
     * "21/03/2025" → "2025-03-25"
     * "24.02.25" → "2025-02-24"
   - Assume 2-digit years 00-50 are 2000s (e.g., 25 = 2025)
   - Assume 2-digit years 51-99 are 1900s (e.g., 99 = 1999)

6. **DATE EXTRACTION EXAMPLES FROM YOUR DOCUMENTS:**

**Example 1 - Greek Invoice Header:**
```
ΤΙΜΟΛΟΓΙΟ - INVOICE
Όνομα: Ballian TechniKi LTD
Ημερ: 15|04|25   εκ: Gr2MH
```
CORRECT: "invoice_date": "2025-04-15"
WRONG: "invoice_date": "2025-01-04" (this would be mixing up day/month)

**Example 2 - Date After Invoice Number:**
```
ΑΡ ΤΙΜΟΛΟΓΙΟΥ: ΑΛΠ000356393
ΗΜΕΡΟΜΗΝΙΑ: 13/5/2025
ΑΡ ΣΕΛΙΔΑΣ: 1
```
CORRECT: "invoice_date": "2025-05-13"

**Example 3 - Greek Date Format:**
```
Ημερομηνία: 24/02/25
```
CORRECT: "invoice_date": "2025-02-24"

7. **DATE VALIDATION CHECKLIST - BEFORE FINALIZING:**
   ☐ Is the date in DD/MM/YYYY format for Greek documents?
   ☐ Does the date make logical sense? (not in future, not too old)
   ☐ Is it the invoice date (not receipt date, payment date, or due date)?
   ☐ Is the date converted to ISO format "YYYY-MM-DD"?
   ☐ Is the day value 01-31?
   ☐ Is the month value 01-12?
   ☐ Does the year make sense for a current invoice? (2024-2025 range expected)

8. **COMMON DATE EXTRACTION ERRORS TO AVOID:**
   ❌ Swapping day and month (15/04 is April 15th, NOT April 15th in MM/DD format)
   ❌ Using page numbers as dates
   ❌ Using reference numbers as dates
   ❌ Using receipt dates instead of invoice dates
   ❌ Extracting dates from footer timestamps
   ❌ Confusing Greek abbreviations (εκ: is "issued", Ημερ: is "date")

9. **CONFIDENCE SCORING FOR DATES:**
   - Set extraction_confidence.dates = "high" ONLY if:
     * Date has explicit label ("ΗΜΕΡΟΜΗΝΙΑ", "Date:", "Ημερ:")
     * Date format is clear and unambiguous
     * Date appears in standard location (header area)
   - Set extraction_confidence.dates = "medium" if:
     * Date inferred from context
     * Multiple dates present but primary is identifiable
   - Set extraction_confidence.dates = "low" if:
     * Date format ambiguous
     * Multiple dates with unclear purpose
     * No explicit date label

10. **SPECIAL HANDLING FOR HANDWRITTEN DATES:**
    - Handwritten dates may be less clear - double-check digit recognition
    - Look for slashes "/" or dots "." separating date components
    - Cross-reference with printed dates elsewhere in document

**ABSOLUTE REQUIREMENT:**
Every invoice MUST have an invoice_date. If you cannot find one with confidence, set extraction_confidence.dates to "low" and flag it in missing_fields, but still attempt to extract the most likely date from the document header area.
"""

def get_mathematical_validation_rules():
    """Returns comprehensive mathematical validation and cross-checking rules"""
    return """
**CRITICAL: MATHEMATICAL VALIDATION & CROSS-CHECKING**

Before finalizing your response, you MUST perform these validation checks:

**STEP 1: IDENTIFY THE TOTALS BLOCK**
- Look for "Total", "Net Value", "Gross Value", "VAT", "Amount" at the bottom of the invoice
- These are your ground truth - all calculations must match these exactly
- Common locations: Bottom of page, summary box, footer area
- Labels may be in English or Greek: "ΣΥΝΟΛΟ", "ΦΠΑ", "ΚΑΘΑΡΗ ΑΞΙΑ"

**STEP 2: REVERSE-ENGINEER FROM TOTALS**
If the document shows:
- Net Value: 677.31
- VAT: 128.69  
- Total: 806.00

Then verify:
✓ Net + VAT = Total (677.31 + 128.69 = 806.00)
✓ Sum of all line items (Amount column) = Net Value (677.31)
✓ VAT calculation is correct (677.31 × 0.19 = 128.69)

**STEP 3: HANDLE AMBIGUOUS COLUMN HEADERS**

Some invoices have reversed or unclear column naming. You MUST cross-check with totals to determine which column represents NET vs GROSS values.

**Common Column Patterns:**
- **Pattern A (Standard):** Price (net) × Qty = Amount (net subtotal)
  Example: Price=56.00, Qty=1, Amount=56.00, then VAT added
  
- **Pattern B (Reversed):** Amount (net) × (1 + VAT%) = Price (gross)
  Example: Amount=47.06 (net), VAT 19%, Price=56.00 (gross)
  
- **Pattern C (Mixed):** Price (gross) ÷ (1 + VAT%) = Amount (net)
  Example: Price=56.00 (gross), Amount=47.06 (net)

**DETECTION METHOD:**
1. Pick first line item
2. Try calculation: Price × Qty = Amount?
   - If YES → Standard Pattern A (Price is NET)
   - If NO → Continue to step 3
3. Try calculation: Amount × (1 + VAT%) = Price?
   - If YES → Reversed Pattern B (Amount is NET, Price is GROSS)
   - If NO → Continue to step 4
4. Try calculation: Price ÷ (1 + VAT%) = Amount?
   - If YES → Pattern C (Price is GROSS, Amount is NET)
5. Cross-check with totals block:
   - Sum all "Amount" values - does it equal "Net Value"?
   - Sum all "Price" values - does it equal "Gross Value" or "Total"?

**CRITICAL: Always verify your interpretation against the totals block**

**STEP 4: VALIDATE EACH LINE ITEM**

For each line, after determining column meanings:

**If Price is NET (Pattern A):**
- price_unit = Price value
- line_total = price_unit × quantity (should equal Amount column if present)
- Calculate expected VAT: line_total × tax_rate
- Verify gross total: line_total + VAT = expected gross

**If Amount is NET (Patterns B or C):**
- line_total = Amount value (this is the NET, taxable base)
- price_unit = line_total ÷ quantity
- Calculate expected VAT: line_total × tax_rate
- Verify Price column = line_total + VAT (should match)

**Validation Checklist per Line:**
☐ price_unit × quantity = line_total (within 0.01 tolerance)
☐ line_total × tax_rate = calculated VAT amount
☐ All values are positive (unless credit note)
☐ Quantity makes sense (usually whole numbers or decimals < 1000)

**STEP 5: FINAL RECONCILIATION**

Before responding, verify:
☐ Sum of all line_totals = subtotal (within 0.02 tolerance for rounding)
☐ subtotal + tax_amount = total_amount (exact match or within 0.02)
☐ Each line item math is internally consistent
☐ All amounts match the totals block at bottom of invoice
☐ VAT calculation uses correct rate (19%, 9%, 5%, etc.)
☐ No impossible values (negative amounts, zero quantities with amounts, etc.)

**STEP 6: HANDLE DISCREPANCIES**

**IF MATH DOESN'T ADD UP:**
- Set extraction_confidence for "total_amount" to "low"
- Set extraction_confidence for "line_items" to "low"  
- Add to missing_fields: "Mathematical discrepancy: [explain what doesn't match]"
- Include detailed explanation in detection_details
- Still provide best-effort extraction but flag the issue clearly
- Note which interpretation you used (Pattern A, B, or C)

**IF DOCUMENT IS HANDWRITTEN:**
- Set column_interpretation to "handwritten" or "handwritten_simple"
- Set extraction_confidence for amounts to "low" or "medium" maximum
- Set extraction_confidence.vendor_name to "low" if vendor name is handwritten
- Add to discrepancies: "Handwritten amounts - manual verification recommended"
- Don't claim "totals_match: true" unless there's a printed totals block to verify against
- Note: Handwritten invoices cannot be fully validated without printed reference

**IF MULTIPLE INTERPRETATIONS POSSIBLE:**
- Choose the interpretation where totals match exactly
- If both match, prefer Pattern A (standard) unless Pattern B/C has exact match
- Document your choice in detection_details

**EXAMPLE WALKTHROUGH (Rovertos Nicolaou Invoice):**

Document shows:
- Line 1: Qty=1, Price=56.00, Amount=47.06, VAT=19%
- Net Value: 677.31
- VAT: 128.69
- Total: 806.00

**Analysis:**
1. Try Pattern A: 56.00 × 1 = 56.00 ≠ 47.06 ❌
2. Try Pattern B: 47.06 × 1.19 = 56.00 ✓
3. Verify: Amount column (47.06) is NET
4. Sum all Amount values = 677.31 = Net Value ✓
5. Calculate VAT: 677.31 × 0.19 = 128.69 ✓
6. Total: 677.31 + 128.69 = 806.00 ✓

**Conclusion:** Pattern B (Reversed) - Amount is NET, Price is GROSS

**Correct Extraction:**
- price_unit: 47.06 (NOT 56.00)
- line_total: 47.06
- subtotal: 677.31
- tax_amount: 128.69
- total_amount: 806.00

**COLUMN INTERPRETATION INDICATORS:**

Look for these clues to help identify column meanings:

**NET Column Indicators:**
- Column labeled: "Net", "Net Amount", "Taxable Amount", "Base", "ΚΑΘΑΡΗ ΑΞΙΑ"
- Sum matches "Net Value" or "Subtotal" in totals
- Smaller number when comparing Price vs Amount

**GROSS Column Indicators:**
- Column labeled: "Total", "Gross", "With VAT", "ΣΥΝΟΛΟ ΜΕ ΦΠΑ"
- Sum matches "Total" or "Grand Total" in totals
- Larger number when comparing Price vs Amount

**Unit Price Indicators:**
- Column labeled: "Price", "Unit Price", "Rate", "ΤΙΜΗ", "Price/Unit"
- Makes sense when multiplied by quantity
- Relatively small numbers (per-unit pricing)

**CONFIDENCE SCORING:**

Set extraction_confidence.total_amount based on validation:
- "high": All calculations match exactly, clear column structure
- "medium": Calculations match with minor rounding differences (<0.05)
- "low": Discrepancies found, ambiguous structure, or assumptions made

**ABSOLUTE REQUIREMENT:**
Every invoice with line items and a totals block MUST have its mathematics validated. If calculations don't match, you MUST flag this with low confidence and explain the discrepancy.
"""
def get_bill_processing_prompt(company_name, company_context=None):
    """Create comprehensive bill processing prompt that combines splitting and extraction"""
    
    # Get bill accounting logic with VAT rules
    bill_logic = get_accounting_logic("bill")
    
    # Get VAT instructions based on company context
    vat_instructions = get_vat_instructions(company_context)
    
    # Get company context section
    company_context_section = get_company_context_section(company_context)

    date_extraction_rules = get_date_extraction_rules()
    
    # NEW: Get mathematical validation rules
    math_validation_rules = get_mathematical_validation_rules()
    
    return f"""You are an advanced bill processing AI. Your task is to analyze a multi-bill PDF document and return structured JSON data.

**CRITICAL INSTRUCTION: Respond with ONLY the JSON object. Do not include any explanatory text, commentary, analysis, or markdown formatting before or after the JSON. Start your response immediately with the opening curly brace {{.**

**INPUT:** Multi-bill PDF document
**COMPANY:** {company_name} (the company receiving these bills)
**OUTPUT:** Raw JSON object only

{company_context_section}

**DOCUMENT SPLITTING RULES (Priority Order):**
1. **PAGE INDICATOR RULE (HIGHEST PRIORITY):**
   - "Page 1 of 1" multiple times = Multiple separate single-page bills
   - "Page 1 of 2", "Page 2 of 2" = One two-page bill
   - "Page 1 of 3", "Page 2 of 3", "Page 3 of 3" = One three-page bill

2. **INVOICE NUMBER RULE (SECOND PRIORITY):**
   - Different invoice numbers = Different bills
   - Same invoice number across pages = Same bill

3. **HEADER COUNT RULE (THIRD PRIORITY):**
   - Multiple "INVOICE" headers typically = Multiple bills

**DATA EXTRACTION FOR EACH BILL:**

**DOCUMENT TYPE:** Always set as "vendor_bill" since {company_name} is receiving these bills.

**COMPANY VALIDATION:**
- Identify ALL company names in the PDF
- Check if any match "{company_name}" (case-insensitive, fuzzy matching)
- Set company_match: "exact_match", "close_match", "no_match", or "unclear"

**MANDATORY FIELDS:**
- Vendor name (Essential)
- Bill Date (Required)
- Due Date or Payment Terms
- Bill Reference (Invoice number)
- Currency and Amounts
- Description (Overall description of the document including details about line items)
- Line Items with calculations AND individual account assignments
- Credit Account (Account to be credited based on bill type)
- Debit Account (Account to be debited based on bill type)

{date_extraction_rules}

**CRITICAL: CAREFUL TEXT READING**

Before extracting vendor names:
1. Look for printed company stamps or letterheads FIRST (more accurate than handwriting)
2. If vendor business type is mentioned (e.g., "Laboratory", "Construction", "Architect"), verify it matches the extracted name
3. Check if vendor makes sense for {company_name}'s industry: {company_context.get('primary_industry', 'N/A') if company_context else 'N/A'}
4. For handwritten text, set confidence to "low" and note in detection_details

Example validation: If document says "Laboratory Testing Services" but you read name as "Cinema Company" → OCR ERROR, re-examine the text more carefully.

{math_validation_rules}

**ACCOUNTING ASSIGNMENT RULES:**

{bill_logic}

**ODOO TAX NAME ASSIGNMENT RULES (CRITICAL & REFINED):**

For EACH line item, you must populate the `tax_name` field. This requires careful, line-by-line analysis.

**Decision Logic (IN ORDER OF PRIORITY):**
1.  **CHECK FOR EXEMPT ITEMS FIRST (HIGHEST PRIORITY):**
    - Analyze the individual line item description. Does it represent a disbursement or a fee that is outside the scope of VAT?
    - Keywords: "submission fees", "government fees", "planning authority fees", "application fees".
    - **If a line is exempt, assign `0% E`. This rule OVERRIDES all other rules for this specific line item, even if the rest of the bill is reverse charge.**

2.  **IF NOT EXEMPT, CHECK FOR REVERSE CHARGE:**
    - If the overall bill (`requires_reverse_charge`) is a reverse charge transaction, and the line item is NOT exempt, then assign `19% RC`.

3.  **IF NOT EXEMPT OR RC, APPLY STANDARD LOGIC:**
    - **Determine Vendor Location:** Use `vendor_data.country_code`.
        - Domestic (Cyprus - 'CY'): Standard Cyprus VAT rules.
        - EU Vendor (e.g., 'GR', 'DE'): EU acquisition taxes.
        - Outside EU (e.g., 'GB', 'US'): Outside EU import taxes.
    - **Determine Goods vs. Services:** Analyze the line description. Append ' S' for services.
    - **Combine:** Construct the `tax_name` using `[Rate]%[Suffix]`.

**Available Tax Categories:**
- **Standard Domestic:** `19%` (Goods), `19% S` (Services)
- **Reduced Domestic:** `9%`/`9% S`, `5%`/`5% S`, `3%`/`3% S`
- **Zero-Rated:** `0%`
- **Reverse Charge:** `19% RC`
- **Exempt:** `0% E`
- **EU Acquisitions:** `19% EU` (Goods), `19% EU S` (Services)
- **Outside EU Imports:** `19% OEU` (Services), `0% OEU` (Goods)

**TAX GRID ASSIGNMENT RULES (CRITICAL & CUSTOM):**

**For VAT Entries:**
- Input VAT (2202) for recoverable VAT → tax_grid: "+4"
- Output VAT (2201) for reverse charge → tax_grid: "-1"
- Non Recoverable VAT (7906) → No tax grid (expense account)

**For Purchase Value Entries on Line Items (ULTIMATE CUSTOM RULE):**
This is your most important rule for the line item tax grid. It is a specific business requirement that you must follow precisely to mean 'Total inputs excluding VAT'.
- **Domestic Purchases Rule (Tax Grid `+7`):** If the vendor's `country_code` is `CY`, you **MUST** assign `tax_grid: "+7"` to **ALL** line items on that bill. This rule applies to all domestic purchases, regardless of their `tax_name` (e.g., `19% RC`, `0% E`, `19% S`, etc.). The goal is to capture the total value of all domestic inputs in this grid.
- **EU Acquisitions (Tax Grid `+8`):** If the purchase is an acquisition of goods/services from another EU country (e.g., country code 'DE', 'GR', 'IT'), use `tax_grid: "+8"`.
- **Other International Purchases:** For purchases from outside the EU (e.g., 'GB', 'US'), the `tax_grid` should be left empty `""`.

**For Sales Value Entries (if applicable):**
- Standard rate sales (19%) → tax_grid: "+5"
- Reduced rate sales (9%, 5%) → tax_grid: "+6"

**LINE-LEVEL ACCOUNT ASSIGNMENT:**
Each line item must be assigned to the most appropriate expense account based on the service/product type:

**Service Type → Account Code Mapping:**
- Legal services, law firm fees → 7600 (Legal fees)
- Accounting, bookkeeping, tax services → 7601 (Audit and accountancy fees)  
- Business consulting, advisory → 7602 (Consultancy fees)
- Portfolio/investment management → 7605 (Portfolio management fees)
- Other professional services → 7603 (Professional fees)
- General property rent → 7100 (Rent)
- Office space, coworking, serviced offices → 7101 (Office space)
- Mixed utility bills → 7190 (Utilities)
- Pure electricity bills → 7200 (Electricity)
- Pure gas bills → 7201 (Gas)
- Water bills → 7102 (Water rates)
- Software subscriptions, SaaS → 7508 (Computer software)
- Internet, broadband, ISP → 7503 (Internet)
- Phone, mobile, telecom → 7502 (Telephone)
- Business travel, flights, transport → 7400 (Traveling)
- Equipment repairs, maintenance → 7800 (Repairs and renewals)
- Shipping, freight, courier → 5100 (Carriage)
- Government fees, permits → 8200 (Other non-operating income or expenses)

**Materials & Goods (CRITICAL - Check Company Inventory Management):**
- IF company does NOT maintain inventory (inventory_management: 'no', 'none', 'project-based', 'on-demand'):
  → Use 5001 (Purchases) for ALL materials, supplies, goods, hardware, equipment purchases
  → Examples: Construction materials, tools, supplies, hardware, consumables → 5001 (Purchases)
- IF company maintains inventory (inventory_management: 'yes', 'perpetual', 'periodic'):
  → Use 1000 (Stock) or 1020 (Raw materials) for inventory items
  → Use 5000 (Cost of goods) when selling inventory items

**Equipment & Capital Items:**
- Office equipment purchases → 0090 (Office equipment) if capitalizable asset
- Computer hardware → 0100 (Computers) if capitalizable asset
- Shipping, freight, courier → 5100 (Carriage)
- Government fees, permits → 8200 (Other non-operating income or expenses)


**CRITICAL: PROPERTY CAPITALIZATION OVERRIDE:**
{get_property_capitalization_rules()}

**CRITICAL VAT CALCULATION FOR ADDITIONAL ENTRIES:**
When creating `additional_entries` for VAT (Input or Output):
1.  **IDENTIFY THE TAXABLE BASE:** Sum the `line_total` of ONLY the line items that are subject to VAT (e.g., those with `tax_name: "19% RC"`).
2.  **EXCLUDE NON-TAXABLE LINES:** You MUST exclude the amounts of any line items marked as exempt (`0% E`) or zero-rated (`0%`) from this sum.
3.  **CALCULATE VAT:** Apply the VAT percentage (e.g., 19%) to this taxable base ONLY.
4.  **EXAMPLE:** If a bill has lines for €2975 (taxable at 19% RC) and €60 (exempt `0% E`), the reverse charge VAT amount is `2975 * 0.19 = 565.25`. It is NOT 19% of the total €3035.

**CRITICAL LINE ITEM ANALYSIS:**
- Analyze EACH line item individually for service type
- Same vendor can provide multiple service types
- Example: Telecom company billing for both "Internet service" (7503) AND "Mobile WiFi" (7502)
- Example: Office supplier selling "Stationery" (7504) AND "Computer equipment" (0090)
- Example: Engineering firm providing "Property mechanical study" (0060) AND "General consulting" (7602)
- Assign the most specific account code for each line item

**CYPRUS VAT REVERSE CHARGE DETECTION (COMPREHENSIVE & ENHANCED):**

The reverse charge mechanism applies when the vendor/supplier falls into ANY of the following categories:

**CATEGORY 1: CONSTRUCTION & PROPERTY SERVICES (ENHANCED)**
Look for these indicators:

**Vendor Types:**
- Construction companies: "Construction", "Building", "Contractor", "Builder"
- Architects: "Architect", "Architecture", "Architectural", "Design Studio" (when doing property work)
- Engineers: "Engineer", "Engineering", "Mechanical Engineer", "Electrical Engineer", "Civil Engineer", "MechEnergy"
- Surveyors: "Surveyor", "Topographer", "Survey", "Topographical", "Τοπογραφ", "ΤΟΠΟΓΡΑΦΟΙ ΜΗΧΑΝΙΚΟΙ"
- Design professionals: "Design Studio", "Planning Consultant"
- Property services: "Property Management", "Real Estate"

**Services (English & Greek):**
- Architectural: "architectural design", "preliminary design", "feasibility study", "σχεδιασμός"
- Engineering studies: "mechanical study", "μηχανολογική μελέτη", "electrical study", "ηλεκτρολογική μελέτη", "structural study"
- Surveying: "topographical work", "τοπογραφικές εργασίες", "land survey", "boundary survey"
- Planning: "planning permit", "planning application", "άδεια δόμησης", "building permit"
- Construction: "construction services", "building work", "installation services", "repair services"

**Explicit Indicators:**
- Document mentions: "Reverse charge applicable", "Article 11B", "άρθρο 11Β", "δεν χρεωνεται ΦΠΑ", "συμφωνα με το αρθρο 11Β"

**Project Identifiers:**
- Property names: "PEYIA HOUSES", "ΔΥΟ ΚΑΤΟΙΚΕΣ ΣΤΗΝ ΠΕΓΕΙΑ", "2 houses in Pegeia"
- Location references: building addresses, plot numbers, property projects

**CATEGORY 2: FOREIGN/EU SERVICE PROVIDERS**
Look for these indicators:
- Vendor located outside Cyprus (check address, VAT number format, country code != CY)
- EU VAT number format (non-Cyprus)
- Services provided from abroad: Legal, Accounting, Consulting, IT services, Marketing, Design, Professional services, Advisory services, Royalties, License fees
- Cross-border B2B services under general reverse charge rule

**CATEGORY 3: GAS & ELECTRICITY SUPPLIERS**
Look for these indicators:
- Pure gas supply to registered business
- Pure electricity supply to registered traders/merchants
- Utility companies selling gas/electricity (not mixed utility bills to consumers)
- Vendor name contains: "Energy", "Power", "Gas Company", "Electricity Authority"

**CATEGORY 4: SCRAP METAL & WASTE DEALERS**
Look for these indicators:
- Scrap metal supplies
- Waste materials supplies
- Vendor name contains: "Scrap", "Recycling", "Waste Management", "Metal Recycling"
- Products: Scrap iron, aluminum, copper, steel, waste materials

**CATEGORY 5: ELECTRONICS SUPPLIERS (HIGH-RISK GOODS)**
Look for these indicators:
- Mobile phones (smartphones, cell phones)
- Tablets and PC tablets
- Laptops and computers
- Microprocessors and CPUs
- Integrated circuits and chips
- Gaming consoles (PlayStation, Xbox, Nintendo)
- Other devices operating in networks
- Vendor selling electronics in bulk/wholesale

**CATEGORY 6: PRECIOUS METALS DEALERS**
Look for these indicators:
- Raw or semi-finished precious metals
- Gold, silver, platinum supplies
- Bullion dealers
- Vendor name contains: "Precious Metals", "Gold", "Silver", "Bullion"
- Products: Gold bars, silver ingots, precious metal materials

**CATEGORY 7: TELECOMMUNICATIONS SERVICES (EU)**
Look for these indicators:
- EU-based telecom service providers
- International telecommunications services
- Services from EU suppliers for Cyprus use
- Vendor name contains international telecom indicators

**CATEGORY 8: IMMOVABLE PROPERTY TRANSFERS**
Look for these indicators:
- Property transfers related to debt restructuring
- Foreclosure sales
- Debt-for-asset swaps
- Forced property transfers
- Bank repossessions

{vat_instructions}

**VAT TREATMENT LOGIC:**

**NORMAL VENDORS (NO REVERSE CHARGE) - VAT Treatment depends on company registration:**
{'''- IF Company is VAT Registered: Use 2202 (Input VAT - Recoverable)
- IF Company is NOT VAT Registered: Use 7906 (Non Recoverable VAT on expenses)''' if not company_context or company_context.get('is_vat_registered') != 'no' else '- Company NOT VAT Registered: MUST use 7906 (Non Recoverable VAT on expenses)'}

**REVERSE CHARGE VENDORS (ALL 8 CATEGORIES ABOVE) - VAT Treatment depends on company registration:**
{'''- IF Company is VAT Registered: Create BOTH Input VAT (2202) AND Output VAT (2201) entries
- IF Company is NOT VAT Registered: Use 7906 (Non Recoverable VAT) instead of 2202, NO Output VAT entry''' if not company_context or company_context.get('is_vat_registered') != 'no' else '- Company NOT VAT Registered: Use 7906 (Non Recoverable VAT) only, NO Output VAT (2201) entry'}

**MIXED LINE ITEMS HANDLING:**
When line items map to different expense accounts:
- Set debit_account to "MIXED"
- Set debit_account_name to "Mixed Line Items"
- Each line item contains its own account_code and account_name
- VAT handling remains the same (vendor-level decision)

**DESCRIPTION FIELD:**
- Create an overall description of the document that summarizes the goods/services provided
- Include key details from line item descriptions
- Can be a shortened combination of the description fields from each line item
- Should give a clear understanding of what the bill is for

**CALCULATION REQUIREMENTS:**
- ALWAYS perform mathematical validation first (see MATHEMATICAL VALIDATION section above)
- Determine if columns are NET or GROSS before extracting
- line_total = NET amount (taxable base) for each line
- price_unit = line_total ÷ quantity
- subtotal = sum of all line_totals before tax
- total_amount = subtotal + tax_amount
- If calculations don't match, flag with low confidence

**STRICT FORMATTING RULES:**
- Text fields: Use empty string "" if not found (never use "none", "null", or "N/A")
- Date fields: Use null if not found (never use empty string)
- Number fields: Use 0 if not found (never use null or empty string)
- Array fields: Use empty array [] if no items found
- Country codes: Use standard 2-letter codes: Cyprus="CY", Greece="GR", USA="US", UK="GB", or "" if unknown

**REQUIRED JSON STRUCTURE - ALL FIELDS MUST BE PRESENT IN EVERY RESPONSE:**

{{
  "success": true,
  "total_bills": <number>,
  "bills": [
    {{
      "bill_index": 1,
      "page_range": "1",
      "document_classification": {{
        "document_type": "vendor_bill",
        "company_position": "recipient",
        "direction_confidence": "high",
        "detection_details": ""
      }},
      "company_validation": {{
        "expected_company": "{company_name}",
        "found_companies": [],
        "company_match": "no_match",
        "match_details": ""
      }},
      "company_data": {{
        "name": "",
        "email": "",
        "phone": "",
        "website": "",
        "street": "",
        "city": "",
        "zip": "",
        "country_code": ""
      }},
      "vendor_data": {{
        "name": "",
        "email": "",
        "phone": "",
        "website": "",
        "street": "",
        "city": "",
        "zip": "",
        "country_code": "",
        "invoice_date": null,
        "due_date": null,
        "vendor_ref": "",
        "payment_reference": "",
        "description": "",
        "subtotal": 0,
        "tax_amount": 0,
        "total_amount": 0,
        "currency_code": "",
        "line_items": []
      }},
      "accounting_assignment": {{
        "debit_account": "",
        "debit_account_name": "",
        "credit_account": "",
        "credit_account_name": "",
        "vat_treatment": "",
        "requires_reverse_charge": false,
        "additional_entries": []
      }},
      "extraction_confidence": {{
        "vendor_name": "low",
        "total_amount": "low",
        "line_items": "low",
        "dates": "low",
        "company_validation": "low",
        "document_classification": "low"
      }},
      "missing_fields": [],
      "mathematical_validation": {{
        "totals_match": false,
        "line_items_sum_verified": false,
        "vat_calculation_verified": false,
        "column_interpretation": "unknown",
        "discrepancies": []
      }}
    }}
  ]
}}

**LINE ITEMS STRUCTURE (ENHANCED - when present):**
Each line item in the line_items array must have this exact structure:
{{
  "description": "",
  "quantity": 0,
  "price_unit": 0,
  "line_total": 0,
  "tax_rate": 0,
  "tax_name": "",
  "account_code": "",
  "account_name": "",
  "tax_grid": ""
}}

**ADDITIONAL ENTRIES STRUCTURE (for VAT and complex transactions):**
Each additional entry in the additional_entries array must have this exact structure:
{{
  "account_code": "",
  "account_name": "",
  "debit_amount": 0,
  "credit_amount": 0,
  "description": "",
  "tax_name": "",
  "tax_grid": ""
}}

**TAX GRID EXAMPLES:**
- Input VAT on reverse charge: tax_grid: "+4"
- Output VAT on reverse charge: tax_grid: "-1"
- Purchase value for ANY domestic (CY) purchase: tax_grid: "+7"
- Standard rate sales value: tax_grid: "+5"
- Reduced rate sales value: tax_grid: "+6"
- EU acquisitions value: tax_grid: "+8"

**ABSOLUTE REQUIREMENTS:**
1. Every field listed above MUST be present in every bill object
2. Use the exact default values shown when data is not found
3. Never omit fields - always include them with default values
4. String fields default to empty string ""
5. Number fields default to 0
6. Date fields default to null
7. Array fields default to empty array []
8. Confidence levels: use "high", "medium", or "low" only
9. Company match: use "exact_match", "close_match", "no_match", or "unclear" only
10. **ACCOUNT CODE CONSISTENCY: Use ONLY the exact account codes and names from the bill logic above**
11. **LINE ITEM ACCOUNT ASSIGNMENT: MANDATORY for every line item - analyze each service individually**
12. **PROPERTY CAPITALIZATION: Check EVERY bill for property development costs that should go to 0060**
13. **MIXED BILLS: When line items have different account codes, set debit_account="MIXED"**
14. **REVERSE CHARGE DETECTION: Check ALL 8 categories comprehensively, especially Category 1 (construction/property professionals)**
15. **GREEK LANGUAGE: Detect Greek keywords for construction services (μηχανολογική, τοπογραφικ, αρχιτεκτον, etc.)**
16. **VAT ACCOUNT SELECTION: Use company VAT registration status to determine correct VAT account (2202 vs 7906)**
17. **TAX GRID ASSIGNMENT: Include appropriate tax_grid for all eligible entries based on the refined, custom rules.**
18. **ODOO TAX NAME ASSIGNMENT: Each line item MUST have a `tax_name` assigned based on the detailed, prioritized rules provided.**
19. **VAT CALCULATION: Always calculate VAT for `additional_entries` based ONLY on the sum of taxable line items.**
20. **MATHEMATICAL VALIDATION: ALWAYS perform full mathematical validation and populate mathematical_validation section**

**FINAL REMINDER: Return ONLY the JSON object with ALL fields present. No explanatory text. Start with {{ and end with }}.**"""


def ensure_line_item_structure(line_item):
    """Ensure each line item has the complete required structure including account assignment and tax grid"""
    default_line_item = {
        "description": "",
        "quantity": 0,
        "price_unit": 0,
        "line_total": 0,
        "tax_rate": 0,
        "tax_name": "",
        "account_code": "",
        "account_name": "",
        "tax_grid": ""
    }
    
    result = {}
    for key, default_value in default_line_item.items():
        if key in line_item and line_item[key] is not None:
            result[key] = line_item[key]
        else:
            result[key] = default_value
    
    return result

def validate_bill_data(bills, company_context=None):
    """Validate extracted bill data for completeness and accuracy including comprehensive reverse charge detection and property capitalization"""
    validation_results = []
    
    for bill in bills:
        bill_validation = {
            "bill_index": bill.get("bill_index", 0),
            "issues": [],
            "warnings": [],
            "mandatory_fields_present": True,
            "structure_complete": True
        }
        
        vendor_data = bill.get("vendor_data", {})
        
        # Check mandatory fields (content validation, not structure)
        mandatory_content = {
            "vendor_name": vendor_data.get("name", ""),
            "total_amount": vendor_data.get("total_amount", 0),
            "invoice_date": vendor_data.get("invoice_date"),
            "description": vendor_data.get("description", "")
        }
        
        for field_name, field_value in mandatory_content.items():
            if not field_value or field_value == "":
                bill_validation["issues"].append(f"Missing content for mandatory field: {field_name}")
                bill_validation["mandatory_fields_present"] = False
        
        # Check line items and their account assignments
        line_items = vendor_data.get("line_items", [])
        description = vendor_data.get("description", "").lower()
        
        if not line_items:
            bill_validation["warnings"].append("No line items found")
        else:
            # Validate line item account assignments and tax grids
            valid_expense_accounts = [
                "0060",  # Property development
                "5001",  # Purchases (for non-inventory companies)
                "7906", "7605", "7101",  # New accounts
                "7602", "7600", "7601", "7603", "7100", "7190", "7200", "7201", "7102",
                "7508", "7503", "7502", "7400", "7800", "5100", "8200", "7104", "7700",
                "7506", "7005", "6201", "6100", "1000", "1020", "5000", "6002", "7402",
                "7401", "7406", "7500", "7501", "7504", "7300", "7301", "7303", "1090", "1160",
                "0080", "0090", "0100", "0110", "0130", "0040", "0030"
            ]
            
            line_item_accounts = set()
            materials_accounts_used = []
            
            for i, item in enumerate(line_items):
                account_code = item.get("account_code", "")
                account_name = item.get("account_name", "")
                tax_grid = item.get("tax_grid", "")
                tax_name = item.get("tax_name", "")
                item_description = item.get("description", "").lower()
                
                if not account_code:
                    bill_validation["issues"].append(f"Line item {i+1} missing account_code")
                elif account_code not in valid_expense_accounts:
                    bill_validation["issues"].append(f"Line item {i+1} has invalid account code: {account_code}")
                
                if not account_name:
                    bill_validation["issues"].append(f"Line item {i+1} missing account_name")
                
                # Track materials/inventory accounts for validation
                if account_code in ["5001", "1000", "1020", "5000"]:
                    materials_accounts_used.append({
                        "line": i+1,
                        "account": account_code,
                        "description": item_description
                    })
                
                # Validate tax name
                if not tax_name and item.get("tax_rate", 0) != 0:
                    bill_validation["warnings"].append(f"Line item {i+1} has a tax rate but is missing Odoo tax_name.")

                # Validate tax grid if present
                if tax_grid and not tax_grid.startswith(('+', '-')):
                    bill_validation["warnings"].append(f"Line item {i+1} has unusual tax_grid format: {tax_grid}")
                
                if account_code:
                    line_item_accounts.add(account_code)
            
            # Validate inventory management consistency
            if company_context and materials_accounts_used:
                business_ops = company_context.get('business_operations', {})
                inventory_management = business_ops.get('inventory_management', '').lower()
                
                for material_item in materials_accounts_used:
                    if inventory_management in ['no', 'none', 'project-based', 'on-demand', 'just-in-time', '']:
                        # Company does NOT maintain inventory
                        if material_item['account'] in ['1000', '1020', '5000']:
                            bill_validation["warnings"].append(
                                f"Line item {material_item['line']}: Company does NOT maintain inventory "
                                f"(inventory_management: '{inventory_management}'), but using inventory account "
                                f"{material_item['account']}. Should use 5001 (Purchases) instead. "
                                f"Description: '{material_item['description']}'"
                            )
                    elif inventory_management in ['yes', 'perpetual', 'periodic']:
                        # Company DOES maintain inventory
                        if material_item['account'] == '5001':
                            # Check if this should be inventory
                            materials_keywords = ['material', 'stock', 'inventory', 'goods', 'supplies', 'raw']
                            if any(keyword in material_item['description'] for keyword in materials_keywords):
                                bill_validation["warnings"].append(
                                    f"Line item {material_item['line']}: Company maintains inventory "
                                    f"(inventory_management: '{inventory_management}'), consider using "
                                    f"1000 (Stock) or 1020 (Raw materials) instead of 5001 (Purchases). "
                                    f"Description: '{material_item['description']}'"
                                )
            
            # Check if bill is mixed (multiple account codes)
            accounting_assignment = bill.get("accounting_assignment", {})
            debit_account = accounting_assignment.get("debit_account", "")
            
            if len(line_item_accounts) > 1 and debit_account != "MIXED":
                bill_validation["warnings"].append(
                    f"Multiple account codes detected in line items ({len(line_item_accounts)}) but debit_account is not 'MIXED'"
                )
            elif len(line_item_accounts) == 1 and debit_account == "MIXED":
                bill_validation["warnings"].append(
                    "Only one account code in line items but debit_account is set to 'MIXED'"
                )
        
        # NEW: Validate mathematical consistency
        math_validation = bill.get("mathematical_validation", {})
        subtotal = vendor_data.get("subtotal", 0)
        tax_amount = vendor_data.get("tax_amount", 0)
        total_amount = vendor_data.get("total_amount", 0)
        
        if total_amount > 0 and line_items:
            # Check if totals match
            calculated_total = subtotal + tax_amount
            if abs(calculated_total - total_amount) > 0.02:
                bill_validation["warnings"].append(
                    f"Amount mismatch: calculated {calculated_total:.2f}, document shows {total_amount:.2f}"
                )
                
                # Check if mathematical_validation was populated
                if not math_validation.get("totals_match"):
                    bill_validation["warnings"].append(
                        "Mathematical validation indicates totals don't match - review extraction"
                    )
            
            # Check if line items sum to subtotal
            line_items_sum = sum(item.get("line_total", 0) for item in line_items)
            if abs(line_items_sum - subtotal) > 0.02:
                bill_validation["warnings"].append(
                    f"Line items sum ({line_items_sum:.2f}) doesn't match subtotal ({subtotal:.2f})"
                )
                
                if not math_validation.get("line_items_sum_verified"):
                    bill_validation["warnings"].append(
                        "Mathematical validation indicates line items sum issue - possible reversed columns"
                    )
            
            # Check column interpretation
            column_interpretation = math_validation.get("column_interpretation", "unknown")
            if column_interpretation == "reversed":
                bill_validation["warnings"].append(
                    "Invoice has reversed columns (Amount=NET, Price=GROSS) - verify extraction is correct"
                )
            elif column_interpretation == "unknown":
                bill_validation["warnings"].append(
                    "Could not determine column structure - mathematical validation may be incomplete"
                )
            
            # Check for discrepancies reported
            discrepancies = math_validation.get("discrepancies", [])
            if discrepancies:
                for discrepancy in discrepancies:
                    bill_validation["warnings"].append(f"Mathematical discrepancy: {discrepancy}")
        
        # Check for property capitalization indicators
        property_keywords = [
            "surveyor", "survey", "topographical", "boundary",
            "architect", "architectural", "design", "feasibility",
            "valuation", "appraisal", "valuer",
            "site investigation", "geotechnical", "environmental assessment",
            "planning permission", "building permit", "zoning",
            "property acquisition", "land purchase", "μηχανολογική μελέτη",
            "mechanical study", "electrical study", "τοπογραφικ"
        ]
        
        has_property_keywords = any(
            keyword in description or 
            any(keyword in item.get("description", "").lower() for item in line_items)
            for keyword in property_keywords
        )
        
        if has_property_keywords:
            # Check if any line items use 0060
            uses_property_account = any(
                item.get("account_code") == "0060" 
                for item in line_items
            )
            
            accounting_assignment = bill.get("accounting_assignment", {})
            debit_account = accounting_assignment.get("debit_account", "")
            
            if not uses_property_account and debit_account != "0060":
                bill_validation["warnings"].append(
                    "Property-related keywords detected but not capitalized to 0060. "
                    "Review for IAS 40 compliance - check if costs are directly "
                    "attributable to property acquisition/development."
                )
        
        # CRITICAL: VAT ACCOUNT VALIDATION BASED ON COMPANY REGISTRATION
        accounting_assignment = bill.get("accounting_assignment", {})
        additional_entries = accounting_assignment.get("additional_entries", [])
        
        if company_context:
            is_vat_registered = company_context.get('is_vat_registered', 'unknown')
            
            if tax_amount > 0:
                has_2202 = any(e.get("account_code") == "2202" for e in additional_entries)
                has_7906 = any(e.get("account_code") == "7906" for e in additional_entries)
                
                # Validate tax grids on VAT entries
                for entry in additional_entries:
                    if entry.get("account_code") == "2202":
                        if entry.get("tax_grid") != "+4":
                            bill_validation["warnings"].append(
                                f"Input VAT (2202) should have tax_grid '+4', found: {entry.get('tax_grid', 'none')}"
                            )
                    elif entry.get("account_code") == "2201":
                        if entry.get("tax_grid") != "-1":
                            bill_validation["warnings"].append(
                                f"Output VAT (2201) should have tax_grid '-1', found: {entry.get('tax_grid', 'none')}"
                            )
                
                if is_vat_registered == 'no':
                    # Non-VAT registered: MUST use 7906, NEVER 2202
                    if has_2202:
                        bill_validation["issues"].append(
                            "Company is NOT VAT registered - CANNOT use 2202 (Input VAT). Must use 7906 (Non Recoverable VAT)"
                        )
                    
                    if not has_7906:
                        bill_validation["issues"].append(
                            "Company is NOT VAT registered - VAT must be posted to 7906 (Non Recoverable VAT on expenses)"
                        )
                
                elif is_vat_registered == 'yes':
                    # VAT registered: Should use 2202 for recoverable VAT
                    if has_7906:
                        bill_validation["warnings"].append(
                            "Company IS VAT registered - VAT should be recoverable (2202), not expense (7906)"
                        )
                    
                    # Check for 2202 unless it's reverse charge (which has different rules)
                    requires_reverse_charge = accounting_assignment.get("requires_reverse_charge", False)
                    if not has_2202 and not requires_reverse_charge:
                        bill_validation["warnings"].append(
                            "Company IS VAT registered - should have Input VAT (2202) entry for recoverable VAT"
                        )
        
        # ENHANCED COMPREHENSIVE REVERSE CHARGE DETECTION
        requires_reverse_charge = accounting_assignment.get("requires_reverse_charge", False)
        vat_treatment = accounting_assignment.get("vat_treatment", "")
        
        # Use enhanced detection function for Category 1
        is_reverse_charge_vendor = False
        detected_category = ""
        confidence_level = "low"
        
        # Category 1: Enhanced Construction/Property Services Detection
        is_construction_rc, construction_reason, construction_confidence = detect_construction_property_reverse_charge(
            vendor_data, line_items
        )
        
        if is_construction_rc:
            is_reverse_charge_vendor = True
            detected_category = f"Construction/Property Services Reverse Charge ({construction_reason})"
            confidence_level = construction_confidence
        
        # Category 2: Check foreign services
        elif vendor_data.get("country_code", "") and vendor_data.get("country_code", "") != "CY":
            is_reverse_charge_vendor = True
            detected_category = "Foreign Services Reverse Charge"
            confidence_level = "high"
        
        # Category 3: Check gas/electricity
        elif any(keyword in vendor_data.get("name", "").lower() or keyword in description 
                 for keyword in ["energy", "power", "gas company", "electricity authority", 
                                 "natural gas", "electric power"]):
            is_reverse_charge_vendor = True
            detected_category = "Gas/Electricity Reverse Charge"
            confidence_level = "medium"
        
        # Category 4: Check scrap metal
        elif any(keyword in vendor_data.get("name", "").lower() or 
                 keyword in " ".join([item.get("description", "").lower() for item in line_items])
                 for keyword in ["scrap", "recycling", "waste management", "metal recycling", 
                                 "scrap metal", "waste materials"]):
            is_reverse_charge_vendor = True
            detected_category = "Scrap Metal Reverse Charge"
            confidence_level = "medium"
        
        # Category 5: Check electronics
        elif any(keyword in vendor_data.get("name", "").lower() or 
                 keyword in " ".join([item.get("description", "").lower() for item in line_items])
                 for keyword in ["mobile phone", "smartphone", "tablet", "laptop", "microprocessor", 
                                 "cpu", "integrated circuit", "gaming console", "playstation", "xbox"]):
            is_reverse_charge_vendor = True
            detected_category = "Electronics Reverse Charge"
            confidence_level = "medium"
        
        # Category 6: Check precious metals
        elif any(keyword in vendor_data.get("name", "").lower() or 
                 keyword in " ".join([item.get("description", "").lower() for item in line_items])
                 for keyword in ["precious metals", "gold", "silver", "platinum", "bullion", 
                                 "gold bars", "silver ingots"]):
            is_reverse_charge_vendor = True
            detected_category = "Precious Metals Reverse Charge"
            confidence_level = "medium"
        
        # Category 7: Check EU telecom
        elif vendor_data.get("country_code", "") in ["GR", "DE", "FR", "IT", "ES"] and \
             any(keyword in vendor_data.get("name", "").lower() or keyword in description 
                 for keyword in ["telecommunications", "telecom services"]):
            is_reverse_charge_vendor = True
            detected_category = "Telecommunications Reverse Charge"
            confidence_level = "medium"
        
        # Category 8: Check property transfer
        elif any(keyword in description or 
                 keyword in " ".join([item.get("description", "").lower() for item in line_items])
                 for keyword in ["debt restructuring", "foreclosure", "debt-for-asset", 
                                 "property transfer", "bank repossession"]):
            is_reverse_charge_vendor = True
            detected_category = "Property Transfer Reverse Charge"
            confidence_level = "medium"
        
        # Validate VAT handling based on detection
        if tax_amount > 0:
            if is_reverse_charge_vendor:
                # Should have proper reverse charge entries based on company VAT status
                if not requires_reverse_charge:
                    bill_validation["issues"].append(
                        f"Vendor qualifies for reverse charge ({detected_category}, confidence: {confidence_level}) "
                        f"but requires_reverse_charge is false"
                    )
                
                if not additional_entries:
                    bill_validation["issues"].append(
                        f"Vendor qualifies for reverse charge ({detected_category}) but no additional_entries created"
                    )
                else:
                    input_vat_entries = [e for e in additional_entries if e.get("account_code") == "2202"]
                    output_vat_entries = [e for e in additional_entries if e.get("account_code") == "2201"]
                    non_recoverable_vat_entries = [e for e in additional_entries if e.get("account_code") == "7906"]
                    
                    if company_context and company_context.get('is_vat_registered') == 'yes':
                        # VAT registered: should have both 2202 and 2201
                        if not input_vat_entries:
                            bill_validation["issues"].append(
                                f"Reverse charge vendor ({detected_category}) missing Input VAT (2202) entry"
                            )
                        
                        if not output_vat_entries:
                            bill_validation["issues"].append(
                                f"Reverse charge vendor ({detected_category}) missing Output VAT (2201) entry"
                            )
                    
                    elif company_context and company_context.get('is_vat_registered') == 'no':
                        # Non-VAT registered: should have only 7906
                        if not non_recoverable_vat_entries:
                            bill_validation["issues"].append(
                                f"Reverse charge vendor - Company NOT VAT registered, should use 7906 (Non Recoverable VAT)"
                            )
                        
                        if input_vat_entries or output_vat_entries:
                            bill_validation["issues"].append(
                                f"Company NOT VAT registered - should not have 2202 or 2201 entries, only 7906"
                            )
            else:
                # Normal domestic vendor - validate VAT treatment
                if requires_reverse_charge:
                    bill_validation["warnings"].append(
                        "Vendor marked as reverse charge but doesn't match any reverse charge category"
                    )
        
        # Check account code consistency for main accounting assignment
        accounting_assignment = bill.get("accounting_assignment", {})
        credit_account = accounting_assignment.get("credit_account", "")
        
        valid_credit_accounts = ["2100", "2201", "2202"]
        valid_expense_accounts_with_mixed = valid_expense_accounts + ["MIXED"]
        
        if debit_account and debit_account not in valid_expense_accounts_with_mixed:
            bill_validation["issues"].append(f"Invalid debit account code: {debit_account}")
        
        if credit_account and credit_account not in valid_credit_accounts:
            bill_validation["issues"].append(f"Invalid credit account code: {credit_account}")
        
        # Check confidence levels
        confidence = bill.get("extraction_confidence", {})
        low_confidence_fields = [
            field for field, conf in confidence.items() 
            if conf == "low"
        ]
        
        if low_confidence_fields:
            bill_validation["warnings"].append(
                f"Low confidence fields: {', '.join(low_confidence_fields)}"
            )
        
        validation_results.append(bill_validation)
    
    return validation_results

def process_bills_with_claude(pdf_content, company_name, company_context=None):
    """Process PDF document with Claude for bill splitting and extraction"""
    try:
        # Initialize Anthropic client
        anthropic_client = anthropic.Anthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY')
        )
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Get comprehensive prompt with integrated accounting logic and company context
        prompt = get_bill_processing_prompt(company_name, company_context)
        
        # Get bill accounting logic for system prompt
        bill_system_logic = get_accounting_logic("bill")
        
        # Build system prompt with company context awareness
        vat_status_note = ""
        if company_context:
            is_vat_registered = company_context.get('is_vat_registered', 'unknown')
            if is_vat_registered == 'yes':
                vat_status_note = "\n- Company IS VAT registered: Use 2202 (Input VAT) for recoverable VAT with tax_grid '+4'"
            elif is_vat_registered == 'no':
                vat_status_note = "\n- Company NOT VAT registered: Use 7906 (Non Recoverable VAT) for all VAT amounts"
        
        # Send to Claude with optimized parameters for structured output
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=18000,
            temperature=0.0,
            system=f"""You are an expert accountant and data extraction system specialized in VENDOR BILLS and EXPENSE transactions with LINE-LEVEL account assignment, COMPREHENSIVE Cyprus VAT reverse charge detection, IAS 40 PROPERTY CAPITALIZATION, TAX GRID ASSIGNMENT, and COMPANY-SPECIFIC VAT treatment.

Your core behavior is to think and act like a professional accountant who understands:
- Double-entry bookkeeping for EXPENSE recognition
- VAT regulations including ALL reverse charge categories
- Granular expense categorization
- IAS 40 Investment Property accounting and pre-construction cost capitalization
- Cyprus Article 11B reverse charge mechanism for construction/property services
- Correct VAT accounting based on company VAT registration status
- Cyprus VAT return box assignments and tax grid mapping{vat_status_note}
- PRECISE DATE EXTRACTION with format awareness (DD/MM/YYYY for Greek documents)

**CRITICAL DATE EXTRACTION EXPERTISE:**
You are an expert at extracting dates from invoices with 100% accuracy:
- You understand Greek date format DD/MM/YYYY (day first, then month)
- You differentiate between invoice date, due date, receipt date, and payment date
- You always look for explicit date labels: "ΗΜΕΡΟΜΗΝΙΑ", "Ημερ:", "Date:", "Invoice Date:"
- You convert all dates to ISO 8601 format: "YYYY-MM-DD"
- You validate dates before finalizing (day 01-31, month 01-12, year makes sense)
- You NEVER confuse day and month values
- You mark low confidence when dates are ambiguous

**CRITICAL VAT CALCULATION:**
When creating VAT entries (e.g., for reverse charge), you MUST calculate the VAT amount based **only on the sum of taxable line items**. Explicitly EXCLUDE any line items marked as exempt (`0% E`) from the taxable base.

**CRITICAL LINE-LEVEL TAX NUANCE:**
You must identify line items within a bill that have special tax treatment (e.g., exempt "submission fees") even if the overall bill is subject to reverse charge. The individual line item's nature takes precedence.

**CRITICAL ODOO TAX NAME EXPERTISE:**
You must assign a valid Odoo tax name (e.g., "19% S", "19% RC", "0% E") to the `tax_name` field for every line item and relevant additional entry.
- **PRIORITY 1: EXEMPT ITEMS.** First, check if a line is for an exempt charge like "submission fees". If so, you MUST assign `0% E` to that line.
- **PRIORITY 2: REVERSE CHARGE.** If a line is not exempt, check if the bill is reverse charge. If so, assign `19% RC`.
- **PRIORITY 3: STANDARD/OTHER.** If neither of the above apply, use the standard logic (Goods/Services, Domestic/EU/OEU) to determine the tax name.

**CRITICAL TAX GRID EXPERTISE (ULTIMATE CUSTOM RULE):**
You must assign correct tax grids based on this specific business requirement for 'Total inputs excluding VAT'.
- Input VAT (2202) → `tax_grid: "+4"`
- Output VAT (2201) → `tax_grid: "-1"`
- **Domestic Purchase Values (Grid `+7`):** This is your most critical rule. You MUST apply `tax_grid: "+7"` to EVERY line item on any bill from a domestic vendor (where `vendor_data.country_code` is `CY`). This rule applies to all domestic tax types (`19% RC`, `0% E`, `19% S`, etc.) without exception.
- EU acquisitions values → `tax_grid: "+8"`

**CRITICAL OCR ACCURACY:**
- Read ALL text carefully, especially handwritten or Greek text
- Greek letters are NOT English (Δ≠D, Η≠H, Ν≠N, Ρ≠P)
- Always look for printed text first (stamps, letterheads) before trusting handwritten text
- If text is unclear, set confidence to "low" - don't guess

**USE COMPANY CONTEXT TO VALIDATE:**
Company: {company_name}
Industry: {company_context.get('primary_industry', 'N/A') if company_context else 'N/A'}
Business: {company_context.get('business_description', 'N/A') if company_context else 'N/A'}

Ask yourself: "Does this vendor make sense for this company's business?"
If a construction company gets a bill from a "cinema" company → re-check the vendor name OCR.

**CRITICAL PROPERTY CAPITALIZATION EXPERTISE:**
You must identify when vendor bills contain costs that should be CAPITALIZED to 0060 (Freehold property) under IAS 40, not expensed. Always check:
1. Is vendor a property-related professional? (architect, surveyor, valuer, engineer, planning consultant)
2. Does service relate to a specific property acquisition/development?
3. Does description contain property identifiers or pre-construction keywords?
If YES to all three → Use account 0060 (Freehold property), not expense accounts

**PROPERTY COST EXAMPLES TO CAPITALIZE:**
- Surveyor fees for property projects → 0060
- Architect fees for property development → 0060
- Valuation fees for property acquisition → 0060
- Site investigations and geotechnical studies → 0060
- Planning permission applications → 0060
- Legal fees for property purchase → 0060

**CRITICAL REVERSE CHARGE EXPERTISE (Category 1 - Construction/Property):**
You must identify Cyprus domestic vendors providing construction/property services under Article 11B:

**Vendor Types (English & Greek):**
- Architects: "architect", "architecture", "αρχιτεκτον"
- Engineers: "engineer", "μηχανικ", "MechEnergy", "mechanical engineer", "electrical engineer"
- Surveyors: "surveyor", "topographer", "τοπογραφ", "ΤΟΠΟΓΡΑΦΟΙ ΜΗΧΑΝΙΚΟΙ"
- Design firms: "design studio" (when doing property work)

**Service Keywords (English & Greek):**
- "mechanical study", "μηχανολογική μελέτη"
- "topographical work", "τοπογραφικές εργασίες"
- "architectural design", "preliminary design"
- "planning permit", "planning application"

**Explicit Indicators:**
- "Article 11B", "άρθρο 11Β"
- "δεν χρεωνεται ΦΠΑ", "συμφωνα με το αρθρο 11Β"

**CRITICAL VAT ACCOUNT SELECTION:**
- IF company is VAT registered: Use 2202 (Input VAT - recoverable asset) with tax_grid "+4"
- IF company is NOT VAT registered: Use 7906 (Non Recoverable VAT on expenses - expense account)
- For reverse charge: VAT registered uses both 2202 (tax_grid "+4") + 2201 (tax_grid "-1"), Non-VAT registered uses only 7906

**CRITICAL ODOO ACCOUNT NAME EXACTNESS:**
Account names must EXACTLY match Odoo's account names (no hyphens unless Odoo has them):
- ✅ CORRECT: "Non Recoverable VAT on expenses" (NO hyphen)
- ❌ WRONG: "Non-Recoverable VAT on expenses" (has hyphen)
- ✅ CORRECT: "Input VAT (Purchases)"
- ✅ CORRECT: "Output VAT (Sales)"
- ✅ CORRECT: "Accounts Payable"

This is critical because account lookup in Odoo is case-sensitive and must match exactly.

**BILL ACCOUNTING EXPERTISE:**
{bill_system_logic}

CORE ACCOUNTING BEHAVIOR FOR VENDOR BILLS WITH LINE-LEVEL PROCESSING:
• Always think: "What did we receive?" (DEBIT) and "What do we owe?" (CREDIT)
• Vendor bills: DEBIT expense account(s), CREDIT accounts payable (2100)
• ANALYZE EACH LINE ITEM INDIVIDUALLY for expense categorization:
  - Legal services → DEBIT 7600 (Legal fees)
  - Accounting services → DEBIT 7601 (Audit and accountancy fees)
  - Business consulting → DEBIT 7602 (Consultancy fees)
  - Portfolio management → DEBIT 7605 (Portfolio management fees)
  - General rent → DEBIT 7100 (Rent)
  - Office space/coworking → DEBIT 7101 (Office space)
  - Internet services → DEBIT 7503 (Internet)
  - Mobile/phone services → DEBIT 7502 (Telephone)
  - Property development services → DEBIT 0060 (Freehold property)
  - Mixed services from same vendor → Use appropriate account per line item
• When line items use different accounts → Set main debit_account to "MIXED"
• Ensure debits always equal credits

LINE-LEVEL ACCOUNT ASSIGNMENT EXPERTISE:
• Each line item gets its own account_code and account_name
• Same vendor can provide multiple service types requiring different accounts
• Example: Telecom company billing Internet (7503) AND Mobile services (7502)
• Example: Office supplier selling Stationery (7504) AND Equipment (0090)
• Example: Engineering firm providing Property study (0060) AND General consulting (7602)

**CRITICAL: INVENTORY MANAGEMENT AWARENESS:**
- ALWAYS check company's business_operations.inventory_management field
- IF inventory_management is 'no', 'none', 'project-based', or 'on-demand':
  → Use 5001 (Purchases) for ALL materials, supplies, goods, and equipment
  → Company purchases on demand for projects - items are NOT held in inventory
  → Examples: Construction materials, hardware, tools, supplies → 5001 (Purchases)
- IF inventory_management is 'yes', 'perpetual', or 'periodic':
  → Use 1000 (Stock) or 1020 (Raw materials) for inventory items
  → Company maintains inventory - purchases are capitalized to inventory accounts

• Be precise - "Mobile WiFi" is telecommunications (7502), not internet (7503)
• Be precise - "Property mechanical study" is capitalized (0060), not consultancy (7602)
• Be precise - "Coworking space" is office space (7101), not general rent (7100)

COMPREHENSIVE CYPRUS VAT REVERSE CHARGE DETECTION:
You must check ALL 8 categories for reverse charge eligibility:

1. CONSTRUCTION & PROPERTY: Construction/property professionals (architects, engineers, surveyors) providing services for a specific project - CHECK BOTH VENDOR TYPE AND SERVICE TYPE
2. FOREIGN/EU SERVICES: Any services from vendors located outside Cyprus (check country code, VAT number, address)
3. GAS & ELECTRICITY: Gas and electricity supplies to registered business traders
4. SCRAP METAL & WASTE: Scrap metal dealers, waste materials, recycling companies
5. ELECTRONICS: Mobile phones, tablets, laptops, microprocessors, CPUs, integrated circuits, gaming consoles
6. PRECIOUS METALS: Gold, silver, platinum, raw/semi-finished precious metals, bullion
7. EU TELECOMMUNICATIONS: Telecom services from EU suppliers
8. PROPERTY TRANSFERS: Foreclosures, debt restructuring, debt-for-asset swaps, bank repossessions

CRITICAL REVERSE CHARGE RULES:
• If vendor matches ANY of the 8 categories AND has VAT:
  - Set requires_reverse_charge: true
  - Set vat_treatment to specific category (e.g., "Construction/Property Services Reverse Charge")
  - For VAT registered companies: Create BOTH Input VAT (2202, tax_grid "+4") AND Output VAT (2201, tax_grid "-1") entries
  - For NON-VAT registered companies: Create ONLY Non Recoverable VAT (7906) entry
  - Main transaction amount should be NET only
  - Credit account 2100 with NET amount only

• If vendor is normal domestic (not in any category) with VAT:
  - Set requires_reverse_charge: false
  - Set vat_treatment: "Standard VAT"
  - For VAT registered: Create ONLY Input VAT (2202, tax_grid "+4") entry, credit 2100 with GROSS
  - For NON-VAT registered: Create ONLY Non Recoverable VAT (7906) entry, credit 2100 with GROSS

  **CRITICAL TAX GRID FOR LINE ITEMS:**
- For reverse charge transactions: expense line items must include tax_grid "+7" to report purchase values
- This applies to ALL line items when requires_reverse_charge is true
- Example: Construction service line items → tax_grid: "+7"
  
OUTPUT FORMAT:
Respond only with valid JSON objects. Never include explanatory text, analysis, or commentary. Always include ALL required fields with their default values when data is missing. Apply your accounting expertise to assign correct debit/credit accounts for every expense transaction AND provide granular line-level account assignments using ONLY the exact account codes provided. Thoroughly check ALL 8 reverse charge categories before determining VAT treatment. Always check for property capitalization opportunities under IAS 40. Pay special attention to Greek language keywords for construction/property services. Most importantly, use the correct VAT account (2202 vs 7906) based on company VAT registration status and assign appropriate tax grids for Cyprus VAT return compliance.""",
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
        
        # Log token usage for monitoring
        print(f"Token usage - Input: {message.usage.input_tokens}, Output: {message.usage.output_tokens}")
        
        # Debug: Log first 200 characters of response to identify issues
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

def ensure_bill_structure(bill):
    """Ensure each bill has the complete required structure with default values"""
    
    # Define the complete structure with default values
    default_bill = {
        "bill_index": 1,
        "page_range": "1",
        "document_classification": {
            "document_type": "vendor_bill",
            "company_position": "recipient",
            "direction_confidence": "low",
            "detection_details": ""
        },
        "company_validation": {
            "expected_company": "",
            "found_companies": [],
            "company_match": "no_match",
            "match_details": ""
        },
        "company_data": {
            "name": "",
            "email": "",
            "phone": "",
            "website": "",
            "street": "",
            "city": "",
            "zip": "",
            "country_code": ""
        },
        "vendor_data": {
            "name": "",
            "email": "",
            "phone": "",
            "website": "",
            "street": "",
            "city": "",
            "zip": "",
            "country_code": "",
            "invoice_date": None,
            "due_date": None,
            "vendor_ref": "",
            "payment_reference": "",
            "description": "",
            "subtotal": 0,
            "tax_amount": 0,
            "total_amount": 0,
            "currency_code": "",
            "line_items": []
        },
        "accounting_assignment": {
            "debit_account": "",
            "debit_account_name": "",
            "credit_account": "",
            "credit_account_name": "",
            "vat_treatment": "",
            "requires_reverse_charge": False,
            "additional_entries": []
        },
        "extraction_confidence": {
            "vendor_name": "low",
            "total_amount": "low",
            "line_items": "low",
            "dates": "low",
            "company_validation": "low",
            "document_classification": "low"
        },
        "missing_fields": [],
        "mathematical_validation": {
            "totals_match": False,
            "line_items_sum_verified": False,
            "vat_calculation_verified": False,
            "column_interpretation": "unknown",
            "discrepancies": []
        }
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
                        # Ensure arrays exist and validate structure for line_items
                        if key == "line_items" and isinstance(source[key], list):
                            result[key] = [ensure_line_item_structure(item) for item in source[key]]
                        else:
                            result[key] = source[key] if isinstance(source[key], list) else default_value
                    else:
                        result[key] = source[key]
                else:
                    result[key] = default_value
            return result
        else:
            return source if source is not None else defaults
    
    return merge_with_defaults(bill, default_bill)
    
    def merge_with_defaults(source, defaults):
        """Recursively merge source with defaults, ensuring all fields are present"""
        if isinstance(defaults, dict):
            result = {}
            for key, default_value in defaults.items():
                if key in source and source[key] is not None:
                    if isinstance(default_value, dict):
                        result[key] = merge_with_defaults(source[key], default_value)
                    elif isinstance(default_value, list):
                        # Ensure arrays exist and validate structure for line_items
                        if key == "line_items" and isinstance(source[key], list):
                            result[key] = [ensure_line_item_structure(item) for item in source[key]]
                        else:
                            result[key] = source[key] if isinstance(source[key], list) else default_value
                    else:
                        result[key] = source[key]
                else:
                    result[key] = default_value
            return result
        else:
            return source if source is not None else defaults
    
    return merge_with_defaults(bill, default_bill)

def parse_bill_response(raw_response):
    """Parse the raw response into structured bill data with improved error handling"""
    try:
        # Clean the response
        cleaned_response = raw_response.strip()
        
        # Remove any markdown formatting if present
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]
        elif cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]
            
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]
            
        cleaned_response = cleaned_response.strip()
        
        # Handle cases where Claude adds explanatory text before JSON
        # Look for the first opening brace
        json_start = cleaned_response.find('{')
        if json_start > 0:
            print(f"Warning: Found text before JSON, removing: {cleaned_response[:json_start][:100]}...")
            cleaned_response = cleaned_response[json_start:]
        
        # Look for the last closing brace (in case there's text after)
        json_end = cleaned_response.rfind('}')
        if json_end > 0 and json_end < len(cleaned_response) - 1:
            print(f"Warning: Found text after JSON, removing: {cleaned_response[json_end+1:][:100]}...")
            cleaned_response = cleaned_response[:json_end + 1]
        
        # Additional cleaning for common issues
        cleaned_response = cleaned_response.strip()
        
        # Parse JSON response
        try:
            result = json.loads(cleaned_response)
            
            # Validate basic structure
            if not isinstance(result, dict):
                raise ValueError("Response is not a JSON object")
            
            # Ensure top-level structure
            if "success" not in result:
                result["success"] = True
            if "total_bills" not in result:
                result["total_bills"] = 0
            if "bills" not in result:
                result["bills"] = []
            
            # Ensure each bill has complete structure
            validated_bills = []
            for i, bill in enumerate(result["bills"]):
                validated_bill = ensure_bill_structure(bill)
                # Ensure bill_index is set correctly
                validated_bill["bill_index"] = i + 1
                validated_bills.append(validated_bill)
            
            result["bills"] = validated_bills
            result["total_bills"] = len(validated_bills)
            
            print(f"Successfully parsed and validated response with {len(result['bills'])} bills")
            return {
                "success": True,
                "result": result
            }
            
        except json.JSONDecodeError as e:
            # Provide more detailed error information
            error_position = getattr(e, 'pos', 0)
            context_start = max(0, error_position - 50)
            context_end = min(len(cleaned_response), error_position + 50)
            context = cleaned_response[context_start:context_end]
            
            return {
                "success": False,
                "error": f"Invalid JSON response at position {error_position}: {str(e)}",
                "context": context,
                "raw_response": cleaned_response[:1000],
                "cleaned_length": len(cleaned_response)
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Error parsing response: {str(e)}",
            "raw_response": raw_response[:500] if raw_response else "No response"
        }

def main(data):
    """
    Main function for combined bill processing (splitting + extraction)
    
    Args:
        data (dict): Request data containing:
            - s3_key (str): S3 key path to the PDF document
            - company_name (str): Name of the company receiving the bills
            - bucket_name (str, optional): S3 bucket name
    
    Returns:
        dict: Processing result with structured bill data
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
        
        print(f"Processing bills for company: {company_name}, S3 key: {s3_key}")
        
        # Fetch comprehensive company context from DynamoDB
        company_context = get_company_context(company_name)
        
        if not company_context:
            print(f"⚠️  Warning: No company context found for {company_name}")
            print(f"  Proceeding with default VAT treatment assumptions")
        else:
            print(f"✅ Company context loaded successfully")
        
        # Download PDF from S3
        pdf_content = download_from_s3(s3_key, bucket_name)
        print(f"Downloaded PDF, size: {len(pdf_content)} bytes")
        
        # Process with Claude for combined splitting and extraction
        claude_result = process_bills_with_claude(pdf_content, company_name, company_context)
        
        if not claude_result["success"]:
            return {
                "success": False,
                "error": f"Claude processing failed: {claude_result['error']}"
            }
        
        # Parse the structured response with validation
        parse_result = parse_bill_response(claude_result["raw_response"])
        
        if not parse_result["success"]:
            return {
                "success": False,
                "error": f"Response parsing failed: {parse_result['error']}",
                "raw_response": claude_result["raw_response"],
                "parse_details": parse_result
            }
        
        result_data = parse_result["result"]
        bills = result_data.get("bills", [])
        
        # Validate extracted bill data with company context
        validation_results = validate_bill_data(bills, company_context)
        
        # Count bills with critical issues
        bills_with_issues = sum(1 for v in validation_results if not v["mandatory_fields_present"])
        total_bills = len(bills)
        
        return {
            "success": True,
            "total_bills": total_bills,
            "bills": bills,
            "processing_summary": {
                "bills_processed": total_bills,
                "bills_with_issues": bills_with_issues,
                "success_rate": f"{((total_bills - bills_with_issues) / total_bills * 100):.1f}%" if total_bills > 0 else "0%"
            },
            "validation_results": validation_results,
            "metadata": {
                "company_name": company_name,
                "company_context_loaded": company_context is not None,
                "company_vat_status": company_context.get('is_vat_registered', 'unknown') if company_context else 'unknown',
                "company_reverse_charge_categories": company_context.get('tax_information', {}).get('reverse_charge', []) if company_context else [],
                "company_special_circumstances": list(company_context.get('special_circumstances', {}).keys()) if company_context else [],
                "s3_key": s3_key,
                "token_usage": claude_result["token_usage"]
            }
        }
        
    except Exception as e:
        print(f"Bill processing error: {str(e)}")
        return {
            "success": False,
            "error": f"Internal processing error: {str(e)}"
        }

def health_check():
    """Health check for the bill processing service"""
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
            "service": "claude-bill-processing",
            "version": "8.0",
            "capabilities": [
                "document_splitting",
                "data_extraction", 
                "monetary_calculation",
                "confidence_scoring",
                "vendor_bill_processing",
                "enhanced_reverse_charge_detection",
                "odoo_accounting_integration",
                "8_category_reverse_charge_support",
                "enhanced_category1_construction_property_detection",
                "greek_language_support",
                "line_level_account_assignment",
                "mixed_service_bill_handling",
                "granular_expense_categorization",
                "ias40_property_capitalization",
                "comprehensive_company_context_integration",
                "vat_registration_aware_processing",
                "non_vat_registered_company_support",
                "dynamodb_company_lookup",
                "industry_specific_guidance",
                "payroll_context_awareness",
                "special_circumstances_handling",
                "business_operations_context",
                "banking_information_context",
                "tax_grid_assignment",
                "cyprus_vat_return_compliance",
                "construction_property_detection",
                "foreign_services_detection",
                "gas_electricity_detection",
                "scrap_metal_detection",
                "electronics_detection",
                "precious_metals_detection",
                "eu_telecom_detection",
                "property_transfer_detection"
            ],
            "anthropic_configured": bool(os.getenv('ANTHROPIC_API_KEY')),
            "aws_configured": bool(os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY')),
            "s3_bucket": os.getenv('S3_BUCKET_NAME', 'company-documents-2025'),
            "dynamodb_table": "users",
            "odoo_accounting_logic": "integrated",
            "vat_compliance": "Cyprus VAT Law - All 8 Reverse Charge Categories with Enhanced Category 1",
            "accounting_standards": "IAS 40 Investment Property Capitalization",
            "supported_languages": "English, Greek (Ελληνικά)",
            "new_features": [
                "Comprehensive company context from DynamoDB",
                "Tax information and reverse charge category awareness", 
                "Payroll information for document classification",
                "Special circumstances handling (construction, retail)",
                "Business operations context integration",
                "Banking information awareness",
                "Tax grid assignment for Cyprus VAT return",
                "Enhanced VAT account selection logic"
            ]
        }
        
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e)
        }