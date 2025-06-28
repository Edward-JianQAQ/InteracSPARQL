import re

from regex import W
import json
from utils.runjs import run_js_script
from utils.utils import load_json


WIKI_PREFIXES = {}

RDFS_VOCABULARY = {
	'rdfs:Resource': ['Resource', 'The class resource, everything.'],
	'rdfs:Class': ['Class', 'The class of classes.'],
	'rdfs:subClassOf': ['subClassOf', 'The subject is a subclass of a class.'],
	'rdfs:subPropertyOf': ['subPropertyOf', 'The subject is a subproperty of a property.'],
	'rdfs:comment': ['comment', 'A description of the subject resource.'],
	'rdfs:label': ['label', 'A human-readable name for the subject.'],
	'rdfs:domain': ['domain', 'A domain of the subject property.'],
	'rdfs:range': ['range', 'A range of the subject property.'],
	'rdfs:seeAlso': ['seeAlso', 'Further information about the subject resource.'],
	'rdfs:isDefinedBy': ['isDefinedBy', 'The definition of the subject resource.'],
	'rdfs:Literal': ['Literal', 'The class of literal values, e.g., textual strings and integers.'],
	'rdfs:Container': ['Container', 'The class of RDF containers.'],
	'rdfs:ContainerMembershipProperty': ['ContainerMembershipProperty', "The class of container membership properties, rdf:_1, rdf:_2, ..., all of which are sub-properties of 'member'."],
	'rdfs:member': ['member', 'A member of the subject resource.'],
	'rdfs:Datatype': ['Datatype', 'The class of RDF datatypes.']
}


def extract_suffix(uri, prefix = 'http://www.w3.org/2000/01/rdf-schema#'):

	# Check if the URI starts with the specified prefix
	if uri.startswith(prefix):
			# Extract and return the suffix after the '#' sign
			return uri[len(prefix):]
	else:
			# Return None if the URI does not start with the prefix
			return None
	
def get_rdfs_info(url):
	"""
	Returns the rdfs:label and rdfs:comment for a given RDFS entity.
	
	:param entity: The entity key (e.g., 'rdfs:label')
	:return: A list containing the rdfs:label and rdfs:comment of the entity
	"""
	# Normalize the input to ensure consistency
	normalized_url = extract_suffix(url, prefix = 'http://www.w3.org/2000/01/rdf-schema#')
	
	normalized_url = 'rdfs:'+normalized_url
	
	# Search for the entity in the RDFS vocabulary
	if normalized_url in RDFS_VOCABULARY:
		return RDFS_VOCABULARY[normalized_url]
	else:
		return ['Not Found', 'The requested entity does not exist in the RDFS vocabulary.']

def detect_used_rdf_prefixes(sparql_query):
    """
    Detects potential RDF prefixes directly used in a SPARQL query without explicit PREFIX declarations.

    Parameters:
    sparql_query (str): The SPARQL query as a string.

    Returns:
    set: A set of unique prefix labels used in the query.
    """
    # Regular expression to match potential prefix:localPart patterns
    # This pattern looks for words that contain a colon, where the prefix part does not contain whitespace or special characters.
    pattern = re.compile(r'\b[A-Za-z0-9_]+:[A-Za-z0-9_]+\b')
    
    # Find all matches in the query
    matches = pattern.findall(sparql_query)
    
    # Extract prefixes (the part before the colon)
    prefixes = set(match.split(':')[0] for match in matches)

    return prefixes



def extract_entity_info(entity_string):
	# Define a regex pattern to match the 'entity(prefix:identifier)' format
	# without assuming 'wd:Q' as the prefix
	pattern = re.compile(r'url_id\(([^:]+:[^\)]+)\)')
	
	# Search the string for the pattern
	#match = re.search(pattern, entity_string)
	match = pattern.findall(entity_string)

	
	# If a match is found, return the entity ID
	if match:
		return match
		#return match.group(1)  # Return the captured group directly
	else:
		return None  # Return None if no match is found

def extract_entity_id(entity_id):
	# General pattern for matching URL form and extracting ID after the last '/'
	url_pattern = r'.*<http[s]?://.*/([A-Za-z0-9_-]+)>'
	# General pattern for matching any Prefix:ID form and extracting ID
	prefix_pattern = r'.*:([A-Za-z0-9_-]+)'
	
	# Try matching URL pattern
	url_match = re.match(url_pattern, entity_id)
	if url_match:
		return url_match.group(1)  # Return the extracted ID from URL
	
	# Try matching Prefix:ID pattern
	prefix_match = re.match(prefix_pattern, entity_id)
	if prefix_match:
		return prefix_match.group(1)  # Return the extracted ID from Prefix+ID
	
	# If no pattern matches, return None or a custom response
	return None


def extract_entity_label(text):
    # Define a regular expression pattern to match 'url_label()' and capture the string within the brackets
    pattern = r'ent_label\((.*?)\)'
    
    # Find all matches in the text
    matches = re.findall(pattern, text)
    
    return matches

def extract_property_label(text):
    # Define a regular expression pattern to match 'url_label()' and capture the string within the brackets
    pattern = r'prop_label\((.*?)\)'
    
    # Find all matches in the text
    matches = re.findall(pattern, text)
    
    return matches





def parse_filter(nl_input = "FILTER(?result != wdt:Q11835640)", pres = WIKI_PREFIXES):

	prefixes = detect_used_rdf_prefixes(nl_input)

	add_parts = ""
	for pre in prefixes:

		add_parts = add_parts + "PREFIX "+pre + ":<" + pres[pre] + "> "

	text = add_parts + """
	SELECT ?result WHERE {"""+nl_input+ """}
	"""

	code = 'parse_raw.js'

	run_js_script(code, text)
	dataparse = load_json('parsedQueryOutput.json')
	return dataparse['where'][0]

















# Search module
########################### 


