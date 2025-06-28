from os import error
import pdb
from SPARQLWrapper import SPARQLWrapper, JSON
from typing import Set, Tuple, Union
# from UnifiedSKG.metrics.mmqa.evaluator import f1
from utils.utils import print_raw_query
import time
import urllib.error
# Constants
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"

def execute_sparql_query_wiki(query: str) -> Union[Set[Tuple], bool]:
    """Execute a SPARQL query against the Wikidata endpoint and return a set of results or a boolean for ASK queries."""
    sparql = SPARQLWrapper(WIKIDATA_ENDPOINT, agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36')
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    
    # Handle ASK query results
    if 'boolean' in results:
        return results['boolean']

    result_set = set()
    
    if 'results' in results and 'bindings' in results['results']:
        for result in results['results']['bindings']:
            result_tuple = tuple(sorted(binding['value'] for binding in result.values()))
            # result_set.add(result_tuple)
            for item in result_tuple:
                result_set.add(item)

    #print("!!!!!!!!!!!!!!!!!",result_set)
    return result_set

def execute_sparql_query_dbpedia(query: str)-> Union[Set[Tuple], bool]:
    # sparql = SPARQLWrapper("http://dbpedia.org/sparql")
    # sparql.setQuery(query)
    # sparql.setReturnFormat(JSON)
    while True:
        try:
            sparql = SPARQLWrapper("http://dbpedia.org/sparql")
            sparql.setQuery(query)
            sparql.setReturnFormat(JSON)
            results = sparql.query().convert()
            break  # Exit the loop if the function call is successful
        except urllib.error.HTTPError as e:
            if e.code == 502:
                print("HTTP Error 502: Bad Gateway encountered. Retrying in 10 seconds...")
                time.sleep(10)
            else:
                raise  # Re-raise any other HTTPError that is not a 502 error
    # results = sparql.query().convert()
    result_set = set()
    if 'results' in results and 'bindings' in results['results']:
        for result in results['results']['bindings']:
            result_tuple = tuple(sorted(binding['value'] for binding in result.values()))
            for item in result_tuple:
                result_set.add(item)
    return result_set


def calculate_metrics(model_results: Union[bool, Set[Tuple]], truth_results: Union[bool, Set[Tuple]]) -> Tuple[float, float, float]:
    """Calculate precision, recall, and F1 score from model results and ground truth based on specific conditions."""
    if isinstance(model_results, bool) and isinstance(truth_results, bool):

        if model_results == truth_results:
            return 1.0, 1.0, 1.0
        else:
            return 0.0, 0.0, 0.0
    else:
        # Handle SELECT query results as previously
        if not truth_results:
            return (1.0, 1.0, 1.0) if not model_results else (0.0, 0.0, 0.0)
        if not model_results:
            return 0.0, 0.0, 0.0
        
        true_positives = len(model_results & truth_results)
        precision = true_positives / len(model_results) if model_results else 0
        recall = true_positives / len(truth_results) if truth_results else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) else 0
        return precision, recall, f1_score


def evaluate_sparql_queries(model_query: str, ground_truth_query: str, kg = 'wiki') -> dict:
    """Evaluate SPARQL queries by comparing results of model's query against ground truth."""
    if kg == 'wiki':
        model_results = execute_sparql_query_wiki(model_query)
        truth_results = execute_sparql_query_wiki(ground_truth_query)
    elif kg == 'dbpedia':
        model_results = execute_sparql_query_dbpedia(model_query)
        truth_results = execute_sparql_query_dbpedia(ground_truth_query)
    #pdb.set_trace()
    # print(model_results)
    # print(truth_results)
    precision, recall, f1_score = calculate_metrics(model_results, truth_results)
    return {
        "precision": precision,
        "recall": recall,
        "F1_score": f1_score
    }



def calculate_metrics_valid(model_results: Union[bool, Set[Tuple]], truth_results: Union[bool, Set[Tuple]]) -> Tuple[float, float, float]:
    """Calculate precision, recall, and F1 score from model results and ground truth based on specific conditions."""
    if isinstance(model_results, bool) and isinstance(truth_results, bool):

        if model_results == truth_results:
            return 1.0, 1.0, 1.0
        else:
            return 0.0, 0.0, 0.0
    else:
        # Handle SELECT query results as previously
        if not truth_results:
            return 0.0, 0.0, 0.0
        if not model_results:
            return 0.0, 0.0, 0.0
        
        true_positives = len(model_results & truth_results)
        precision = true_positives / len(model_results) if model_results else 0
        recall = true_positives / len(truth_results) if truth_results else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) else 0
        return precision, recall, f1_score

def evaluate_sparql_queries_with_res(model_query_res, ground_truth_res) -> dict:
    """Evaluate SPARQL queries by comparing results of model's query against ground truth."""

    model_results = model_query_res
    truth_results = ground_truth_res

    #pdb.set_trace()
    # print(model_results)
    # print(truth_results)
    precision, recall, f1_score = calculate_metrics_valid(model_results, truth_results)
    return {
        "precision": precision,
        "recall": recall,
        "F1_score": f1_score
    }






def compute_overall_metrics(eval_list):
    total_precision_raw = 0
    total_recall_raw = 0
    total_f1_raw = 0
    total_precision_final = 0
    total_recall_final = 0
    total_f1_final = 0
    count = 0

    # Iterate through each evaluation in the list
    for eval in eval_list:
        if 'eval_raw' in eval:
            total_precision_raw += eval['eval_raw']['precision']
            total_recall_raw += eval['eval_raw']['recall']
            total_f1_raw += eval['eval_raw']['F1_score']
        
        if 'eval_final' in eval:
            total_precision_final += eval['eval_final']['precision']
            total_recall_final += eval['eval_final']['recall']
            total_f1_final += eval['eval_final']['F1_score']
        count += 1

    # Calculate averages
    if count > 0:
        average_precision_raw = total_precision_raw / count
        average_recall_raw = total_recall_raw / count
        average_f1_raw = total_f1_raw / count

        average_precision_final = total_precision_final / count
        average_recall_final = total_recall_final / count
        average_f1_final = total_f1_final / count
    else:
        average_precision_raw = 0
        average_recall_raw = 0
        average_f1_raw = 0
        average_precision_final = 0
        average_recall_final = 0
        average_f1_final = 0

    return {
        'average_precision_raw': average_precision_raw,
        'average_recall_raw': average_recall_raw,
        'average_f1_raw': average_f1_raw,
        'average_precision_final': average_precision_final,
        'average_recall_final': average_recall_final,
        'average_f1_final': average_f1_final
    }


def return_all_error(eval_list, f1_threshold = 1):
    error_list_raw = []
    error_list_final = []
    for eval in eval_list:
        if 'eval_raw' in eval:
            if eval['eval_raw']['F1_score'] < f1_threshold:
                error_list_raw.append(eval)

        if 'eval_final' in eval:
            if eval['eval_final']['F1_score'] < f1_threshold:
                error_list_final.append(eval)

    return error_list_raw, error_list_final


def compare_query(error_list):
    for i in error_list:
        print("Start================================================================")
        print(i['index'])
        print(i['gt_result'])
        print(i['gen_result'])
        print(i['final_result'])
        print_raw_query(i['gt_query'])
        print_raw_query(i['gen_query'])
        print_raw_query(i['revised_query'])
        print("Result================================================================")
        