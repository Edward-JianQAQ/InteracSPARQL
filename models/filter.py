#from llama import model
from openai import OpenAI
from utils.utils import return_after_word, check_filter, load_object, sample_examples, load_json, save_json
from utils.runjs import run_js_script
import json, random

def filter_get_example():
    return load_object('module_data/filter/examples.pk')

def filter_get_query():
    return load_object('module_data/filter/query.pk')

def filter_get_path_index():
    return load_object('module_data/filter/path_index.pk')

def filter_get_full_parsed():
    return load_object('module_data/filter/full_parsed.pk')

def filter_get_full_query():
    return load_object('module_data/filter/full_query.pk')

# def filter_get_question():
#     return load_object('module_data/filter/question.pk')

def filter_build_examples(num_shots = 10, seed = 0):
    EXAMPLE = filter_get_example()

    random.seed(seed)
    index = sample_examples(len(EXAMPLE[0]), len(EXAMPLE[0]))
    random.seed()

    examples = [[EXAMPLE[0][ind] for ind in index[:num_shots]], [EXAMPLE[1][ind] for ind in index[:num_shots]]]
	
    return examples



################################################################## main code

def filter2nl_parsed(nl, examples = [[], []], model="gpt-4-1106-preview", print_msg = False, temperature = 0.2):

	client = OpenAI()
	message = [{"role": "system", "content": """You are a verbalizer to convert the parsing results of a FILTER clause in sparql into natural language. 
		If spot any identifier of entity, replace it with url_id(identifier), 
		if the identifier has starts with '<' and ends with '>', keep the format in the generation like url_id(<identifier>)"""}]
	  
	for i in range(len(examples[0])):
		message.append({"role": "user", "content": examples[0][i]})
		message.append({"role": "assistant", "content": examples[1][i]})
   
	message.append({"role": "user", "content": nl})
	
	if print_msg:
		for msg in message:
			print(msg)
		
	response = client.chat.completions.create(
	  model=model,
	  #response_format={"type": "json_object"},
	  temperature = temperature,
	  messages= message,
	)

	return response.choices[0].message.content


def nl2filter_parsed(nl, examples = [[],[]], model="gpt-4-1106-preview", print_msg = False, temperature = 0.2):

	client = OpenAI()

	message = [{"role": "system", "content": """You are a query writer to convert the given natural language description into the parsing result of a single FILTER clause in sparql language.
				The value of key 'type' must be 'filter' and the value of 'expression' should be the content of this single FILTER clause. Please only consider it is a FILTER operation. Please generate the result in json format. """}]
	  
	for i in range(len(examples[0])):
		message.append({"role": "user", "content": examples[1][i]})
		message.append({"role": "assistant", "content": examples[0][i]})
   
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

def produce_raw_examples_filter(qdata, generator = filter2nl_parsed, topk = None):
	filter_id = qdata.get_sp_query(check_filter)
	examples = [[], []]
	query_str = []
	pat_index = []
	full_parsed = []
	full_query = []
	for i in range(len(filter_id)):
		if (topk is not None) and (i > topk):
			break
		query_str.append(return_after_word(qdata.extracted_data[filter_id[i]]['query'], 'FILTER'))
		for j, entry in enumerate(qdata.extracted_data[filter_id[i]]['parsed']['where']):
			if entry['type'] == 'filter':
				examples[0].append(json.dumps(entry))
				#examples[1].append(generator(examples[0][-1]))
				pat_index.append((i, j))
				full_parsed.append(qdata.extracted_data[filter_id[i]]['parsed'])
				full_query.append(qdata.extracted_data[filter_id[i]]['query'])


	return examples, query_str, pat_index, full_parsed, full_query


def generate_filter_from_gt(query_ori, 
                         query_gt, 
                         nl2filter = nl2filter_parsed, 
                         filter2nl = filter2nl_parsed, 
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

    filter_gt = [] #ground truth filter
    #fiter_ori = [] #original filter

    nl_gt = [] #ground truth nl
    filter_gen_gt = [] #generated filter from nl

    examples = filter_build_examples(num_shots = num_shots, seed = seed)

    for pattern in patterns_gt:
        if pattern['type'] == 'filter':
            nl_pattern = filter2nl(json.dumps(pattern), examples=examples, print_msg=False, model=model_name)
            filter_gen_pattern = nl2filter(nl_pattern, examples=examples, print_msg=False, model=model_name)
            js = json.loads(filter_gen_pattern)

            filter_gt.append(json.dumps(pattern))
            nl_gt.append(nl_pattern)
            filter_gen_gt.append(js)


    #return bgp_gt, bgp_gen_gt, nl_gt, gen_bgp_parsed
    if replace_ori:
        parse_to_update = parse_ori
    else:
        parse_to_update = parse_gt

    new_patterns = []
    for pattern in parse_to_update['where']:
        if pattern['type'] != 'filter':
            new_patterns.append(pattern)
    
    new_patterns += filter_gen_gt
    parse_to_update['where'] = new_patterns

    
    text = 'parsedQueryOutput.json'
    save_json(parse_to_update, text)
    code = 'convert.js'

    run_js_script(code, text)

    # load a string from txt file 'output.txt'
    with open('output.txt', 'r') as file:
        new_query = file.read()

    return new_query



