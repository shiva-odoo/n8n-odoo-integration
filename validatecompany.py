import re
import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
import os
import logging

# ============================================================================
# CYPRUS COMPANY REGISTRY - NAME AND REGISTRATION PROCESSING FUNCTIONS
# ============================================================================

def process_company_name(name):
    """
    Process company name: convert to uppercase and trim spaces
    Args:
        name (str): The company name to process
    Returns:
        str: Processed company name (uppercase, trimmed)
    """
    if not name or not isinstance(name, str):
        return ''
    
    # Trim spaces from both sides and convert to uppercase
    return name.strip().upper()

def process_director_name(name):
    """
    Process director name: convert to uppercase and trim spaces
    Args:
        name (str): The director name to process
    Returns:
        str: Processed director name (uppercase, trimmed)
    """
    if not name or not isinstance(name, str):
        return ''
    
    # Trim spaces from both sides and convert to uppercase
    return name.strip().upper()

def process_registration_number(reg_number):
    """
    Extract and validate registration number (numbers only)
    Args:
        reg_number (str): The registration number to process
    Returns:
        str: Extracted numbers only, or empty string if invalid
    """
    if not reg_number or not isinstance(reg_number, str):
        return ''
    
    # Extract only numbers using regex (removes ΗΕ prefix and any non-digits)
    numbers_only = re.sub(r'\D', '', reg_number)
    
    # Validate that we have at least one digit
    if re.match(r'^\d+$', numbers_only):
        return numbers_only
    return ''

def is_valid_company_name(name):
    """
    Validate company name format (basic validation)
    Args:
        name (str): The company name to validate
    Returns:
        bool: True if valid format
    """
    if not name or not isinstance(name, str):
        return False
    
    # More permissive validation for company names with special characters
    name_regex = re.compile(r'^[A-Za-z0-9\s&.,\'\-()]+$')
    trimmed_name = name.strip()
    
    return len(trimmed_name) > 0 and name_regex.match(trimmed_name) is not None

def is_valid_registration_number(reg_number):
    """
    Validate registration number format (numbers only, specific length if needed)
    Args:
        reg_number (str): The registration number to validate
    Returns:
        bool: True if valid format
    """
    if not reg_number or not isinstance(reg_number, str):
        return False
    
    # For Cyprus companies, allow flexibility for different lengths
    number_regex = re.compile(r'^\d{4,8}$')  # Allow 4-8 digits for flexibility
    clean_number = re.sub(r'\D', '', reg_number)
    
    return number_regex.match(clean_number) is not None

# ============================================================================
# CYPRUS-SPECIFIC VALIDATION (MORE FLEXIBLE)
# ============================================================================

# More permissive regex patterns for Cyprus companies
cyprus_company_name_regex = re.compile(r'^[A-Z0-9\s&.,\'\-()]+$')  # Added parentheses and more chars
cyprus_registration_regex = re.compile(r'^\d{4,8}$')  # More flexible length (4-8 digits)

def is_valid_cyprus_company_name(name):
    """
    Cyprus company name validation (more permissive)
    Args:
        name (str): Processed company name (should be uppercase, trimmed)
    Returns:
        bool: True if matches Cyprus company name pattern
    """
    if not name:
        return False
    return cyprus_company_name_regex.match(name) is not None and len(name) > 0

def is_valid_cyprus_registration_number(reg_number):
    """
    Cyprus registration number validation (flexible)
    Args:
        reg_number (str): Registration number (should be numbers only)
    Returns:
        bool: True if matches Cyprus registration pattern
    """
    if not reg_number:
        return False
    return cyprus_registration_regex.match(reg_number) is not None

def process_company_data(raw_name, raw_reg_number):
    """
    Process and validate both company name and registration number
    Args:
        raw_name (str): Raw company name input
        raw_reg_number (str): Raw registration number input
    Returns:
        dict: Object with processed values and validation results
    """
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

# ============================================================================
# GOOGLE TRANSLATE INTEGRATION
# ============================================================================

def translate_text_google(text, target_language='en', source_language='el'):
    """
    Translate text using Google Translate API or googletrans library
    Args:
        text (str): Text to translate
        target_language (str): Target language code (default: 'en')
        source_language (str): Source language code (default: 'el' for Greek)
    Returns:
        str: Translated text or original text if translation fails
    """
    try:
        from googletrans import Translator
        translator = Translator()
        
        # Detect language first
        detection = translator.detect(text)
        print(f"Detected language: {detection.lang} (confidence: {detection.confidence})")
        
        # Only translate if source is different from target
        if detection.lang != target_language:
            result = translator.translate(text, src=source_language, dest=target_language)
            translated = result.text.strip().upper()
            print(f"Translation: '{text}' -> '{translated}'")
            return translated
        else:
            print(f"Text already in target language: {text}")
            return text.strip().upper()
            
    except ImportError:
        print("googletrans library not installed. Install with: pip install googletrans==4.0.0-rc1")
        return text.strip().upper()
    except Exception as e:
        print(f"Translation failed: {e}")
        return text.strip().upper()

# ============================================================================
# HTML PARSING FUNCTIONS
# ============================================================================

def parse_company_data(html_content):
    """Parse HTML content and extract company information as JSON"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    company_data = {
        "success": False,
        "company_info": {},
        "errors": [],
        "raw_tables": []
    }
    
    try:
        # Look for error messages first
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
        
        # Look for result tables or data containers
        tables = soup.find_all('table')
        
        for i, table in enumerate(tables):
            table_data = []
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_data = [cell.get_text(strip=True) for cell in cells]
                    if any(row_data):  # Only add non-empty rows
                        table_data.append(row_data)
            
            if table_data:
                company_data["raw_tables"].append({
                    "table_index": i,
                    "data": table_data
                })
        
        # Try to extract specific company information
        text_content = soup.get_text()
        
        # Extract registration number
        reg_patterns = [
            r'Registration\s*(?:Number|No\.?)\s*:?\s*(\d+)',
            r'Reg\.?\s*(?:Number|No\.?)\s*:?\s*(\d+)',
            r'Company\s*(?:Number|No\.?)\s*:?\s*(\d+)'
        ]
        
        for pattern in reg_patterns:
            reg_match = re.search(pattern, text_content, re.IGNORECASE)
            if reg_match:
                raw_reg = reg_match.group(1)
                company_data["company_info"]["registration_number"] = process_registration_number(raw_reg)
                break
        
        # Extract company name
        name_patterns = [
            r'Company\s*Name\s*:?\s*([^\n\r]+)',
            r'Name\s*:?\s*([^\n\r]+)',
            r'Entity\s*Name\s*:?\s*([^\n\r]+)'
        ]
        
        for pattern in name_patterns:
            name_match = re.search(pattern, text_content, re.IGNORECASE)
            if name_match:
                raw_name = name_match.group(1).strip()
                if len(raw_name) > 3:  # Avoid capturing short/empty matches
                    company_data["company_info"]["company_name"] = process_company_name(raw_name)
                    break
        
        # Extract status
        status_match = re.search(r'Status\s*:?\s*([^\n\r]+)', text_content, re.IGNORECASE)
        if status_match:
            company_data["company_info"]["status"] = status_match.group(1).strip()
        
        # Extract incorporation date
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
        
        # Look for address information
        address_match = re.search(r'Address\s*:?\s*([^\n\r]+(?:\n[^\n\r]+)*)', text_content, re.IGNORECASE)
        if address_match:
            company_data["company_info"]["address"] = address_match.group(1).strip()
        
        # Check if we found any meaningful data
        if company_data["company_info"] or company_data["raw_tables"]:
            company_data["success"] = True
        
        # If no structured data but no errors, might be a "no results" case
        if not company_data["errors"] and not company_data["company_info"] and not company_data["raw_tables"]:
            if "no results" in text_content.lower() or "not found" in text_content.lower():
                company_data["errors"].append("No results found for the search criteria")
            else:
                company_data["errors"].append("Unable to parse response - no recognizable data structure found")
        
    except Exception as e:
        company_data["errors"].append(f"Parsing error: {str(e)}")
    
    return company_data

def parse_directors_data(html_content):
    """Parse HTML content from directors page and extract director information"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    directors_data = {
        "success": False,
        "directors": [],
        "errors": [],
        "raw_tables": []
    }
    
    try:
        # Look for error messages first
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
        
        # Look for director tables or data containers
        tables = soup.find_all('table')
        
        for i, table in enumerate(tables):
            table_data = []
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_data = [cell.get_text(strip=True) for cell in cells]
                    if any(row_data):  # Only add non-empty rows
                        table_data.append(row_data)
            
            if table_data:
                directors_data["raw_tables"].append({
                    "table_index": i,
                    "data": table_data
                })
        
        # Extract director names from tables
        text_content = soup.get_text()
        
        # Look for director names in tables
        for table in directors_data["raw_tables"]:
            for row in table["data"]:
                for cell in row:
                    # Check if cell contains a person's name (basic heuristic)
                    if len(cell) > 3 and any(char.isalpha() for char in cell):
                        # Filter out common non-name entries (English and Greek)
                        exclude_terms = [
                            'Όνομα', 'Name', 'Διευθυντής', 'Director', 'Γραμματέας', 'Secretary', 
                            'Ημερομηνία', 'Date', 'Στοιχεία', 'Details', 'Τύπος', 'Type',
                            'Position', 'Θέση', 'Status', 'Κατάσταση', 'Address', 'Διεύθυνση',
                            'Registration', 'Εγγραφή', 'Company', 'Εταιρεία'
                        ]
                        
                        if not any(term.lower() in cell.lower() for term in exclude_terms):
                            # Check if it looks like a name (has at least 2 words with letters)
                            words = cell.split()
                            if len(words) >= 2 and all(any(c.isalpha() for c in word) for word in words):
                                # Process as potential director name
                                processed_name = process_director_name(cell)
                                if processed_name and processed_name not in directors_data["directors"]:
                                    directors_data["directors"].append(processed_name)
        
        # Check if we found any directors
        if directors_data["directors"] or directors_data["raw_tables"]:
            directors_data["success"] = True
        
        # If no directors found but no errors
        if not directors_data["errors"] and not directors_data["directors"]:
            directors_data["errors"].append("No directors found on this page")
        
    except Exception as e:
        directors_data["errors"].append(f"Parsing error: {str(e)}")
    
    return directors_data

# ============================================================================
# ENHANCED DIRECTOR VALIDATION WITH GOOGLE TRANSLATE
# ============================================================================

def validate_director_with_translation(director_name, directors_list):
    """
    Advanced director validation with Google Translate for Greek/English matching
    Args:
        director_name (str): Director name to validate
        directors_list (list): List of director names from the website
    Returns:
        dict: Enhanced validation result with translation attempts
    """
    processed_director = process_director_name(director_name)
    
    validation_result = {
        "director_name": director_name,
        "processed_director_name": processed_director,
        "directors_found": directors_list,
        "director_valid": False,
        "matched_name": None,
        "translation_attempts": [],
        "match_method": None
    }
    
    print(f"\nValidating director: '{processed_director}' against {len(directors_list)} found directors")
    
    # Strategy 1: Exact match
    if processed_director in directors_list:
        validation_result["director_valid"] = True
        validation_result["matched_name"] = processed_director
        validation_result["match_method"] = "exact_match"
        print(f"EXACT MATCH found: {processed_director}")
        return validation_result
    
    # Strategy 2: Case-insensitive match
    for director in directors_list:
        if processed_director.upper() == director.upper():
            validation_result["director_valid"] = True
            validation_result["matched_name"] = director
            validation_result["match_method"] = "case_insensitive_match"
            print(f"CASE INSENSITIVE MATCH found: {director}")
            return validation_result
    
    # Strategy 3: Google Translate each director name to English
    print("Attempting Google Translate for director names...")
    
    for director in directors_list:
        try:
            # Translate director name from Greek to English
            translated_director = translate_text_google(director, target_language='en', source_language='el')
            validation_result["translation_attempts"].append({
                "original": director,
                "translated": translated_director
            })
            
            # Check if translated name matches
            if processed_director == translated_director:
                validation_result["director_valid"] = True
                validation_result["matched_name"] = director
                validation_result["match_method"] = "google_translate_exact"
                print(f"GOOGLE TRANSLATE EXACT MATCH: '{director}' -> '{translated_director}'")
                return validation_result
            
            # Check word-by-word match for translated name
            director_words = processed_director.split()
            translated_words = translated_director.split()
            
            if len(director_words) >= 2 and len(translated_words) >= 2:
                # Check if all words from search name appear in translated name
                if all(word in translated_director for word in director_words):
                    validation_result["director_valid"] = True
                    validation_result["matched_name"] = director
                    validation_result["match_method"] = "google_translate_partial"
                    print(f"GOOGLE TRANSLATE PARTIAL MATCH: '{director}' -> '{translated_director}'")
                    return validation_result
                
                # Check reverse - if all words from translated name appear in search name
                if all(word in processed_director for word in translated_words):
                    validation_result["director_valid"] = True
                    validation_result["matched_name"] = director
                    validation_result["match_method"] = "google_translate_reverse"
                    print(f"GOOGLE TRANSLATE REVERSE MATCH: '{director}' -> '{translated_director}'")
                    return validation_result
            
        except Exception as e:
            print(f"Translation failed for '{director}': {e}")
            continue
    
    # Strategy 4: Translate search name to Greek and compare
    print("Translating search name to Greek...")
    try:
        translated_search_name = translate_text_google(processed_director, target_language='el', source_language='en')
        validation_result["translation_attempts"].append({
            "original": processed_director,
            "translated_to_greek": translated_search_name
        })
        
        for director in directors_list:
            if translated_search_name == director.upper():
                validation_result["director_valid"] = True
                validation_result["matched_name"] = director
                validation_result["match_method"] = "english_to_greek_translate"
                print(f"ENGLISH TO GREEK MATCH: '{processed_director}' -> '{translated_search_name}' = '{director}'")
                return validation_result
            
            # Partial match with translated Greek name
            search_words = translated_search_name.split()
            director_words = director.split()
            if len(search_words) >= 2 and len(director_words) >= 2:
                if all(word in director.upper() for word in search_words):
                    validation_result["director_valid"] = True
                    validation_result["matched_name"] = director
                    validation_result["match_method"] = "english_to_greek_partial"
                    print(f"ENGLISH TO GREEK PARTIAL: '{processed_director}' -> '{translated_search_name}' ~ '{director}'")
                    return validation_result
    
    except Exception as e:
        print(f"English to Greek translation failed: {e}")
    
    # Strategy 5: Phonetic/fuzzy matching
    print("Attempting fuzzy matching...")
    try:
        from difflib import SequenceMatcher
        
        best_match_ratio = 0
        best_match_director = None
        
        for director in directors_list:
            # Try direct comparison
            ratio = SequenceMatcher(None, processed_director, director.upper()).ratio()
            if ratio > best_match_ratio:
                best_match_ratio = ratio
                best_match_director = director
            
            # Try comparison with translated version if available
            for attempt in validation_result["translation_attempts"]:
                if attempt["original"] == director and "translated" in attempt:
                    translated_ratio = SequenceMatcher(None, processed_director, attempt["translated"]).ratio()
                    if translated_ratio > best_match_ratio:
                        best_match_ratio = translated_ratio
                        best_match_director = director
        
        # If similarity is high enough (>= 0.8), consider it a match
        if best_match_ratio >= 0.8:
            validation_result["director_valid"] = True
            validation_result["matched_name"] = best_match_director
            validation_result["match_method"] = f"fuzzy_match_{best_match_ratio:.2f}"
            print(f"FUZZY MATCH ({best_match_ratio:.2f}): '{processed_director}' ~ '{best_match_director}'")
            return validation_result
            
    except Exception as e:
        print(f"Fuzzy matching failed: {e}")
    
    print(f"NO MATCH FOUND for '{processed_director}'")
    print(f"Available directors: {directors_list}")
    return validation_result

def validate_director(director_name, directors_list):
    """
    Main director validation function - now uses Google Translate
    """
    return validate_director_with_translation(director_name, directors_list)

# ============================================================================
# ENHANCED CHROME TRANSLATE FUNCTIONS
# ============================================================================

def enhanced_trigger_translate(driver):
    """
    Enhanced translation trigger with multiple strategies
    """
    try:
        print("Triggering enhanced translation...")
        
        # Strategy 1: Set Chrome translate preferences via JavaScript
        try:
            driver.execute_script("""
                // Try to trigger Google Translate
                if (typeof google !== 'undefined' && google.translate) {
                    if (google.translate.TranslateElement) {
                        google.translate.TranslateElement({
                            pageLanguage: 'el', 
                            includedLanguages: 'en',
                            autoDisplay: false
                        }, 'google_translate_element');
                    }
                }
                
                // Set page language attributes to trigger auto-translate
                document.documentElement.lang = 'el';
                document.documentElement.setAttribute('translate', 'yes');
                
                // Add Google Translate meta tag
                var meta = document.createElement('meta');
                meta.name = 'google';
                meta.content = 'translate';
                document.getElementsByTagName('head')[0].appendChild(meta);
                
                // Try to trigger Chrome's built-in translate
                if (window.chrome && window.chrome.runtime) {
                    try {
                        window.chrome.runtime.sendMessage({action: 'translate'});
                    } catch(e) {}
                }
            """)
            time.sleep(3)
            print("JavaScript translation triggers executed")
        except Exception as e:
            print(f"JavaScript translate failed: {e}")
        
        # Strategy 2: Check for existing translate elements and interact with them
        translate_selectors = [
            ".goog-te-banner-frame",
            ".goog-te-combo",
            "[id*='google_translate']",
            ".translate-button",
            "[data-translate-button]",
            "select[class*='goog-te']",
            ".goog-te-menu-value span"
        ]
        
        for selector in translate_selectors:
            try:
                translate_elems = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in translate_elems:
                    if elem.is_displayed() and elem.is_enabled():
                        elem.click()
                        time.sleep(2)
                        print(f"Translation triggered via {selector}")
                        break
            except Exception as e:
                continue
        
        # Strategy 3: Try to find and select English from dropdown
        try:
            # Look for translate dropdown options
            english_options = driver.find_elements(By.XPATH, "//option[contains(text(), 'English') or contains(text(), 'Αγγλικά')]")
            for option in english_options:
                if option.is_displayed():
                    option.click()
                    time.sleep(2)
                    print("English selected from translate dropdown")
                    break
        except:
            pass
        
        # Strategy 4: Detect Greek text and add delay for Chrome auto-detect
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            greek_chars = sum(1 for char in page_text if char in "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψω")
            if greek_chars > 10:
                print(f"Greek text detected ({greek_chars} characters) - Chrome should offer translation")
                # Add extra delay for Chrome to auto-detect and offer translation
                time.sleep(5)
                
                # Try to trigger the translate bar
                driver.execute_script("""
                    // Simulate user interaction to trigger translate detection
                    document.body.click();
                    setTimeout(function() {
                        // Try to find and click translate bar if it appears
                        var translateBar = document.querySelector('.goog-te-banner-frame, [id*="translate"], .translate-message');
                        if (translateBar) {
                            translateBar.click();
                        }
                    }, 1000);
                """)
                time.sleep(3)
            else:
                print("No significant Greek text detected")
        except Exception as e:
            print(f"Greek text detection failed: {e}")
        
        # Strategy 5: Try keyboard shortcut for translate (Ctrl+Shift+T)
        try:
            actions = ActionChains(driver)
            actions.key_down(Keys.CONTROL).key_down(Keys.SHIFT).send_keys('t').key_up(Keys.SHIFT).key_up(Keys.CONTROL).perform()
            time.sleep(2)
            print("Translation keyboard shortcut attempted")
        except:
            pass
            
        print("All translation triggers completed")
        
    except Exception as e:
        print(f"Translation trigger failed: {e}")

# ============================================================================
# MAIN SEARCH FUNCTIONS
# ============================================================================

def search_cyprus_company_with_selenium(reg_number, company_name, director_name):
    """
    Perform the actual Cyprus company registry search with enhanced director validation using Selenium
    """
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    # CRITICAL: Add language settings for Google Translate integration
    chrome_options.add_argument("--lang=en")
    chrome_options.add_experimental_option("prefs", {
        "translate_whitelists": {"el": "en"},  # Greek to English
        "translate": {"enabled": True},
        "translate_ranker_model": True
    })
    
    # Make headless optional based on environment
    if os.environ.get('HEADLESS', 'true').lower() == 'true':
        chrome_options.add_argument("--headless")
    
    # Add user agent to avoid detection
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Navigate to the webpage (English version)
        print("Navigating to Cyprus eFiling website (English)...")
        driver.get("https://efiling.drcor.mcit.gov.cy/DrcorPublic/SearchForm.aspx?sc=0&lang=en")
        
        # Wait for page to load
        wait = WebDriverWait(driver, 15)
        
        # Fill registration number field
        print(f"Filling registration number: {reg_number}")
        reg_number_field = wait.until(
            EC.presence_of_element_located((By.ID, "ctl00_cphMyMasterCentral_ucSearch_txtNumber"))
        )
        reg_number_field.clear()
        reg_number_field.send_keys(reg_number)
        
        # Fill name field
        print(f"Filling company name: {company_name}")
        name_field = driver.find_element(By.ID, "ctl00_cphMyMasterCentral_ucSearch_txtName")
        name_field.clear()
        name_field.send_keys(company_name)
        
        # Click the Go button
        print("Clicking search button...")
        go_button = driver.find_element(By.XPATH, "//*[@id='ctl00_cphMyMasterCentral_ucSearch_lbtnSearch']")
        go_button.click()
        
        # Wait for results to load
        print("Waiting for search results...")
        time.sleep(5)
        
        # Wait for the page to change or results to appear
        try:
            wait.until(lambda driver: driver.current_url != "https://efiling.drcor.mcit.gov.cy/DrcorPublic/SearchForm.aspx?sc=0&lang=en")
        except TimeoutException:
            print("Page didn't change - checking for results on same page...")
        
        # Get the company search results
        html_response = driver.page_source
        company_search_result = parse_company_data(html_response)
        
        search_response = {
            "success": False,
            "overall_valid": False,
            "director_valid": False,
            "company_search": company_search_result,
            "director_validation": {},
            "search_url": driver.current_url,
            "errors": []
        }
        
        # Check if company search was successful
        if not company_search_result["success"]:
            search_response["errors"] = company_search_result.get("errors", [])
            search_response["errors"].append("Company search failed - no valid results found")
            search_response["overall_valid"] = False
            return search_response
        
        # Company found - set overall_valid to True
        search_response["overall_valid"] = True
        search_response["success"] = True
        
        # Try to click on the first result and navigate to directors page
        try:
            print("Company found! Navigating to details page...")
            
            # Look for the results table row with multiple fallback selectors
            result_selectors = [
                "tr.basket",
                "tr[class*='basket']", 
                ".CompanyDetails a",
                "table tr td a",
                "tr td:first-child"
            ]
            
            result_clicked = False
            for selector in result_selectors:
                try:
                    result_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if result_elements:
                        result_element = result_elements[0]  # Click first result
                        driver.execute_script("arguments[0].click();", result_element)
                        result_clicked = True
                        print(f"Clicked search result using selector: {selector}")
                        break
                except Exception as e:
                    print(f"Selector {selector} failed: {e}")
                    continue
            
            if not result_clicked:
                search_response["errors"].append("Could not click on search results")
                search_response["director_validation"] = {
                    "error": "Could not access company details page",
                    "director_valid": False
                }
                return search_response
            
            time.sleep(3)
            
            # Enhanced directors tab navigation with page inspection
            print("Looking for directors tab...")
            
            # Get all clickable elements
            all_links = driver.find_elements(By.TAG_NAME, "a")
            all_buttons = driver.find_elements(By.TAG_NAME, "button")
            all_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='button'], input[type='submit']")
            all_spans = driver.find_elements(By.TAG_NAME, "span")
            all_divs = driver.find_elements(By.CSS_SELECTOR, "div[onclick], div[class*='tab'], div[id*='tab']")
            
            # Look for directors-related text in all elements
            directors_keywords = ['directors', 'διευθυντές', 'director', 'διευθυντής', 'board', 'officers']
            potential_directors_elements = []
            
            all_elements = all_links + all_buttons + all_inputs + all_spans + all_divs
            
            for element in all_elements:
                try:
                    element_text = element.text.lower().strip()
                    element_id = element.get_attribute('id') or ''
                    element_class = element.get_attribute('class') or ''
                    element_onclick = element.get_attribute('onclick') or ''
                    
                    # Check if element contains directors-related keywords
                    if any(keyword in element_text for keyword in directors_keywords) or \
                       any(keyword in element_id.lower() for keyword in directors_keywords) or \
                       any(keyword in element_class.lower() for keyword in directors_keywords) or \
                       any(keyword in element_onclick.lower() for keyword in directors_keywords):
                        
                        potential_directors_elements.append({
                            'element': element,
                            'text': element_text,
                            'id': element_id,
                            'class': element_class,
                            'onclick': element_onclick,
                            'tag': element.tag_name
                        })
                        
                except Exception as e:
                    continue
            
            # Try to click on potential directors elements
            directors_tab_clicked = False
            
            if potential_directors_elements:
                print(f"Found {len(potential_directors_elements)} potential directors elements")
                
                for i, elem_info in enumerate(potential_directors_elements):
                    try:
                        element = elem_info['element']
                        print(f"Attempting click #{i+1}: {elem_info['tag']} with text '{elem_info['text'][:30]}...'")
                        
                        # Try multiple click methods
                        click_methods = [
                            lambda: element.click(),
                            lambda: driver.execute_script("arguments[0].click();", element),
                            lambda: driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true}));", element),
                            lambda: ActionChains(driver).click(element).perform()
                        ]
                        
                        for method_idx, click_method in enumerate(click_methods):
                            try:
                                click_method()
                                time.sleep(2)
                                
                                # Check if page changed or directors content appeared
                                page_source = driver.page_source.lower()
                                
                                if 'directors' in page_source or 'διευθυντές' in page_source:
                                    directors_tab_clicked = True
                                    print(f"Successfully clicked directors element (method {method_idx+1})")
                                    break
                                    
                            except Exception as e:
                                continue
                        
                        if directors_tab_clicked:
                            break
                            
                    except Exception as e:
                        continue
            
            # Fallback: Try original selectors
            if not directors_tab_clicked:
                print("Trying original directors tab selectors...")
                
                director_tab_selectors = [
                    "#ctl00_cphMyMasterCentral_directors",
                    "a[href*='directors']",
                    ".tab-directors",
                    "[id*='directors']",
                    "[class*='directors']",
                    "//a[contains(text(), 'Directors')]",
                    "//a[contains(text(), 'Διευθυντές')]"
                ]
                
                for selector in director_tab_selectors:
                    try:
                        if selector.startswith("//"):
                            elements = driver.find_elements(By.XPATH, selector)
                        else:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        
                        for element in elements:
                            try:
                                if element.is_displayed() and element.is_enabled():
                                    driver.execute_script("arguments[0].click();", element)
                                    time.sleep(3)
                                    
                                    # Check if directors content appeared
                                    if 'directors' in driver.page_source.lower() or 'διευθυντές' in driver.page_source.lower():
                                        directors_tab_clicked = True
                                        print(f"Directors tab clicked using: {selector}")
                                        break
                            except Exception as e:
                                continue
                        
                        if directors_tab_clicked:
                            break
                            
                    except Exception as e:
                        continue
            
            # Check if we're already on directors page or if directors info is visible
            if not directors_tab_clicked:
                print("Checking if directors information is already visible...")
                page_content = driver.page_source.lower()
                
                if 'directors' in page_content or 'διευθυντές' in page_content:
                    print("Directors information appears to be already visible on the page")
                    directors_tab_clicked = True
            
            # Trigger Google Translate
            if directors_tab_clicked:
                print("Triggering Google Translate for directors page...")
                enhanced_trigger_translate(driver)
                time.sleep(5)
            
            # Parse directors page
            print("Parsing directors information...")
            directors_html = driver.page_source
            directors_result = parse_directors_data(directors_html)
            
            # Also try to extract directors from page text using regex patterns
            if not directors_result.get('directors'):
                print("Attempting regex-based director extraction from page text...")
                page_text = driver.find_element(By.TAG_NAME, "body").text
                
                # Enhanced director name patterns (both English and Greek)
                director_patterns = [
                    r'(?:Director|Διευθυντής|Board Member|Μέλος Διοικητικού)\s*:?\s*([A-ZΑ-Ω][A-Za-zΑ-Ωα-ω\s\.]+)',
                    r'([A-ZΑ-Ω][A-Za-zΑ-Ωα-ω]+\s+[A-ZΑ-Ω][A-Za-zΑ-Ωα-ω]+)(?:\s*-\s*(?:Director|Διευθυντής))',
                    r'Name\s*:?\s*([A-ZΑ-Ω][A-Za-zΑ-Ωα-ω\s\.]+)',
                    r'Όνομα\s*:?\s*([Α-Ω][Α-Ωα-ω\s\.]+)',
                    # Look for capitalized names (common format)
                    r'\b([A-ZΑ-Ω][A-Za-zΑ-Ωα-ω]+\s+[A-ZΑ-Ω][A-Za-zΑ-Ωα-ω]+(?:\s+[A-ZΑ-Ω][A-Za-zΑ-Ωα-ω]+)?)\b'
                ]
                
                potential_directors = set()
                for pattern in director_patterns:
                    matches = re.findall(pattern, page_text, re.MULTILINE)
                    for match in matches:
                        name = match.strip()
                        # Filter out common false positives
                        exclude_terms = [
                            'Cyprus', 'Company', 'Registration', 'Search', 'Details', 'Information',
                            'Date', 'Status', 'Address', 'Email', 'Phone', 'Website', 'Limited',
                            'Ltd', 'Corporation', 'Corp', 'Public', 'Private'
                        ]
                        
                        if (len(name.split()) >= 2 and 
                            len(name) > 5 and 
                            not any(term.lower() in name.lower() for term in exclude_terms) and
                            any(c.isalpha() for c in name)):
                            potential_directors.add(process_director_name(name))
                
                if potential_directors:
                    print(f"Regex extraction found potential directors: {list(potential_directors)}")
                    directors_result['directors'].extend(list(potential_directors))
                    directors_result['success'] = True
            
            print(f"Directors parsing result: Success={directors_result.get('success', False)}")
            print(f"   Found {len(directors_result.get('directors', []))} directors: {directors_result.get('directors', [])}")
            
            # Validate director with Google Translate
            print("Starting enhanced director validation with Google Translate...")
            director_validation = validate_director_with_translation(director_name, directors_result.get('directors', []))
            search_response["director_validation"] = director_validation
            search_response["director_valid"] = director_validation["director_valid"]
            
            if director_validation["director_valid"]:
                print(f"Director validation SUCCESSFUL!")
                print(f"   Method: {director_validation['match_method']}")
                print(f"   Matched: {director_validation['matched_name']}")
            else:
                print(f"Director validation FAILED")
                print(f"   Search name: {director_validation['processed_director_name']}")
                print(f"   Found directors: {director_validation['directors_found']}")
                
                # If no directors found, add helpful error message
                if not directors_result.get('directors'):
                    search_response["errors"].append("No director information found on the company page")
                else:
                    search_response["errors"].append(f"Director '{director_name}' not found among listed directors")
            
        except (TimeoutException, NoSuchElementException) as e:
            search_response["director_validation"] = {
                "error": f"Could not access directors page: {str(e)}",
                "director_valid": False,
                "directors_found": [],
                "translation_attempts": []
            }
            search_response["errors"].append(f"Directors page navigation failed: {str(e)}")
        
        return search_response
        
    except Exception as e:
        return {
            "success": False,
            "overall_valid": False,
            "director_valid": False,
            "error": f"Search failed: {str(e)}",
            "errors": [f"Critical error: {str(e)}"]
        }
    finally:
        # Close the browser
        print("Closing browser...")
        driver.quit()

def search_cyprus_company_with_director_validation(data):
    """
    Main function to search Cyprus company registry with director validation
    
    Expected data format:
    {
        "company_name": "KYRASTEL ENTERPRISES LTD",
        "registration_number": "474078",
        "director_name": "STELIOS KYRANIDES",  # Required for director validation
        "perform_search": true  # Set to true to perform actual search
    }
    
    Returns:
        dict: Validation results and search results with director validation
    """
    
    # Validate required fields
    if not data.get('company_name') and not data.get('registration_number'):
        return {
            'success': False,
            'overall_valid': False,
            'director_valid': False,
            'error': 'Either company_name or registration_number is required',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    company_name = data.get('company_name', '')
    registration_number = data.get('registration_number', '')
    director_name = data.get('director_name', '')
    perform_search = data.get('perform_search', False)
    
    # Process and validate the company data
    processed_data = process_company_data(company_name, registration_number)
    processed_director = process_director_name(director_name)
    
    # Prepare initial response
    response = {
        'success': True,
        'overall_valid': False,  # Will be set based on company presence
        'director_valid': False,
        'validation': {
            'company_name': {
                'original': processed_data['original']['name'],
                'processed': processed_data['processed']['name'],
                'is_valid': processed_data['validation']['name_valid'],
                'cyprus_valid': processed_data['validation']['cyprus_name_valid']
            },
            'registration_number': {
                'original': processed_data['original']['registration'],
                'processed': processed_data['processed']['registration'],
                'is_valid': processed_data['validation']['reg_number_valid'],
                'cyprus_valid': processed_data['validation']['cyprus_reg_number_valid']
            },
            'director_name': {
                'original': director_name,
                'processed': processed_director,
                'is_valid': bool(processed_director)
            },
            'input_format_valid': (
                processed_data['validation']['cyprus_name_valid'] and 
                processed_data['validation']['cyprus_reg_number_valid'] and
                bool(processed_director)
            )
        },
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Add validation summary
    validation_issues = []
    if not processed_data['validation']['cyprus_name_valid']:
        validation_issues.append("Company name format is invalid for Cyprus registry")
    if not processed_data['validation']['cyprus_reg_number_valid']:
        validation_issues.append("Registration number format is invalid")
    if not processed_director:
        validation_issues.append("Director name is required for director validation")
    
    if validation_issues:
        response['validation_issues'] = validation_issues
    
    # Perform actual search if requested and basic validation passed
    if perform_search and response['validation']['input_format_valid']:
        try:
            print("Starting Cyprus company search with enhanced director validation...")
            search_results = search_cyprus_company_with_selenium(
                processed_data['processed']['registration'],
                processed_data['processed']['name'],
                processed_director
            )
            response['search'] = search_results
            
            # Update response based on search results
            response['success'] = search_results.get('success', False)
            response['overall_valid'] = search_results.get('overall_valid', False)  # Company present
            response['director_valid'] = search_results.get('director_valid', False)
            
            if search_results.get('errors'):
                response['errors'] = search_results['errors']
            
        except Exception as e:
            response['search'] = {
                'search_performed': False,
                'error': f"Search failed: {str(e)}"
            }
            response['success'] = False
            response['overall_valid'] = False
            response['director_valid'] = False
            response['errors'] = [f"Search failed: {str(e)}"]
    elif perform_search and not response['validation']['input_format_valid']:
        response['search'] = {
            'search_performed': False,
            'error': "Search skipped due to validation failures"
        }
        response['success'] = False
        response['overall_valid'] = False
        response['director_valid'] = False
    
    return response

# ============================================================================
# WRAPPER FUNCTION FOR FLASK INTEGRATION
# ============================================================================


def main(data):
    """
    Main function to execute the enhanced Cyprus company search with Google Translate director validation
    
    Args:
        data (dict): Dictionary with registration_number, company_name, director_name
    
    Returns:
        dict: JSON response with complete search and validation results
    """
    
    
    print("\n" + "="*80)
    print("STARTING ENHANCED CYPRUS COMPANY SEARCH WITH GOOGLE TRANSLATE")
    print("="*80)

    reg_number = data.get("registration_number")
    company_name = data.get("company_name")  
    director_name = data.get("director_name")
    
    print(f"Search Parameters:")
    print(f"   Company: {company_name}")
    print(f"   Registration: {reg_number}")
    print(f"   Director: {director_name}")
    
    # Execute the enhanced search
    result = search_cyprus_company_with_director_validation(data
    )
    
    if result:
        print("\n" + "="*50)
        print("FINAL RESULTS")
        print("="*50)
        print(f"Search Success: {result['success']}")
        print(f"Company Valid: {result['overall_valid']}")
        print(f"Director Valid: {result['director_valid']}")
        
        if result.get('director_validation', {}).get('match_method'):
            print(f"Match Method: {result['director_validation']['match_method']}")
        
        if result.get('errors'):
            print(f"Errors: {result['errors']}")
        
        
        return result
    else:
        print("Enhanced search failed - no response received")
        result = {
            "success": False,
            "overall_valid": False,
            "director_valid": False,
            "errors": ["No response received from search function"],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        return result

# ============================================================================
# TESTING AND FLASK INTEGRATION
# ============================================================================

if __name__ == "__main__":
    # Test the enhanced system
    test_data = {
        "registration_number": "143043",
        "company_name": "A.S.K. Management Consulting Limited", 
        "director_name": "ATHOS KOIRANIDIS",
        "perform_search": True
    }
    
    print("Running test with problematic data...")
    result = main(test_data)
    
    print("\n" + "="*50)
    print("TEST RESULTS")
    print("="*50)
    print(json.dumps(result, indent=2, ensure_ascii=False))