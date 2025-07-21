import json
import os

def find_matching_test_function(intent_action, enhanced_index):
    """
    Find a matching test function for the given intent action in the provided function index.
    Returns the test function name and its arguments if found, otherwise (None, None, None).
    """
    func = intent_action['function']
    info = enhanced_index.get(func, {})
    if info.get('called_in'):
        for call in info['called_in']:
            if call.get('caller', '').startswith('test_'):
                return call['caller'], call['args'], call['kwargs']
    return None, None, None

def generate_stub_script(actions, function_index=None):
    """
    Generate a Python stub/test script for the given actions using the provided SUT-aware function index.
    Prefers calling an existing test function if available, otherwise chains functions as seen in real code/tests.
    If function_index is None, falls back to the default index (for backward compatibility).
    Returns the script as a string.
    """
    if function_index is None:
        ENHANCED_INDEX_PATH = os.path.join(os.path.dirname(__file__), 'enhanced_function_index.json')
        with open(ENHANCED_INDEX_PATH) as f:
            function_index = json.load(f)
    lines = ["from vwt_monitor import *"]
    for action in actions:
        func = action['function']
        params = action['params']
        # Prefer existing test function if available
        test_func, test_args, test_kwargs = find_matching_test_function(action, function_index)
        if test_func:
            arg_str = ', '.join(test_args) if test_args else ''
            lines.append(f"{test_func}({arg_str})")
            continue
        info = function_index.get(func, {})
        # Use example or called_in for argument patterns if available
        if info.get('examples'):
            lines.append(info['examples'][0])
        else:
            param_str = ', '.join(f'{k}={repr(v)}' for k, v in params.items())
            lines.append(f"{func}({param_str})")
    return "\n".join(lines) 