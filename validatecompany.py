import re
import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

# ============================================================================

def process_company_name(name):
    if not name or not isinstance(name, str):
        return ''
    return name.strip().upper()

def process_director_name(name):
    if not name or not isinstance(name, str):
        return ''
    return name.strip().upper()

def process_registration_number(reg_number):
    if not reg_number or not isinstance(reg_number, str):
        return ''
    numbers_only = re.sub(r'\D', '', reg_number)
    if re.match(r'^\d+$', numbers_only):
        return numbers_only
    return ''

def is_valid_company_name(name):
    if not name or not isinstance(name, str):
        return False
    name_regex = re.compile(r'^[A-Za-z0-9\s&.,\'-]+$')
    trimmed_name = name.strip()
    return len(trimmed_name) > 0 and name_regex.match(trimmed_name) is not None

def is_valid_registration_number(reg_number):
    if not reg_number or not isinstance(reg_number, str):
        return False
    number_regex = re.compile(r'^\d{4,8}$')
    clean_number = re.sub(r'\D', '', reg_number)
    return number_regex.match(clean_number) is not None

# ============================================================================
# CYPRUS-SPECIFIC STRICT VALIDATION
# ============================================================================

cyprus_company_name_regex = re.compile(r'^[A-Z0-9\s&.,\'-]+$')
cyprus_registration_regex = re.compile(r'^\d{6}$')

def is_valid_cyprus_company_name(name):
    return cyprus_company_name_regex.match(name) is not None and len(name) > 0

def is_valid_cyprus_registration_number(reg_number):
    return cyprus_registration_regex.match(reg_number) is not None

def process_company_data(raw_name, raw_reg_number):
    processed_name = process_company_name(raw_name)
    processed_reg_number = process_registration_number(raw_reg_number)
    return {
        "original": {
            "name": raw_name,
            "registration": raw_reg_number
        },
        "processed": {
            "name": processed_name,
            "registration": processed_reg_number
        },
        "validation": {
            "name_valid": is_valid_company_name(processed_name),
            "reg_number_valid": is_valid_registration_number(processed_reg_number),
            "cyprus_name_valid": is_valid_cyprus_company_name(processed_name),
            "cyprus_reg_number_valid": is_valid_cyprus_registration_number(processed_reg_number)
        }
    }

def parse_company_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    company_data = {
        "success": False,
        "company_info": {},
        "errors": [],
        "raw_tables": []
    }
    try:
        error_selectors = [
            '.error', '.alert', '[class*="error"]', '.message',
            '#ctl00_cphMyMasterCentral_lblMessage',
            '[id*="Message"]', '[id*="Error"]'
        ]
        for selector in error_selectors:
            error_elements = soup.select(selector)
            for error in error_elements:
                error_text = error.get_text(strip=True)
                if error_text and error_text not in company_data["errors"]:
                    company_data["errors"].append(error_text)
        tables = soup.find_all('table')
        for i, table in enumerate(tables):
            table_data = []
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_data = [cell.get_text(strip=True) for cell in cells]
                    if any(row_data):
                        table_data.append(row_data)
            if table_data:
                company_data["raw_tables"].append({
                    "table_index": i,
                    "data": table_data
                })
        text_content = soup.get_text()
        reg_match = re.search(r'Registration\s*(?:Number|No\.?)\s*:?\s*(\d+)', text_content, re.IGNORECASE)
        if reg_match:
            raw_reg = reg_match.group(1)
            company_data["company_info"]["registration_number"] = process_registration_number(raw_reg)
        name_patterns = [
            r'Company\s*Name\s*:?\s*([^\n\r]+)',
            r'Name\s*:?\s*([^\n\r]+)',
        ]
        for pattern in name_patterns:
            name_match = re.search(pattern, text_content, re.IGNORECASE)
            if name_match:
                raw_name = name_match.group(1).strip()
                if len(raw_name) > 3:
                    company_data["company_info"]["company_name"] = process_company_name(raw_name)
                    break
        status_match = re.search(r'Status\s*:?\s*([^\n\r]+)', text_content, re.IGNORECASE)
        if status_match:
            company_data["company_info"]["status"] = status_match.group(1).strip()
        date_patterns = [
            r'Incorporation\s*Date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'Date\s*of\s*Incorporation\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'Registered\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})'
        ]
        for pattern in date_patterns:
            date_match = re.search(pattern, text_content, re.IGNORECASE)
            if date_match:
                company_data["company_info"]["incorporation_date"] = date_match.group(1)
                break
        address_match = re.search(r'Address\s*:?\s*([^\n\r]+(?:\n[^\n\r]+)*)', text_content, re.IGNORECASE)
        if address_match:
            company_data["company_info"]["address"] = address_match.group(1).strip()
        if company_data["company_info"] or company_data["raw_tables"]:
            company_data["success"] = True
        if not company_data["errors"] and not company_data["company_info"] and not company_data["raw_tables"]:
            if "no results" in text_content.lower() or "not found" in text_content.lower():
                company_data["errors"].append("No results found for the search criteria")
            else:
                company_data["errors"].append("Unable to parse response - no recognizable data structure found")
    except Exception as e:
        company_data["errors"].append(f"Parsing error: {str(e)}")
    return company_data

def parse_directors_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    directors_data = {
        "success": False,
        "directors": [],
        "errors": [],
        "raw_tables": []
    }
    try:
        error_selectors = [
            '.error', '.alert', '[class*="error"]', '.message',
            '#ctl00_cphMyMasterCentral_lblMessage',
            '[id*="Message"]', '[id*="Error"]'
        ]
        for selector in error_selectors:
            error_elements = soup.select(selector)
            for error in error_elements:
                error_text = error.get_text(strip=True)
                if error_text and error_text not in directors_data["errors"]:
                    directors_data["errors"].append(error_text)
        tables = soup.find_all('table')
        for i, table in enumerate(tables):
            table_data = []
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_data = [cell.get_text(strip=True) for cell in cells]
                    if any(row_data):
                        table_data.append(row_data)
            if table_data:
                directors_data["raw_tables"].append({
                    "table_index": i,
                    "data": table_data
                })
        for table in directors_data["raw_tables"]:
            for row in table["data"]:
                for cell in row:
                    if len(cell) > 3 and any(char.isalpha() for char in cell):
                        exclude_terms = ['Όνομα', 'Name', 'Διευθυντής', 'Director', 'Γραμματέας', 'Secretary',
                                         'Ημερομηνία', 'Date', 'Στοιχεία', 'Details', 'Τύπος', 'Type']
                        if not any(term.lower() in cell.lower() for term in exclude_terms):
                            processed_name = process_director_name(cell)
                            if processed_name and processed_name not in directors_data["directors"]:
                                directors_data["directors"].append(processed_name)
        if directors_data["directors"] or directors_data["raw_tables"]:
            directors_data["success"] = True
        if not directors_data["errors"] and not directors_data["directors"]:
            directors_data["errors"].append("No directors found on this page")
    except Exception as e:
        directors_data["errors"].append(f"Parsing error: {str(e)}")
    return directors_data

def search_cyprus_company_with_director_validation(data):
    base_url = "https://efiling.drcor.mcit.gov.cy/DrcorPublic/SearchResults.aspx?lang=EN&name="
    company_name = process_company_name(data.get("company_name", ""))
    registration_number = process_registration_number(data.get("registration_number", ""))
    director_name = process_director_name(data.get("director_name", ""))
    perform_search = data.get("perform_search", False)
    validation_results = process_company_data(company_name, registration_number)
    director_matches = {
        "match_found": False,
        "matching_director": None,
        "all_directors": [],
        "match_method": None
    }
    html_response = None
    director_html_response = None
    if not perform_search:
        return {
            "input": data,
            "validation": validation_results,
            "search_performed": False,
            "message": "Search was skipped as per the flag",
            "timestamp": datetime.now().isoformat()
        }
    try:
        url = f"{base_url}{company_name}"
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        html_response = driver.page_source
        company_data = parse_company_data(html_response)
        company_data["url"] = url
        try:
            link = driver.find_element(By.XPATH, '//a[contains(text(),"Details")]')
            link.click()
            time.sleep(3)
            director_html_response = driver.page_source
            director_data = parse_directors_data(director_html_response)
        except NoSuchElementException:
            director_data = {
                "success": False,
                "directors": [],
                "errors": ["No 'Details' link found for company page"]
            }
        driver.quit()
        all_directors = director_data.get("directors", [])
        director_matches["all_directors"] = all_directors
        if director_name and all_directors:
            for d in all_directors:
                if director_name == d:
                    director_matches["match_found"] = True
                    director_matches["matching_director"] = d
                    director_matches["match_method"] = "exact"
                    break
            if not director_matches["match_found"]:
                for d in all_directors:
                    if director_name in d or d in director_name:
                        director_matches["match_found"] = True
                        director_matches["matching_director"] = d
                        director_matches["match_method"] = "partial"
                        break
        return {
            "input": data,
            "validation": validation_results,
            "search_performed": True,
            "company_data": company_data,
            "director_data": director_data,
            "director_validation": director_matches,
            "html_response": html_response,
            "director_html_response": director_html_response,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "input": data,
            "validation": validation_results,
            "search_performed": True,
            "error": f"Exception occurred during search: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

# ============================================================================
# Main execution function (CLEANED)
# ============================================================================

def main(data):
    """
    Executes Cyprus company registry validator with director validation.
    Args:
        data (dict): {
            "company_name": "KYRASTEL ENTERPRISES LTD",
            "registration_number": "474078",
            "director_name": "STELIOS KYRANIDES",
            "perform_search": True
        }
    """
    print("=== CYPRUS COMPANY REGISTRY VALIDATOR WITH DIRECTOR VALIDATION ===")
    print("Input Data:")
    print(json.dumps(data, indent=2))
    result = search_cyprus_company_with_director_validation(data)
    print("\nValidation Result:")
    print(json.dumps(result, indent=2))

