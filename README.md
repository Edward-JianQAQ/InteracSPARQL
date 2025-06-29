# InteracSPARQL

Official implementation for **InteracSPARQL: an Interactive Tool for SPARQL Query
Refinement Using Natural Language Explanations**

---

## Appendix

For more details on the system architecture, prompt templates, NLE format and evaluation protocol, please refer to the appendix document available in the repository:

📄 [`appendix.pdf`](./appendix.pdf)

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Hosting Qwen with vLLM](#hosting-qwen-with-vllm)
- [Configuration](#configuration)
- [Running Experiments](#running-experiments)
- [Logging & Results](#logging--results)
- [License](#license)

---

## Features

- **Interactive Query Construction**\
  Guide users step-by-step through SPARQL authoring, with continuous, targeted feedback.
- **Natural Language Explanations**\
  Generate clear, section-by-section NLEs (Natural Language Explanations) for any SPARQL query.
- **Deterministic Rule-Based Core**\
  Derive structured explanations from the query’s AST for accuracy and consistency.
- **LLM-Driven Refinement**\
  Polish explanations and refine queries via GPT-4o, Claude 3.5 Sonnet, or other LLMs.
- **Expert-in-the-Loop & Self-Refinement**\
  Support both human oversight and automated LLM “self-refinement” modes.
- **Real-Time Corrections**\
  Fix mislabeled entities, ambiguous filters, or incomplete clauses on the fly.
- **Educational Mode**\
  Serve as an interactive learning guide—ideal for newcomers to SPARQL.
- **Configurable & Extensible**\
  All behaviors and model pairings defined via YAML so you can plug in new datasets or LLMs.

---

## Prerequisites

- **Node.js** (for `sparqljs`)
- **Conda** (to manage Python environments)
- **Python 3.10**
- API keys for any closed-source models you wish to use:

```bash
export OPENAI_API_KEY="<your OpenAI key>"
export ANTHROPIC_API_KEY="<your Anthropic key>"
```

---

## Installation

1. **Install**

```bash
npm install sparqljs
```

2. **Create & activate Conda environment**

```bash
conda create -n interacSparql python=3.10 -y
conda activate interacSparql
```

3. **Install Python requirements**

```bash
pip install -r requirements.txt
```

---

## Hosting Qwen with vLLM

You can host Qwen locally using the vLLM backend. Two example launch scripts are provided in the `vllm/` directory:

1. **Launch Qwen-2.5-32b with custom configuration**

```bash
bash vllm/qwen2_5_32b.bash
```

2. **Launch Qwen-2.5-14b with custom configuration**

```bash
bash vllm/qwen2_5_14b.bash
```

---

## Configuration

All experiment settings live in the `configs/` directory.\
Each dataset + LLM pairing has its own YAML file. For example:

```bash
configs/qald10/gpt4o/self_ref.yaml
```

---

## Running Experiments

To launch a self-refinement run:

```bash
python exp_sum.py \
  --config configs/qald10/gpt4o/self_ref.yaml \
  --task_id 1
```

- `--config` : Path to your YAML config
- `--task_id`: Numeric ID for your experiment case (you can just keep it as 1)

---

## Logging & Results

- **Logs** → `log/`
- **Evaluation results** → `eval_results/`

Both directories are created automatically if they don’t exist.

---

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.
