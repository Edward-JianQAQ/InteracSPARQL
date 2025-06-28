#from llama import model
from openai import OpenAI
from utils.utils import return_after_word, check_bind, load_object, sample_examples, load_json, save_json
from utils.runjs import run_js_script
import json, random

def bind_get_example():
    return load_object('module_data/bind/examples.pk')

def bind_get_query():
    return load_object('module_data/bind/query.pk')

def bind_get_path_index():
    return load_object('module_data/bind/path_index.pk')

def bind_get_full_parsed():
    return load_object('module_data/bind/full_parsed.pk')

def bind_get_full_query():
    return load_object('module_data/bind/full_query.pk')

# def bind_get_question():
#     return load_object('module_data/bind/question.pk')

def bind_build_examples(num_shots = 10, seed = 0):
    EXAMPLE = bind_get_example()

    random.seed(seed)
    index = sample_examples(len(EXAMPLE[0]), len(EXAMPLE[0]))
    random.seed()

    examples = [[EXAMPLE[0][ind] for ind in index[:num_shots]], [EXAMPLE[1][ind] for ind in index[:num_shots]]]
	
    return examples



################################################################## main code

BIND_CONST_PARSE = ['''{"type": "bind", "variable": {"termType": "Variable", "value": "result"}, "expression": {"type": "operation", "operator": "-", "args": [{"type": "operation", "operator": "year", "args": [{"termType": "Variable", "value": "dd"}]}, {"type": "operation", "operator": "year", "args": [{"termType": "Variable", "value": "db"}]}]}}''',\
					'''{"type": "bind", "variable": {"termType": "Variable", "value": "result"}, "expression": {"type": "operation", "operator": "if", "args": [{"type": "operation", "operator": "exists", "args": [{"type": "group", "patterns": [{"type": "bgp", "triples": [{"subject": {"termType": "NamedNode", "value": "http://www.wikidata.org/entity/Q33602"}, "predicate": {"termType": "NamedNode", "value": "http://www.wikidata.org/prop/direct/P4214"}, "object": {"termType": "Variable", "value": "lp"}}, {"subject": {"termType": "NamedNode", "value": "http://www.wikidata.org/entity/Q36101"}, "predicate": {"termType": "NamedNode", "value": "http://www.wikidata.org/prop/direct/P4214"}, "object": {"termType": "Variable", "value": "lk"}}]}, {"type": "bind", "expression": {"type": "operation", "operator": ">", "args": [{"termType": "Variable", "value": "lp"}, {"termType": "Variable", "value": "lk"}]}}]}]}, {"termType": "NamedNode", "value": "http://www.wikidata.org/entity/Q33602"}, {"termType": "NamedNode", "value": "http://www.wikidata.org/entity/Q36101"}]}}''']
BIND_CONST_NL = ['''The BIND clause creates a new variable named `result` which is calculated by subtracting the year extracted from the variable `db` from the year extracted from the variable `dd`.''', \
                 '''The BIND clause creates a new variable named `result`. This variable is assigned the value of url_id(<http://www.wikidata.org/entity/Q33602>) if there exists a pattern where:\n\n1. The entity url_id(<http://www.wikidata.org/entity/Q33602>) has a property url_id(<http://www.wikidata.org/prop/direct/P4214>) with some value bound to the variable `lp`.\n2. The entity url_id(<http://www.wikidata.org/entity/Q36101>) has the same property url_id(<http://www.wikidata.org/prop/direct/P4214>) with some value bound to the variable `lk`.\n3. The value of `lp` is greater than the value of `lk`.\n\nIf the above conditions are not met, then `result` is assigned the value of url_id(<http://www.wikidata.org/entity/Q36101>).'''  ]


def bind2nl_parsed(nl, examples = [[], []], const_prompt = [BIND_CONST_PARSE, BIND_CONST_NL], model="gpt-4-1106-preview", print_msg = False, temperature = 0.2):

	client = OpenAI()
	message = [{"role": "system", "content": """You are a verbalizer to convert the parsing results of a BIND clause in sparql into natural language. 
		If spot any identifier of entity, replace it with url_id(identifier), 
		if the identifier has starts with '<' and ends with '>', keep the format in the generation like url_id(<identifier>)"""}]


	  
	for i in range(len(examples[0])):
		message.append({"role": "user", "content": examples[0][i]})
		message.append({"role": "assistant", "content": examples[1][i]})
	
	for i in range(len(const_prompt[0])):
		message.append({"role": "user", "content": const_prompt[0][i]})
		message.append({"role": "assistant", "content": const_prompt[1][i]})
   
	message.append({"role": "user", "content": nl})
	
	if print_msg:
		for msg in message:
			print(msg)
		
	response = client.chat.completions.create(
	  model=model,
	  #response_format={"type": "json_object"},
	  temperature = temperature,
	  messages= message
	)

	return response.choices[0].message.content



def nl2bind_parsed(nl, examples = [[],[]], const_propmt = [BIND_CONST_PARSE, BIND_CONST_NL], model="gpt-4-1106-preview", print_msg = False, temperature = 0.2):

	client = OpenAI()

	message = [{"role": "system", "content": """You are a query writer to convert the given natural language description into the parsing result of a single BIND clause in sparql language.
				The value of key 'type' must be 'bind', the value of key 'variable' will be the information of the assigned variable and the value of key 'expression' should be the content of this single bind clause. 
				Please generate the result in json format. """}]
	  
	for i in range(len(examples[0])):
		message.append({"role": "user", "content": examples[1][i]})
		message.append({"role": "assistant", "content": examples[0][i]})
	for i in range(len(const_propmt[0])):
		message.append({"role": "user", "content": const_propmt[1][i]})
		message.append({"role": "assistant", "content": const_propmt[0][i]})
   
	message.append({"role": "user", "content": nl})
	
	if print_msg:
		for msg in message:
			print(msg)

	response = client.chat.completions.create(
		model=model,
		response_format={"type": "json_object"},
		temperature = temperature,
		messages=message
	)

	return response.choices[0].message.content


###################################################### testing code

def produce_raw_examples_bind(qdata, generator = bind2nl_parsed, topk = None):
	bind_id = qdata.get_sp_query(check_bind) #### var
	examples = [[], []]
	query_str = []
	pat_index = []
	full_parsed = []
	full_query = []
	for i in range(len(bind_id)):
		if (topk is not None) and (i > topk):
			break
		query_str.append(return_after_word(qdata.extracted_data[bind_id[i]]['query'], 'BIND'))  #### var
		for j, entry in enumerate(qdata.extracted_data[bind_id[i]]['parsed']['where']):
			if entry['type'] == 'bind': #### var
				examples[0].append(json.dumps(entry))
				examples[1].append(generator(examples[0][-1]))
				pat_index.append((i, j))
				full_parsed.append(qdata.extracted_data[bind_id[i]]['parsed'])
				full_query.append(qdata.extracted_data[bind_id[i]]['query'])


	return examples, query_str, pat_index, full_parsed, full_query


def generate_bind_from_gt(query_ori, 
                         query_gt, 
                         nl2bind = nl2bind_parsed, 
                         bind2nl = bind2nl_parsed, 
                         replace_ori = True, 
                         num_shots = 10,
                         seed = None,
                         model_name = "gpt-4-1106-preview"):
    code = 'parse.js'
    run_js_script(code, query_ori)
    parse_ori = load_json("parsedQueryOutput.json")
    run_js_script(code, query_gt)
    parse_gt = load_json("parsedQueryOutput.json")
    #print(parse_gt)
    patterns_gt = parse_gt['where']

    bind_gt = [] #ground truth bind
    #fiter_ori = [] #original bind

    nl_gt = [] #ground truth nl
    bind_gen_gt = [] #generated bind from nl

    examples = bind_build_examples(num_shots = num_shots, seed = seed)

    for pattern in patterns_gt:
        if pattern['type'] == 'bind':
            nl_pattern = bind2nl(json.dumps(pattern), examples=examples, print_msg=False, model=model_name)
            bind_gen_pattern = nl2bind(nl_pattern, examples=examples, print_msg=False, model=model_name)
            js = json.loads(bind_gen_pattern)

            bind_gt.append(json.dumps(pattern))
            nl_gt.append(nl_pattern)
            bind_gen_gt.append(js)


    #return bgp_gt, bgp_gen_gt, nl_gt, gen_bgp_parsed
    if replace_ori:
        parse_to_update = parse_ori
    else:
        parse_to_update = parse_gt

    new_patterns = []
    for pattern in parse_to_update['where']:
        if pattern['type'] != 'bind':
            new_patterns.append(pattern)
    
    new_patterns += bind_gen_gt
    parse_to_update['where'] = new_patterns

    
    text = 'parsedQueryOutput.json'
    save_json(parse_to_update, text)
    code = 'convert.js'

    run_js_script(code, text)

    # load a string from txt file 'output.txt'
    with open('output.txt', 'r') as file:
        new_query = file.read()

    return new_query

if __name__ == '__main__':
    seed = 0

