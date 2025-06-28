import os
from openai import OpenAI
import utils.utils
import utils.wikidata
import utils.dbpedia
from utils.llm_call import llm_call
import pdb
import json


# client = OpenAI(
#     # This is the default and can be omitted
#     api_key=os.environ.get("OPENAI_API_KEY"),
# )

from utils.utils import load_object
import interface as itf
import re

def remove_sparql_comments(query: str) -> str:
    """
    Remove all SPARQL comments (from '#' to end of line) without altering any other content.
    """
    # Process each line: strip off '#' and anything following it
    lines = query.splitlines()
    cleaned_lines = []
    for line in lines:
        if '#' in line:
            # Keep everything before the first '#'
            cleaned_lines.append(line[:line.index('#')])
        else:
            cleaned_lines.append(line)
    # Rejoin lines, preserving original line breaks
    return "\n".join(cleaned_lines)



# Load data
data_name = os.environ.get("INTER_DATA_NAME", "qald10")
remove_corr = os.environ.get("REMOVE_CORR", "True").lower() == "true"
use_question = os.environ.get("USE_QUESTION", "False").lower() == "true"
use_labels = os.environ.get("USE_LABELS", "True").lower() == "true"
use_parsed = os.environ.get("USE_PARSED", "True").lower() == "true"
use_layout = os.environ.get("USE_LAYOUT", "True").lower() == "true"
remove_few_shot = os.environ.get("REMOVE_FEW_SHOT", "False").lower() == "true"
use_raw_query = os.environ.get("USE_RAW_QUERY", "False").lower() == "true"
use_raw_query_with_shots = os.environ.get("USE_RAW_QUERY_WITH_SHOTS", "False").lower() == "true"
new_NL_exp_prompt = os.environ.get("NEW_NL_EXP_PROMPT", "True").lower() == "true"
no_comment_remover = os.environ.get("NO_COMMENT_REMOVER_NLE", "False").lower() == "true"

# print use_question
print("use_question", use_question)
print("remove_corr", remove_corr)
print("use_labels", use_labels)
print("use_parsed", use_parsed)
print("use_layout", use_layout)
print("remove_few_shot", remove_few_shot)
print("use_raw_query", use_raw_query)
print("use_raw_query_with_shots", use_raw_query_with_shots)
print("new_NL_exp_prompt", new_NL_exp_prompt)
print("no_comment_remover", no_comment_remover)


config = load_object("utils/datasets/config.pk") # camera
data_dump = config[data_name]
global data, qdata, parsed_data, test_patterns
data = data_dump['data']
qdata = data_dump['qdata']
parsed_data = data_dump['parsed_data']
test_patterns = data_dump['test_patterns']



def load_json_as_string(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return json.dumps(data, indent=4)  # Convert JSON object back to a string with formatting
    except FileNotFoundError:
        return "File not found."
    except json.JSONDecodeError:
        return "Invalid JSON file."



def get_user_prompt_with_raw(data_entry, use_labels=True, label_func=utils.wikidata.id2info, data_name=None, use_question=False, use_layout=True, use_parsed=True, use_raw_query=False, from_example=False):

    if len(data_entry) == 3:
        gt_query, nl_question, parsed_result = data_entry
    elif type(data_entry) == int:
        assert data_name is not None, "data_name must be provided when data_entry is an integer"
        data_source = config[data_name]

        gt_query = data_source['data']['questions'][data_entry]['query']['sparql']
        parsed_result = data_source['parsed_data'][str(data_entry)]
        nl_question = data_source['data']['questions'][data_entry]['question'][0]['string']

    elif type(data_entry) == dict:
        assert 'query' in data_entry and 'question' in data_entry, "data_entry must have 'query' and 'question' keys"
        gt_query = data_entry['query']
        nl_question = data_entry['question']
        parsed_result = utils.utils.parse_query(data_entry['query'])
    
    explanation, paths = itf.parse_sparql_query(parsed_result, use_labels=use_labels, label_func=label_func)


    if not from_example and not no_comment_remover:
        gt_query = remove_sparql_comments(gt_query)

    # deal with user_question
    if use_question:
        nl_question_str = \
f"""
Natural Language(NL) Question:
{nl_question}

"""
    else:
        nl_question_str = ""

    if use_parsed:
        parsed_result_str = \
f"""
Parsed Result:
{parsed_result}

"""
    else:
        parsed_result_str = ""


    # deal with user_query
    if use_labels:
        label_str = \
f"""
Information for NamedNodes:
{utils.utils.extract_namednode_values(parsed_result, label_func=label_func)}

"""
        
    else:
        label_str = ""

    if use_layout:
        layout_str = \
f"""
General layout:
{explanation}

"""
    else:
        layout_str = ""

    user_prompt = \
f"""
{nl_question_str}SPARQL Query:
{gt_query}

{parsed_result_str}{label_str}{layout_str}
"""
    
    if use_raw_query:
        user_prompt = \
f"""
SPARQL Query:
{gt_query}
"""

    return user_prompt


def get_user_prompt_with_index(index, use_labels=True, label_func=utils.wikidata.id2info, data = None, parsed_data = None, use_question=True, use_layout=True, use_parsed=True, use_raw_query=False):
    gt_query = data['questions'][index]['query']['sparql']
    parsed_result = parsed_data[str(index)]
    nl_question = data['questions'][index]['question'][0]['string']

    user_prompt = get_user_prompt_with_raw((gt_query, nl_question, parsed_result), use_labels=use_labels, label_func=label_func, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed, use_raw_query=use_raw_query, from_example=True)

    return user_prompt

# load use_labels from environment

if use_labels:
    entity_note = "label of entiries and properties applied in the query are given in brackets after the id, **please adhere to this in the generation**."
else:
    entity_note = ""

system_prompt_2 = \
f"""
I give you the question in natural language, the corresponding SPARQL query and the parsed result of that query in JSON. 
Please return in modularized way in JSON using the general layout({entity_note}) as a reference and make it easy to understand with smooth language.
Please obey the following requirements:
1. Make sure each module has sparql statement (related query part), an explanation in natural language, an desciption of which part of question corresponds to this module. Also give an overall NL explanation for the query.
2. When any variable included in certain module , please include the variable name (like (?result)) in the explanation.
3. If there is subquery in the query, please explain the subquery like a new query. Put it in nested version in subquery pattern.
4. Explain the 'group by', 'order by', 'limit' and 'offset' pattern in the query and put related explanation in the 'Explanation' and 'Correspondence' Variable section. Also attach the corresponding code part to 'SPARQL'. Please do not add special keys in the json for this part!!!!!!".
5. In Explanation, please put URL/ID of the entities and properties in <> and its label in [], like <Q123> [label]."""

if remove_corr:
    system_prompt_2 = \
f"""
I give you the question in natural language, the corresponding SPARQL query and the parsed result of that query in JSON. 
Please return in modularized way in JSON using the general layout({entity_note}) as a reference and make it easy to understand with smooth language.
Please obey the following requirements:
1. Make sure each module has sparql statement (related query part) and an explanation in natural language. Also give an overall NL explanation for the query.
2. When any variable included in certain module , please include the variable name (like (?result)) in the explanation.
3. If there is subquery in the query, please explain the subquery like a new query. Put it in nested version in subquery pattern.
4. Explain the 'group by', 'order by', 'limit' and 'offset' pattern in the query and put related explanation in the 'Explanation' Variable section. Also attach the corresponding code part to 'SPARQL'. Please do not add special keys in the json for this part!".
5. In Explanation, please put URL/ID of the entities and properties in <> and its label in [], like <Q123> [label]."""

if not use_question:
    system_prompt_2 = \
f"""
I give you a SPARQL query and the parsed result of that query in JSON. Your task is to explain the query in natural language.
Please return in modularized way in JSON using the general layout({entity_note}) as a reference and make it easy to understand with smooth language.
Please obey the following requirements:
1. Make sure each module has sparql statement (related query part) and an explanation in natural language. Also give an overall NL explanation for the query.
2. When any variable included in certain module , please include the variable name (like (?result)) in the explanation.
3. If there is subquery in the query, please explain the subquery like a new query. Put it in nested version in subquery pattern.
4. Explain the 'group by', 'order by', 'limit' and 'offset' pattern in the query and put related explanation in the 'Explanation' Variable section. Also attach the corresponding code part to 'SPARQL'. Please do not add special keys in the json for this part!".
5. In Explanation, please put URL/ID of the entities and properties in <> and its label in [], like <Q123> [label]."""

if new_NL_exp_prompt == False:
    system_prompt_2  += "\n"
else:
    system_prompt_2  += " Please always stick to use the entity/predicate label given in the General Layout under any case, please make 100% sure to do it!!!!!!\n"


system_prompt_raw = \
f"""
I give you a SPARQL query. Your task is to explain the query in natural language.
Please return in modularized way in JSON make it easy to understand with smooth language.
"""

if new_NL_exp_prompt == False:
    extra_user_prompt = "Please stick to the label of the entities and properties given in \"Information for NamedNodes\" in the generation when label needed (but do not mess with other part). But still Please stick to the format expressed in system prompt and given in above examples"
else:
    extra_user_prompt = "Please firmly stick to the label of the entities and properties given in \"Information for NamedNodes\" in () after each node in the generation when label needed in filling in any square bracket for any entity mentioned, e.g. in [], even the label does not fit the query intention at all! Do not care whether it makes, just stick whatever it is!!!"



user_prompt_1 = get_user_prompt_with_index(374, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed) + extra_user_prompt  # (bind)
if remove_corr:
    assist_prompt_1 = load_json_as_string("nle_few_shot_exp/exp1.json")
else:
    raise ValueError("assist_prompt_1 is not defined, please check the path")

if use_raw_query_with_shots:
    user_prompt_1 = get_user_prompt_with_index(374, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed, use_raw_query=True) 


user_prompt_2 = get_user_prompt_with_index(30, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed) + extra_user_prompt  # (bgp, union, filter)
if remove_corr:
    assist_prompt_2 = load_json_as_string("nle_few_shot_exp/exp2.json")
else:
    raise ValueError("assist_prompt_2 is not defined, please check the path")

if use_raw_query_with_shots:
    user_prompt_2 = get_user_prompt_with_index(30, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed, use_raw_query=True)


user_prompt_4 = get_user_prompt_with_index(159, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed) + extra_user_prompt # (bgp, union, filter)
if remove_corr:
    assist_prompt_4 = load_json_as_string("nle_few_shot_exp/exp4.json")
else:
    raise ValueError("assist_prompt_4 is not defined, please check the path")

if use_raw_query_with_shots:
    user_prompt_4 = get_user_prompt_with_index(159, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed, use_raw_query=True) 

user_prompt_5 = get_user_prompt_with_index(22, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed) + extra_user_prompt      # (subquery, filter, minus)
if remove_corr:
    assist_prompt_5 = load_json_as_string("nle_few_shot_exp/exp5.json")
else:
    raise ValueError("assist_prompt_5 is not defined, please check the path")

if use_raw_query_with_shots:
    user_prompt_5 = get_user_prompt_with_index(22, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed, use_raw_query=True) 
    

user_prompt_6 = get_user_prompt_with_index(23, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed) + extra_user_prompt   # (groupby, subquery, optional)
if remove_corr:
    assist_prompt_6 = load_json_as_string("nle_few_shot_exp/exp6.json")
else:
    raise ValueError("assist_prompt_6 is not defined, please check the path")

if use_raw_query_with_shots:
    user_prompt_6 = get_user_prompt_with_index(23, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed, use_raw_query=True) 


user_prompt_7 = get_user_prompt_with_index(310, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed) + extra_user_prompt  # (groupby, orderby, limit, having)
if remove_corr:
    assist_prompt_7 = load_json_as_string("nle_few_shot_exp/exp7.json")
else:
    raise ValueError("assist_prompt_7 is not defined, please check the path")

if use_raw_query_with_shots:
    user_prompt_7 = get_user_prompt_with_index(310, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed, use_raw_query=True) 


user_prompt_8 = get_user_prompt_with_index(27, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed) + extra_user_prompt # (bgp, filter, orderby, limit, offset, limit)
if remove_corr:
    assist_prompt_8 = load_json_as_string("nle_few_shot_exp/exp8.json")
else:
    raise ValueError("assist_prompt_8 is not defined, please check the path")

if use_raw_query_with_shots:
    user_prompt_8 = get_user_prompt_with_index(27, use_labels=use_labels, label_func=utils.wikidata.id2info, data=data, parsed_data=parsed_data, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed, use_raw_query=True)



# def generate_nl_explanation(data_entry, model_name="gpt-4o-2024-08-06", temperature=0, use_labels=True, label_func=utils.wikidata.id2info, use_question=False, use_layout=True, use_parsed=True):
#     user_prompt_9 = get_user_prompt_with_raw(data_entry, use_labels=use_labels, label_func=label_func, use_layout=use_layout, use_parsed=use_parsed) + extra_user_prompt



#     message1 = [{"role": "system", "content": system_prompt_2},
#                 {"role": "user", "content": user_prompt_1},
#                 {"role": "assistant", "content": assist_prompt_1},
#                 {"role": "user", "content": user_prompt_2},
#                 {"role": "assistant", "content": assist_prompt_2},
#                 {"role": "user", "content": user_prompt_4},
#                 {"role": "assistant", "content": assist_prompt_4},
#                 {"role": "user", "content": user_prompt_5},
#                 {"role": "assistant", "content": assist_prompt_5},
#                 {"role": "user", "content": user_prompt_6},
#                 {"role": "assistant", "content": assist_prompt_6},
#                 {"role": "user", "content": user_prompt_7},
#                 {"role": "assistant", "content": assist_prompt_7},
#                 {"role": "user", "content": user_prompt_8},
#                 {"role": "assistant", "content": assist_prompt_8},
#                 {"role": "user", "content": user_prompt_9}
#             ]
    

#     if model_name == "gpt-4o-2024-08-06":
#         response_1 = client.chat.completions.create(
#         model=model_name,
#         response_format={"type": "json_object"},
#         temperature = temperature,
#         messages=message1
#     )

#     elif model_name == "o1-preview":
#         user_prompt = system_prompt_2 + user_prompt_1
#         message = message1
#         response_1 = client.chat.completions.create(
#         model=model_name,
#         messages=message
#     )

#     else:
#         raise ValueError("model name not supported")
            
#     return response_1.choices[0].message.content




def generate_nl_explanation_with_cfg(data_entry, llm_name, model_version, use_labels, label_func, use_question, use_layout, use_parsed, llm_cfg):
    user_prompt_9 = get_user_prompt_with_raw(data_entry, use_labels=use_labels, label_func=label_func, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed) + extra_user_prompt


    # print("final user prompt", user_prompt_9)



    message1 = [{"role": "system", "content": system_prompt_2},
                {"role": "user", "content": user_prompt_1},
                {"role": "assistant", "content": assist_prompt_1},
                {"role": "user", "content": user_prompt_2},
                {"role": "assistant", "content": assist_prompt_2},
                {"role": "user", "content": user_prompt_4},
                {"role": "assistant", "content": assist_prompt_4},
                {"role": "user", "content": user_prompt_5},
                {"role": "assistant", "content": assist_prompt_5},
                {"role": "user", "content": user_prompt_6},
                {"role": "assistant", "content": assist_prompt_6},
                {"role": "user", "content": user_prompt_7},
                {"role": "assistant", "content": assist_prompt_7},
                {"role": "user", "content": user_prompt_8},
                {"role": "assistant", "content": assist_prompt_8},
                {"role": "user", "content": user_prompt_9}
            ]

    
    if model_version == "Qwen/Qwen2.5-32B-Instruct":
        message1 = [{"role": "system", "content": system_prompt_2},
                {"role": "user", "content": user_prompt_1},
                {"role": "assistant", "content": assist_prompt_1},
                {"role": "user", "content": user_prompt_4},
                {"role": "assistant", "content": assist_prompt_4},
                {"role": "user", "content": user_prompt_5},
                {"role": "assistant", "content": assist_prompt_5},
                {"role": "user", "content": user_prompt_6},
                {"role": "assistant", "content": assist_prompt_6},
                {"role": "user", "content": user_prompt_7},
                {"role": "assistant", "content": assist_prompt_7},
                {"role": "user", "content": user_prompt_8},
                {"role": "assistant", "content": assist_prompt_8},
                {"role": "user", "content": user_prompt_9}
            ]
        

    if remove_few_shot and not use_raw_query:
        message1 = [{"role": "system", "content": system_prompt_2},
                {"role": "user", "content": user_prompt_9}]

    if use_raw_query_with_shots and not use_raw_query:
        user_prompt_9 = get_user_prompt_with_raw(data_entry, use_labels=use_labels, label_func=label_func, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed, use_raw_query=True) # + extra_user_prompt

        message1 = [{"role": "system", "content": system_prompt_raw},
                {"role": "user", "content": user_prompt_1},
                {"role": "assistant", "content": assist_prompt_1},
                {"role": "user", "content": user_prompt_4},
                {"role": "assistant", "content": assist_prompt_4},
                {"role": "user", "content": user_prompt_5},
                {"role": "assistant", "content": assist_prompt_5},
                {"role": "user", "content": user_prompt_6},
                {"role": "assistant", "content": assist_prompt_6},
                {"role": "user", "content": user_prompt_7},
                {"role": "assistant", "content": assist_prompt_7},
                {"role": "user", "content": user_prompt_8},
                {"role": "assistant", "content": assist_prompt_8},
                {"role": "user", "content": user_prompt_9}
            ]

    if use_raw_query:
        user_prompt_9 = get_user_prompt_with_raw(data_entry, use_labels=use_labels, label_func=label_func, use_question=use_question, use_layout=use_layout, use_parsed=use_parsed, use_raw_query=True) # + extra_user_prompt
        

        message1 = [{"role": "system", "content": system_prompt_raw},
                {"role": "user", "content": user_prompt_9}]


    output = llm_call(llm_name, model_version, message1, llm_cfg)

    return output

