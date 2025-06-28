
from openai import OpenAI
from utils.utils import load_object, sample_examples, load_json, save_json
import json
from utils.runjs import run_js_script

# input is the parsed['variables']
from zmq import has


def check_for_distinct_in_aggregation(query_results):
    # Loop through each item in the query results list
    if 'variables' not in query_results:
        return False
    variables = query_results['variables']
    for result in variables:
        # Access the 'expression' key and further nested keys
        if 'expression' in result:
            expression = result['expression']
            # Check if the type is 'aggregate' and the aggregation is 'count'
            if expression.get('type') == 'aggregate' and expression.get('aggregation') == 'count':
                # Check the 'distinct' status
                is_distinct = expression.get('distinct', False)  # Default to False if not found
                # Print the result with a message
                # print(f"COUNT aggregation uses DISTINCT: {is_distinct}")
                return is_distinct
    # If no count aggregation found, return False
    # print("No COUNT aggregation found or does not specify DISTINCT.")
    return False

def set_distinct_in_aggregation(query_results, new_distinct_value):
    # Indicates if an update has been made
    updated = False

    if 'variables' not in query_results:
        print("No variables found in query results.")
        return query_results
    variables = query_results['variables']

    # Loop through each item in the query results list
    for result in variables:
        # Access the 'expression' key and further nested keys
        if 'expression' in result:
            expression = result['expression']
            # Check if the type is 'aggregate' and the aggregation is 'count'
            if expression.get('type') == 'aggregate' and expression.get('aggregation') == 'count':
                # Set the 'distinct' key to the new value
                expression['distinct'] = new_distinct_value
                updated = True
                # Print a message indicating the update
                # print(f"Updated 'distinct' to {new_distinct_value} for aggregation: {expression}")

    # Check if any updates were made
    if not updated:
        print("No applicable COUNT aggregation found to update.")

    return query_results

def detect_distinct(query_result):
    """
    Detects whether 'DISTINCT' is used in a SPARQL query.
    
    Args:
    query_result (dict): The parsed SPARQL query result in JSON format.

    Returns:
    bool: True if 'DISTINCT' is present, otherwise False.
    """
    # Check for the 'distinct' key in the query result
    is_distinct = query_result.get('distinct', False)
    print(f"'DISTINCT' present: {is_distinct}")
    return is_distinct

def modify_distinct(query_result, set_distinct):
    """
    Modifies the 'DISTINCT' status in a SPARQL query.
    
    Args:
    query_result (dict): The parsed SPARQL query result in JSON format.
    set_distinct (bool): Desired state for 'DISTINCT' (True or False).

    Returns:
    dict: The modified query result.
    """
    # Modify the 'distinct' key in the query result
    if 'distinct' in query_result or set_distinct:
        query_result['distinct'] = set_distinct
        print(f"'DISTINCT' set to: {set_distinct}")
    return query_result



def detect_limit(query_result):
    """
    Detects whether 'LIMIT' is used in a SPARQL query.
    
    Args:
    query_result (dict): The parsed SPARQL query result in JSON format.

    Returns:
    bool: True if 'LIMIT' is present, otherwise False.
    """

    # Check for the 'limit' key in the query result
    has_limit = 'limit' in query_result
    limit_val = query_result.get('limit', None)
    if has_limit:
        print(f"'LIMIT' present with value: {query_result['limit']}")
    else:
        print("'LIMIT' not present")
    return has_limit, limit_val

def modify_limit(query_result, new_limit):
    """
    Modifies the 'LIMIT' value in a SPARQL query.
    
    Args:
    query_result (dict): The parsed SPARQL query result in JSON format.
    new_limit (int): Desired new value for 'LIMIT'.

    Returns:
    dict: The modified query result.
    """
    # Modify the 'limit' key in the query result
    query_result['limit'] = new_limit
    print(f"'LIMIT' set to: {new_limit}")
    return query_result

def delete_limit(query_result):
    """
    Deletes the 'LIMIT' clause from a SPARQL query.
    
    Args:
    query_result (dict): The parsed SPARQL query result in JSON format.

    Returns:
    dict: The modified query result without the 'LIMIT' clause.
    """
    # Check for the 'limit' key in the query result
    if 'limit' in query_result:
        # Delete the 'limit' key from the query result
        del query_result['limit']
        print("'LIMIT' deleted")
    else:
        print("'LIMIT' not present")
    return query_result

def detect_order(query_result):
    """
    Detects and returns the details of the 'ORDER BY' clause in a SPARQL query.
    
    Args:
    query_result (dict): The parsed SPARQL query result in JSON format.

    Returns:
    dict or None: The details of the 'ORDER BY' clause if present, otherwise None.
    """
    # Check for the 'order' key in the query result and return its details
    order_details = query_result.get('order', None)
    if order_details is not None:
        print(f"'ORDER BY' details: {order_details}")
        has_order = True
    else:
        print("'ORDER BY' not present")
        has_order = False
    return has_order, order_details

def modify_order(query_result, new_order_details):
    """
    Modifies the 'ORDER BY' clause in a SPARQL query.
    
    Args:
    query_result (dict): The parsed SPARQL query result in JSON format.
    new_order_details (list): A new list representing the full 'ORDER BY' condition(s).

    Returns:
    dict: The modified query result.
    """
    # Modify the 'order' key in the query result
    query_result['order'] = new_order_details
    print(f"'ORDER BY' modified to: {new_order_details}")
    return query_result

def delete_order(query_result):
    """
    Deletes the 'ORDER BY' clause from a SPARQL query.
    
    Args:
    query_result (dict): The parsed SPARQL query result in JSON format.

    Returns:
    dict: The modified query result without the 'ORDER BY' clause.
    """
    # Check for the 'order' key in the query result
    if 'order' in query_result:
        # Delete the 'order' key from the query result
        del query_result['order']
        print("'ORDER BY' deleted")
    else:
        print("'ORDER BY' not present")
    return query_result


###################################################################### test code


def generate_keyword_from_gt(query_ori, 
                         query_gt,
                         count_distinct = True,
                         distinct = True,
                         limit = True,
                         order = False,
                         change_only_when_empty_order = False,):
    code = 'parse.js'
    run_js_script(code, query_ori)
    parse_ori = load_json("parsedQueryOutput.json")
    run_js_script(code, query_gt)
    parse_gt = load_json("parsedQueryOutput.json")


    if count_distinct:
        if check_for_distinct_in_aggregation(parse_gt):
            parse_ori = set_distinct_in_aggregation(parse_ori, True)
        else:
            parse_ori = set_distinct_in_aggregation(parse_ori, False)
    
    if distinct:
        if detect_distinct(parse_gt):
            parse_ori = modify_distinct(parse_ori, True)
        else:
            parse_ori = modify_distinct(parse_ori, False)

    if limit:
        has_limit, limit_val = detect_limit(parse_gt)
        if has_limit:
            parse_ori = modify_limit(parse_ori, limit_val)
        else:
            parse_ori = delete_limit(parse_ori)

    if order:
        has_order, order_details = detect_order(parse_gt)
        if has_order:
            if change_only_when_empty_order and detect_order(parse_ori)[0]:
                pass
            else:
                parse_ori = modify_order(parse_ori, order_details)
            
        else:
            parse_ori = delete_order(parse_ori)

    text = 'parsedQueryOutput.json'
    save_json(parse_ori, text)
    code = 'convert.js'

    run_js_script(code, text)

        # load a string from txt file 'output.txt'
    with open('output.txt', 'r') as file:
        new_query = file.read()

    return new_query




    






