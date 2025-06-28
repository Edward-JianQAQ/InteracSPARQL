import anthropic
from openai import OpenAI
import sys
import os
from tenacity import retry, stop_after_attempt, wait_fixed
import pdb

client_cl = anthropic.Anthropic(
    # defaults to os.environ.get("ANTHROPIC_API_KEY")
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
)

# pdb.set_trace()  
client = OpenAI(
    # This is the default and can be omitted
    api_key=os.environ.get("OPENAI_API_KEY"),
)


# Set OpenAI's API key and API base to use vLLM's API server.
openai_api_key = "EMPTY"
# openai_api_base = "http://localhost:5000/v1"
openai_api_base = "http://localhost:4999/v1"

client_open = OpenAI(
    api_key=openai_api_key,
    base_url=openai_api_base,
)




def extract_system_prompt_and_clean_message(message):
    """
    Extracts the system prompt content from a message and returns
    the cleaned message without the system prompt.

    Args:
        message (list): A list of dictionaries with "role" and "content".

    Returns:
        tuple: A tuple containing the system prompt (str) and the cleaned message (list).
    """
    system_prompt = None
    cleaned_message = []

    for msg in message:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        else:
            cleaned_message.append(msg)
    
    return system_prompt, cleaned_message

def llm_call(llm_name, model_version, msg, cfg):
    if cfg["max_tokens"] == -1:
        cfg["max_tokens"] = None

    if llm_name == "Claude":

        system_prompt, cleaned_message = extract_system_prompt_and_clean_message(msg)
        

        if cfg["max_tokens"] is None:
            #print("2222222222222")

            message = client_cl.messages.create(
                model=model_version,
                #system="I want to make a benchmark that measures how LLM can understand the topology of graph given some context of the graph, like medical or social.",
                system=system_prompt,
                temperature=cfg["temperature"],
                messages=cleaned_message
            )

            
        else:
            #print("havei there!!!!!!!!!!!!!!!!!")
            message = client_cl.messages.create(
                model=model_version,
                #system="I want to make a benchmark that measures how LLM can understand the topology of graph given some context of the graph, like medical or social.",
                system=system_prompt,
                max_tokens=cfg["max_tokens"],
                temperature=cfg["temperature"],
                messages=cleaned_message
            )


        output = message.content[0].text


    elif llm_name == "GPT4o" or llm_name == "GPT4o-mini":

        if cfg["response_format_json"]:
            message = client.chat.completions.create(
                model=model_version,
                messages=msg,
                max_tokens=cfg["max_tokens"],
                temperature= cfg["temperature"],
                response_format={ "type": "json_object"}
            )
        else:
            message = client.chat.completions.create(
                model=model_version,
                messages=msg,
                max_tokens=cfg["max_tokens"],
                temperature= cfg["temperature"]
            )

        output = message.choices[0].message.content
    
    # model version:
    # "Qwen/Qwen2.5-14B-Instruct"
    # "Qwen/Qwen2.5-32B-Instruct"
    elif llm_name == "Qwen2.5":
        if cfg["response_format_json"]:
            chat_response = client_open.chat.completions.create(
                model=model_version,
                messages=msg,
                max_tokens=cfg["max_tokens"],
                temperature=cfg["temperature"],
                response_format={ "type": "json_object"}
            )
        else:
            chat_response = client_open.chat.completions.create(
                model=model_version,
                messages=msg,
                max_tokens=cfg["max_tokens"],
                temperature=cfg["temperature"]
            )

        output = chat_response.choices[0].message.content


    return output


def make_retry_decorator(max_attempts, wait_seconds):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_fixed(wait_seconds),
        reraise=True
    )
