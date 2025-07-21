# Training the NLPCodeGen4vWT Model

## Approaches

1. **Retrieval-Augmented Generation (RAG):**
   - Index your codebase (function names, docstrings, signatures).
   - At inference, retrieve relevant functions for the user query and provide them as context to the LLM.

2. **Fine-tuning:**
   - Collect (user query, function mapping, parameter mapping) pairs.
   - Fine-tune an open-source LLM (e.g., CodeLlama, StarCoder) on these pairs.
   - For OpenAI/Gemini, use prompt engineering and RAG (fine-tuning is not always available).

## Data Preparation

- Extract all function signatures and docstrings from `vwt_monitor` (see `function_indexer.py`).
- Collect user queries and annotate them with the correct function and parameter mapping.
- Format as JSONL or CSV for training.

## Example Training Data

```
{
  "user_query": "Apply URL blocking policy to block URL- test_domain.com and verify the traffic is blocked for this url",
  "actions": [
    {"function": "apply_url_policy", "params": {"org_id": {"call": "get_org_id", "params": {"url": "test_domain.com"}}, "policy_config": {"block_url": "test_domain.com"}}},
    {"function": "send_test_traffic", "params": {"url": "test_domain.com"}},
    {"function": "collect_metrics", "params": {}}
  ]
}
```

## Training

- For RAG: Use LlamaIndex or LangChain retriever with your function index.
- For fine-tuning: Use HuggingFace Trainer or OpenAI fine-tuning API (if available).

## Evaluation

- Test with held-out user queries.
- Measure accuracy of function and parameter mapping.

## Improving the System

- Add more annotated examples.
- Add more detailed docstrings to your codebase.
- Use user feedback to iteratively improve mappings. 