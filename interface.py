import copy
import json
import pdb
from models.rewrite import rewrite_sparql
from models.bgp import generate_bgp_from_gt, nl2bgp_parsed, bgp2nl_parsed, bgp_get_example
from models.filter import generate_filter_from_gt, nl2filter_parsed, filter2nl_parsed, filter_get_example
from models.bind import generate_bind_from_gt, nl2bind_parsed, bind2nl_parsed, bind_get_example

from utils.utils import filter_pattern, load_json, save_json, load_jsonl, save_object, load_object, sample_examples, check_bgp, check_bind, check_filter, check_group,\
      check_union, check_reg_path, check_if_variable_str, print_all_pattern, print_raw_query, replace_pattern, return_after_word, print_after_word, return_raw_query, select_certain_pattern,\
      filter_pattern

from utils.runjs import run_js_script

from utils.prefix import RDFS_VOCABULARY, extract_entity_id, extract_entity_info

from utils.wikidata import id2info, entity2id, property2id, extract_url, general_wiki_search, extract_url_and_replace, extract_label_and_replace, run_wikidata_query

import numpy as np
import json
from openai import OpenAI
import os
import random


def increment_last_digit(prefix):
    parts = prefix.split('.')
    parts[-1] = str(int(parts[-1]) + 1)
    return '.'.join(parts)

# Placeholder explanation functions for each pattern keyword
def explain_query_type(query, prefix, path):
    query_type = query.get("queryType", "SELECT")
    distinct = query.get("distinct", False)
    distinct_text = " distinct" if distinct else ""
    # return f"{prefix}: This query is asking for{distinct_text} {query_type} data.", path, {prefix: (path, 'queryType')}
    return f"{prefix}: This query is asking to {query_type} data.", path, {prefix: (path, 'queryType')}

def explain_distinct(distinct, prefix, path):
    distinct_text = "DISTINCT" if distinct else "not DISTINCT"
    return f"{prefix}: The query searches for {distinct_text} results.", path, {prefix: (path, 'distinct')}




def explain_variables(variables, prefix, path, use_labels=False, label_func=None):
    explanations = []
    paths = {prefix: (path, 'variables')}
    
    for i, var in enumerate(variables, start=1):
        sub_prefix = f"{prefix}.var.{i}"
        
        # Check if the variable contains an expression (complex case)
        if 'expression' in var:
            expression = var['expression']
            agg_type = expression.get('aggregation', None)
            inner_expr = expression.get('expression', {})
            agg_expr = inner_expr.get('value', 'unknown')
            distinct = expression.get('distinct', False)
            distinct_text = '"Distinct" ' if distinct else ''
            
            # Capitalize aggregation type
            agg_type = agg_type.capitalize() if agg_type else 'aggregate'
            
            # Handle nested expressions or simple expressions
            if inner_expr.get('termType') == 'Variable':
                explanations.append(
                    f"{sub_prefix} The variable '{var['variable']['value']}' is the result of applying {distinct_text}\"{agg_type}\" to the variable '{agg_expr}'."
                )
            elif inner_expr.get('termType') == 'NamedNode':
                if use_labels and label_func:
                    label = label_func(agg_expr)
                    explanations.append(
                        f"{sub_prefix} The variable '{var['variable']['value']}' is the result of applying {distinct_text}\"{agg_type}\" to the entity '{agg_expr}' ({label})."
                    )
                else:
                    explanations.append(
                        f"{sub_prefix} The variable '{var['variable']['value']}' is the result of applying {distinct_text}\"{agg_type}\" to the entity '{agg_expr}'."
                    )
            else:
                explanations.append(
                    f"{sub_prefix} The variable '{var['variable']['value']}' is the result of applying {distinct_text}\"{agg_type}\" to an unknown expression."
                )
        
        # Handle the case where there's no expression (simple variable)
        else:
            distinct_text = '"Distinct" ' if var.get('distinct', False) else ''
            variable_value = var.get('value', 'unknown')
            
            if var.get('termType') == 'Variable':
                explanations.append(
                    f"{sub_prefix} The query returns the {distinct_text}variable '{variable_value}'."
                )
            elif var.get('termType') == 'NamedNode':
                if use_labels and label_func:
                    label = label_func(variable_value)
                    explanations.append(
                        f"{sub_prefix} The query returns the {distinct_text}entity '{variable_value}' ({label})."
                    )
                else:
                    explanations.append(
                        f"{sub_prefix} The query returns the {distinct_text}entity '{variable_value}'."
                    )
            else:
                explanations.append(
                    f"{sub_prefix} The query returns an unknown {distinct_text}term '{variable_value}'."
                )
        
        # Update the path dictionary
        paths[sub_prefix] = (path + [i - 1], 'variable')
    
    return "\n".join(explanations), path, paths




def explain_bgp(triples, prefix, path, use_labels=False, label_func=None):
    explanations = []
    paths = {prefix: (path, 'bgp')}
    
    for i, triple in enumerate(triples, start=1):
        sub_prefix = f"{prefix}.{i}"
        subject = triple.get('subject', {})
        object_ = triple.get('object', {})
        predicate = triple.get('predicate', {})
        
        # Extract subject and object values
        subject_value = subject.get('value', 'unknown')
        object_value = object_.get('value', 'unknown')
        
        # Apply label_func if use_labels is True and termType is NamedNode
        if use_labels and label_func:
            if subject.get('termType') == 'NamedNode':
                subject_value = f"{subject_value} ({label_func(subject_value)})"
            if object_.get('termType') == 'NamedNode':
                object_value = f"{object_value} ({label_func(object_value)})"
        
        # Check if the predicate is of 'path' type
        if predicate.get('type') == 'path':
            path_type = predicate.get('pathType', 'unknown')
            items = predicate.get('items', [])
            
            # Handle the '/' path type (concatenation of paths)
            if path_type == '/':
                item_values = " followed by ".join(
                    explain_path_item(item, use_labels, label_func) for item in items
                )
                explanations.append(
                    f"{sub_prefix} The entity '{subject_value}' follows a sequence of paths: {item_values}, ending at '{object_value}'."
                )
            # Handle the '*' path type (any number of steps along the path)
            elif path_type == '*':
                explanations.append(
                    f"{sub_prefix} The entity '{subject_value}' can traverse any number of steps through the path: {explain_path_item(items[0], use_labels, label_func)}, and reach '{object_value}'."
                )
            else:
                explanations.append(
                    f"{sub_prefix} The entity '{subject_value}' follows the path '{path_type}' and reaches '{object_value}'."
                )
        else:
            # Handle standard predicate structure
            predicate_value = predicate.get('value', 'unknown')
            if use_labels and label_func and predicate.get('termType') == 'NamedNode':
                predicate_value = f"{predicate_value} ({label_func(predicate_value)})"
            
            explanations.append(
                f"{sub_prefix} The entity '{subject_value}' has the property '{predicate_value}', and its value is '{object_value}'."
            )
        
        # Update paths
        paths[sub_prefix] = (path + ["triples", i - 1], 'triple')
    
    return f"{prefix} The Basic Graph Pattern (BGP) includes the following statements:\n" + "\n".join(explanations), path, paths

# Helper function to explain path items, applying label_func if applicable
def explain_path_item(item, use_labels=False, label_func=None):
    if item.get('pathType') == '*':
        item_value = item.get('items', [{}])[0].get('value', 'unknown')
        if use_labels and label_func and item.get('items', [{}])[0].get('termType') == 'NamedNode':
            item_value = f"{item_value} ({label_func(item_value)})"
        return f"zero or more steps along '{item_value}'"
    
    item_value = item.get('value', 'unknown')
    if use_labels and label_func and item.get('termType') == 'NamedNode':
        item_value = f"{item_value} ({label_func(item_value)})"
    
    return item_value



# Helper function to explain nested paths like '*' (Kleene star)
def explain_nested_path(item):
    if item.get('pathType') == '*':
        return f"zero or more steps along '{item.get('items', [{}])[0].get('value', 'unknown')}'"
    return item.get('value', 'unknown')




def explain_filter(expression, prefix, path, use_labels=False, label_func=None):
    operator = expression.get("operator")
    args = expression.get("args", [])

    if operator and args:
        # Extract argument descriptions
        arg_descriptions = []
        for arg in args:
            if isinstance(arg, list):
                # Handle the case where the argument is a list (e.g., in the case of the 'in' operator)
                list_items = []
                for item in arg:
                    item_value = item.get('value', 'unknown')
                    if use_labels and label_func and item.get('termType') == 'NamedNode':
                        item_value = f"{item_value} ({label_func(item_value)})"
                    list_items.append(f"'{item_value}'")
                arg_descriptions.append(f"a list containing {', '.join(list_items)}")
            elif arg.get("termType") == "Variable":
                arg_descriptions.append(f"the value of variable '{arg.get('value')}'")
            elif arg.get("termType") == "NamedNode":
                arg_value = arg.get('value')
                if use_labels and label_func:
                    arg_value = f"{arg_value} ({label_func(arg_value)})"
                arg_descriptions.append(f"the entity '{arg_value}'")
            elif arg.get("termType") == "Literal":
                arg_descriptions.append(f"the literal value '{arg.get('value')}'")
            else:
                arg_descriptions.append(f"an unknown argument '{arg}'")

        # Build the natural language explanation for the filter
        if len(arg_descriptions) == 2:
            explanation = f"A filter is applied to include results where {arg_descriptions[0]} {operator} {arg_descriptions[1]}."
        else:
            explanation = f"A filter is applied with the operator '{operator}' but has an unusual number of arguments."

        return f"{prefix}: {explanation}", path, {prefix: (path, 'filter')}

    return f"{prefix}: A filter is applied.", path, {prefix: (path, 'filter')}



def explain_group(patterns, prefix, path, use_labels=False, label_func=None):
    explanations = []
    paths = {prefix: (path, 'group')}
    for i, p in enumerate(patterns):
        sub_prefix = f"{prefix}.{i+1}"
        expl, sub_path, sub_paths_dict = explain_pattern(p, sub_prefix, path + ["patterns", i], use_labels=use_labels, label_func=label_func)
        explanations.append(expl)
        paths.update(sub_paths_dict)
    return f"{prefix} This part groups the following patterns:\n" + "\n".join(explanations), path, paths

def explain_optional(patterns, prefix, path, use_labels=False, label_func=None):
    explanations = []
    paths = {prefix: (path, 'optional')}
    for i, p in enumerate(patterns):
        sub_prefix = f"{prefix}.{i+1}"
        expl, sub_path, sub_paths_dict = explain_pattern(p, sub_prefix, path + ["patterns", i], use_labels=use_labels, label_func=label_func)
        explanations.append(expl)
        paths.update(sub_paths_dict)
    return f"{prefix} Optional patterns include:\n" + "\n".join(explanations), path, paths

def explain_minus(patterns, prefix, path, use_labels=False, label_func=None):
    explanations = []
    paths = {prefix: (path, 'minus')}
    for i, p in enumerate(patterns):
        sub_prefix = f"{prefix}.{i+1}"
        expl, sub_path, sub_paths_dict = explain_pattern(p, sub_prefix, path + ["patterns", i], use_labels=use_labels, label_func=label_func)
        explanations.append(expl)
        paths.update(sub_paths_dict)
    return f"{prefix} Minus patterns exclude:\n" + "\n".join(explanations), path, paths


def explain_order(order, prefix, path, use_labels=False, label_func=None):
    explanations = []
    paths = {prefix: (path, 'order')}
    
    for i, o in enumerate(order, start=1):
        sub_prefix = f"{prefix}.{i}"
        
        # Extract expression and sorting details
        expression = o.get('expression', {})
        expr_value = expression.get('value', 'unknown')
        descending = o.get('descending', False)

        # Check if expression is a NamedNode or Variable
        if expression.get('termType') == 'Variable':
            order_by = f"variable '{expr_value}'"
        elif expression.get('termType') == 'NamedNode':
            order_by = f"the entity '{expr_value}'"
            if use_labels and label_func:
                label = label_func(expr_value)
                order_by += f" ({label})"
        else:
            order_by = f"an expression '{expr_value}'"

        # Determine order direction
        order_direction = "descending" if descending else "ascending"
        
        explanations.append(f"{sub_prefix} The results are ordered by {order_by} in {order_direction} order.")
        
        paths[sub_prefix] = (path + [i - 1], 'orderItem')
    
    return f"{prefix} Results are ordered by:\n" + "\n".join(explanations), path, paths




def explain_bind(bind, prefix, path, use_labels=False, label_func=None):
    variable = bind.get("variable", {}).get("value", "unknown")
    expression_details = bind.get("expression", {})
    operator = expression_details.get("operator", "")
    args = expression_details.get("args", [])

    # Handle cases with operations like 'if', 'coalesce', etc.
    if operator:
        if operator == "if":
            # Check for three arguments in the 'if' expression
            if len(args) == 3:
                condition = args[0]
                true_value = args[1]
                false_value = args[2]

                # Explain the condition
                condition_operator = condition.get("operator", "unknown")
                condition_args = condition.get("args", [])
                if len(condition_args) == 2:
                    left_cond = condition_args[0].get('value', 'unknown')
                    right_cond = condition_args[1].get('value', 'unknown')

                    # Apply label function if use_labels is True
                    if use_labels and label_func:
                        if condition_args[0].get('termType') == 'NamedNode':
                            left_cond = f"{left_cond} ({label_func(left_cond)})"
                        if condition_args[1].get('termType') == 'NamedNode':
                            right_cond = f"{right_cond} ({label_func(right_cond)})"

                    condition_text = f"if the value of '{left_cond}' {condition_operator} the value of '{right_cond}'"
                else:
                    condition_text = "a complex condition"

                # Get the true and false values
                true_value_text = true_value.get('value', 'unknown')
                false_value_text = false_value.get('value', 'unknown')

                # Apply label function to true/false values if they are NamedNodes
                if use_labels and label_func:
                    if true_value.get('termType') == 'NamedNode':
                        true_value_text = f"{true_value_text} ({label_func(true_value_text)})"
                    if false_value.get('termType') == 'NamedNode':
                        false_value_text = f"{false_value_text} ({label_func(false_value_text)})"

                explanation = (f"{prefix}: The variable '{variable}' is bound based on the condition: "
                               f"{condition_text}. If the condition holds true, '{variable}' is bound to '{true_value_text}'; "
                               f"otherwise, it is bound to '{false_value_text}'.")

            else:
                explanation = f"{prefix}: The variable '{variable}' is bound using a complex 'if' operation."
        
        elif operator == "coalesce":
            # Handle 'coalesce' operations which take multiple arguments
            arg_descriptions = []
            for arg in args:
                arg_value = arg.get('value', 'unknown')
                if use_labels and label_func and arg.get('termType') == 'NamedNode':
                    arg_value = f"{arg_value} ({label_func(arg_value)})"
                arg_descriptions.append(f"'{arg_value}'")

            explanation = (f"{prefix}: The variable '{variable}' is bound to the first non-null value among: "
                           f"{', '.join(arg_descriptions)}.")

        else:
            # Handle other operations
            arg_descriptions = []
            for arg in args:
                arg_value = arg.get('value', 'unknown')
                if use_labels and label_func and arg.get('termType') == 'NamedNode':
                    arg_value = f"{arg_value} ({label_func(arg_value)})"
                arg_descriptions.append(f"'{arg_value}'")
            
            explanation = (f"{prefix}: The variable '{variable}' is bound using the '{operator}' operation on "
                           f"{', '.join(arg_descriptions)}.")

    else:
        # Handle simple expression cases without operations
        expression_value = expression_details.get("value", "unknown")
        expression_type = expression_details.get("termType", "unknown")

        # If using labels, apply the label function to NamedNode expressions
        if use_labels and label_func and expression_type == 'NamedNode':
            expression_value = f"{expression_value} ({label_func(expression_value)})"

        expression_description = (f"a literal value '{expression_value}'" if expression_type == "Literal"
                                  else f"the value of the variable '{expression_value}'" if expression_type == "Variable"
                                  else f"the entity '{expression_value}'" if expression_type == "NamedNode"
                                  else f"an unknown type of expression '{expression_value}'")

        explanation = (f"{prefix}: The variable '{variable}' is bound to {expression_description}.")
    
    return explanation, path, {prefix: (path, 'bind')}




def explain_group_by(group_by, prefix, path, use_labels=False, label_func=None):
    explanations = []
    paths = {prefix: (path, 'groupBy')}
    
    for i, g in enumerate(group_by, start=1):
        sub_prefix = f"{prefix}.{i}"
        expression = g.get('expression', {})
        variable_value = expression.get('value', 'unknown')
        variable_type = expression.get('termType', 'unknown')

        # Handle case when the grouping is by a variable or named node
        if variable_type == 'Variable':
            explanations.append(f"{sub_prefix} The results are grouped by the variable '{variable_value}'.")
        elif variable_type == 'NamedNode':
            if use_labels and label_func:
                label = label_func(variable_value)
                explanations.append(f"{sub_prefix} The results are grouped by the entity '{variable_value}' ({label}).")
            else:
                explanations.append(f"{sub_prefix} The results are grouped by the entity '{variable_value}'.")
        else:
            explanations.append(f"{sub_prefix} The results are grouped by an unknown expression '{variable_value}'.")

        # Adding the paths
        paths[sub_prefix] = (path + [i - 1], 'groupByItem')
    
    return f"{prefix} Results are grouped by:\n" + "\n".join(explanations), path, paths


def explain_pattern(pattern, prefix, path, use_labels=False, label_func=None):
    pattern_type = pattern.get("type")
    if pattern_type == "bgp":
        return explain_bgp(pattern.get("triples", []), prefix, path, use_labels=use_labels, label_func=label_func)
    elif pattern_type == "group":
        return explain_group(pattern.get("patterns", []), prefix, path, use_labels=use_labels, label_func=label_func)
    elif pattern_type == "filter":
        return explain_filter(pattern.get("expression", {}), prefix, path, use_labels=use_labels, label_func=label_func)
    elif pattern.get("queryType") == "SELECT":
        return explain_select(pattern, prefix, path, use_labels=use_labels, label_func=label_func)
    elif pattern.get("queryType") == "ASK":
        return explain_ask(pattern, prefix, path, use_labels=use_labels, label_func=label_func)
    elif pattern_type == "optional":
        return explain_optional(pattern.get("patterns", []), prefix, path, use_labels=use_labels, label_func=label_func)
    elif pattern_type == "minus":
        return explain_minus(pattern.get("patterns", []), prefix, path, use_labels=use_labels, label_func=label_func)
    elif pattern_type == "bind":
        return explain_bind(pattern, prefix, path, use_labels=use_labels, label_func=label_func)
    elif pattern_type == "union":
        return explain_union(pattern.get("patterns", []), prefix, path, use_labels=use_labels, label_func=label_func)
    return "", path, {}


def explain_union(patterns, prefix, path, use_labels=False, label_func=None):
    explanations = []
    paths = {prefix: (path, 'union')}
    for i, p in enumerate(patterns):
        sub_prefix = f"{prefix}.{i+1}"
        expl, sub_path, sub_paths_dict = explain_pattern(p, sub_prefix, path + ["patterns", i], use_labels=use_labels, label_func=label_func)
        explanations.append(expl)
        paths.update(sub_paths_dict)
    return f"{prefix} Union patterns include:\n" + "\n".join(explanations), path, paths


def explain_select(select, prefix, path, use_labels=False, label_func=None):
    explanations = []
    paths = {prefix: (path, 'select')}

    explanations.append(f"{prefix} This pattern is a subquery. The following are the details of the subquery:")

    expl, sub_path, sub_paths_dict = explain_query_type(select, f"{prefix}.1", path + ["queryType"])
    explanations.append(expl)
    paths.update(sub_paths_dict)

    expl, sub_path, sub_paths_dict = explain_variables(select.get("variables", []), f"{prefix}.2", path + ["variables"])
    explanations.append(expl)
    paths.update(sub_paths_dict)

    sub_prefix = f"{prefix}.3"
    explanations.append(f"{sub_prefix} Patterns: The following conditions should be satisfied:")
    paths[sub_prefix] = (path + ["where"], 'patterns')

    for i, p in enumerate(select.get("where", [])):
        expl, sub_path, sub_paths_dict = explain_pattern(p, f"{sub_prefix}.{i+1}", path + ["where", i], use_labels=use_labels, label_func=label_func)
        explanations.append(expl)
        paths.update(sub_paths_dict)

    if "order" in select:
        order_prefix = increment_last_digit(sub_prefix)
        expl, sub_path, sub_paths_dict = explain_order(select.get("order", []), f"{order_prefix}", path + ["order"])
        explanations.append(expl)
        paths.update(sub_paths_dict)

    if "limit" in select:
        limit_prefix = increment_last_digit(order_prefix if "order" in select else sub_prefix)
        explanations.append(f"{limit_prefix} The query limits results to {select.get('limit')}.")
        paths[limit_prefix] = (path + ["limit"], 'limit')

    if "offset" in select:
        offset_prefix = increment_last_digit(limit_prefix if "limit" in select else (order_prefix if "order" in select else sub_prefix))
        explanations.append(f"{offset_prefix} The query skips the first {select.get('offset')} results.")
        paths[offset_prefix] = (path + ["offset"], 'offset')

    return "\n".join(explanations), path, paths

def explain_ask(ask, prefix, path, use_labels=False, label_func=None):
    explanations = []
    paths = {prefix: (path, 'ask')}

    explanations.append(f"{prefix} This pattern is an ASK query. The following conditions should be checked:")

    sub_prefix = f"{prefix}.1"
    explanations.append(f"{sub_prefix} Patterns: The following conditions should be satisfied:")
    paths[sub_prefix] = (path + ["where"], 'patterns')

    for i, p in enumerate(ask.get("where", [])):
        expl, sub_path, sub_paths_dict = explain_pattern(p, f"{sub_prefix}.{i+1}", path + ["where", i], use_labels=use_labels, label_func=label_func)
        explanations.append(expl)
        paths.update(sub_paths_dict)

    return "\n".join(explanations), path, paths

def parse_sparql_query(query,use_labels=False, label_func=None):
    #try:
    explanations = []
    paths = {}

    expl, sub_path, sub_paths_dict = explain_query_type(query, "Query Type", ["queryType"])
    explanations.append(expl)
    paths.update(sub_paths_dict)
    explanations.append('\n')

    if query.get("distinct", False):
        expl, sub_path, sub_paths_dict = explain_distinct(query["distinct"], "Distinct", ["distinct"])
        explanations.append(expl)
        paths.update(sub_paths_dict)
        explanations.append('\n')

    if query.get("queryType", "SELECT") == "SELECT":
        expl = "Variables: The query contains the following variables."
        explanations.append(expl)
        expl, sub_path, sub_paths_dict = explain_variables(query.get("variables", []), "Variables", ["variables"])
        explanations.append(expl)
        paths.update(sub_paths_dict)

    else:
        expl = "Variables: The query does not return any variables. Just check whether the following stands."
        explanations.append(expl)

    explanations.append('\n')
    sub_prefix = "Patterns"
    explanations.append(f"{sub_prefix}: The following conditions should be satisfied:")
    paths[sub_prefix] = (["where"], 'patterns')

    for i, p in enumerate(query.get("where", [])):
        expl, sub_path, sub_paths_dict = explain_pattern(p, f"{i+1}", ["where", i], use_labels=use_labels, label_func=label_func)
        explanations.append(f"{expl}")
        paths.update(sub_paths_dict)


    if "group" in query:
        group_prefix = increment_last_digit(str(i+1))
        expl, sub_path, sub_paths_dict = explain_group_by(query.get("group", []), group_prefix, ["group"])
        explanations.append(expl)
        paths.update(sub_paths_dict)

    if "order" in query:
        # order_prefix = increment_last_digit(str(i+1))
        order_prefix = increment_last_digit(group_prefix if "group" in query else str(i+1))
        expl, sub_path, sub_paths_dict = explain_order(query.get("order", []), order_prefix, ["order"], use_labels=use_labels, label_func=label_func)
        explanations.append(expl)
        paths.update(sub_paths_dict)

    if "limit" in query:
        limit_prefix = increment_last_digit(order_prefix if "order" in query else str(i+1))
        explanations.append(f"{limit_prefix} The query limits results to {query.get('limit')}.")
        paths[limit_prefix] = (["limit"], 'limit')

    if "offset" in query:
        offset_prefix = increment_last_digit(limit_prefix if "limit" in query else (order_prefix if "order" in query else str(i+1)))
        explanations.append(f"{offset_prefix} The query skips the first {query.get('offset')} results.")
        paths[offset_prefix] = (["offset"], 'offset')

    return "\n".join(explanations), paths
    # except Exception as e:
    #     return str(e), {}


# Functions to isolate and revise parts of the query
def set_query_type_value(new_value, if_llm = False, if_nl = True, model = "gpt-4-turbo"):
    assert new_value in ['SELECT', 'ASK'], "Invalid query type."
    return new_value

def set_distinct_value(new_value, if_llm=False, if_nl=True, model = "gpt-4-turbo"):
    assert isinstance(new_value, bool), "Distinct value must be a boolean."
    return new_value

def set_query_distinct_value(new_value, if_llm = False, if_nl = True, model = "gpt-4-turbo"):
    assert isinstance(new_value, bool), "Distinct value must be a boolean."
    return new_value

def set_limit_value(new_value, if_llm = False, if_nl = True, model = "gpt-4-turbo"):
    assert (isinstance(new_value, int) and new_value >= 0) or (new_value == False), "Limit value must be a non-negative integer."
    if new_value == False:
        return 0
    return new_value

def set_offset_value(new_value, if_llm = False, if_nl = True, model = "gpt-4-turbo"):
    assert (isinstance(new_value, int) and new_value >= 0) or (new_value == False), "Offset value must be a non-negative integer."
    if new_value == False:
        return 0
    return new_value

def set_prefixes_value(new_value, if_llm = False, if_nl = True, model = "gpt-4-turbo"):
    return new_value

def set_group_by_value(new_value, if_llm=False, if_nl=True, model = "gpt-4-turbo"):
    return new_value

def set_group_by_item_value(new_value, if_llm=False, if_nl=True, model = "gpt-4-turbo"):
    return new_value

# under development
def set_order_value(new_value, if_llm = False, if_nl = True, model = "gpt-4-turbo"):

    return new_value

# under development
def set_variables_value(new_value, if_llm = False, if_nl = True, model = "gpt-4-turbo"):
    return new_value

# under development
def set_where_value(new_value, if_llm = False, if_nl = True, model = "gpt-4-turbo"):
    return new_value

# under development
def set_pattern_value(new_value, if_llm = False, if_nl = True, model = "gpt-4-turbo"):
    return new_value
# under development
def set_union_value(new_value, if_llm=False, if_nl=True, model = "gpt-4-turbo"):
    return new_value
# under development
def set_union_item_value(new_value, if_llm=False, if_nl=True, model = "gpt-4-turbo"):
    return new_value
# under development
def set_group_value(new_value, if_llm=False, if_nl=True, model = "gpt-4-turbo"):
    return new_value

def set_bgp_value(new_value, if_llm = False, if_nl = True, seed = 3407, num_shots = 10, model = "gpt-4-turbo"):
    return {'type': 'bgp', 'triples':[]}
        

def set_triple_value(new_value, if_llm = False, if_nl = True, seed = 3407, num_shots = 10, model = "gpt-4-turbo"):
    if if_llm:
        EXAMPLE = bgp_get_example()

        random.seed(seed)
        index = sample_examples(len(EXAMPLE[0]), len(EXAMPLE[0]))
        random.seed()

        examples = [[EXAMPLE[0][ind] for ind in index[:num_shots]], [EXAMPLE[1][ind] for ind in index[:num_shots]]]
        if if_nl:
            return json.loads(nl2bgp_parsed(new_value, examples=examples, model=model))
        else:
            new_value = json.dumps(new_value)
            temp_nl = bgp2nl_parsed(new_value, examples=examples, model=model)
            return json.loads(nl2bgp_parsed(temp_nl, examples=examples, model=model))
    return new_value

def set_filter_value(new_value, if_llm = False, if_nl = True, seed = 3407, num_shots = 10, model = "gpt-4-turbo"):
    if if_llm:
        EXAMPLE = filter_get_example()

        random.seed(seed)
        index = sample_examples(len(EXAMPLE[0]), len(EXAMPLE[0]))
        random.seed()

        examples = [[EXAMPLE[0][ind] for ind in index[:num_shots]], [EXAMPLE[1][ind] for ind in index[:num_shots]]]
        if if_nl:
            return json.loads(nl2filter_parsed(new_value, examples=examples, model=model))
        else:
            new_value = json.dumps(new_value)
            temp_nl = filter2nl_parsed(new_value, examples=examples, model=model)
            return json.loads(nl2filter_parsed(temp_nl, examples=examples, model=model))
    return new_value                                                                

def set_bind_value(new_value, if_llm = False, if_nl = True, seed = 3407, num_shots = 10, model = "gpt-4-turbo"):
    if if_llm:
        EXAMPLE = bind_get_example()

        random.seed(seed)
        index = sample_examples(len(EXAMPLE[0]), len(EXAMPLE[0]))
        random.seed()

        examples = [[EXAMPLE[0][ind] for ind in index[:num_shots]], [EXAMPLE[1][ind] for ind in index[:num_shots]]]
        if if_nl:
            return json.loads(nl2bind_parsed(new_value, examples=examples, model=model))
        else:
            new_value = json.dumps(new_value)
            temp_nl = bind2nl_parsed(new_value, examples=examples, model=model)
            return json.loads(nl2bind_parsed(temp_nl, examples=examples, model=model))
    return new_value



generation_functions = {
    "queryType": set_query_type_value,
    "variables": set_variables_value,
    #"variable": set_variables_value,
    "bgp": set_bgp_value, # change
    "triple": set_triple_value, # change
    "filter": set_filter_value,
    "group": set_pattern_value,
    "optional": set_pattern_value,
    "minus": set_pattern_value,
    "order": set_order_value,
    #"orderItem": set_order_value,
    "bind": set_bind_value,
    "select": set_where_value,
    "ask": set_where_value,
    #"patterns": set_where_value,
    "limit": set_limit_value,
    "offset": set_offset_value,
    "groupBy": set_group_by_value,
    #"groupByItem": set_group_by_item_value,
    "distinct": set_distinct_value,
    "union": set_union_value,
    #"unionItem": set_union_item_value,
}

exclude_types = ["variable","orderItem","groupByItem", "unionItem"]

def revise_query_by_path(query, paths, prefix, new_value, if_llm = False, if_nl = True, model = "gpt-4-turbo"):
    path = paths[prefix][0]
    part_type = classify_content_type(prefix, paths)
    current = query
    print("feed paths!!!!!!",current)
    for key in path[:-1]:
        current = current[key]
    #print(current)
    print("current paths!!!!!!",current)
    generation_func = generation_functions.get(part_type)
    if generation_func:
        new_res = generation_func(new_value, if_llm = if_llm, if_nl = if_nl, model= model)
        current[path[-1]] = new_res
    else:
        #current[path[-1]] = new_value
        print("skip " + part_type)
        
def classify_content_type(prefix, paths):
    return paths[prefix][1]

def get_query_part(query, path):
    current = query
    for key in path:
        #print(key, current)
        current = current[key]
    return current



def provide_revision_instructions(content_type):
    instructions = {
        "queryType": "To revise the query type, provide a new type such as 'SELECT', 'ASK', etc.",
        "variables": "To revise the variables, provide a list of new variables.",
        "variable": "To revise a variable, provide the new variable details including any aggregation and distinct attributes.",
        "bgp": "To revise the BGP, provide the new basic graph patterns.",
        "triple": "To revise a triple, provide the new subject, predicate, and object.",
        "filter": "To revise the filter, provide the new filter condition.",
        "group": "To revise the group, provide the new grouped patterns.",
        "optional": "To revise the optional patterns, provide the new optional patterns.",
        "minus": "To revise the minus patterns, provide the new minus patterns.",
        "order": "To revise the order, provide the new ordering conditions.",
        "orderItem": "To revise the order item, provide the new expression and whether it's descending.",
        "bind": "To revise the bind, provide the new expression and variable.",
        "select": "To revise the select pattern, provide the new query details.",
        "ask": "To revise the ask pattern, provide the new query details.",
        "patterns": "To revise the patterns, provide the new patterns.",
        "limit": "To revise the limit, provide the new limit value.",
        "offset": "To revise the offset, provide the new offset value."
    }
    return instructions.get(content_type, "No instructions available for this content type.")


# Function to create the path in a new query based on the path from the original query
def create_path_in_new_query(new_parsed_result, path, original_value):
    current = new_parsed_result
    for key in path[:-1]:
        if isinstance(key, int):
            if not isinstance(current, list):
                raise ValueError(f"Expected list at path {path[:-1]}, but found {type(current).__name__}")
            while len(current) <= key:
                current.append({})
            current = current[key]
        else:
            if not isinstance(current, dict):
                raise ValueError(f"Expected dict at path {path[:-1]}, but found {type(current).__name__}")
            if key not in current:
                current[key] = {}
            current = current[key]

    if isinstance(original_value, list):
        if isinstance(path[-1], int):
            if not isinstance(current, list):
                raise ValueError(f"Expected list at path {path[:-1]}, but found {type(current).__name__}")
            while len(current) <= path[-1]:
                current.append([])
            current[path[-1]] = []
        else:
            current[path[-1]] = []
    else:
        if isinstance(path[-1], int):
            if not isinstance(current, list):
                raise ValueError(f"Expected list at path {path[:-1]}, but found {type(current).__name__}")
            while len(current) <= path[-1]:
                current.append({})
            current[path[-1]] = {}
        else:
            current[path[-1]] = {}

def create_dict_from_all_paths(parsed_result, paths_dict, if_llm=False, if_nl=True, model = "gpt-4-turbo"):
    new_parsed_result = {}
    #print(parsed_result)
    for prefix, (path, content_type) in paths_dict.items():
        #pdb.set_trace()
        #print("==============="+ str(path))
        original_value = get_query_part(copy.deepcopy(parsed_result), path)
        # print("=============================")
        # print("start_result!!!!!!!", new_parsed_result)
        # print("content type!!!!!!!", content_type)
        if content_type in exclude_types:
            continue
        # if content_type == 'triple':
        #     break
        create_path_in_new_query(new_parsed_result, path, original_value)
        #print("create_result!!!!!!!", new_parsed_result)

        #value = get_query_part(parsed_result, path)
        if if_llm:

            # print(prefix)
            
            revise_query_by_path(new_parsed_result, paths_dict, prefix, original_value, if_llm=if_llm, if_nl=if_nl, model=model)
            # print(new_parsed_result)
            # print("=============================")

    new_parsed_result['prefixes'] = parsed_result['prefixes']
    new_parsed_result['type'] = parsed_result['type']
    return new_parsed_result

