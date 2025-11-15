import requests
import urllib.parse
from SPARQLWrapper import SPARQLWrapper, JSON
import time
from functools import lru_cache
import urllib.error

@lru_cache(maxsize=10000)
def dbpedia_id2label(named_node, only_label=True):
    # Encode the named node for use in the SPARQL query
    named_node_encoded = urllib.parse.quote(named_node)
    endpoint = "https://dbpedia.org/sparql"

    rdf_namespace = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    rdfs_namespace = "http://www.w3.org/2000/01/rdf-schema#"
    yago_namespace = "http://dbpedia.org/class/yago/"

    # Check if the named node is from RDF, RDFS, or YAGO namespace
    if named_node.startswith(rdf_namespace) or named_node.startswith(rdfs_namespace):
        # Return the part after "#"
        return named_node.split("#")[-1]
    elif named_node.startswith(yago_namespace):
        # Return the part after the last "/"
        return named_node.split("/")[-1]
    
    query = f"""
    PREFIX dbo: <http://dbpedia.org/ontology/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    
    SELECT ?label
    WHERE {{
        <{named_node}> rdfs:label ?label .
        FILTER (lang(?label) = "en")
    }}
    LIMIT 1
    """
    
    params = {
        "query": query,
        "format": "application/json"
    }

    # Retry logic with exponential backoff
    max_retries = 5
    retry_delay = 10  # Start with 10 seconds

    for attempt in range(max_retries):
        try:
            response = requests.get(endpoint, params=params, timeout=30)

            if response.status_code == 502:
                if attempt < max_retries - 1:
                    print(f"HTTP Error 502: Bad Gateway encountered. Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    print(f"Failed after {max_retries} attempts. Giving up.")
                    return None
            elif response.status_code == 200:
                break  # Success
            else:
                print(f"Failed to fetch data from DBpedia, status code: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                print(f"Request timeout. Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                print(f"Request timed out after {max_retries} attempts.")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Request error: {e}")
            return None

    # Add a small delay to avoid overwhelming the endpoint
    time.sleep(0.5)

    data = response.json()
    #print(data)
    if 'results' in data and 'bindings' in data['results'] and len(data['results']['bindings']) > 0:
        if only_label:
            return data['results']['bindings'][0]['label']['value']
        else:
            return data['results']['bindings'][0]
    else:
        print(f"No label found for {named_node}")
        return None

def rdf_rdfs_id2label(named_node, only_label=True):
    # Define RDF and RDFS namespaces
    rdf_namespace = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    rdfs_namespace = "http://www.w3.org/2000/01/rdf-schema#"

    # Check if the named node is from the RDF or RDFS namespace
    if named_node.startswith(rdf_namespace) or named_node.startswith(rdfs_namespace):
        # Return the part after "#"
        return named_node.split("#")[-1]
    else:
        return None


import requests
import xml.etree.ElementTree as ET

def dbpedia_search(query):
    """
    Searches the DBpedia Lookup API for the given query and returns the results.

    Args:
        query (str): The search query string.

    Returns:
        list: A list of dictionaries containing search results.
    """
    # Build the API URL
    url = f'https://lookup.dbpedia.org/api/search?query={query}'
    
    # Headers to specify the response format as XML
    headers = {'Accept': 'application/xml'}
    
    # Make the GET request to the API
    response = requests.get(url, headers=headers)
    
    # Check if the request was successful
    if response.status_code != 200:
        print('Error fetching data from DBpedia API')
        return None
    
    # Parse the XML response
    root = ET.fromstring(response.content)
    
    # List to hold all the results
    results = []
    
    # Iterate over each <Result> element in the XML
    for result in root.findall('Result'):
        # Extract basic information
        label = result.findtext('Label')
        uri = result.findtext('URI')
        description = result.findtext('Description')
        refcount = result.findtext('Refcount')
        
        # Extract classes
        classes = []
        for class_element in result.findall('Classes/Class'):
            class_label = class_element.findtext('Label')
            class_uri = class_element.findtext('URI')
            classes.append({'Label': class_label, 'URI': class_uri})
        
        # Extract categories
        categories = []
        for category_element in result.findall('Categories/Category'):
            category_label = category_element.findtext('Label')
            category_uri = category_element.findtext('URI')
            categories.append({'Label': category_label, 'URI': category_uri})
        
        # Compile the result into a dictionary
        result_dict = {
            'Label': label,
            'URI': uri,
            'Description': description,
            'Refcount': refcount,
            'Classes': classes,
            'Categories': categories
        }
        
        # Add the result to the list
        results.append(result_dict)
    
    return results

def id_search_dbpedia(q):
    """
    Searches the DBpedia Lookup API for the given query and returns the top result with only
    'URI', 'Label', and 'Description'.

    Args:
        query (str): The search query string.

    Returns:
        dict or None: A dictionary with 'URI', 'Label', and 'Description' of the top result,
                      or None if no results are found.
    """
    # Call the existing dbpedia_search function to get all results
    results = dbpedia_search(q)
    
    # Check if there are any results
    if results and len(results) > 0:
        top_result = results[0]
        # Extract only 'URI', 'Label', and 'Description'
        return {
            'URI': top_result.get('URI'),
            'Label': top_result.get('Label'),
            'Description': top_result.get('Description')
        }
    else:
        # No results found
        return None

def search_dbpedia_properties(q, limit=50):
    """
    Search DBpedia for ontology and property URLs matching a fuzzy label with flexible matching.

    Args:
        fuzzy_label (str): The fuzzy label to search for.
        limit (int): The maximum number of results to return.

    Returns:
        list: A list of dictionaries containing 'URI', 'Label', and 'Description'.
    """
    # Initialize the SPARQL endpoint
    sparql = SPARQLWrapper("https://dbpedia.org/sparql")

    # Construct the SPARQL query with fuzzy matching
    query = f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX dbo: <http://dbpedia.org/ontology/>
    PREFIX dcterms: <http://purl.org/dc/terms/>
    SELECT DISTINCT ?URI ?Label ?Description
    WHERE {{
      ?URI rdfs:label ?Label .
      OPTIONAL {{ ?URI dcterms:description ?Description . }}
      FILTER (
    
        CONTAINS(LCASE(?Label), "{q.lower()}") || 
        REGEX(?Label, "{q}", "i")
      )
      FILTER (LANG(?Label) = "" || LANG(?Label) = "en") # Ensure labels are in English or no language specified
      FILTER (STRSTARTS(STR(?URI), "http://dbpedia.org/ontology/") || 
              STRSTARTS(STR(?URI), "http://dbpedia.org/property/"))
    }}
    LIMIT {limit}
    """
    
    # Set up the query
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)

    # Execute the query with retry logic
    max_retries = 5
    retry_delay = 10

    for attempt in range(max_retries):
        try:
            results = sparql.query().convert()
            break  # Exit the loop if successful
        except urllib.error.HTTPError as e:
            if e.code == 502:
                if attempt < max_retries - 1:
                    print(f"HTTP Error 502: Bad Gateway encountered in search_dbpedia_properties. Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print(f"Failed after {max_retries} attempts in search_dbpedia_properties.")
                    return []
            else:
                raise  # Re-raise any other HTTPError
        except Exception as e:
            print(f"Error in search_dbpedia_properties: {e}")
            return []

    # Add a small delay to avoid overwhelming the endpoint
    time.sleep(0.5)

    # Extract results into the desired format
    formatted_results = []
    for result in results["results"]["bindings"]:
        formatted_results.append({
            'URI': result.get('URI', {}).get('value'),
            'Label': result.get('Label', {}).get('value'),
            'Description': result.get('Description', {}).get('value', '')
        })

    return formatted_results


# Example usage:
if __name__ == '__main__':
    query = 'berlin'
    top_result = id_search_dbpedia(query)
    if top_result:
        print(f"Label: {top_result['Label']}")
        print(f"URI: {top_result['URI']}")
        print(f"Description: {top_result['Description']}")
    else:
        print("No results found.")


