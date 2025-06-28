vllm serve Qwen/Qwen2.5-32B-Instruct --port 4999 --max-num-seqs 1 --max_num_batched_tokens 22000 --max_model_len 22000 --gpu_memory_utilization 0.95 --dtype bfloat16
