import os
import json
import re
import logging
from datetime import datetime
from tqdm import tqdm
import pdb
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError
from utils.eval_raw import evaluate_sparql_queries, execute_sparql_query_dbpedia, execute_sparql_query_wiki
from utils.datasets.quad10 import QALD10, QALD9
import utils.NL_exp
import utils.wikidata
import utils.dbpedia
from utils.dbpedia import id_search_dbpedia, search_dbpedia_properties
from utils.wikidata import entity_id_search_wiki, property_id_search_wiki
from utils.utils import load_json
from utils.llm_call import make_retry_decorator, llm_call
import time
from openai import OpenAI
###########################################################################
# Tool definitions and function mapping
###########################################################################
function_mapping = {
	"entity_id_search_wiki": entity_id_search_wiki,
	"property_id_search_wiki": property_id_search_wiki,
	"id_search_dbpedia": id_search_dbpedia,
	"search_dbpedia_properties": search_dbpedia_properties
}
tools_wiki = [
	{
		"type": "function",
		"function": {
			"name": "entity_id_search_wiki",
			"description": "Searches Wikidata for an entity and returns the top result's URL, label, and description.",
			"parameters": {
				"type": "object",
				"properties": {
					"q": {"type": "string", "description": "The search query for the entity."}
				},
				"required": ["q"],
				"additionalProperties": False
			}
		}
	},
	{
		"type": "function",
		"function": {
			"name": "property_id_search_wiki",
			"description": "Searches Wikidata for a property and returns the top result's URL, label, and description.",
			"parameters": {
				"type": "object",
				"properties": {
					"q": {"type": "string", "description": "The search query for the property."}
				},
				"required": ["q"],
				"additionalProperties": False
			}
		}
	}
]
tools_dbpedia = [
	{
		"type": "function",
		"function": {
			"name": "id_search_dbpedia",
			"description": "Searches DBpedia for an entity and returns the top result's URI, label, and description.",
			"parameters": {
				"type": "object",
				"properties": {
					"q": {"type": "string", "description": "The search query for the entity."}
				},
				"required": ["q"],
				"additionalProperties": False
			}
		}
	},
	{
		"type": "function",
		"function": {
			"name": "search_dbpedia_properties",
			"description": "Searches DBpedia properties based on a query label and returns matching results.",
			"parameters": {
				"type": "object",
				"properties": {
					"q": {"type": "string", "description": "The label or keyword to search for."}
				},
				"required": ["q"],
				"additionalProperties": False
			}
		}
	}
]

###########################################################################
# Customized NL Explanation via create_llm_call_for_nle_gen
###########################################################################
def create_llm_call_for_nle_gen(llm_name, model_version, max_tokens, temperature, response_format_json, kg,
								use_label, use_question, use_layout, use_parsed, json_parsable, max_attempts=3, wait_seconds=1):
	"""
	Returns a function (already decorated) that fetches data.
	"""
	@make_retry_decorator(max_attempts, wait_seconds)
	def nle_gen_call(data_entry):
		cfg = {
			"max_tokens": max_tokens,
			"temperature": temperature,
			"response_format_json": response_format_json
		}
		if kg == "wiki":
			label_func = utils.wikidata.id2info
		elif kg == "dbpedia":
			label_func = utils.dbpedia.dbpedia_id2label

		output = utils.NL_exp.generate_nl_explanation_with_cfg(
			data_entry, llm_name, model_version, use_label, label_func, use_question, use_layout, use_parsed, cfg
		)

		if json_parsable:
			try:
				output = json.loads(output)
				print("Output is json parsable")
			except:
				print("Output is not json parsable w/o modification")
				res = re.sub(r'^```json', '', output)
				res = re.sub(r'```$', '', res)
				output = json.loads(res)
				print("Output is json parsable now!!!")
		return output
	return nle_gen_call

def generate_nl_explanation(sparql_query, question, kg_name, nle_config):
	"""
	Generates a natural language explanation using the unified nle_config.
	nle_config is assumed to be built from environment variables for NL settings.
	"""
	data_entry = {'query': sparql_query, 'question': question}
	nle_gen_call = create_llm_call_for_nle_gen(
		nle_config["llm_name"],
		nle_config["model_version"],
		nle_config["max_tokens"],
		nle_config["temperature"],
		nle_config["response_format_json"],
		kg_name,
		nle_config["use_label"],
		nle_config["use_question"],
		nle_config["use_layout"],
		nle_config["use_parsed"],
		nle_config["json_parsable"],
		nle_config["max_attempts"],
		nle_config["wait_seconds"]
	)
	return nle_gen_call(data_entry)

###########################################################################
# Feedback Module (using GPT4o with tool usage; fixed to GPT4o)
###########################################################################
def feedback_module(question, sparql_query, nl_explanation, query_results, feedback_config, use_tools, kg_name):
	"""
	Uses GPT4o (with tools if specified) to provide feedback on the SPARQL query.
	The configuration is taken from feedback_config.
	"""
	from openai import OpenAI
	client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
	# system_prompt = (
	#     "You are an expert in SPARQL query evaluation and refinement. Analyze the SPARQL query, its natural language explanation, and the query results. "
	#     "Return your feedback as a JSON object with keys 'decision' (a boolean) and 'advise' (a string with suggestions)."
	# )

	system_prompt = (
		"You are an expert in SPARQL query evaluation and refinement. "
		"Your task is to analyze a SPARQL query, its natural language explanation, and the results produced by the query. "
		"You will evaluate whether the query aligns with the given natural language question and produces logical results. "
		"If the query is correct and aligned with the question, you will validate it. If it is incorrect, "
		"you will suggest specific refinements. Always return your feedback in a JSON object with the following structure:\n\n"
		"1. 'decision': A boolean value where 'true' means refinement is needed and 'false' means the query is correct.\n"
		"2. 'advise': A string containing suggestions for improvement if 'decision' is true, or a validation message if it is false.\n"
		"If the query has issues on entity or property selection, be sure to use the provided tools/function to search for the correct entity or property\n\n"
		"For example:\n"
		"{\n"
		"  \"decision\": True,\n"
		"  \"advise\": \"The query is missing a filter to exclude non-European countries. Add a condition to ensure ?country belongs to Europe.\"\n"
		"}\n\n"
		"OR\n"
		"{\n"
		"  \"decision\": False,\n"
		"  \"advise\": \"The query aligns well with the natural language question and produces accurate results.\"\n"
		"}\n\n"
		"Always ensure the output is valid JSON. Do not include any other text outside the JSON object."
	)

	user_prompt = "Natural Language Question:\n" + question + "\n\n"
	if sparql_query:
		user_prompt += "SPARQL Query:\n" + sparql_query + "\n\n"
	if nl_explanation:

		user_prompt += "Natural Language Explanation:\n" + json.dumps(nl_explanation, indent=4) + "\n\n"
		extra_prompt = "please use the Natural Language Explanation well to help you understand the query better."
	if query_results is not None:
		user_prompt += "Query Results:\n" + str(query_results) + "\n\n"

	if kg_name == 'dbpedia':
		user_prompt += (
			"Do the query results align with the natural language question? If not, suggest specific refinements. "
			"If you are sure the query has issues on entity or property usage, you can use the provided tools to search for the correct entity or property.\n"
		)
		if nl_explanation is not None:
			user_prompt += extra_prompt
		user_prompt += (
			"Return your response in JSON format as described above."
		)
	else:
		user_prompt += (
		"Do the query results align with the natural language question? If not, suggest specific refinements "
		"(when you think the current query is far away from truth, you might recommend rewrite completely). "
		"If the query has issues on entity or property usage, be sure use the provided tools to search for the correct entity or property.\n\n"
		"Return your response in JSON format as described above."
	)
	

	messages = [
		{"role": "system", "content": system_prompt},
		{"role": "user", "content": user_prompt}
	]
	response = client.chat.completions.create(
		model=feedback_config["llm_name"],
		response_format={"type": "json_object"},
		temperature=feedback_config["temperature"],
		messages=messages,
		tools=(tools_wiki if kg_name == "wiki" else tools_dbpedia) if use_tools else None
	)
	calls = response.choices[0].message.tool_calls
	if calls:
		new_msgs = [
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt},
			response.choices[0].message
		]
		for call in calls:
			args_dict = json.loads(call.function.arguments)
			q = args_dict.get("q", None)
			func_name = call.function.name
			func = function_mapping.get(func_name)
			if q and func:
				result = func(q)
				tool_reply = {
					"role": "tool",
					"content": json.dumps({"q": q, "SearchResult": result}),
					"tool_call_id": call.id
				}
				new_msgs.append(tool_reply)
		response = client.chat.completions.create(
			model=feedback_config["llm_name"],
			response_format={"type": "json_object"},
			temperature=feedback_config["temperature"],
			messages=new_msgs
		)
	feedback_str = response.choices[0].message.content.strip()
	try:
		return json.loads(feedback_str)
	except json.JSONDecodeError:
		print("Feedback not in valid JSON format.")
		return {"decision": False, "advise": "Feedback generation failed."}
	


def feedback_module_1(question, sparql_query, nl_explanation, query_results, feedback_config, use_tools, kg_name):
    """
    Uses GPT-4o (with tools if specified) to provide feedback on the SPARQL query.
    The feedback is returned as a JSON object with:
    - 'decision': bool indicating whether refinement is needed
    - 'advise': a string with suggestions or validation
    """

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # System prompt for role definition
    system_prompt = (
        "You are an expert in SPARQL query evaluation and refinement. "
        "Given a natural language question, a SPARQL query, its explanation, and the query results, "
        "evaluate whether the query correctly answers the question. If not, suggest improvements.\n\n"
        "Always return your output as a *valid JSON* object with two fields:\n"
        "  - 'decision': true if the query needs refinement, false otherwise\n"
        "  - 'advise': a string with your reasoning or refinement suggestion\n\n"
        "If the query has issues related to entity or property selection, use the provided tools to improve it.\n"
        "Do not include any text outside the JSON object.\n\n"
        "Examples:\n"
        "{\n"
        "  \"decision\": true,\n"
        "  \"advise\": \"The query uses the wrong property for cast membership. Use wdt:P161 instead of wdt:P57.\"\n"
        "}\n\n"
        "{\n"
        "  \"decision\": false,\n"
        "  \"advise\": \"The query is semantically correct and aligned with the question.\"\n"
        "}"
    )

    # Construct user prompt with structured headers
    user_prompt = f"""### Natural Language Question:
{question}

### SPARQL Query:
{sparql_query or "[Not provided]"}

### Natural Language Explanation:
{json.dumps(nl_explanation, indent=4) if nl_explanation else "[Not provided]"}
(Use this explanation to better understand the query structure.)

### Query Results:
{str(query_results) if query_results is not None else "[Not provided]"}

### Evaluation Instructions:
Evaluate if the query answers the question accurately. If it doesn't, suggest specific refinements.
- If the query is correct, return 'decision': false and explain why.
- If it's incorrect, return 'decision': true and suggest precise changes.
- If entity or property usage seems wrong, use the provided tools to improve it.
- If it's fundamentally flawed, you may recommend rewriting it entirely.
Respond with *only* a valid JSON object as shown in the examples.
"""

    # Assemble messages
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # Prepare tools if applicable
    tools = None
    if use_tools:
        tools = tools_wiki if kg_name == "wiki" else tools_dbpedia

    # Initial model call
    response = client.chat.completions.create(
        model=feedback_config["llm_name"],
        response_format={"type": "json_object"},
        temperature=feedback_config["temperature"],
        messages=messages,
        tools=tools
    )

    # Handle tool calls if any
    calls = response.choices[0].message.tool_calls
    if calls:
        new_msgs = messages + [response.choices[0].message]
        for call in calls:
            args = json.loads(call.function.arguments)
            query_term = args.get("q")
            func = function_mapping.get(call.function.name)
            if query_term and func:
                result = func(query_term)
                tool_reply = {
                    "role": "tool",
                    "content": json.dumps({"q": query_term, "SearchResult": result}),
                    "tool_call_id": call.id
                }
                new_msgs.append(tool_reply)

        # Second pass with tool results
        response = client.chat.completions.create(
            model=feedback_config["llm_name"],
            response_format={"type": "json_object"},
            temperature=feedback_config["temperature"],
            messages=new_msgs
        )

    # Final output parsing
    feedback_str = response.choices[0].message.content.strip()
    try:
        return json.loads(feedback_str)
    except json.JSONDecodeError:
        print("⚠️ Feedback not in valid JSON format.")
        return {
            "decision": False,
            "advise": "The feedback could not be parsed. Model may have returned malformed output."
        }

### choice of feedback module
feedback_module_dict = {
	"func1" : feedback_module_1}

###########################################################################
# Refine SPARQL Query using customized llm_call with refine_config
###########################################################################
def refine_sparql_query(question, sparql_query, feedback, label_func, kg_name, refine_config, use_nl_exp=True, nl_exp=None):
	if not feedback.get("decision", False):
		return sparql_query
	if use_nl_exp:
		nl_explanation = nl_exp if nl_exp else generate_nl_explanation(sparql_query, question, kg_name, refine_config)
	else:
		nl_explanation = None
	advice = feedback.get("advise", "No advice provided.")
	# system_prompt = (
	# 	"You are an expert in SPARQL query generation and refinement. Refine the given SPARQL query using the provided feedback so that it better aligns with the natural language question. Return only the refined SPARQL query."
	# )

	# if no comment
	if refine_config["no_comment_regen"]:
		system_prompt = (
			"You are an expert in SPARQL query generation and refinement. Your task is to refine a given SPARQL query "
			"based on feedback. Use the provided feedback to improve the query while ensuring it remains aligned with "
			"the original question and its explanation. Only return the refined SPARQL query, without additional text."
			"Do not generate any comments or explanations other than the query itself. "
			"You do not need to limit yourself to the feedback and refine the query as much as possible to the original question and any hint you can find. " 
		)
	else:
		system_prompt = (
			"You are an expert in SPARQL query generation and refinement. Your task is to refine a given SPARQL query "
			"based on feedback. Use the provided feedback to improve the query while ensuring it remains aligned with "
			"the original question and its explanation. Only return the refined SPARQL query, without additional text."
		)

	# if nl_explanation:
	# 	user_prompt = (
	# 		f"Natural Language Question:\n{question}\n\n"
	# 		f"Current SPARQL Query:\n{sparql_query}\n\n"
	# 		f"Natural Language Explanation:\n{nl_explanation}\n\n"
	# 		f"Feedback:\n{advice}\n\n"
	# 		"Refine the SPARQL query accordingly."
	# 	)
	# else:
	# 	user_prompt = (
	# 		f"Natural Language Question:\n{question}\n\n"
	# 		f"Current SPARQL Query:\n{sparql_query}\n\n"
	# 		f"Feedback:\n{advice}\n\n"
	# 		"Refine the SPARQL query accordingly."
	# 	)

	if nl_explanation:
		# Construct the user prompt with detailed context
		user_prompt = (
			f"Natural Language Question:\n{question}\n\n"
			f"Current SPARQL Query:\n{sparql_query}\n\n"
			f"Natural Language Explanation of the Query:\n{nl_explanation}\n\n"
			f"Feedback for Refinement:\n{advice}\n\n"
			"Refine the SPARQL query based on the feedback and ensure it aligns with the natural language question."
		)
	else:
		# Construct the user prompt without the NL explanation
		user_prompt = (
			f"Natural Language Question:\n{question}\n\n"
			f"Current SPARQL Query:\n{sparql_query}\n\n"
			f"Feedback for Refinement:\n{advice}\n\n"
			"Refine the SPARQL query based on the feedback and ensure it aligns with the natural language question."
		)
	messages = [
		{"role": "system", "content": system_prompt},
		{"role": "user", "content": user_prompt}
	]
	cfg = {
		"max_tokens": refine_config["max_tokens"],
		"temperature": refine_config["temperature"],
		"response_format_json": refine_config["response_format_json"]
	}
	output = llm_call(refine_config["llm_name"], refine_config["model_version"], messages, cfg)
	return output

###########################################################################
# Utility: Clean SPARQL Response
###########################################################################
def clean_sparql_response(resp):
	resp = resp.strip()
	if resp.startswith("```sparql"):
		resp = resp[9:]
	elif resp.startswith("```"):
		resp = resp[3:]
	if resp.endswith("```"):
		resp = resp[:-3]
	return resp.strip()

###########################################################################
# Retry Wrapper
###########################################################################
@retry(stop=stop_after_attempt(5), wait=wait_fixed(2), reraise=True)
def execute_with_retry(func, *args, **kwargs):
	return func(*args, **kwargs)

###########################################################################
# Iterative Refinement Functions
###########################################################################
def iterative_refinement(question, initial_query, kg_name, tools_flag, max_iters, nle_config, feedback_config, refine_config):
	sparql_query = initial_query
	iters = 0
	while iters < max_iters:
		if kg_name == "wiki":
			nl_explanation = generate_nl_explanation(sparql_query, question, kg_name, nle_config)
			query_results = execute_sparql_query_wiki(sparql_query)
			if feedback_config['feedback_func'] is not None:
				feedback_module_use = feedback_module_dict[feedback_config['feedback_func']]
				feedback = feedback_module_use(question, sparql_query, nl_explanation, list(query_results), feedback_config, tools_flag, kg_name)
				# pdb.set_trace()
			else:
				feedback = feedback_module(question, sparql_query, nl_explanation, list(query_results), feedback_config, tools_flag, kg_name)
			logging.info(f"Iteration {iters+1} Feedback: {feedback}")
			if not feedback.get("decision", False):
				break
			sparql_query = refine_sparql_query(question, sparql_query, feedback, utils.wikidata.id2info, kg_name, refine_config, True, nl_explanation)
			sparql_query = clean_sparql_response(sparql_query)
			print(sparql_query)
		elif kg_name == "dbpedia":
			nl_explanation = generate_nl_explanation(sparql_query, question, kg_name, nle_config)
			query_results = execute_sparql_query_dbpedia(sparql_query)
			feedback = feedback_module(question, sparql_query, nl_explanation, query_results, feedback_config, tools_flag, kg_name)
			logging.info(f"Iteration {iters+1} Feedback: {feedback}")
			if not feedback.get("decision", False):
				break
			sparql_query = refine_sparql_query(question, sparql_query, feedback, utils.dbpedia.dbpedia_id2label, kg_name, refine_config, True, nl_explanation)
			sparql_query = clean_sparql_response(sparql_query)
			print(sparql_query)
		else:
			print("Knowledge Graph not supported.")
			break
		iters += 1
	return sparql_query

def iterative_refinement_ground(question, initial_query, kg_name, tools_flag, max_iters, nle_config, feedback_config, refine_config):
	sparql_query = initial_query
	iters = 0
	while iters < max_iters:
		if kg_name == "wiki":
			feedback = feedback_module(question, sparql_query, None, None, feedback_config, tools_flag, kg_name)
			if not feedback.get("decision", False):
				break
			sparql_query = refine_sparql_query(question, sparql_query, feedback, None, kg_name, refine_config, False)
			sparql_query = clean_sparql_response(sparql_query)
			print(sparql_query)
		elif kg_name == "dbpedia":
			feedback = feedback_module(question, sparql_query, None, None, feedback_config, tools_flag, kg_name)
			if not feedback.get("decision", False):
				break
			sparql_query = refine_sparql_query(question, sparql_query, feedback, None, kg_name, refine_config, False)
			sparql_query = clean_sparql_response(sparql_query)
			print(sparql_query)
		else:
			print("Knowledge Graph not supported.")
			break
		iters += 1
	return sparql_query

def iterative_refinement_nl_exp(question, initial_query, kg_name, tools_flag, max_iters, nle_config, feedback_config, refine_config):
	sparql_query = initial_query
	iters = 0
	while iters < max_iters:
		if kg_name == "wiki":
			nl_explanation = generate_nl_explanation(sparql_query, question, kg_name, nle_config)
			feedback = feedback_module(question, sparql_query, nl_explanation, None, feedback_config, tools_flag, kg_name)
			if not feedback.get("decision", False):
				break
			sparql_query = refine_sparql_query(question, sparql_query, feedback, utils.wikidata.id2info, kg_name, refine_config, True, nl_explanation)
			sparql_query = clean_sparql_response(sparql_query)
			print(sparql_query)
		elif kg_name == "dbpedia":
			nl_explanation = generate_nl_explanation(sparql_query, question, kg_name, nle_config)
			feedback = feedback_module(question, sparql_query, nl_explanation, None, feedback_config, tools_flag, kg_name)
			if not feedback.get("decision", False):
				break
			sparql_query = refine_sparql_query(question, sparql_query, feedback, utils.dbpedia.dbpedia_id2label, kg_name, refine_config, True, nl_explanation)
			sparql_query = clean_sparql_response(sparql_query)
			print(sparql_query)
		else:
			print("Knowledge Graph not supported.")
			break
		iters += 1
	return sparql_query

def iterative_refinement_external(question, initial_query, kg_name, tools_flag, max_iters, nle_config, feedback_config, refine_config):
	sparql_query = initial_query
	iters = 0
	while iters < max_iters:
		if kg_name == "wiki":
			query_results = execute_sparql_query_wiki(sparql_query)
			feedback = feedback_module(question, sparql_query, None, list(query_results), feedback_config, tools_flag, kg_name)
			if not feedback.get("decision", False):
				break
			sparql_query = refine_sparql_query(question, sparql_query, feedback, utils.wikidata.id2info, kg_name, refine_config, False)
			sparql_query = clean_sparql_response(sparql_query)
			print(sparql_query)
		elif kg_name == "dbpedia":
			query_results = execute_sparql_query_dbpedia(sparql_query)
			feedback = feedback_module(question, sparql_query, None, query_results, feedback_config, tools_flag, kg_name)
			if not feedback.get("decision", False):
				break
			sparql_query = refine_sparql_query(question, sparql_query, feedback, utils.dbpedia.dbpedia_id2label, kg_name, refine_config, False)
			sparql_query = clean_sparql_response(sparql_query)
			print(sparql_query)
		else:
			print("Knowledge Graph not supported.")
			break
		iters += 1
	return sparql_query

###########################################################################
# Main Pipeline Entry Point for Self-Refinement
###########################################################################
def run_self_refine(config):
	"""
	Main pipeline for self-refinement.
	Uses parameters with prefix 'self_refine_'.
	"""
	# Load environment variables for NL explanation generation (already set externally)
	# Build unified configuration dictionaries from config keys:
	nle_config = {
		"llm_name": config.get("self_refine_nle_llm_name", "GPT4o"),
		"model_version": config.get("self_refine_nle_model_version", "gpt-4o-2024-08-06"),
		"temperature": config.get("self_refine_nle_temperature", 0.0),
		"max_tokens": config.get("self_refine_nle_max_tokens", -1),
		"response_format_json": config.get("self_refine_nle_response_format_json", True),
		"use_label": os.environ.get("USE_LABELS", "True") == "True",
		"use_question": os.environ.get("USE_QUESTION", "False") == "True",
		"use_layout": os.environ.get("USE_LAYOUT", "True") == "True",
		"use_parsed": os.environ.get("USE_PARSED", "True") == "True",
		"use_raw_query": os.environ.get("USE_RAW_QUERY", "False") == "True",
		"remove_few_shot": os.environ.get("REMOVE_FEW_SHOT", "False") == "True",
		"use_raw_query_with_shots": os.environ.get("USE_RAW_QUERY_WITH_SHOTS", "False") == "True",
		"new_NL_exp_prompt": os.environ.get("NEW_NL_EXP_PROMPT", "True") == "True",
		"no_comment_remover": os.environ.get("NO_COMMENT_REMOVER_NLE", "False") == "True",
		"json_parsable": config.get("self_refine_nle_json_parsable", True),
		"max_attempts": config.get("self_refine_nle_max_attempts", 3),
		"wait_seconds": config.get("self_refine_nle_wait_seconds", 1)
	}
	feedback_config = {
		"llm_name": config.get("self_refine_feedback_llm_name", "GPT4o"),
		"temperature": config.get("self_refine_feedback_temperature", 0.2),
		"openai_api_key": config.get("openai_api_key", os.environ.get("OPENAI_API_KEY", None)),
		"feedback_func": config.get("self_refine_feedback_func", None),  
	}
	refine_config = {
		"llm_name": config.get("self_refine_refine_query_llm_name", "GPT4o"),
		"model_version": config.get("self_refine_refine_query_model_version", "gpt-4o-2024-08-06"),
		"temperature": config.get("self_refine_refine_query_temperature", 0.0),
		"max_tokens": config.get("self_refine_refine_query_max_tokens", -1),
		"response_format_json": config.get("self_refine_refine_query_response_format_json", True),
		"no_comment_regen": config.get("self_refine_refine_query_no_comment_regen", True)
	}

	# Common dataset and KG settings (using self_refine_ prefixed keys)
	dataset = config.get("self_refine_dataset", "QALD10")
	kg_name = config.get("self_refine_knowledge_graph", "wiki")
	if_debug = config.get("self_refine_dbg", False)
	print(f"The value of debug is {if_debug}")
	
	# Load dataset
	if dataset == "QALD10":
		data_path = config.get("self_refine_data_path")
		# pdb.set_trace()
		cache_path = config.get("self_refine_base_cache_path")
		
		dataset_obj = QALD10(load_json(data_path), cache=cache_path)
	elif dataset == "QALD9":
		data_path = config.get("self_refine_data_path")
		cache_path = config.get("self_refine_base_cache_path")
		if kg_name == "dbpedia":
			dataset_obj = QALD9(load_json(data_path), cache=cache_path, kg="dbpedia")
		else:
			dataset_obj = QALD9(load_json(data_path), cache=cache_path, kg="wiki")
	else:
		print("Dataset not supported for self_refine.")
		return

	# Set up logging and results paths for self_refine
	log_dir = config.get("self_refine_log_dir", "logs")  # Use relative path for local testing, camera
	os.makedirs(log_dir, exist_ok=True)
	log_file = os.path.join(log_dir, f"self_refine_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
	logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
	logging.info("Starting self_refine evaluation process.")
	logging.info(f"Dataset: {dataset}")
	logging.info(f"KG: {kg_name}")
	logging.info(f"Unified NLE Config: {nle_config}")
	logging.info(f"Feedback Config: {feedback_config}")
	logging.info(f"Refine Config: {refine_config}")
	logging.info(f"Max Iterations: {config.get('self_refine_max_iterations', 5)}")
	logging.info(f"If Ground: {config.get('self_refine_if_ground', False)}")
	logging.info(f"If NL Exp: {config.get('self_refine_if_nl_exp', False)}")
	logging.info(f"If External: {config.get('self_refine_if_external', False)}")
	
	results_save_path = config.get("self_refine_results_save_path", "eval_results")  # Use relative path for local testing, camera

	# Create results directory if it doesn't exist
	os.makedirs(results_save_path, exist_ok=True)
	results_file = os.path.join(results_save_path, f"eval_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
	
	raw_precisions, raw_recalls, raw_f1_scores = [], [], []
	refined_precisions, refined_recalls, refined_f1_scores = [], [], []
	
	# Process each dataset entry
	for idx, entry in enumerate(tqdm(dataset_obj.extracted_data, desc="Processing entries", unit="entry")):
		if not entry.get('non_empty_gt_query', False):
			logging.error(f"Entry {idx+1} has no non-empty GT query. Skipping.")
			continue

		question = entry.get('question')
		raw_query = entry.get('raw_generated_query')
		gt_query = entry.get('query')
		if not question or not raw_query or not gt_query:
			logging.error(f"Missing data for entry {idx+1}. Skipping.")
			continue
		# if idx < 304:
		# 	continue

		# print(f"idx is {idx}!!!!!!!!!!")	
		# pdb.set_trace()
		# # continue
		if kg_name == "dbpedia":
			gt_results = execute_sparql_query_dbpedia(gt_query)
			# while True:
			# 	try:
			# 		gt_results = execute_sparql_query_dbpedia(gt_query)
			# 		break  # Exit the loop if the function call is successful
			# 	except Exception as e:
			# 		print(f"Error encountered: {e}. Retrying in 10 seconds...")
			# 		time.sleep(10)
		else:
			gt_results = execute_sparql_query_wiki(gt_query)
		logging.info(f"Entry {idx+1} GT Results: {gt_results}")
		if not gt_results:
			logging.error(f"No GT results for entry {idx+1}. Skipping.")
			continue
		logging.info(f"Processing entry {idx+1}")
		logging.info(f"Question: {question}")
		logging.info(f"GT Query: {gt_query}")
		logging.info(f"Raw Query: {raw_query}")
		try:
			if config.get("self_refine_if_ground", False):
				print("!!!!!!!!!!!!!!Ground")
				revised_query = execute_with_retry(
					iterative_refinement_ground,
					question, raw_query, kg_name, False,
					config.get("self_refine_max_iterations", 5),
					nle_config, feedback_config, refine_config
				)
			elif config.get("self_refine_if_nl_exp", False):
				print("!!!!!!!!!!!!!!NL Exp")
				revised_query = execute_with_retry(
					iterative_refinement_nl_exp,
					question, raw_query, kg_name, False,
					config.get("self_refine_max_iterations", 5),
					nle_config, feedback_config, refine_config
				)
			elif config.get("self_refine_if_external", False):
				print("!!!!!!!!!!!!!!External")
				revised_query = execute_with_retry(
					iterative_refinement_external,
					question, raw_query, kg_name, True,
					config.get("self_refine_max_iterations", 5),
					nle_config, feedback_config, refine_config
				)
			else:
				# Default pipeline
				if config.get("self_refine_debug", False):
					revised_query = iterative_refinement(
						question, raw_query, kg_name, True,
						config.get("self_refine_max_iterations", 5),
						nle_config, feedback_config, refine_config
					)
				else:

					revised_query = execute_with_retry(
						iterative_refinement,
						question, raw_query, kg_name, True,
						config.get("self_refine_max_iterations", 5),
						nle_config, feedback_config, refine_config
					)
			logging.info(f"Revised Query: {revised_query}")
			# add revised query to the entry
			entry['self_refined_query'] = revised_query
			raw_eval = execute_with_retry(evaluate_sparql_queries, raw_query, gt_query, kg=kg_name)
			revised_eval = execute_with_retry(evaluate_sparql_queries, revised_query, gt_query, kg=kg_name)
			logging.info(f"Raw Eval: {raw_eval}")
			raw_precisions.append(raw_eval['precision'])
			raw_recalls.append(raw_eval['recall'])
			raw_f1_scores.append(raw_eval['F1_score'])
			logging.info(f"Revised Eval: {revised_eval}")
			# add evaluation results to the entry
			entry['self_refined_eval'] = revised_eval
			refined_precisions.append(revised_eval['precision'])
			refined_recalls.append(revised_eval['recall'])
			refined_f1_scores.append(revised_eval['F1_score'])
			logging.info("Averages so far:")
			logging.info(f"Raw Precision: {sum(raw_precisions)/len(raw_precisions)}")
			logging.info(f"Raw Recall: {sum(raw_recalls)/len(raw_recalls)}")
			logging.info(f"Raw F1: {sum(raw_f1_scores)/len(raw_f1_scores)}")
			logging.info(f"Refined Precision: {sum(refined_precisions)/len(refined_precisions)}")
			logging.info(f"Refined Recall: {sum(refined_recalls)/len(refined_recalls)}")
			logging.info(f"Refined F1: {sum(refined_f1_scores)/len(refined_f1_scores)}")
		except RetryError as r_err:
			logging.error(f"Retry failed for entry {idx+1}: {r_err}")
		except Exception as e:
			logging.error(f"Error processing entry {idx+1}: {e}")
			continue
		
		if if_debug:
			break
	
	logging.info("Completed self_refine evaluation process.")
	results = {
		"raw_precisions": raw_precisions,
		"raw_recalls": raw_recalls,
		"raw_f1_scores": raw_f1_scores,
		"refined_precisions": refined_precisions,
		"refined_recalls": refined_recalls,
		"refined_f1_scores": refined_f1_scores
	}
	from utils.utils import save_json
	save_json(results, results_file)
	logging.info(f"Results saved to: {results_file}")
	print(results)

	raw_save_path = config.get("self_refine_raw_save_path", "utils/temp_res_folder")  # Use relative path for local testing, camera
    

	try:
		os.makedirs(raw_save_path, exist_ok=False)
	except:
		print(f"Directory {raw_save_path} already exists")
		raw_save_path = os.path.join("utils", "temp_res_folder") # Use relative path for local testing, camera
		os.makedirs(raw_save_path, exist_ok=True)
		print(f"Using default path {raw_save_path}")


	# use the nle_config to create a save path for the data obj
	model_version = nle_config["model_version"]
	llm_model = nle_config["llm_name"]

	# if model_version includes a ".", replace it with "_"
	model_version = model_version.replace(".", "_")
	llm_model = llm_model.replace(".", "_")

	# if model version includes a slash, replace it with "_"
	model_version = model_version.replace("/", "_")
	

	# path for data obj pickle
	save_path = os.path.join(raw_save_path, f"data_obj_{dataset}_{kg_name}_{llm_model}_{model_version}.pk")
	dataset_obj.save_pk(save_path)
	print(f"Saving data obj to {save_path}")

	config_save_path = os.path.join(raw_save_path, f"config_{dataset}_{kg_name}_{llm_model}_{model_version}.yaml")
	config.save_config_to_file(config_save_path)

	# create a dict for all save path
	save_path_dict = {
		"results": results_file,
		"data_obj": save_path,
		"log": log_file,
		"config": config_save_path
	}

	# save the dict to a json file in raw_save_path
	save_path_json = os.path.join(raw_save_path, f"save_path_dict_{dataset}_{kg_name}_{llm_model}_{model_version}.json")
	save_json(save_path_dict, save_path_json)

	print(f"Saving save path dict to {save_path_json}")

	print("final results:")
	overall_metrics = dataset_obj.compute_overall_metrics(target="final", key = "self_refined", only_valid = True, base_raw = True)
	print("Overall metrics for self-refinement:" + str(overall_metrics))

def run_self_refine_main():
	# For testing the pipeline directly (if needed)
	pass

