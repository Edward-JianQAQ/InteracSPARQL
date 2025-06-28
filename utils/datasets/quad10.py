from utils.utils import load_json, save_json, check_group, add_prefixes, \
					check_union, check_bind, check_filter, check_reg_path, dict_add_and_report, load_object, save_object, return_all_pattern, extract_sparql_query
from utils.runjs import run_js_script
from utils.eval_raw import calculate_metrics, evaluate_sparql_queries, execute_sparql_query_dbpedia, \
	execute_sparql_query_wiki, evaluate_sparql_queries_with_res
import utils.dbpedia
import utils.wikidata
from utils.llm_call import llm_call, make_retry_decorator
import pdb
import time
import pickle
# from utils.triple import triple
import os
import json
from tqdm import tqdm
from openai import OpenAI
# client = OpenAI(
# 	# This is the default and can be omitted
# 	api_key=os.environ.get("OPENAI_API_KEY"),
# )
from tenacity import retry, stop_after_attempt, wait_fixed



class BasicKG(object):
	def __init__(self, data, cache = None, kg = 'wiki', parse_code = 'parse.js', version = 'qald_10'):
		self.data = data
		self.kg = kg
		self.parse_code = parse_code
		self.version = version

		if kg not in {"wiki", "dbpedia"}:
			raise ValueError("Invalid value for kg. Expected 'wiki' or 'dbpedia'.")
		

		if cache is None:
			self.extracted_data = self._extract_info()
			self._get_parsed()
		else:
			# self.extracted_data = load_json(cache)['data']
			self.extracted_data = load_object(cache)



	
	def _extract_info(self):
		extracted_data = []
		for sample in tqdm(self.data['questions']):
			dic = {}
			dic['id'] = sample['id']

			for lang in sample['question']:
				if lang['language'] == 'en':
					dic['question'] = lang['string']
					break
			dic['query'] = sample['query']['sparql']

			res_list = []
			#print(sample['answers'][0])
			for res in sample['answers'][0]: # answer no more than 1
				res_list.append(res)
			
			dic['results'] = res_list

			extracted_data.append(dic)
		return extracted_data

	def _get_parsed(self):
		for entry in tqdm(self.extracted_data):
			query = entry['query']
			flag = run_js_script(self.parse_code, query)
			parsed = load_json('parsedQueryOutput.json')
			entry['parsed'] = parsed
			entry['if_parsed_success'] = flag

	def save_data(self, sname):
		try:
			sdict = {'dataset_id':self.version, 'data':self.extracted_data}
			save_json(sdict, sname)
		except Exception as e:
			# Handle TypeError and ValueError exceptions
			print("Caught an exception:", e)
	
	def save_pk(self, sname):
		try:
			save_object(self.extracted_data, sname)
		except Exception as e:
			# Handle TypeError and ValueError exceptions
			print("Caught an exception:", e)

	# save the parsed data to a json as a dict using the id as key
	def save_parsed(self, sname):
		try:
			sdict = {}
			for entry in self.extracted_data:
				sdict[str(entry['id'])] = entry['parsed']
			save_json(sdict, sname)
		except Exception as e:
			# Handle TypeError and ValueError exceptions
			print("Caught an exception:", e)


	# save as a list of patterns, s
	def save_patterns(self, sname):
		try:
			slist = []
			for entry in self.extracted_data:
				slist.append(return_all_pattern(entry['parsed']))
			save_object(slist, sname)
		except Exception as e:
			# Handle TypeError and ValueError exceptions
			print("Caught an exception:", e)

				
	def get_sp_query(self, check_func, skip = 0):
		res_id = []

		for cnt, entry in enumerate(self.extracted_data):
			#print(entry['id'])
			if cnt < skip:
				continue

			if check_func(entry['parsed']):
				res_id.append(cnt)

		return res_id 

	def prefix_dict(self, pres = {}):
		#pres = {}
		for entry in self.extracted_data:
			dict_add_and_report(pres, entry['parsed']['prefixes'])
		return pres


	def create_llm_call_for_query_gen(self, llm_model, model_version, max_tokens, temperature, response_format_json, 
					 max_attempts=3, wait_seconds=1):
		"""
		Returns a function (already decorated) that fetches data.
		"""
		@make_retry_decorator(max_attempts, wait_seconds)
		def query_gen_call(msg):
			cfg = {
				"max_tokens": max_tokens,
				"temperature": temperature,
				"response_format_json": response_format_json
			}
			output = llm_call(llm_model, model_version, msg, cfg)	

			output = output.strip()
			sparql_query = extract_sparql_query(output)

			if llm_model == "Qwen2.5":
				# add the prefix of rdfs
				if "rdfs:label" in sparql_query:
					sparql_query = "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> " + sparql_query
				elif "wikibase:label" in sparql_query:
					sparql_query = "PREFIX wikibase: <http://wikiba.se/ontology#> " + sparql_query

			print(sparql_query)
			flag = run_js_script("parse.js", sparql_query)
			if not flag:
				raise ValueError("Failed to parse the generated SPARQL query.")
			
			return sparql_query


		return query_gen_call
	

	def generate_raw_sparql(self,  llm_name, model_version,  max_tokens, temperature,
						  response_format_json, max_attempts, wait_seconds):

		print(f"Generating raw SPARQL queries using {model_version} with temperature {temperature} and max tokens {max_tokens}.")

		custom_llm_call = self.create_llm_call_for_query_gen(llm_name, model_version, max_tokens, 
													   temperature, response_format_json, max_attempts, 
													   wait_seconds)

		
		kg_exp = "DBpedia" if self.kg == "dbpedia" else "Wikidata"

		wiki_note = " Please do not use label service (wikibase:label) unless necessary."
		dbpedia_note = ""
		
		note = wiki_note if self.kg == "wiki" else dbpedia_note


		# special treament for different models
		if llm_name == "Qwen2.5":
			extra_system_prompt = "Do not use rdfs:label in the query no matter when. "
			print("Qwen2.5 model detected. Adding extra system prompt.")
		else:
			extra_system_prompt = ""

		for entry in tqdm(self.extracted_data):
			question = entry['question']
			message = [
				{"role": "system", "content": f"You are an expert at generating SPARQL queries from natural language questions. Add necessary prefix if needed. {extra_system_prompt}Please only return the SPARQL query with nothing else. " + note},
				{"role": "user", "content": f"Generate a SPARQL query on {kg_exp} for the question: \"{question}\"." + note + f" Do not forget to generate the prefix if needed. {extra_system_prompt}"}
			]
			#pdb.set_trace()
			try:
				sparql_query = custom_llm_call(message)
				# sparql_query = add_prefixes(sparql_query, self.kg)
				entry['parsable_raw_generated_query'] =True
				entry['raw_generated_query'] = sparql_query
			except Exception as e:
				print(f"Failed to generate SPARQL for question ID {entry['id']}: {e}")
				entry['parsable_raw_generated_query'] =False
				entry['raw_generated_query'] = None
				sparql_query = None

			if_valid_query = False
			try:
				if self.kg == 'dbpedia':
					result_gt = execute_sparql_query_dbpedia(entry['query'])
				elif self.kg == 'wiki':
					result_gt = execute_sparql_query_wiki(entry['query'])
				else:
					raise ValueError("Invalid KG")
				

				# check if result_gt is boolean
				if isinstance(result_gt, bool):
					if_valid_query = True
				else:
					if result_gt is not None and len(result_gt) > 0:
						if_valid_query = True

			except Exception as e:
				print(f"Failed to execute GT SPARQL for question ID {entry['id']}: {e}")
				result_gt = None
			
			entry["gt_query_res"] = result_gt
			entry['non_empty_gt_query'] = if_valid_query
						

			try:
				if self.kg == 'dbpedia':
					result = execute_sparql_query_dbpedia(sparql_query)
				elif self.kg == 'wiki':
					result = execute_sparql_query_wiki(sparql_query)
				else:
					raise ValueError("Invalid KG")
				entry['raw_generated_exec'] = True
				entry['raw_generated_res'] = result
			except Exception as e:
				print(f"Failed to execute SPARQL for question ID {entry['id']}: {e}")
				result = None
				entry['raw_generated_exec'] = False
				entry['raw_generated_res'] = result


			try:
			
				#eval_res = evaluate_sparql_queries(sparql_query, entry['query'], self.kg)
				eval_res = evaluate_sparql_queries_with_res(result, result_gt)
				
				# entry['raw_generated_query'] = sparql_query

				entry['raw_generated_eval'] = eval_res
				entry['evaluated_raw_generated_query'] = True

			except Exception as e:
				print(f"Failed to evaluate SPARQL for question ID {entry['id']}: {e}")

				eval_res = {'precision': 0, 'recall': 0, 'F1_score': 0}
				entry['raw_generated_eval'] = eval_res
				entry['evaluated_raw_generated_query'] = False

			print(entry["non_empty_gt_query"])
			print("Ground truth results:" + str(result_gt))
			print("Generated results:" + str(result))
			print(eval_res)
			time.sleep(1)

		print("Finished generating raw SPARQL queries.")
		overall_metrics = self.compute_overall_metrics(target="raw", only_valid = True)
		print("Overall metrics for raw SPARQL queries:" + str(overall_metrics))


	def load_NLExp_from_func(self, nlexp_func, save_func):
		for iid, entry in tqdm(enumerate(self.extracted_data)):
			question = entry['question']
			query = entry['query']
			parsed = entry['parsed']
			data_entry = (query, question, parsed)
			try:
				nle = nlexp_func(data_entry)
				entry['nle_str'] = json.dumps(nle, indent=4)
			except Exception as e:
				print(f"Failed to generate NL explanation for question ID {entry['id']}: {e}, fall back to save_func")
				nle = save_func(data_entry)
				entry['nle_str'] = nle

			try:
				if not isinstance(nle, dict):
					nl_json = json.loads(nle)
					#entry['nle_json'] = json.dumps(nl_json, indent=4)
					entry['nle_json'] = nl_json
				else:
					entry['nle_json'] = nle
				# pdb.set_trace()
			except Exception as e:
				print(f"Failed to load NL explanation for question ID {entry['id']}: {e}")
				entry['nle_json'] = None

			
				
			

	@classmethod
	def remove_sparql_keys(self, json_data):
		"""
		Recursively removes all keys labeled "SPARQL" and their corresponding values from a JSON object.
		"""
		if isinstance(json_data, dict):
			return {key: self.remove_sparql_keys(value) for key, value in json_data.items() if key != "SPARQL"}
		elif isinstance(json_data, list):
			return [self.remove_sparql_keys(item) for item in json_data]
		else:
			return json_data

	def load_and_filter_NLExp(self, nlexp_path):
		"""
		Loads NL explanations, filters out SPARQL keys, and saves the filtered JSON in a new folder.

		Args:
			nlexp_path (str): Path to the folder containing NL explanation JSON files.
		"""
		# Create a new folder for filtered NL explanations
		filtered_save_path = os.path.join(nlexp_path, "filtered_nl_explanations")
		os.makedirs(filtered_save_path, exist_ok=True)

		for iid, entry in tqdm(enumerate(self.extracted_data)):
			# Load the JSON file for the current entry
			nl_json_path = os.path.join(nlexp_path, f'id_{iid}_gen.json')
			nl_json = load_json(nl_json_path)

			# Filter out SPARQL keys
			filtered_nl_json = self.remove_sparql_keys(nl_json)

			# Save the filtered JSON back into the new folder
			filtered_nl_json_path = os.path.join(filtered_save_path, f'id_{iid}_gen_filtered_sparql.json')
			with open(filtered_nl_json_path, 'w', encoding='utf-8') as f:
				json.dump(filtered_nl_json, f, indent=4)

			# Save the filtered JSON as a string in the entry under a new key
			entry['nl_exp_filtered_sparql'] = json.dumps(filtered_nl_json, indent=4)


	def generate_final_sparql(self, llm_name, model_version,  max_tokens, temperature,
						  response_format_json, max_attempts, wait_seconds, nle_key):
		

		print(f"Generating raw SPARQL queries using {model_version} with temperature {temperature} and max tokens {max_tokens}.")

		custom_llm_call = self.create_llm_call_for_query_gen(llm_name, model_version, max_tokens,
													   temperature, response_format_json, max_attempts,
													   wait_seconds)

		kg_exp = "DBpedia" if self.kg == "dbpedia" else "Wikidata"

		wiki_note = " Please do not use label service (wikibase:label) unless necessary."
		dbpedia_note = ""
		
		note = wiki_note if self.kg == "wiki" else dbpedia_note

		for entry in tqdm(self.extracted_data):
			question = entry['question']
			message = [
				{"role": "system", "content": "You are an expert at generating SPARQL queries from natural language questions.  Add necessary prefix if needed. Please only return the SPARQL query with nothing else." + note},
				{"role": "user", "content": f"Generate a SPARQL query on {kg_exp} for the question: \"{question}\"." + note + "\nI give a parsed explanation in natural language for you reference:\n" + entry[nle_key] + "\n" + "Do not forget to generate the prefix if needed."}
			]
			#pdb.set_trace()
			try:
				sparql_query = custom_llm_call(message)
				entry['parsable_final_generated_query'] =True
				entry['final_generated_query'] = sparql_query

			except Exception as e:
				print(f"Failed to generate SPARQL for question ID {entry['id']}: {e}")
				entry['parsable_final_generated_query'] =False
				entry['final_generated_query'] = None
				sparql_query = None

			print(sparql_query)

			try:
				if self.kg == 'dbpedia':
					result = execute_sparql_query_dbpedia(sparql_query)
				elif self.kg == 'wiki':
					result = execute_sparql_query_wiki(sparql_query)
				else:
					raise ValueError("Invalid KG")
				entry['final_generated_exec'] = True
				entry['final_generated_res'] = result
			except Exception as e:
				print(f"Failed to execute SPARQL for question ID {entry['id']}: {e}")
				result = None
				entry['final_generated_exec'] = False
				entry['final_generated_res'] = result


			try:
				assert 'gt_query_res' in entry, "No ground truth query results found."
				assert 'non_empty_gt_query' in entry, "No ground truth query validity found."

				result_gt = entry['gt_query_res']

				eval_res = evaluate_sparql_queries_with_res(result, result_gt)

				entry['final_generated_eval'] = eval_res
				entry['evaluated_final_generated_query'] = True

			except Exception as e:
				print(f"Failed to evaluate SPARQL for question ID {entry['id']}: {e}")

				eval_res = {'precision': 0, 'recall': 0, 'F1_score': 0}
				entry['final_generated_eval'] = eval_res
				entry['evaluated_final_generated_query'] = False

			print(entry["non_empty_gt_query"])
			print("Ground truth results:" + str(result_gt))
			print("Generated results:" + str(result))
			print(eval_res)
			time.sleep(1)
		print("Finished generating raw SPARQL queries.")
		overall_metrics = self.compute_overall_metrics(target="final", key = None, only_valid = True)
		print("Overall metrics for raw SPARQL queries:" + str(overall_metrics))

	
	def compute_overall_metrics(self, target="raw", key ='nl_exp', only_valid = False, base_raw = False):
		total_precision_raw = 0
		total_recall_raw = 0
		total_f1_raw = 0
		total_precision_final = 0
		total_recall_final = 0
		total_f1_final = 0
		count_raw = 0
		count_final = 0

		for entry in self.extracted_data:
			#pdb.set_trace()
			valid_flag = True
			if only_valid and entry['non_empty_gt_query'] == False:
				valid_flag = False
				# print("Invalid entry found.")
				# print(entry['id'])

			if target in {"raw", "all", "final"} and 'raw_generated_eval' in entry:
				eval_raw = entry['raw_generated_eval']

				
				if eval_raw and valid_flag:
					total_precision_raw += eval_raw['precision']
					total_recall_raw += eval_raw['recall']
					total_f1_raw += eval_raw['F1_score']
					count_raw += 1

			if target in {"final", "all"}:
			
				if 'final_generated_eval' in entry and key is None and valid_flag:
					eval_final = entry['final_generated_eval']
					
					if eval_final:
						total_precision_final += eval_final['precision']
						total_recall_final += eval_final['recall']
						total_f1_final += eval_final['F1_score']
						count_final += 1
			
				elif f'{key}_eval' in entry and valid_flag:
					eval_final = entry[f'{key}_eval']
					
					if eval_final:
						total_precision_final += eval_final['precision']
						total_recall_final += eval_final['recall']
						total_f1_final += eval_final['F1_score']
						count_final += 1

				else:
					pass

		result = {}
		print("Count raw:")
		print(count_raw)
		print("Count final:")
		print(count_final)
		if count_raw > 0:
			result['average_precision_raw'] = total_precision_raw / count_raw
			result['average_recall_raw'] = total_recall_raw / count_raw
			result['average_f1_raw'] = total_f1_raw / count_raw
		else:
			result['average_precision_raw'] = result['average_recall_raw'] = result['average_f1_raw'] = 0

		if base_raw:
			count_final = count_raw

		if count_final > 0:
			result['average_precision_final'] = total_precision_final / count_final
			result['average_recall_final'] = total_recall_final / count_final
			result['average_f1_final'] = total_f1_final / count_final
		else:
			result['average_precision_final'] = result['average_recall_final'] = result['average_f1_final'] = 0

		# Filter results based on target
		if target == "raw":
			result = {k: v for k, v in result.items() if "raw" in k}
		elif target == "final":
			result = {k: v for k, v in result.items() if "final" in k}

		return result


# INHERITANCE
class QALD10(BasicKG):
	def __init__(self, data, cache = None, parse_code = 'parse.js', version = 'qald_10'):
		kg = 'wiki'
		super().__init__(data, cache, kg, parse_code, version)

class QALD9(BasicKG):
	def __init__(self, data, cache = None, kg = 'wiki', parse_code = 'parse.js', version = 'qald_9'):
		super().__init__(data, cache, kg, parse_code, version)

	def save_parsed(self, sname):
		try:
			sdict = {}
			for entry in self.extracted_data:
				sdict[str(int(entry['id'])-1)] = entry['parsed']
			save_json(sdict, sname)
		except Exception as e:
			# Handle TypeError and ValueError exceptions
			print("Caught an exception:", e)

	def _get_parsed(self):
		for i, entry in enumerate(self.extracted_data):
			query = entry['query']
			print(i)
			flag = run_js_script(self.parse_code, query)
			if flag:
				parsed = load_json('parsedQueryOutput.json')
				flag1 = True
			else:
				query = "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> PREFIX dbo: <http://dbpedia.org/ontology/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX yago: <http://dbpedia.org/class/yago/> " + query
				print("try to fix!")
				flag1 = run_js_script(self.parse_code, query)
				if flag1:
					print("fixed!")
					time.sleep(2)
				parsed = load_json('parsedQueryOutput.json')
			entry['parsed'] = parsed
			entry['if_parsed_success'] = flag1

# class LCQUAD2(BasicKG):
# 	def __init__(self, data, cache = None, kg = 'wiki', parse_code = 'parse.js', version = 'lcquad_2'):
# 		super().__init__(data, cache, kg, parse_code, version)

# 	def _extract_info(self):
# 		extracted_data = []
# 		for index, sample in enumerate(self.data):
# 			dic = {}
# 			dic['id'] = sample['uid']
# 			dic['index'] = index

# 			dic['question'] = sample['question']
# 			if self.kg == 'wiki':
# 				dic['query'] = sample['sparql_wikidata']
# 			elif self.kg == 'dbpedia':
# 				dic['query'] = sample['sparql_dbpedia18']
# 			else:
# 				raise ValueError("Invalid KG")

# 			res_list = []
# 			#print(sample['answers'][0])
# 			try:
# 				for res in sample['answers'][0]: # answer no more than 1
# 					res_list.append(res)
# 			except:
# 				pass

# 			dic['results'] = res_list

# 			# extra info
# 			dic['paraphrased_question'] = sample['paraphrased_question']
# 			dic['parsed_question'] = sample['NNQT_question']
# 			dic['template'] = sample['template']
# 			dic['subgraph'] = sample['subgraph']

# 			extracted_data.append(dic)

# 		return extracted_data
	
# 	def _get_parsed(self):
# 		for i, entry in enumerate(self.extracted_data):
# 			query = entry['query']
# 			print(i)
# 			flag = run_js_script(self.parse_code, query)
# 			if flag:
# 				parsed = load_json('parsedQueryOutput.json')
# 				flag1 = True
# 			else:
# 				if self.kg == 'wiki':
# 					query = "PREFIX bd: <http://www.bigdata.com/rdf#> PREFIX dct: <http://purl.org/dc/terms/> PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX p: <http://www.wikidata.org/prop/> PREFIX pq: <http://www.wikidata.org/prop/qualifier/> PREFIX ps: <http://www.wikidata.org/prop/statement/> PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wds: <http://www.wikidata.org/entity/statement/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> PREFIX wdv: <http://www.wikidata.org/value/> PREFIX wikibase: <http://wikiba.se/ontology#> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> " + query
# 				elif self.kg == 'dbpedia':
# 					query = "PREFIX yago: <http://dbpedia.org/class/yago/> PREFIX dbo: <http://dbpedia.org/ontology/> PREFIX dbp: <http://dbpedia.org/property/> PREFIX dbr: <http://dbpedia.org/resource/> PREFIX dbpedia: <http://dbpedia.org/> PREFIX dbpedia-owl: <http://dbpedia.org/ontology/> PREFIX foaf: <http://xmlns.com/foaf/0.1/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> " + query
# 				#print("try to fix!")
# 				flag1 = run_js_script(self.parse_code, query)
# 				# if flag1:
# 				# 	print("fixed!")
# 				if not flag1:
# 					print("failed to fix!")
# 				parsed = load_json('parsedQueryOutput.json')
# 			entry['parsed'] = parsed
# 			entry['if_parsed_success'] = flag1

# 	# save the parsed data to a json as a dict using the id as key
# 	def save_parsed(self, sname):
# 		try:
# 			sdict = {}
# 			for entry in self.extracted_data:
# 				sdict[str(entry['index'])] = entry['parsed']
# 			save_json(sdict, sname)
# 		except Exception as e:
# 			# Handle TypeError and ValueError exceptions
# 			print("Caught an exception:", e)


