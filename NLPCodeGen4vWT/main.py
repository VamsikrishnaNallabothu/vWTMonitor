import sys
import yaml
import json
import os
from langgraph_workflow import build_langgraph_workflow
from metrics_memory import get_all_metrics

SUTS = ['ZIA', 'ZPA', 'ZTGW', 'SMCA']
SHARED_INDEX = 'enhanced_function_index_shared.json'

# Utility to load and merge SUT indexes
def load_sut_indexes(selected_suts):
    indexes = []
    for sut in selected_suts:
        path = f"enhanced_function_index_{sut}.json"
        if os.path.exists(path):
            with open(path) as f:
                indexes.append(json.load(f))
    if os.path.exists(SHARED_INDEX):
        with open(SHARED_INDEX) as f:
            indexes.append(json.load(f))
    merged = {}
    for idx in indexes:
        merged.update(idx)
    return merged

def cli_user_prompt(param, func_name, extra_context):
    return input(f"Please provide a value for '{param}': ")

def main():
    print("Available SUTs:", ', '.join(SUTS))
    selected = input("Select SUT(s) to test (comma-separated, e.g., ZIA,ZTGW): ").strip().split(',')
    selected = [s.strip().upper() for s in selected if s.strip().upper() in SUTS]
    if not selected:
        print("No valid SUT selected. Exiting.")
        return
    function_index = load_sut_indexes(selected)
    print(f"Loaded function index for SUT(s): {', '.join(selected)}")
    print("NLPCodeGen4vWT CLI - Type your test request. Type 'exit' or 'quit' to stop. Type 'metrics' to see collected metrics. Type 'training on' or 'training off' to toggle training mode.")
    training_mode = False
    while True:
        user_input = input("\n>>> ").strip()
        if user_input.lower() in ('exit', 'quit'):
            print("Exiting.")
            break
        if user_input.lower() == 'metrics':
            print("Collected metrics from previous runs:")
            print(get_all_metrics())
            continue
        if user_input.lower() == 'training on':
            training_mode = True
            print("Training mode enabled.")
            continue
        if user_input.lower() == 'training off':
            training_mode = False
            print("Training mode disabled.")
            continue
        if not user_input:
            continue
        g, state = build_langgraph_workflow(
            'config.yaml',
            user_input,
            user_prompt_fn=cli_user_prompt,
            training_mode=training_mode,
            function_index=function_index
        )
        result_state = g.run(state)
        print("\n--- Workflow Actions ---\n", result_state['final_result']['actions'])
        print("\n--- Generated Code ---\n", result_state['final_result']['code'])
        print("\n--- Execution Result ---\n", result_state['final_result']['result'])

if __name__ == "__main__":
    main() 