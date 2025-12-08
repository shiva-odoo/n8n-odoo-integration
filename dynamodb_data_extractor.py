import boto3
import os
from decimal import Decimal
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr

def convert_dynamodb_types(obj):
    """
    Convert DynamoDB types to standard Python types for JSON serialization
    Handles: Decimal, List (L), Map (M), String (S), Number (N), Boolean (BOOL), Null (NULL)
    """
    if obj is None:
        return None
    
    # Handle Decimal types
    if isinstance(obj, Decimal):
        # Convert to int if it's a whole number, otherwise float
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    
    # Handle dictionaries (includes DynamoDB Maps)
    elif isinstance(obj, dict):
        # Check if this is a raw DynamoDB type descriptor
        if len(obj) == 1:
            key = list(obj.keys())[0]
            value = obj[key]
            
            # DynamoDB type descriptors
            if key == 'S':  # String
                return str(value)
            elif key == 'N':  # Number
                try:
                    num = Decimal(value)
                    return int(num) if num % 1 == 0 else float(num)
                except:
                    return value
            elif key == 'BOOL':  # Boolean
                return bool(value)
            elif key == 'NULL':  # Null
                return None
            elif key == 'L':  # List
                return [convert_dynamodb_types(item) for item in value]
            elif key == 'M':  # Map
                return {k: convert_dynamodb_types(v) for k, v in value.items()}
            elif key == 'SS':  # String Set
                return list(value)
            elif key == 'NS':  # Number Set
                return [convert_dynamodb_types({'N': n}) for n in value]
            elif key == 'BS':  # Binary Set
                return list(value)
        
        # Regular dictionary - recurse through all keys
        return {k: convert_dynamodb_types(v) for k, v in obj.items()}
    
    # Handle lists
    elif isinstance(obj, list):
        return [convert_dynamodb_types(item) for item in obj]
    
    # Return primitive types as-is
    return obj

def is_dynamodb_json_format(item):
    """
    Detect if an item is in raw DynamoDB JSON format
    DynamoDB JSON has type descriptors like {'S': 'value'}, {'N': '123'}, etc.
    """
    if not isinstance(item, dict):
        return False
    
    # Check if any top-level keys are DynamoDB type descriptors
    dynamodb_types = {'S', 'N', 'BOOL', 'NULL', 'L', 'M', 'SS', 'NS', 'BS', 'B'}
    
    for key, value in item.items():
        if isinstance(value, dict) and len(value) == 1:
            type_key = list(value.keys())[0]
            if type_key in dynamodb_types:
                return True
    
    return False

def initialize_dynamodb_client():
    """Initialize DynamoDB client with environment variables"""
    try:
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_REGION', 'eu-north-1')
        
        if aws_access_key and aws_secret_key:
            dynamodb = boto3.resource(
                'dynamodb',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=aws_region
            )
        else:
            dynamodb = boto3.resource('dynamodb', region_name=aws_region)
        
        return dynamodb
    except Exception as e:
        raise Exception(f"Failed to initialize DynamoDB client: {str(e)}")

def extract_table_data(table_name, filter_params=None):
    """
    Extract all data from a DynamoDB table with optional filtering
    
    Args:
        table_name (str): Name of the DynamoDB table
        filter_params (dict, optional): Filter parameters for querying
            - company_name (str): Filter by company_name (required)
            - company_id (str): Filter by company_id (optional)
            - start_date (str): Filter by date range start (ISO format)
            - end_date (str): Filter by date range end (ISO format)
            - status (str): Filter by status field
    
    Returns:
        list: All items from the table
    """
    try:
        dynamodb = initialize_dynamodb_client()
        table = dynamodb.Table(table_name)
        
        # Build scan parameters
        scan_kwargs = {}
        
        # Add filter expressions if provided
        if filter_params:
            filter_expressions = []
            expression_attribute_values = {}
            expression_attribute_names = {}
            
            # Company Name filter (required)
            if filter_params.get('company_name'):
                filter_expressions.append('#company_name = :company_name')
                expression_attribute_values[':company_name'] = filter_params['company_name']
                expression_attribute_names['#company_name'] = 'company_name'
            
            # Company ID filter (optional)
            if filter_params.get('company_id'):
                filter_expressions.append('#company_id = :company_id')
                expression_attribute_values[':company_id'] = filter_params['company_id']
                expression_attribute_names['#company_id'] = 'company_id'
            
            # Date range filter (assuming there's a date field)
            if filter_params.get('start_date'):
                filter_expressions.append('#date >= :start_date')
                expression_attribute_values[':start_date'] = filter_params['start_date']
                expression_attribute_names['#date'] = filter_params.get('date_field', 'transaction_date')
            
            if filter_params.get('end_date'):
                filter_expressions.append('#date <= :end_date')
                expression_attribute_values[':end_date'] = filter_params['end_date']
                expression_attribute_names['#date'] = filter_params.get('date_field', 'transaction_date')
            
            # Status filter
            if filter_params.get('status'):
                filter_expressions.append('#status = :status')
                expression_attribute_values[':status'] = filter_params['status']
                expression_attribute_names['#status'] = 'status'

            # Only retrieve non-reconciled entries
            filter_expressions.append(
                "("
                "attribute_not_exists(#reconciled) "
                "OR #reconciled = :empty_str "
                "OR #reconciled = :false_bool "
                "OR #reconciled = :false_str "
                "OR (#reconciled <> :true_val AND #reconciled <> :true_str)"
                ")"
            )

            expression_attribute_values[':empty_str'] = ""
            expression_attribute_values[':false_bool'] = False
            expression_attribute_values[':false_str'] = "false"
            expression_attribute_values[':true_val'] = True         # boolean true
            expression_attribute_values[':true_str'] = "true"       # string "true"
            expression_attribute_names['#reconciled'] = 'reconciled'


            
            # Combine filter expressions
            if filter_expressions:
                scan_kwargs['FilterExpression'] = ' AND '.join(filter_expressions)
                scan_kwargs['ExpressionAttributeValues'] = expression_attribute_values
                scan_kwargs['ExpressionAttributeNames'] = expression_attribute_names
        
        # Perform scan with pagination
        items = []
        response = table.scan(**scan_kwargs)
        items.extend(response.get('Items', []))
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = table.scan(**scan_kwargs)
            items.extend(response.get('Items', []))
        
        # Convert DynamoDB types to standard Python types for JSON serialization
        # The boto3 SDK usually returns Python-native types (with Decimals),
        # but we also handle raw DynamoDB JSON format if encountered
        converted_items = []
        for item in items:
            if is_dynamodb_json_format(item):
                # Raw DynamoDB JSON format - convert type descriptors
                print(f"⚠️  Detected raw DynamoDB JSON format in {table_name}, converting...")
                converted_items.append(convert_dynamodb_types(item))
            else:
                # Standard boto3 format - just convert Decimals
                converted_items.append(convert_dynamodb_types(item))
        
        print(f"✅ Extracted {len(converted_items)} items from table: {table_name}")
        return converted_items
        
    except Exception as e:
        print(f"❌ Error extracting data from table {table_name}: {str(e)}")
        raise Exception(f"Failed to extract data from {table_name}: {str(e)}")

def extract_partner_data(items, partner_type):
    """
    Extract unique partner (customer/vendor) data from transaction items
    
    Args:
        items (list): List of transaction items
        partner_type (str): Type of partner to extract ('customer' or 'vendor')
    
    Returns:
        list: Unique partner entries
    """
    try:
        partners = {}
        partner_field = 'partner_data' if partner_type in ['customer', 'vendor'] else None
        
        if not partner_field:
            return []
        
        for item in items:
            partner_data = item.get(partner_field, {})
            partner_name = partner_data.get('name')
            
            if partner_name and partner_name not in partners:
                partners[partner_name] = {
                    'name': partner_data.get('name', ''),
                    'email': partner_data.get('email', ''),
                    'phone': partner_data.get('phone', ''),
                    'website': partner_data.get('website', ''),
                    'street': partner_data.get('street', ''),
                    'city': partner_data.get('city', ''),
                    'zip': partner_data.get('zip', ''),
                    'country_code': partner_data.get('country_code', ''),
                    'partner_type': partner_type
                }
        
        return list(partners.values())
        
    except Exception as e:
        print(f"⚠️  Warning: Error extracting {partner_type} data: {str(e)}")
        return []

def validate_extraction_params(data):
    """
    Validate extraction parameters
    
    Args:
        data (dict): Request data
    
    Returns:
        dict: Validation result with success status and error message
    """
    # Required company_name validation
    if 'company_name' not in data:
        return {
            'valid': False,
            'error': 'Missing required parameter: company_name'
        }
    
    if not isinstance(data['company_name'], str) or not data['company_name'].strip():
        return {
            'valid': False,
            'error': 'Invalid company_name: must be a non-empty string'
        }
    
    # Optional company_id validation
    if 'company_id' in data:
        if not isinstance(data['company_id'], str) or not data['company_id'].strip():
            return {
                'valid': False,
                'error': 'Invalid company_id: must be a non-empty string'
            }
    
    # Optional date range validation
    if 'start_date' in data or 'end_date' in data:
        date_fields = ['start_date', 'end_date']
        for field in date_fields:
            if field in data:
                try:
                    # Validate ISO date format
                    datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                except ValueError:
                    return {
                        'valid': False,
                        'error': f'Invalid {field}: must be in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)'
                    }
    
    # Optional table selection validation
    if 'tables' in data:
        if not isinstance(data['tables'], list):
            return {
                'valid': False,
                'error': 'Invalid tables parameter: must be an array'
            }
        
        valid_tables = ['invoices', 'bills', 'payroll_transactions', 'share_transactions', 'transactions']
        invalid_tables = [t for t in data['tables'] if t not in valid_tables]
        
        if invalid_tables:
            return {
                'valid': False,
                'error': f"Invalid table names: {', '.join(invalid_tables)}. Valid options: {', '.join(valid_tables)}"
            }
    
    return {'valid': True}

def main(data):
    """
    Main function to extract data from DynamoDB tables
    
    Args:
        data (dict): Request data containing:
            - company_name (str, required): Filter by company name
            - company_id (str, optional): Filter by company ID
            - start_date (str, optional): Start date for filtering (ISO format)
            - end_date (str, optional): End date for filtering (ISO format)
            - tables (list, optional): Specific tables to extract ['invoices', 'bills', etc.]
            - include_partners (bool, optional): Whether to extract customer/vendor data (default: True)
    
    Returns:
        dict: Extraction result with all table data
    """
    try:
        print("📊 Starting DynamoDB data extraction...")
        
        # Validate parameters
        validation_result = validate_extraction_params(data)
        if not validation_result['valid']:
            return {
                'success': False,
                'error': validation_result['error']
            }
        
        # Extract filter parameters
        filter_params = {
            'company_name': data['company_name']  # Required
        }
        
        if data.get('company_id'):
            filter_params['company_id'] = data['company_id']
        if data.get('start_date'):
            filter_params['start_date'] = data['start_date']
        if data.get('end_date'):
            filter_params['end_date'] = data['end_date']
        if data.get('status'):
            filter_params['status'] = data['status']
        
        # Determine which tables to extract
        tables_to_extract = data.get('tables', ['invoices', 'bills', 'payroll_transactions', 'share_transactions', 'transactions'])
        include_partners = data.get('include_partners', True)
        
        # Initialize result structure
        result = {
            'success': True,
            'extraction_summary': {
                'total_records': 0,
                'tables_extracted': [],
                'extraction_timestamp': datetime.utcnow().isoformat() + 'Z',
                'company_name': data['company_name']
            },
            'data': {}
        }
        
        # Add company_id to summary if provided
        if data.get('company_id'):
            result['extraction_summary']['company_id'] = data['company_id']
        
        # Track extraction metrics
        extraction_metrics = {}
        
        # Extract data from each table
        if 'invoices' in tables_to_extract:
            try:
                invoices = extract_table_data('invoices', filter_params)
                result['data']['invoices'] = invoices
                extraction_metrics['invoices'] = len(invoices)
                result['extraction_summary']['tables_extracted'].append('invoices')
            except Exception as e:
                result['data']['invoices'] = []
                extraction_metrics['invoices'] = 0
                print(f"⚠️  Warning: Could not extract invoices: {str(e)}")
        
        if 'bills' in tables_to_extract:
            try:
                bills = extract_table_data('bills', filter_params)
                result['data']['bills'] = bills
                extraction_metrics['bills'] = len(bills)
                result['extraction_summary']['tables_extracted'].append('bills')
            except Exception as e:
                result['data']['bills'] = []
                extraction_metrics['bills'] = 0
                print(f"⚠️  Warning: Could not extract bills: {str(e)}")
        
        if 'payroll_transactions' in tables_to_extract:
            try:
                payroll = extract_table_data('payroll_transactions', filter_params)
                result['data']['payroll_transactions'] = payroll
                extraction_metrics['payroll_transactions'] = len(payroll)
                result['extraction_summary']['tables_extracted'].append('payroll_transactions')
            except Exception as e:
                result['data']['payroll_transactions'] = []
                extraction_metrics['payroll_transactions'] = 0
                print(f"⚠️  Warning: Could not extract payroll_transactions: {str(e)}")
        
        if 'share_transactions' in tables_to_extract:
            try:
                shares = extract_table_data('share_transactions', filter_params)
                result['data']['share_transactions'] = shares
                extraction_metrics['share_transactions'] = len(shares)
                result['extraction_summary']['tables_extracted'].append('share_transactions')
            except Exception as e:
                result['data']['share_transactions'] = []
                extraction_metrics['share_transactions'] = 0
                print(f"⚠️  Warning: Could not extract share_transactions: {str(e)}")
        
        if 'transactions' in tables_to_extract:
            try:
                transactions = extract_table_data('transactions', filter_params)
                result['data']['bank_transactions'] = transactions
                extraction_metrics['bank_transactions'] = len(transactions)
                result['extraction_summary']['tables_extracted'].append('transactions')
            except Exception as e:
                result['data']['bank_transactions'] = []
                extraction_metrics['bank_transactions'] = 0
                print(f"⚠️  Warning: Could not extract transactions: {str(e)}")
        
        # Extract partner data if requested
        if include_partners:
            try:
                # Extract customers from invoices
                customers = []
                if 'invoices' in result['data'] and result['data']['invoices']:
                    customers = extract_partner_data(result['data']['invoices'], 'customer')
                
                # Extract vendors from bills
                vendors = []
                if 'bills' in result['data'] and result['data']['bills']:
                    vendors = extract_partner_data(result['data']['bills'], 'vendor')
                
                result['data']['customers'] = customers
                result['data']['vendors'] = vendors
                extraction_metrics['customers'] = len(customers)
                extraction_metrics['vendors'] = len(vendors)
                
                if customers:
                    result['extraction_summary']['tables_extracted'].append('customers')
                if vendors:
                    result['extraction_summary']['tables_extracted'].append('vendors')
                    
            except Exception as e:
                result['data']['customers'] = []
                result['data']['vendors'] = []
                print(f"⚠️  Warning: Could not extract partner data: {str(e)}")
        
        # Calculate total records
        result['extraction_summary']['total_records'] = sum(extraction_metrics.values())
        result['extraction_summary']['records_by_table'] = extraction_metrics
        
        # Add filter information if filters were applied
        if filter_params:
            result['extraction_summary']['filters_applied'] = filter_params
        
        print(f"✅ Successfully extracted {result['extraction_summary']['total_records']} total records for company: {data['company_name']}")
        print(f"📋 Tables extracted: {', '.join(result['extraction_summary']['tables_extracted'])}")
        
        return result
        
    except Exception as e:
        print(f"❌ DynamoDB extraction error: {str(e)}")
        return {
            'success': False,
            'error': f"Internal extraction error: {str(e)}"
        }

def health_check():
    """Health check for the DynamoDB extraction service"""
    try:
        # Check if AWS credentials are configured
        aws_configured = bool(
            os.getenv('AWS_ACCESS_KEY_ID') and 
            os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        
        # Try to initialize DynamoDB client
        try:
            dynamodb = initialize_dynamodb_client()
            dynamodb_accessible = True
        except Exception:
            dynamodb_accessible = False
        
        return {
            'healthy': True,
            'service': 'dynamodb-data-extraction',
            'version': '1.1',
            'capabilities': [
                'multi_table_extraction',
                'data_filtering',
                'partner_extraction',
                'pagination_handling',
                'decimal_conversion',
                'date_range_filtering',
                'company_name_filtering',
                'company_id_filtering'
            ],
            'aws_configured': aws_configured,
            'dynamodb_accessible': dynamodb_accessible,
            'aws_region': os.getenv('AWS_REGION', 'eu-north-1'),
            'supported_tables': [
                'invoices',
                'bills',
                'payroll_transactions',
                'share_transactions',
                'transactions'
            ],
            'required_parameters': ['company_name'],
            'optional_parameters': ['company_id', 'start_date', 'end_date', 'status', 'tables', 'include_partners']
        }
        
    except Exception as e:
        return {
            'healthy': False,
            'error': str(e)
        }