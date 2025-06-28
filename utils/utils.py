import pickle
import json
import random
import copy
import re
from click import password_option
from utils.runjs import run_js_script

def sample_examples(num_points, size):


	# Sample 10 unique points from 0 to 50
	points = random.sample(range(size), num_points)

	return points


def load_json(filename):
	try:
		with open(filename, 'r') as file:
			return json.load(file)
	except FileNotFoundError:
		print(f"File {filename} not found.")
		return None
	except json.JSONDecodeError:
		print(f"Error decoding JSON from {filename}.")
		return None


def save_json(data, filename):
	"""
	Saves a dictionary to a JSON file.
	
	:param data: Dictionary to be saved.
	:param filename: Filename for the saved JSON.
	"""
	with open(filename, 'w') as f:
		json.dump(data, f, indent=4)

def load_jsonl(filename):
	data = []
	try:
		with open(filename, 'r') as file:
			for line in file:
				try:
					data.append(json.loads(line))
				except json.JSONDecodeError as e:
					print(f"Error decoding JSON from line: {line}\nError: {e}")
	except FileNotFoundError:
		print(f"File {filename} not found.")
	return data

def save_jsonl(data, filename):
	"""
	Saves a list of dictionaries to a JSONL file. Overwrite the file everytime.
	
	:param data: List of dictionaries to be saved.
	:param filename: Filename for the saved JSONL.
	"""
	with open(filename, 'w') as f:
		for entry in data:
			json.dump(entry, f)
			f.write('\n')

def save_object(obj, filename):

	with open(filename, 'wb') as file:
		pickle.dump(obj, file)

def load_object(filename):

	with open(filename, 'rb') as file:
		return pickle.load(file)



def dict_add_and_report(d1, d2):
	"""
	Adds all key-value pairs from d2 into d1. Reports if the same key exists with a different valu
	e.

	Parameters:
	d1 (dict): The destination dictionary to update.
	d2 (dict): The source dictionary from which to add key-value pairs.

	Returns:
	None: The function updates d1 in place and prints warnings for mismatched values.
	"""
	for key, value in d2.items():
		if key in d1 and d1[key] != value:
			print(f"Warning: Key '{key}' has a different value in d1. d1[{key}] = {d1[key]}, d2[{key}] = {value}")
		d1[key] = value




def add_prefixes(query, kg):
	if kg == 'wiki':
		query = "PREFIX bd: <http://www.bigdata.com/rdf#> PREFIX dct: <http://purl.org/dc/terms/> PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX p: <http://www.wikidata.org/prop/> PREFIX pq: <http://www.wikidata.org/prop/qualifier/> PREFIX ps: <http://www.wikidata.org/prop/statement/> PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wds: <http://www.wikidata.org/entity/statement/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> PREFIX wdv: <http://www.wikidata.org/value/> PREFIX wikibase: <http://wikiba.se/ontology#> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> " + query
	elif kg == 'dbpedia':
		query = "PREFIX yago: <http://dbpedia.org/class/yago/> PREFIX dbo: <http://dbpedia.org/ontology/> PREFIX dbp: <http://dbpedia.org/property/> PREFIX dbr: <http://dbpedia.org/resource/> PREFIX dbpedia: <http://dbpedia.org/> PREFIX dbpedia-owl: <http://dbpedia.org/ontology/> PREFIX foaf: <http://xmlns.com/foaf/0.1/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> " + query
	return query






		
def check_bgp(parsed_data):
	
	for i in range(len(parsed_data['where'])):
		if parsed_data['where'][i]['type'] == 'bgp':
			return True
			
	return False

			

def check_reg_path(parsed_data):
	
	for tp in parsed_data['where']:
		print(tp)
		if 'triples' in tp.keys():
			tp = tp['triples']
			if 'type' in tp['predicate'] and tp['predicate']['type'] == 'path':
				return True
			
	return False

def check_group(parsed_data):

	for i in range(len(parsed_data['where'])):
		if parsed_data['where'][i]['type'] == 'group':
			return True
		
	return False

def check_union(parsed_data):

	for i in range(len(parsed_data['where'])):
		if parsed_data['where'][i]['type'] == 'union':
			return True
		
	return False	

def check_bind(parsed_data):

	for i in range(len(parsed_data['where'])):
		if parsed_data['where'][i]['type'] == 'bind':
			return True
		
	return False

def check_filter(parsed_data):

	for i in range(len(parsed_data['where'])):
		if parsed_data['where'][i]['type'] == 'filter':
			return True
		
	return False

def check_if_variable_str(label):
	if label.startswith('?'):
		return True 
	return False


def replace_pattern(ind, js, index, FULL_PARSED, PAT_INDEX):
	new_query = copy.deepcopy(FULL_PARSED[index[ind]])

	new_query['where'][PAT_INDEX[index[ind]][1]] = js

	return new_query

def select_certain_pattern(patterns, pattern, if_only = True, if_all_exist = False):
	"""
	1. if_only means the patterns in 'pattern' must be the only pattern(s) in the query. 
	For example, if pattern = ['bgp', 'filter'], if_only = True, then the query must only contain 'bgp' or 'filter' patterns.
	
	2. if_all_exist means all patterns in 'pattern' must exist in the query.
	For example, if pattern = ['bgp', 'filter'], if_all_exist = True, then the query must contain both 'bgp' and 'filter' patterns. 
	"""
	selected = []
	for i, query in enumerate(patterns):
		if isinstance(pattern, list):
			if if_only:
				all_pattern = all(p in pattern for p in query)
				if all_pattern:
					if if_all_exist and not all(p in query for p in pattern):
						continue
					selected.append(i)
			else:
				if any(p in pattern for p in query):
					if if_all_exist and not all(p in query for p in pattern):
						continue
					selected.append(i)

		

		elif isinstance(pattern, str):
			if if_only:
				all_pattern = all(p == pattern for p in query)
				if all_pattern:
					selected.append(i)
			else:
				if pattern in query:
					selected.append(i)

		else:
			print("Invalid pattern type.")
			return None

	return selected

def filter_pattern(patterns_with_index, patterns, pattern):
	selected = []
	for index in patterns_with_index:
		if pattern in patterns[index]:
			selected.append(index)

	return selected



def print_all_pattern(parsed):
	rlist = []
	for entry in parsed['where']:
		rlist.append(entry['type'])
	print(rlist)

def return_all_pattern(parsed):
	rlist = []
	for entry in parsed['where']:
		rlist.append(entry['type'])
	return rlist




def print_after_word(text, word):
	position = text.find(word)
	if position != -1:
		print(text[position:])
		return 1
	else:
		# print("Word not found.")
		return 0
	
def return_after_word(text, word):
	position = text.find(word)
	if position != -1:
		return text[position:]
	else:
		return None

def print_raw_query(query):
		
	pres = print_after_word(query, 'SELECT')
	if pres == 0:
		print_after_word(query, 'ASK')


def return_raw_query(query):
		
	pres = return_after_word(query, 'SELECT')
	if pres is None:
		pres = return_after_word(query, 'ASK')
	return pres
############################################################################




def extract_namednode_values(data, path=None, label_func=None):
    """
    Recursively extracts all values where termType is 'NamedNode' from a nested dictionary or list,
    and returns them as a dictionary with paths as keys and 'value' entries for 'NamedNode' termType as values.
    It also adds labels using the provided label_func.

    Args:
    - data: The input data (can be a dictionary or a list).
    - path: The current path (used for recursion, default is None).
    - label_func: A function that takes an ID (from the NamedNode value) and returns a label (default is None).

    Returns:
    - A dictionary with paths as keys and values as 'value (label)' if a label is found, or just 'value'.
    """
    if path is None:
        path = []

    namednode_dict = {}

    # If the data is a dictionary, check for 'termType' and 'value'
    if isinstance(data, dict):
        if data.get("termType") == "NamedNode":
            # Convert the path list to a string representation for the dictionary key
            path_key = '.'.join(map(str, path))
            value = data.get("value")
            label = label_func(value) if label_func else None
            if label:
                namednode_dict[path_key] = f"{value} ({label})"
            else:
                namednode_dict[path_key] = value
        # Recursively search through each key-value pair
        for key, value in data.items():
            new_path = path + [key]
            namednode_dict.update(extract_namednode_values(value, new_path, label_func))

    # If the data is a list, iterate through each item
    elif isinstance(data, list):
        for index, item in enumerate(data):
            new_path = path + [index]
            namednode_dict.update(extract_namednode_values(item, new_path, label_func))

    return namednode_dict


def extract_sparql_query(text):
    match = re.search(r"```sparql(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        return text


def parse_query(query):
	        			
	run_js_script("parse.js", query)
	parsed = load_json('parsedQueryOutput.json')
	
	return parsed

