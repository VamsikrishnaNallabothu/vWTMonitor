from langgraph import Graph, Node, Edge
from intent_parser import IntentParser
from param_filler import ParamFiller
from param_resolver import ParamResolver
import yaml
import json
import tempfile
import subprocess

def intent_parsing_node(state):
    user_input = state['user_input']
    parser = state['intent_parser']
    actions = parser.parse_intent(user_input)
    state['actions'] = actions
    return state

def param_filling_node(state):
    actions = state['actions']
    param_filler = state['param_filler']
    function_index = state['function_index']
    user_input = state['user_input']
    filled_params = []
    for action in actions:
        func = action['function']
        func_info = function_index.get(func, {})
        params = param_filler.fill_params(func, func_info, user_input, function_index)
        filled_params.append({'function': func, 'params': params})
    state['filled_params'] = filled_params
    return state

def param_resolution_node(state):
    filled_params = state['filled_params']
    param_resolver = state['param_resolver']
    resolved_params = []
    missing_param = None
    for item in filled_params:
        func = item['function']
        params = item['params']
        resolved = {}
        for k, v in params.items():
            if isinstance(v, dict) and 'call' in v:
                resolved[k] = v
            else:
                val = param_resolver.resolve(k, func_name=func, extra_context={'user_input': state['user_input']})
                if val is None:
                    missing_param = k
                    break
                resolved[k] = val
        resolved_params.append({'function': func, 'params': resolved})
        if missing_param:
            break
    state['resolved_params'] = resolved_params
    state['missing_param'] = missing_param
    return state

def user_prompt_node(state):
    param = state['missing_param']
    if state.get('user_prompt_fn'):
        value = state['user_prompt_fn'](param, None, None)
        state['param_resolver'].web_context['pending_param'] = None
        state['param_resolver'].web_context['last_param_value'] = value
    else:
        state['param_resolver'].web_context['pending_param'] = param
    return state

def code_generation_node(state):
    resolved_params = state['resolved_params']
    code_lines = ["from vwt_monitor import *", "import json"]
    for item in resolved_params:
        func = item['function']
        params = item['params']
        param_assignments = [f"{k} = {json.dumps(v)}" for k, v in params.items()]
        param_str = ', '.join([f"{k}={k}" for k in params.keys()])
        code_lines.extend(param_assignments)
        code_lines.append(f"result_{func} = {func}({param_str})")
        code_lines.append(f"print('RESULT_{func}:', json.dumps(result_{func}, default=str))")
    state['workflow_code'] = '\n'.join(code_lines)
    return state

def execution_node(state):
    code = state['workflow_code']
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_path = f.name
    try:
        output = subprocess.check_output(['python3', temp_path], stderr=subprocess.STDOUT, timeout=120)
        state['execution_result'] = output.decode()
    except subprocess.CalledProcessError as e:
        state['execution_result'] = e.output.decode()
    finally:
        import os
        os.remove(temp_path)
    return state

def result_reporting_node(state):
    state['final_result'] = {
        'actions': state.get('actions'),
        'code': state.get('workflow_code'),
        'result': state.get('execution_result')
    }
    return state

def build_langgraph_workflow(config_path, user_input, user_prompt_fn=None, web_context=None, training_mode=False, function_index=None):
    with open(config_path) as f:
        config = yaml.safe_load(f)
    if function_index is None:
        from intent_parser import ENHANCED_INDEX_PATH
        with open(ENHANCED_INDEX_PATH) as f:
            function_index = json.load(f)
    state = {
        'user_input': user_input,
        'intent_parser': IntentParser(config_path, function_index_path=None),
        'param_filler': ParamFiller(config),
        'param_resolver': ParamResolver(config, training_mode=training_mode, user_prompt_fn=user_prompt_fn, web_context=web_context),
        'function_index': function_index,
        'user_prompt_fn': user_prompt_fn
    }
    # Patch intent_parser and param_filler to use the SUT-specific function_index
    state['intent_parser'].function_index = function_index
    state['param_filler'].function_index = function_index
    g = Graph()
    g.add_node(Node('intent_parsing', intent_parsing_node))
    g.add_node(Node('param_filling', param_filling_node))
    g.add_node(Node('param_resolution', param_resolution_node))
    g.add_node(Node('user_prompt', user_prompt_node))
    g.add_node(Node('code_generation', code_generation_node))
    g.add_node(Node('execution', execution_node))
    g.add_node(Node('result_reporting', result_reporting_node))
    g.add_edge(Edge('intent_parsing', 'param_filling'))
    g.add_edge(Edge('param_filling', 'param_resolution'))
    def param_resolution_branch(state):
        return 'user_prompt' if state.get('missing_param') else 'code_generation'
    g.add_edge(Edge('param_resolution', param_resolution_branch))
    g.add_edge(Edge('user_prompt', 'param_resolution'))
    g.add_edge(Edge('code_generation', 'execution'))
    g.add_edge(Edge('execution', 'result_reporting'))
    return g, state

def cli_user_prompt(param, func_name, extra_context):
    return input(f"Please provide a value for '{param}': ")

def build_llm_prompt(user_input, enhanced_index):
    func_blocks = []
    for name, info in enhanced_index.items():
        block = f"{name}:\n  - Doc: {info.get('doc', '')}\n  - Args: {', '.join(info.get('args', []))}"
        if info.get('examples'):
            block += f"\n  - Example: {info['examples'][0]}"
        if info.get('called_in'):
            call = info['called_in'][0]
            block += f"\n  - Called in: {call.get('caller', '')} (with args: {', '.join(call.get('args', []))})"
        func_blocks.append(block)
    func_str = "\n\n".join(func_blocks[:10])  # Limit for prompt size
    prompt = f"""You are an assistant that maps user requests to Python function calls.
Here are some available functions and their usage patterns:

{func_str}

User request: {user_input}

Output a JSON list of actions, each with 'function' and 'params'.
"""
    return prompt

def generate_stub_script(actions, enhanced_index):
    lines = ["from vwt_monitor import *"]
    for action in actions:
        func = action['function']
        params = action['params']
        info = enhanced_index.get(func, {})
        # Use example or called_in for argument patterns if available
        if info.get('examples'):
            lines.append(info['examples'][0])
        else:
            param_str = ', '.join(f'{k}={repr(v)}' for k, v in params.items())
            lines.append(f"{func}({param_str})")
    return "\n".join(lines)

def find_matching_test_function(intent_action, enhanced_index):
    func = intent_action['function']
    info = enhanced_index.get(func, {})
    if info.get('called_in'):
        for call in info['called_in']:
            if call.get('caller', '').startswith('test_'):
                return call['caller'], call['args'], call['kwargs']
    return None, None, None

g, state = build_langgraph_workflow(
    'config.yaml',
    'Apply URL blocking policy to block URL- test_domain.com',
    user_prompt_fn=cli_user_prompt,
    training_mode=True
)
result_state = g.run(state)
print(result_state['final_result']) 