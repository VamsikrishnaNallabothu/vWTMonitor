# NLPCodeGen4vWT

A prototype for a code-aware NLP system that maps user intent to workflows using the vWTMonitor codebase. It leverages LLMs (Gemini/CodeLlama/OpenAI/Anthropic/Ollama), Python AST, dynamic code analysis, and orchestration frameworks (LangChain/LangGraph) to:

- Parse user requests (e.g., "Apply URL blocking policy to block URL- test_domain.com and verify the traffic is blocked for this url")
- Map intent to code functions and parameters using real code/test usage and capabilities
- Generate and execute test workflows with robust script templates
- Collect and report results
- Support follow-up questions (e.g., about metrics)
- Learn interactively how to resolve missing parameters

---

## **Setup & Usage**

### 1. **Index your codebase**

**A. Dynamic Analysis (runtime info, capabilities, types):**
```bash
python dynamic_code_analyzer.py
```
- Produces `dynamic_knowledge_base.json` with runtime signatures, docstrings, and capabilities.

**B. Enhanced Indexing (merges static and dynamic info):**
```bash
python enhanced_function_indexer.py
```
- Produces `enhanced_function_index.json` (used for all LLM prompting and script generation).

### 2. **Start the CLI or Web UI**

- **CLI:**
  ```bash
  python main.py
  ```
- **Web UI:**
  ```bash
  python webui.py
  ```

### 3. **Enter your test request**
- Example: `Apply URL blocking policy to block URL- test_domain.com and verify the traffic is blocked for this url`

### 4. **System Workflow**
- **Intent Parsing:** LLM uses a rich prompt (docstrings, examples, capabilities, call graph) to map intent to function(s).
- **Parameter Filling:** LLM fills parameters, with mapping/scoring layer to validate/correct.
- **Stub Generation:** Produces a full, production-ready test script, using templates and real usage patterns.
- **Execution:** Runs the script and reports results.
- **Interactive Training:** If a parameter is missing, the system learns how to fetch it for future runs.

---

## **Workflow Summary**

1. **Dynamic + Static Indexing:**
   - Combines AST and runtime inspection for the most complete function/class index.
   - Tags functions/classes with capabilities (e.g., 'traffic', 'metrics', 'ssh').
2. **LLM-Driven Intent Mapping:**
   - Uses real code/test examples, call graphs, and capabilities for accurate mapping.
3. **Parameter Mapping/Scoring:**
   - Validates and corrects LLM parameter mappings for robustness.
4. **Script Generation Templates:**
   - Generates full, production-quality test scripts with logging, error handling, and reporting.
5. **Modular Orchestration:**
   - All steps are modular and extensible via LangGraph.

---

## **Sample Run**

### **CLI Example**
```
$ python main.py
NLPCodeGen4vWT CLI - Type your test request. Type 'exit' or 'quit' to stop. Type 'metrics' to see collected metrics. Type 'training on' or 'training off' to toggle training mode.

>>> Apply URL blocking policy to block URL- test_domain.com and verify the traffic is blocked for this url

--- Workflow Actions ---
 [
  {
    "function": "apply_url_policy",
    "params": {
      "org_id": {"call": "get_org_id", "params": {"url": "test_domain.com"}},
      "policy_config": {"block_url": "test_domain.com"}
    }
  },
  {
    "function": "send_test_traffic",
    "params": {"url": "test_domain.com"}
  },
  {
    "function": "collect_metrics",
    "params": {}
  }
]

--- Generated Code ---
from vwt_monitor import *
import json
org_id = get_org_id(url="test_domain.com")
policy_config = {"block_url": "test_domain.com"}
result_apply_url_policy = apply_url_policy(org_id=org_id, policy_config=policy_config)
url = "test_domain.com"
result_send_test_traffic = send_test_traffic(url=url)
result_collect_metrics = collect_metrics()
print('RESULT_apply_url_policy:', json.dumps(result_apply_url_policy, default=str))
print('RESULT_send_test_traffic:', json.dumps(result_send_test_traffic, default=str))
print('RESULT_collect_metrics:', json.dumps(result_collect_metrics, default=str))

--- Execution Result ---
RESULT_apply_url_policy: {"status": "success", "org_id": "org-123", "policy": {"block_url": "test_domain.com"}}
RESULT_send_test_traffic: {"url": "test_domain.com", "traffic_blocked": true}
RESULT_collect_metrics: {"packet_drops": 42, "blocked_urls": ["test_domain.com"], "timestamp": "2024-06-10T12:34:56"}
```

### **Web UI Example**
- Visit [http://localhost:5000/](http://localhost:5000/)
- Enter your request in the input box.
- The system will display:
  - Workflow Actions (parsed intent)
  - Generated Code (Python code for the workflow)
  - Execution Result (output/result of the workflow)
- If a parameter is missing, a form will appear for you to provide it (and optionally train the system for future runs).

---

## **Improvements and Features**
- Combines static and dynamic code analysis for the most complete function/class index.
- Tags functions/classes with capabilities for smarter intent mapping and chaining.
- Validates and corrects LLM parameter mappings for robustness.
- Generates full, production-quality test scripts with logging, error handling, and reporting.
- Keeps all orchestration modular and extensible via LangGraph.
- Interactive training for parameter resolution.

---

## **Troubleshooting**
- If you add new modules or functions, rerun both the dynamic analyzer and enhanced indexer.
- Make sure your LLM API keys are set in `config.yaml`.
- For best results, keep your codebase and tests well-documented with clear docstrings and examples. 