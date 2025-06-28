# from llama import model
from openai import OpenAI
from utils.utils import load_object, sample_examples, load_json, save_json
import json
from utils.runjs import run_js_script
import random


def bgp_get_example():
    return load_object('module_data/bgp/examples.pk')

def bgp_get_query():
    return load_object('module_data/bgp/query.pk')

def bgp_get_path_index():
    return load_object('module_data/bgp/path_index.pk')

def bgp_get_full_parsed():
    return load_object('module_data/bgp/full_parsed.pk')

def bgp_get_full_query():
    return load_object('module_data/bgp/full_query.pk')

def bgp_get_question():
    return load_object('module_data/bgp/question.pk')



PATH_CONST_PARSE = ['''{"subject": {"termType": "Variable", "value": "eventStatement"}, "predicate": {"type": "path", "pathType": "*", "items": [{"termType": "NamedNode", "value": "http://www.wikidata.org/prop/direct/P361"}]}, "object": {"termType": "NamedNode", "value": "http://www.wikidata.org/entity/Q181278"}}''',
                   '''{"subject": {"termType": "Variable", "value": "b2"}, "predicate": {"type": "path", "pathType": "*", "items": [{"termType": "NamedNode", "value": "http://www.wikidata.org/prop/direct/P131"}]}, "object": {"termType": "Variable", "value": "state"}}''',
                   '''{"subject": {"termType": "NamedNode", "value": "http://www.wikidata.org/entity/Q641"}, "predicate": {"type": "path", "pathType": "/", "items": [{"termType": "NamedNode", "value": "http://www.wikidata.org/prop/P17"}, {"termType": "NamedNode", "value": "http://www.wikidata.org/prop/statement/P17"}]}, "object": {"termType": "NamedNode", "value": "http://www.wikidata.org/entity/Q131964"}}''',
                   '''{"subject": {"termType": "Variable", "value": "result"}, "predicate": {"type": "path", "pathType": "/", "items": [{"termType": "NamedNode", "value": "http://purl.org/dc/terms/language"}, {"termType": "NamedNode", "value": "http://www.wikidata.org/prop/direct/P218"}]}, "object": {"termType": "Literal", "value": "tr", "language": "", "datatype": {"termType": "NamedNode", "value": "http://www.w3.org/2001/XMLSchema#string"}}}''']
PATH_CONST_NL = ['''The variable ?eventStatement is connected to the entity url_id(<http://www.wikidata.org/entity/Q181278>) through any number of occurrences of the property url_id(http://www.wikidata.org/prop/direct/P361)''',
                 '''The variable ?b2 is connected to the variable ?state through any number of occurrences of property url_id(<http://www.wikidata.org/prop/direct/P131>)''',
                 '''The subject url_id(<http://www.wikidata.org/entity/Q641>) has a property path that starts with property url_id(<http://www.wikidata.org/prop/P17>) and then follows with the property url_id(<http://www.wikidata.org/prop/statement/P17>), leading to the entity url_id(<http://www.wikidata.org/entity/Q131964>)''',
                 '''The entity url_id(<http://www.wikidata.org/entity/Q158895>) has a property path that starts with property url_id(<http://www.wikidata.org/prop/direct/P136>) and then follows any number of occurrences of property url_id(<http://www.wikidata.org/prop/direct/P279>), leading to the entity url_id(<http://www.wikidata.org/entity/Q11399>)''']

BGP_CONST_PARSE = ['''{"subject": {"termType": "NamedNode", "value": "http://www.wikidata.org/entity/Q761383"}, "predicate": {"termType": "NamedNode", "value": "http://www.wikidata.org/prop/direct/P138"}, "object": {"termType": "Variable", "value": "result"}}''',
                   '''{"subject": {"termType": "Variable", "value": "result"}, "predicate": {"termType": "NamedNode", "value": "http://www.wikidata.org/prop/direct/P451"}, "object": {"termType": "Variable", "value": "p2"}}''']
BGP_CONST_NL = ['''The entity url_id(<http://www.wikidata.org/entity/Q761383>) is connected through the property url_id(<http://www.wikidata.org/prop/direct/P138>) to the variable ?result''',
                '''The variable ?result is connected through the property url_id(<http://www.wikidata.org/prop/direct/P451>) to the variable ?p2''']

def bgp2nl_parsed(nl, examples = [[], []],const_prompt = [PATH_CONST_PARSE + BGP_CONST_PARSE, PATH_CONST_NL + BGP_CONST_NL], model="gpt-4-1106-preview", print_msg = False, model_config = {}):

    client = OpenAI()
    message = [{"role": "system", "content": """You are a verbalizer to convert the parsing results of a BGP(basic graph pattern) clause in sparql into natural language. 
        If spot any identifier of entity or property, replace it with url_id(identifier), 
        if the value of nay namednode is a url, keep the format in the generation like url_id(<url>)"""}]
      
    for i in range(len(examples[0])):
        message.append({"role": "user", "content": examples[0][i]})
        message.append({"role": "assistant", "content": examples[1][i]})

    for i in range(len(const_prompt[0])):
        message.append({"role": "user", "content": const_prompt[0][i]})
        message.append({"role": "assistant", "content": const_prompt[1][i]})
        
    message.append({"role": "user", "content": nl})
    

    if 'temperature' in model_config:
        temperature = model_config['temperature']
    else:
        temperature = 0.2
    
    
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



def nl2bgp_parsed(nl, examples = [[],[]], const_propmt = [PATH_CONST_NL + BGP_CONST_NL, PATH_CONST_PARSE + BGP_CONST_PARSE], model="gpt-4-1106-preview", print_msg = False, model_config = {}):

    client = OpenAI()

    message = [{"role": "system", "content": """You are a query writer to convert the given natural language description into the parsing result of a single BGP(basic graph pattern) clause in sparql language.
                There must be three keys, 'subject', 'predicate' and 'object'. 
                Please generate the result in json format. """}]
      
    for i in range(len(examples[0])):
        message.append({"role": "user", "content": examples[1][i]})
        message.append({"role": "assistant", "content": examples[0][i]})
    for i in range(len(const_propmt[0])):
        message.append({"role": "user", "content": const_propmt[1][i]})
        message.append({"role": "assistant", "content": const_propmt[0][i]})
   
    message.append({"role": "user", "content": nl})

    if 'temperature' in model_config:
        temperature = model_config['temperature']
    else:
        temperature = 0.2
    
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






# def nl2bgp_parsed(nl, examples = [[],[]], const_propmt = [PATH_CONST_NL + BGP_CONST_NL, PATH_CONST_PARSE + BGP_CONST_PARSE], model="gpt-4-1106-preview", print_msg = False):

# 	client = OpenAI()

# 	message = [{"role": "system", "content": """You are a query writer to convert the given natural language description into the parsing result of a single BGP(basic graph pattern) clause in sparql language.
# 				There must be three keys, 'subject', 'predicate' and 'object'. 
# 				Please generate the result in json format. """}]
	  
# 	for i in range(len(examples[0])):
# 		message.append({"role": "user", "content": examples[1][i]})
# 		message.append({"role": "assistant", "content": examples[0][i]})
# 	for i in range(len(const_propmt[0])):
# 		message.append({"role": "user", "content": const_propmt[1][i]})
# 		message.append({"role": "assistant", "content": const_propmt[0][i]})
   
# 	message.append({"role": "user", "content": nl})
	
# 	if print_msg:
# 		for msg in message:
# 			print(msg)

# 	response = client.chat.completions.create(
# 		model=model,
# 		response_format={"type": "json_object"},
# 		temperature = 0.2,
# 		messages=message
# 	)

# 	return response.choices[0].message.content




def generate_bgp_from_gt(query_ori, 
                         query_gt, 
                         nl2bgp = nl2bgp_parsed, 
                         bgp2nl = bgp2nl_parsed, 
                         replace_ori = True, 
                         num_shots = 10,
                         seed = None,
                         model_name = "gpt-4-1106-preview"):
    code = 'parse.js'
    flag = run_js_script(code, query_ori)
    #print(11111111111, flag)
    parse_ori = load_json("parsedQueryOutput.json")
    flag = run_js_script(code, query_gt)
    #print(22222222222, flag)
    parse_gt = load_json("parsedQueryOutput.json")
    #print(parse_gt)
    patterns_gt = parse_gt['where']

    bgp_gt = [] #ground truth bgp
    #bgp_ori = [] #original bgp

    nl_gt = [] #ground truth nl
    bgp_gen_gt = [] #generated bgp from nl

    EXAMPLE = bgp_get_example()

    random.seed(seed)
    index = sample_examples(len(EXAMPLE[0]), len(EXAMPLE[0]))
    random.seed()

    examples = [[EXAMPLE[0][ind] for ind in index[:num_shots]], [EXAMPLE[1][ind] for ind in index[:num_shots]]]

    gen_bgp_parsed = [] # generated bgp patterns
    
    for pattern in patterns_gt:
        if pattern['type'] == 'bgp':
            nl_pattern = []
            bgp_pattern = []
            bgp_gen_pattern = []
            for entry in pattern['triples']:
                bgp_pattern.append(json.dumps(entry))
                nl_pattern.append(bgp2nl(bgp_pattern[-1], examples = examples, model = model_name, print_msg = False))
                bgp_gen_pattern.append(json.loads(nl2bgp(nl_pattern[-1], examples = examples, model = model_name, print_msg = False)))
            bgp_gt.append(bgp_pattern)
            nl_gt.append(nl_pattern)
            bgp_gen_gt.append(bgp_gen_pattern)
            gen_bgp_parsed.append({'type': 'bgp', 'triples': bgp_gen_pattern})



    #return bgp_gt, bgp_gen_gt, nl_gt, gen_bgp_parsed
    if replace_ori:
        parse_to_update = parse_ori
    else:
        parse_to_update = parse_gt

    new_patterns = []
    for pattern in parse_to_update['where']:
        if pattern['type'] != 'bgp':
            new_patterns.append(pattern)
    
    new_patterns += gen_bgp_parsed
    parse_to_update['where'] = new_patterns

    
    text = 'parsedQueryOutput.json'
    save_json(parse_to_update, text)
    code = 'convert.js'

    run_js_script(code, text)

    # load a string from txt file 'output.txt'
    with open('output.txt', 'r') as file:
        new_query = file.read()

    return new_query
