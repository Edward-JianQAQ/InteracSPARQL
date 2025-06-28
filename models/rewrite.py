
from math import e
from openai import OpenAI


def factory_sys_msg(task, kb_name):
    if task == 'modification':
        return f"""Given the following original SPARQL query on {kb_name} and specific modifications, please rewrite the query to incorporate these changes while ensuring the new query remains syntactically correct and executable. Please only return the revised query without any additional information."""
    elif task == 'var_align':
        return f"""Given the following SPARQL query on {kb_name}, please align the variables in the SELECT and FILTER clause to the those mentioned in the query body. Do not delete the any clause. Please only return the revised query without any additional information."""
    elif task == 'var_align_inv':
        return f"""Given the following SPARQL query on {kb_name}, please align the variables in the SELECT clause to the those mentioned in the query body based the similarity between them. Do not delete the any clause. Make it unchanged if you think it's already aligned. Please only return the revised query without any additional information."""


MOD_ORI = ["""SELECT ?person ?name ?birthdate WHERE {?person wdt:P31 wd:Q5; wdt:P569 ?birthdate. FILTER(YEAR(?birthdate) = 1990) OPTIONAL { ?person rdfs:label ?name FILTER (LANG(?name) = "en")}} LIMIT 100"""]
MOD_INS = ["""Modifications: 1. Change the year of birth to 1991. 2. Include the occupation of the person in the query. 3. Increase the limit of results to 200"""]
MOD_RES = ["""SELECT ?person ?name ?birthdate ?occupation WHERE {?person wdt:P31 wd:Q5; wdt:P569 ?birthdate; wdt:P106 ?occupation. FILTER(YEAR(?birthdate) = 1991) OPTIONAL { ?person rdfs:label ?name FILTER (LANG(?name) = "en")}} LIMIT 200"""]

MODIFICATION_EXAMPLE = [MOD_ORI, MOD_INS, MOD_RES]


VAR_ORI = ["""PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> SELECT (COUNT(?article) AS ?result) WHERE {?art wdt:P31 wd:Q13442814; wdt:P921 wd:Q24901201. FILTER(?art IN (wd:Q4205826, wd:Q4463198))}""",
           """PREFIX bd: <http://www.bigdata.com/rdf#> PREFIX dct: <http://purl.org/dc/terms/> PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX p: <http://www.wikidata.org/prop/> PREFIX pq: <http://www.wikidata.org/prop/qualifier/> PREFIX ps: <http://www.wikidata.org/prop/statement/> PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wds: <http://www.wikidata.org/entity/statement/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> PREFIX wdv: <http://www.wikidata.org/value/> PREFIX wikibase: <http://wikiba.se/ontology#> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> SELECT DISTINCT ?result WHERE {wd:Q11835640 wdt:P674 ?res. ?res wdt:P451 ?p1, ?p2. FILTER(?p1 != ?p2 &&(?res IN (wd:Q4205826, wd:Q4463198)))}"""]
VAR_RES = ["""PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> SELECT (COUNT(?article) AS ?result) WHERE {?article wdt:P31 wd:Q13442814; wdt:P921 wd:Q24901201. FILTER(?article IN (wd:Q4205826, wd:Q4463198))}""",
           """PREFIX bd: <http://www.bigdata.com/rdf#> PREFIX dct: <http://purl.org/dc/terms/> PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX p: <http://www.wikidata.org/prop/> PREFIX pq: <http://www.wikidata.org/prop/qualifier/> PREFIX ps: <http://www.wikidata.org/prop/statement/> PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wds: <http://www.wikidata.org/entity/statement/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> PREFIX wdv: <http://www.wikidata.org/value/> PREFIX wikibase: <http://wikiba.se/ontology#> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> SELECT DISTINCT ?result WHERE {wd:Q11835640 wdt:P674 ?result. ?result wdt:P451 ?p1, ?p2. FILTER(?p1 != ?p2 &&(?result IN (wd:Q4205826, wd:Q4463198)))}"""]

VAR_ORI_INV = ["""PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> SELECT (COUNT(?article) AS ?result) WHERE {?art wdt:P31 wd:Q13442814; wdt:P921 wd:Q24901201. FILTER(?art IN (wd:Q4205826, wd:Q4463198))}""",
           """PREFIX bd: <http://www.bigdata.com/rdf#> PREFIX dct: <http://purl.org/dc/terms/> PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX p: <http://www.wikidata.org/prop/> PREFIX pq: <http://www.wikidata.org/prop/qualifier/> PREFIX ps: <http://www.wikidata.org/prop/statement/> PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wds: <http://www.wikidata.org/entity/statement/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> PREFIX wdv: <http://www.wikidata.org/value/> PREFIX wikibase: <http://wikiba.se/ontology#> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> SELECT DISTINCT ?result WHERE {wd:Q11835640 wdt:P674 ?res. ?res wdt:P451 ?p1, ?p2. FILTER(?p1 != ?p2 &&(?res IN (wd:Q4205826, wd:Q4463198)))}""",
           """PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> SELECT DISTINCT ?result WHERE {?fl wdt:P31 wd:Q19793459; wdt:P361 wd:Q8216; wdt:P156 ?result. FILTER(NOT EXISTS { ?fl wdt:P155 ?we. })}"""]
VAR_RES_INV = ["""PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> SELECT (COUNT(?art) AS ?result) WHERE {?art wdt:P31 wd:Q13442814; wdt:P921 wd:Q24901201. FILTER(?art IN (wd:Q4205826, wd:Q4463198))}""",
           """PREFIX bd: <http://www.bigdata.com/rdf#> PREFIX dct: <http://purl.org/dc/terms/> PREFIX geo: <http://www.opengis.net/ont/geosparql#> PREFIX p: <http://www.wikidata.org/prop/> PREFIX pq: <http://www.wikidata.org/prop/qualifier/> PREFIX ps: <http://www.wikidata.org/prop/statement/> PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wds: <http://www.wikidata.org/entity/statement/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> PREFIX wdv: <http://www.wikidata.org/value/> PREFIX wikibase: <http://wikiba.se/ontology#> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> SELECT DISTINCT ?res WHERE {wd:Q11835640 wdt:P674 ?res. ?res wdt:P451 ?p1, ?p2. FILTER(?p1 != ?p2 &&(?res IN (wd:Q4205826, wd:Q4463198)))}""",
           """PREFIX wd: <http://www.wikidata.org/entity/> PREFIX wdt: <http://www.wikidata.org/prop/direct/> SELECT DISTINCT ?result WHERE {?fl wdt:P31 wd:Q19793459; wdt:P361 wd:Q8216; wdt:P156 ?result. FILTER(NOT EXISTS { ?fl wdt:P155 ?we. })}"""]



VAR_EXAMPLE = [VAR_ORI, VAR_RES]
VAR_EXAMPLE_INV = [VAR_ORI_INV, VAR_RES_INV]


def rewrite_sparql(nl, task, examples = [], model="gpt-4-1106-preview", print_msg = False, model_config = {'kg_name': 'Wikidata', "include_exp": True, "temperature": 0.2}):
    kb_name = model_config['kg_name']
    
    client = OpenAI()
    sys_msg = factory_sys_msg(task, kb_name)
    message = [{"role": "system", "content": sys_msg}]
    
    if model_config['include_exp']:
        if task == 'modification':
            if examples == []:
                examples = MODIFICATION_EXAMPLE
            for i in range(len(examples[0])):
                message.append({"role": "user", "content": examples[0][i] + '\n' + examples[1][i]})
                message.append({"role": "assistant", "content": examples[2][i]})
        elif task == 'var_align':
            if examples == []:
                examples = VAR_EXAMPLE
            for i in range(len(examples[0])):
                message.append({"role": "user", "content": examples[0][i]})
                message.append({"role": "assistant", "content": examples[1][i]})

        elif task == 'var_align_inv':
            if examples == []:
                examples = VAR_EXAMPLE_INV
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
      temperature = model_config['temperature'],
      messages= message
    )

    return response.choices[0].message.content