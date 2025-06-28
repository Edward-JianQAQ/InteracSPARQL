from SPARQLWrapper import SPARQLWrapper, JSON
from utils.prefix import extract_suffix, get_rdfs_info, extract_entity_id, extract_entity_info, extract_entity_label, extract_property_label
from openai import OpenAI
from utils.utils import check_if_variable_str
import json, urllib.request # Needed libs

def run_wikidata_query(sparql_query):
    """
    Execute a SPARQL query against the Wikidata endpoint and return the results.

    Parameters:
    - sparql_query (str): The SPARQL query to execute.

    Returns:
    - A dictionary containing the query results.
    """
    # Define the Wikidata endpoint URL
    endpoint_url = "https://query.wikidata.org/sparql"
    
    # Create a SPARQLWrapper object with the defined endpoint URL
    sparql = SPARQLWrapper(endpoint_url)
    
    # Set the query
    sparql.setQuery(sparql_query)
    
    # Set the return format to JSON
    sparql.setReturnFormat(JSON)
    
    # Execute the query and return the results
    try:
        results = sparql.query().convert()
        return results
    except Exception as e:
        return {"error": str(e)}



def entity2id(q):
	# Get wikidata id from wikidata api
	ans = []
	url = "https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&search="+"+".join(q.split(" "))+"&language=en"
	response = json.loads(urllib.request.urlopen(url).read())
	ans += response["search"]
	if (ans == [] and " " in q):

		url = "https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&search="+"+".join(q.split(" ")[::-1])+"&language=en"
		response = json.loads(urllib.request.urlopen(url).read())
		ans += response["search"]
	if (ans == [] and len(q.split(" ")) > 2):
		# Abbreviation
		url = "https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&search="+"+".join([q.split(" ")[0], q.split(" ")[-1]])+"&language=en"
		response = json.loads(urllib.request.urlopen(url).read())
		ans += response["search"]
	# if len(ans) > 0:
	# 	# Returns the first one, most likely one
	# 	return ans[0]["id"]
	# else:
	# 	# Some outliers : Salvador Domingo Felipe Jacinto Dali i Domenech - Q5577
	# 	return "Not Applicable"
	return ans

def entity_id_search_wiki(q):
	# only get top 1 result
	res = entity2id(q)

	try:
		return {"URL": res[0]['concepturi'], "Label": res[0]['label'], "Description": res[0]['description']}
	except Exception as e:
		print(f"Error: {e}")
		return "no result found"

def property2id(q):
	ans = []
	url = "https://www.wikidata.org/w/api.php?action=wbsearchentities&search="+"+".join(q.split(" "))+"&language=en&type=property&format=json"
	response = json.loads(urllib.request.urlopen(url).read())
	ans += response["search"]

	if (ans == [] and " " in q):
		# Reverse 
		url = "https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&search="+"+".join(q.split(" ")[::-1])+"&language=en&type=property&format=json"
		response = json.loads(urllib.request.urlopen(url).read())
		ans += response["search"]
	if (ans == [] and len(q.split(" ")) > 2):
		# Abbreviation 
		url = "https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&search="+"+".join([q.split(" ")[0], q.split(" ")[-1]])+"&language=en&type=property&format=json"
		response = json.loads(urllib.request.urlopen(url).read())
		ans += response["search"]
	if (ans == [] and len(q.split(" ")) > 2):
		# Abbreviation 
		url = "https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&search="+"+".join([q.split(" ")[-2], q.split(" ")[-1]])+"&language=en&type=property&format=json"
		response = json.loads(urllib.request.urlopen(url).read())
		ans += response["search"]
	if (ans == [] and len(q.split(" ")) > 1):
		# Abbreviation 
		url = "https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json&search="+"+".join([q.split(" ")[-1]])+"&language=en&type=property&format=json"
		response = json.loads(urllib.request.urlopen(url).read())
		ans += response["search"]
	return ans

def property_id_search_wiki(q):
	# only get top 1 result
	res = property2id(q)
	try:
		return {"URL": res[0]['concepturi'], "Label": res[0]['label'], "Description": res[0]['description']}
	except Exception as e:
		print(f"Error: {e}")
		return "no result found"


def extract_url(res, topk = 1, has_label = False, has_desp = False):
	"""
    Extracts the URL, label, and description of the top-k results from a entity2id or property2id search.
	
	"""
	out = []
	for i in range(topk):
		dic = {}
		dic['url'] = res[i]['concepturi']
		if has_label:
			dic['label'] = res[i]['label']
		if has_desp:
			dic['desp'] = res[i]['description']

		out.append(dic)
	return out

def general_wiki_search(label, is_entity = True):
	if check_if_variable_str(label):
		return label[1:]

	if is_entity:
		return entity2id(label)[0]['concepturi']
	else:
		return property2id(label)[0]['concepturi']

def id2info(q, only_label=True):
	# Get wikidata id from wikidata api
	ans = []
	q = q.split('/')[-1]
	url = "https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&ids="+q+"&languages=en"
	response = json.loads(urllib.request.urlopen(url).read())

	try:
		entity_list = list(response['entities'].keys())
	except Exception as e:
		print(f"Namednode not from wikidata")
		return ""

	if len(entity_list)> 1:
		print("More than one result found, not expected")
		return None


	if only_label:
		try: 
			return response['entities'][entity_list[0]]['labels']['en']['value']
		except Exception as e:
			try:
				print(f"not en label, try to use mul label")
				url = "https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&ids="+q+"&languages=mul"
				response = json.loads(urllib.request.urlopen(url).read())

				entity_list = list(response['entities'].keys())

				if len(entity_list)> 1:
					print("More than one result found, not expected")
					return None
			

				return response['entities'][entity_list[0]]['labels']['mul']['value']
			except Exception as e:
				print(f"An unexpected error occurred: {e}")

			return None
 
	return response['entities'][entity_list[0]]


def extract_url_and_replace(nl_des):
	ents = extract_entity_info(nl_des)

	if ents is not None:
		#print(ents)
		for ent in ents:
			eid = extract_entity_id(ent)
			elabel = id2info(eid)
			nl_des = nl_des.replace("url_id("+ ent +")", "(" + elabel + ")" )
	return nl_des



def extract_label_and_replace(nl_input):
	ent_labels = extract_entity_label(nl_input)
	if len(ent_labels) > 0:
		for label in ent_labels:
			s_res = entity2id(label)[0]['concepturi']
			nl_input = nl_input.replace('ent_label('+ label +')', 'url_id(<' + s_res + '>)')


	prop_labels = extract_property_label(nl_input)
	if len(prop_labels) > 0:
		for label in prop_labels:
			s_res = property2id(label)[0]['concepturi']
			nl_input = nl_input.replace('prop_label('+ label +')', 'url_id(<' + s_res + '>)')	
		 
	return nl_input



def wiki_entity_label(url):
	#sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
	sparql = SPARQLWrapper("https://query.wikidata.org/sparql", agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36')
	sparql.setQuery('''PREFIX wd: <http://www.wikidata.org/entity/>
	PREFIX wdt: <http://www.wikidata.org/prop/direct/>
	PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
	PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

	SELECT DISTINCT ?label WHERE {
		{
			<'''+url+'''> rdfs:label ?label .
			FILTER(LANG(?label) = "en")
		} 
	} ''')

	sparql.setReturnFormat(JSON)
	results = sparql.query().convert()
	return results['results']['bindings'][0]['label']['value']


def wiki_predicate_label(url, if_wd = True):
	#sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
	sparql = SPARQLWrapper("https://query.wikidata.org/sparql", agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36')

	rdfs_prop = extract_suffix(url, prefix = 'http://www.w3.org/2000/01/rdf-schema#')

	if rdfs_prop is not None:
		return get_rdfs_info(url)[0]

	if if_wd:
			url = url.split('/')[-1]
			query = '''PREFIX wd: <http://www.wikidata.org/entity/>
			PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
			PREFIX schema: <http://schema.org/>
			
			SELECT DISTINCT ?label
			WHERE {
				wd:'''+url+''' rdfs:label ?label .
				FILTER(LANG(?label) = "en") 
			}'''
	else:
			query = '''PREFIX wd: <http://www.wikidata.org/entity/>
			PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
			PREFIX schema: <http://schema.org/>
			
			SELECT DISTINCT ?label
			WHERE {
				<'''+url+'''> rdfs:label ?label .
				FILTER(LANG(?label) = "en") 
			}'''
	#print(query)
	sparql.setQuery(query)
	sparql.setReturnFormat(JSON)
	results = sparql.query().convert()
	#print(results)
	# return results['results']['bindings'][0]['label']['value']
	return results['results']['bindings'][0]['label']['value']


def compose_message(triple, has_var, var_pos=0):
	if not has_var:
		messages = [
			{"role": "system", "content": "Given a RDF triple, your goal is to generate natural language description of that triple. Do not care about whether the triple is valid or not"},
			{"role": "user", "content": "The triple is ('Italy', 'leaderName', 'Matteo Renzi')"},
			{"role": "assistant", "content": "The country Italy is currently led by Matteo Renzi"},
			{"role": "user", "content": f"The triple is {triple}"}]
	else:
		if var_pos == 0:
			messages = [
			{"role": "system", "content": """Given a RDF triple, your goal is to generate natural language description of that triple. 
			If you encounter that starts with 'var', keep it intact as variable. Please keep the predicate as intact as possible. """},
			{"role": "user", "content": "The triple is ('Italy', 'leaderName', 'var')"},
			{"role": "assistant", "content": "The country Italy is currently led by var"},
			{"role": "user", "content": "The triple is ('var', 'instance of', 'taxon')"},
			{"role": "assistant", "content": "The item represented by var is a member of the taxonomic class taxon"},
			{"role": "user", "content": "The triple is ('var', 'participating', 'australian defence force')"},
			{"role": "assistant", "content": "The individual represented by var participate in the Australian Defence Force."},
			{"role": "user", "content": f"The triple is {triple}"}]   

		elif var_pos == 1:
			messages = [
			{"role": "system", "content": """Given a RDF triple, your goal is to generate natural language description of that triple. 
			If you encounter that starts with 'var', keep it intact as variable.  Please keep the predicate as intact as possible. """},
			{"role": "user", "content": "The triple is ('Joe Biden', 'var', 'USA')"},
			{"role": "assistant", "content": "Joe Biden is connected with USA with a relation of var"},
			{"role": "user", "content": f"The triple is {triple}"}]   
		
		elif var_pos == 13:
			messages = [
			{"role": "system", "content": "Given a RDF triple, your goal is to generate natural language description of that triple. If you encounter that starts with 'var', keep it intact as variable"},
			{"role": "user", "content": "The triple is ('var1', 'is friend of', 'var2')"},
			{"role": "assistant", "content": "var1 is friend of var2"},
			{"role": "user", "content": "The triple is ('var1', 'participant', 'var2')"},
			{"role": "assistant", "content": "var1 is a participant in something involving var2"},
			{"role": "user", "content": f"The triple is {triple}"}]   

		else: 
			messages = [
			{"role": "system", "content": "Given a RDF triple, your goal is to generate natural language description of that triple. If you encounter that starts with 'var', keep it intact as variable"},
			{"role": "user", "content": "The triple is ('var', 'isPartOf', 'California_State_Legislature')"},
			{"role": "assistant", "content": "var is part of the California State Legislature"},
			{"role": "user", "content": f"The triple is {triple}"}] 
  
		
	return messages


	

def triple2NL_gpt(triple, has_var, var_pos=0, model="gpt-4-1106-preview"):
		#print(triple)
	triple = tuple(triple)
	#print(triple)
	messages = compose_message(triple, has_var, var_pos=var_pos)
	#print(messages)
	client = OpenAI()

	response = client.chat.completions.create(
	  model = model,
	  temperature = 0.3,
	  messages = messages
	)

	return response.choices[0].message.content


def NL2triple_gpt(nl, model="gpt-4-1106-preview"):

    client = OpenAI()
    response = client.chat.completions.create(
      model=model,
      temperature = 0.3,
      messages=[
        {"role": "system", "content": """Some text is provided below. Extract one knowledge
      triplet in the form (subject, predicate, object) from the text. If encounter variable starts with '?', keep it intact."""},
        {"role": "user", "content": "Abilene, Texas is in the United States"},
        {"role": "assistant", "content": '''("abilene texas", "country", "united states")'''},
        {"role": "user", "content": "?result was born in the city of Ulm."},
        {"role": "assistant", "content": '''("?result", "born in", "ulm")'''},
        {"role": "user", "content": nl}
      ]
    )

    return response.choices[0].message.content