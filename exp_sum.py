import json
import argparse
import sys
import os
import re
from utils.datasets.quad10 import QALD10, QALD9
from utils.config import ConfigManager
from utils.utils import load_json, save_json
from utils.llm_call import make_retry_decorator, llm_call
from tenacity import retry, stop_after_attempt, wait_fixed
from utils.wikidata import id2info
from utils.dbpedia import dbpedia_id2label

def supported_general_models():
	return ["GPT4o", "Claude", "Qwen2.5", "GPT4o-mini"]

def supported_dataset():
	return ["QALD10", "QALD9", "LCQUAD2"]

def supported_kg():
	return ["dbpedia", "wiki"]

def check_model_params(config):

	llm_model = config.get("llm_model")
	if llm_model == "GPT4o" or llm_model == "Claude":
		model_version = config.get("model_version")
		assert model_version, "Model version not found"


	temp = config.get("temperature")
	max_tokens = config.get("max_tokens")
	assert temp is not None, "Temperature not found"

	if max_tokens is None:
		max_tokens = 8192
		print("Max tokens not found, using default value 8192")

	if llm_model == "GPT4o":
		if config.get("response_format_json") is True:
			response_format_json = True
		else:
			response_format_json = False
	else:
		response_format_json = None

	llm_cfg = {"temperature": temp, "max_tokens": max_tokens, "response_format_json": response_format_json}

	return llm_cfg


TASK_NAME = {0: "data_generation",1: "self_refine", 2: "nle_visualization"}

def data_generation(config):
	print("Data generation")

	
	dataset = config.get("dataset")
	llm_model = config.get("llm_model")
	data_path = config.get("data_path")
	raw_save_path = config.get("raw_save_path")
	use_base_cache = config.get("base_cache")
	raw_query_gen = config.get("raw_query_gen")
	nle_gen = config.get("nle_gen")
	final_query_gen = config.get("final_query_gen")

	assert dataset in supported_dataset(), f"Dataset {dataset} not found"
	assert llm_model in supported_general_models(), "Model not found"
	assert data_path, "Data path not found"
	assert raw_save_path, "Raw save path not found"
	assert use_base_cache is not None, "Use base cache not found"





	######################## process the nle config first ########################
	if nle_gen:
		nle_gen_remove_corr = config.get("nle_gen_remove_corr")
		if nle_gen_remove_corr is None:
			nle_gen_remove_corr = True
			print(f"NLE generation remove correct not found, using default value {nle_gen_remove_corr}")

		if nle_gen_remove_corr:
			os.environ["REMOVE_CORR"] = "True"
		else:
			os.environ["REMOVE_CORR"] = "False"
		
		nle_gen_use_question = config.get("nle_gen_use_question")
		if nle_gen_use_question is None:
			nle_gen_use_question = False
			print(f"NLE generation use question not found, using default value {nle_gen_use_question}")

		if nle_gen_use_question:
			os.environ["USE_QUESTION"] = "True"
		else:
			os.environ["USE_QUESTION"] = "False"

		nle_gen_use_label = config.get("nle_gen_use_label")
		if nle_gen_use_label is None:
			nle_gen_use_label = True
			print(f"NLE generation use labels not found, using default value {nle_gen_use_label}")

		if nle_gen_use_label:
			os.environ["USE_LABELS"] = "True"
		else:
			os.environ["USE_LABELS"] = "False"

		nle_gen_use_parsed = config.get("nle_gen_use_parsed")
		if nle_gen_use_parsed is None:
			nle_gen_use_parsed = True
			print(f"NLE generation use parsed not found, using default value {nle_gen_use_parsed}")

		if nle_gen_use_parsed:
			os.environ["USE_PARSED"] = "True"
		else:
			os.environ["USE_PARSED"] = "False"

		nle_gen_use_layout = config.get("nle_gen_use_layout")
		if nle_gen_use_layout is None:
			nle_gen_use_layout = True
			print(f"NLE generation use layout not found, using default value {nle_gen_use_layout}")

		if nle_gen_use_layout:
			os.environ["USE_LAYOUT"] = "True"
		else:
			os.environ["USE_LAYOUT"] = "False"


		nle_gen_remove_few_shot = config.get("nle_gen_remove_few_shot")
		if nle_gen_remove_few_shot is None:
			nle_gen_remove_few_shot = False
			print(f"NLE generation remove few shot not found, using default value {nle_gen_remove_few_shot}")
		
		if nle_gen_remove_few_shot:
			os.environ["REMOVE_FEW_SHOT"] = "True"
		else:
			os.environ["REMOVE_FEW_SHOT"] = "False"

		nle_gen_use_raw_query = config.get("nle_gen_use_raw_query")
		if nle_gen_use_raw_query is None:
			nle_gen_use_raw_query = False
			print(f"NLE generation use raw query not found, using default value {nle_gen_use_raw_query}")
		
		if nle_gen_use_raw_query:
			os.environ["USE_RAW_QUERY"] = "True"
		else:
			os.environ["USE_RAW_QUERY"] = "False"

		nle_gen_use_raw_query_with_shots = config.get("nle_gen_use_raw_query_with_shots")
		if nle_gen_use_raw_query_with_shots is None:
			nle_gen_use_raw_query_with_shots = False
			print(f"NLE generation use raw query with shots not found, using default value {nle_gen_use_raw_query_with_shots}")

		if nle_gen_use_raw_query_with_shots:
			os.environ["USE_RAW_QUERY_WITH_SHOTS"] = "True"
		else:
			os.environ["USE_RAW_QUERY_WITH_SHOTS"] = "False"

		nle_new_NL_exp_prompt = config.get("nle_new_NL_exp_prompt")
		if nle_new_NL_exp_prompt is None:
			nle_new_NL_exp_prompt = True
			print(f"NLE generation new NL explanation prompt not found, using default value {nle_new_NL_exp_prompt}")
		if nle_new_NL_exp_prompt:
			os.environ["NEW_NL_EXP_PROMPT"] = "True"
		else:
			os.environ["NEW_NL_EXP_PROMPT"] = "False"


		from utils.NL_exp import generate_nl_explanation_with_cfg



	######################## dataset loading ########################
	
	if use_base_cache:
		base_cache_path = config.get("base_cache_path")
		assert base_cache_path, "Base cache path not found"
		# check it is a pickle file
		assert base_cache_path.endswith(".pkl") or base_cache_path.endswith(".pickle") or base_cache_path.endswith(".pk"), "Base cache should be a pickle file"

	if dataset == "QALD9" or dataset == "LCQUAD2":
		kg = config.get("knowledge_graph")
		assert kg in supported_kg(), "Knowledge graph not supported"

	if dataset == "QALD10":
		kg = "wiki"


	llm_cfg = check_model_params(config)
	model_version = config.get("model_version")




	raw_data = load_json(data_path)

	if dataset == "QALD10":
		if use_base_cache:
			data_obj = QALD10(raw_data, cache=base_cache_path)
		else:
			data_obj = QALD10(raw_data)

	elif dataset == "QALD9":
		if use_base_cache:
			data_obj = QALD9(raw_data, cache=base_cache_path, kg=kg)
		else:
			data_obj = QALD9(raw_data, kg=kg)

	# elif dataset == "LCQUAD2":
	# 	if use_base_cache:
	# 		data_obj = LCQUAD2(raw_data, cache=base_cache_path, kg=kg)
	# 	else:
	# 		data_obj = LCQUAD2(raw_data, kg=kg)
	else:
		print("Dataset not found")
		return
	
	########################## raw query generation ##########################
	if raw_query_gen:


		query_gen_llm_name = config.get("query_gen_llm_name")
		if query_gen_llm_name is None:
			query_gen_llm_name = llm_model
			print(f"Query generation LLM name not found, using default value {query_gen_llm_name}")


		#### deal with different models for different tasks
		query_gen_model_version = config.get("query_gen_model_version")
		if query_gen_model_version is None:
			query_gen_model_version = model_version
			print(f"Query generation model version not found, using default value {query_gen_model_version}")

		#### deal with the temperature for different tasks
		query_gen_temp = config.get("query_gen_temp")
		if query_gen_temp is None:
			query_gen_temp = llm_cfg["temperature"]
			print(f"Query generation temperature not found, using default value {query_gen_temp}")

		#### deal with the max tokens for different tasks
		query_gen_max_tokens = config.get("query_gen_max_tokens")
		if query_gen_max_tokens is None:
			query_gen_max_tokens = llm_cfg["max_tokens"]
			print(f"Query generation max tokens not found, using default value {query_gen_max_tokens}")

		### deal with the response format for different tasks
		query_gen_response_format_json = config.get("query_gen_response_format_json")
		if query_gen_response_format_json is None:
			query_gen_response_format_json = llm_cfg["response_format_json"]
			print(f"Query generation response format not found, using default value {query_gen_response_format_json}")

		query_gen_max_attempts = config.get("query_gen_max_attempts")
		if query_gen_max_attempts is None:
			query_gen_max_attempts = 1
			print(f"Query generation max attempts not found, using default value {query_gen_max_attempts}")

		query_gen_wait_time = config.get("query_gen_wait_time")
		if query_gen_wait_time is None:
			query_gen_wait_time = 1
			print(f"Query generation wait time not found, using default value {query_gen_wait_time}")

		data_obj.generate_raw_sparql(query_gen_llm_name, query_gen_model_version, query_gen_max_tokens, query_gen_temp,
									  query_gen_response_format_json, query_gen_max_attempts, query_gen_wait_time)


	########################## NLE generation ##########################
	if nle_gen:

		#### deal with different models for different tasks
		nle_gen_llm_name = config.get("nle_gen_llm_name")
		if nle_gen_llm_name is None:
			nle_gen_llm_name = llm_model
			print(f"NLE generation LLM name not found, using default value {nle_gen_llm_name}")

		nle_gen_model_version = config.get("nle_gen_model_version")
		if nle_gen_model_version is None:
			nle_gen_model_version = model_version
			print(f"NLE generation model version not found, using default value {nle_gen_model_version}")
																				 
		#### deal with the temperature for different tasks
		nle_gen_temp = config.get("nle_gen_temp")
		if nle_gen_temp is None:
			nle_gen_temp = llm_cfg["temperature"]
			print(f"NLE generation temperature not found, using default value {nle_gen_temp}")

		#### deal with the max tokens for different tasks
		nle_gen_max_tokens = config.get("nle_gen_max_tokens")
		if nle_gen_max_tokens is None:
			nle_gen_max_tokens = llm_cfg["max_tokens"]
			print(f"NLE generation max tokens not found, using default value {nle_gen_max_tokens}")

		### deal with the response format for different tasks
		nle_gen_response_format_json = config.get("nle_gen_response_format_json")
		if nle_gen_response_format_json is None:
			nle_gen_response_format_json = llm_cfg["response_format_json"]
			print(f"NLE generation response format not found, using default value {nle_gen_response_format_json}")



		nle_gen_max_attempts = config.get("nle_gen_max_attempts")
		if nle_gen_max_attempts is None:
			nle_gen_max_attempts = 1
			print(f"NLE generation max attempts not found, using default value {nle_gen_max_attempts}")

		nle_gen_wait_time = config.get("nle_gen_wait_time")
		if nle_gen_wait_time is None:
			nle_gen_wait_time = 1
			print(f"NLE generation wait time not found, using default value {nle_gen_wait_time}")

		nle_gen_json_parsable = config.get("nle_gen_json_parsable")
		if nle_gen_json_parsable is None:
			nle_gen_json_parsable = False
			print(f"NLE generation json parsable not found, using default value {nle_gen_json_parsable}")

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
					label_func = id2info
				elif kg == "dbpedia":
					label_func = dbpedia_id2label
				
				output = generate_nl_explanation_with_cfg(data_entry, llm_name, model_version, use_label, label_func,  use_question, use_layout, use_parsed, cfg)

				if json_parsable:
					try:
						output = json.loads(output)
						print("Output is json parsable")
					except:
						print("Output is not json parsable w/o modification")
						res = re.sub(r'^```json', '', output)
						res = re.sub(r'```$', '', res)
						res = json.loads(res)

						output = res

						print("Output is json parsable now!!!")
				
				return output

			return nle_gen_call
		
		if nle_gen_json_parsable:
			nle_gen_call = create_llm_call_for_nle_gen(nle_gen_llm_name, nle_gen_model_version, nle_gen_max_tokens, nle_gen_temp, 
											  nle_gen_response_format_json, kg, nle_gen_use_label,nle_gen_use_question, nle_gen_use_layout, nle_gen_use_parsed, 
											  True, nle_gen_max_attempts, nle_gen_wait_time)
			
			nle_gen_save_call = create_llm_call_for_nle_gen(nle_gen_llm_name, nle_gen_model_version, nle_gen_max_tokens, nle_gen_temp, 
											  nle_gen_response_format_json, kg, nle_gen_use_label, nle_gen_use_question, nle_gen_use_layout, nle_gen_use_parsed,
											  False, nle_gen_max_attempts, nle_gen_wait_time)
		else:
			nle_gen_call = create_llm_call_for_nle_gen(nle_gen_llm_name, nle_gen_model_version, nle_gen_max_tokens, nle_gen_temp, 
											  nle_gen_response_format_json, kg, nle_gen_use_label, nle_gen_use_question, nle_gen_use_layout, nle_gen_use_parsed,
											  False, nle_gen_max_attempts, nle_gen_wait_time)
			
			nle_gen_save_call = nle_gen_call

		data_obj.load_NLExp_from_func(nle_gen_call, nle_gen_save_call)


	########################## upper bound query generation ##########################
	if final_query_gen:
		
		final_query_gen_llm_name = config.get("final_query_gen_llm_name")
		if final_query_gen_llm_name is None:
			final_query_gen_llm_name = llm_model
			print(f"Final query generation LLM name not found, using default value {final_query_gen_llm_name}")

		#### deal with different models for different tasks
		final_query_gen_model_version = config.get("final_query_gen_model_version")
		if final_query_gen_model_version is None:
			final_query_gen_model_version = model_version
			print(f"Final query generation model version not found, using default value {final_query_gen_model_version}")

		#### deal with the temperature for different tasks
		final_query_gen_temp = config.get("final_query_gen_temp")
		if final_query_gen_temp is None:
			final_query_gen_temp = llm_cfg["temperature"]
			print(f"Final query generation temperature not found, using default value {final_query_gen_temp}")

		#### deal with the max tokens for different tasks
		final_query_gen_max_tokens = config.get("final_query_gen_max_tokens")
		if final_query_gen_max_tokens is None:
			final_query_gen_max_tokens = llm_cfg["max_tokens"]
			print(f"Final query generation max tokens not found, using default value {final_query_gen_max_tokens}")

		### deal with the response format for different tasks
		final_query_gen_response_format_json = config.get("final_query_gen_response_format_json")
		if final_query_gen_response_format_json is None:
			final_query_gen_response_format_json = llm_cfg["response_format_json"]
			print(f"Final query generation response format not found, using default value {final_query_gen_response_format_json}")

		final_query_gen_max_attempts = config.get("final_query_gen_max_attempts")
		if final_query_gen_max_attempts is None:
			final_query_gen_max_attempts = 1
			print(f"Final query generation max attempts not found, using default value {final_query_gen_max_attempts}")

		final_query_gen_wait_time = config.get("final_query_gen_wait_time")
		if final_query_gen_wait_time is None:
			final_query_gen_wait_time = 1
			print(f"Final query generation wait time not found, using default value {final_query_gen_wait_time}")

		final_query_gen_nle_key = config.get("final_query_gen_nle_key")
		if final_query_gen_nle_key is None:
			final_query_gen_nle_key = "nle_str"
			print(f"Final query generation NLE key not found, using default value {final_query_gen_nle_key}")

		data_obj.generate_final_sparql(final_query_gen_llm_name, final_query_gen_model_version, final_query_gen_max_tokens, final_query_gen_temp,
									  final_query_gen_response_format_json, final_query_gen_max_attempts, final_query_gen_wait_time, final_query_gen_nle_key)
	


	########################## save module ##########################
	if_save = config.get("if_save_gen_raw")
	if if_save is None:
		if_save = True
		print("if_save_gen_raw not found, using default value True")

	if if_save:
		try:
			os.makedirs(raw_save_path, exist_ok=False)
		except:
			print(f"Directory {raw_save_path} already exists")
			raw_save_path = os.path.join(os.getcwd(), "temp_res_folder") # local, camera

			os.makedirs(raw_save_path, exist_ok=True)
			print(f"Using default path {raw_save_path}")

		# if model_version includes a ".", replace it with "_"
		model_version = model_version.replace(".", "_")
		llm_model = llm_model.replace(".", "_")

		# if model version includes a slash, replace it with "_"
		model_version = model_version.replace("/", "_")

		# path for data obj pickle
		save_path = os.path.join(raw_save_path, f"data_obj_{dataset}_{kg}_{llm_model}_{model_version}.pk")
		data_obj.save_pk(save_path)
		print(f"Saving data obj to {save_path}")
		# # save the raw data
		# save_path = os.path.join(raw_save_path, f"raw_data_{dataset}_{kg}.json")
		# data_obj.save_data(save_path)
		# print(f"Saving raw data to {save_path}")
		# save parsed list
		save_path = os.path.join(raw_save_path, f"parsed_dict_{dataset}_{kg}_{llm_model}_{model_version}.json")
		data_obj.save_parsed(save_path)
		print(f"Saving parsed data to {save_path}")
		# save the patterns in the data
		save_path = os.path.join(raw_save_path, f"patterns_{dataset}_{kg}_{llm_model}_{model_version}.pk")
		data_obj.save_patterns(save_path)
		print(f"Saving patterns to {save_path}")
		# save the config yaml
		save_path = os.path.join(raw_save_path, f"config_{dataset}_{kg}_{llm_model}_{model_version}.yaml")
		config.save_config_to_file(save_path)


def self_refine(config):
	# import pdb
	if_debug = config.get("self_refine_dbg", False)
	print("if_debug: ", if_debug)
	# pdb.set_trace()
	if config.get("self_refine_nle_gen", False):
		print("Self refine with NLE generation")
		os.environ["REMOVE_CORR"] = "True" if config.get("self_refine_nle_gen_remove_corr", True) else "False"
		os.environ["USE_QUESTION"] = "True" if config.get("self_refine_nle_gen_use_question", False) else "False"
		os.environ["USE_LABELS"] = "True" if config.get("self_refine_nle_gen_use_label", True) else "False"
		os.environ["USE_PARSED"] = "True" if config.get("self_refine_nle_gen_use_parsed", True) else "False"
		os.environ["USE_LAYOUT"] = "True" if config.get("self_refine_nle_gen_use_layout", True) else "False"
		os.environ["REMOVE_FEW_SHOT"] = "True" if config.get("self_refine_nle_gen_remove_few_shot", True) else "False"
		os.environ["USE_RAW_QUERY"] = "True" if config.get("self_refine_nle_gen_use_raw_query", False) else "False"
		os.environ["USE_RAW_QUERY_WITH_SHOTS"] = "True" if config.get("self_refine_nle_gen_use_raw_query_with_shots", False) else "False" # added already
		os.environ["NEW_NL_EXP_PROMPT"] = "True" if config.get("self_refine_nle_gen_new_NL_exp_prompt", True) else "False"
		os.environ["NO_COMMENT_REMOVER_NLE"] = "True" if config.get("self_refine_nle_gen_no_comment_remover", False) else "False"
	# --- Call the separated self_refine pipeline ---
	from utils.self_refine_pipeline import run_self_refine
	run_self_refine(config)

def nle_visualization(config):
	pass


if __name__ == '__main__':

	argparse = argparse.ArgumentParser()
	argparse.add_argument('--config', type=str, default='config.json')
	argparse.add_argument('--task_id', type=int, default=0)

	args = argparse.parse_args()
	config = ConfigManager(args.config)
	task_id = args.task_id
	task_name = TASK_NAME[task_id]

	config.load_config()

	print("task_name: ", task_name)



	if task_name == "data_generation":
		data_generation(config)

	elif task_name == "self_refine":
		self_refine(config)

	elif task_name == "nle_visualization":
		nle_visualization(config)

	else:
		print("Task not found")

