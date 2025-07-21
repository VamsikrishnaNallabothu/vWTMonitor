import inspect
import importlib
import json
import os

def extract_capabilities(docstring, func_name):
    """
    Extract capability tags (e.g., 'traffic', 'metrics', 'ssh') from a function's docstring and name.
    Used to help with intent mapping and function selection.
    """
    capabilities = []
    keywords = {
        'traffic': ['traffic', 'packet', 'http', 'tcp', 'udp', 'dns', 'send', 'generate'],
        'metrics': ['metric', 'collect', 'monitor', 'measure', 'cpu', 'memory', 'network'],
        'ssh': ['ssh', 'connect', 'remote', 'execute'],
        'scale': ['scale', 'autoscaling', 'instance', 'asg'],
        'test': ['test', 'validate', 'verify', 'check']
    }
    text = (docstring or "") + " " + func_name.lower()
    for category, keys in keywords.items():
        if any(k in text for k in keys):
            capabilities.append(category)
    return capabilities

def analyze_modules(modules, output_path):
    """
    Analyze the given list of Python modules using inspect/importlib to extract function/class info,
    docstrings, parameters, return types, and capabilities. Writes the result to output_path as JSON.
    Used as part of the dynamic code analysis step in the indexing workflow.
    """
    functions_db = {}
    classes_db = {}
    for module_name in modules:
        try:
            module = importlib.import_module(module_name)
            for name, obj in inspect.getmembers(module):
                if inspect.isfunction(obj) and obj.__module__ == module_name:
                    sig = inspect.signature(obj)
                    params = {k: str(v.annotation) if v.annotation != inspect.Parameter.empty else 'Any'
                              for k, v in sig.parameters.items()}
                    doc = obj.__doc__ or ""
                    capabilities = extract_capabilities(doc, name)
                    functions_db[name] = {
                        'name': name,
                        'module': module_name,
                        'parameters': params,
                        'docstring': doc,
                        'return_type': str(sig.return_annotation) if sig.return_annotation != inspect.Signature.empty else 'Any',
                        'capabilities': capabilities
                    }
                elif inspect.isclass(obj) and obj.__module__ == module_name:
                    # Optionally add class info
                    pass
        except ImportError as e:
            print(f"Could not import {module_name}: {e}")
    with open(output_path, 'w') as f:
        json.dump({'functions': functions_db, 'classes': classes_db}, f, indent=2)
    print(f"Dynamic knowledge base written to {output_path}")

# Example usage:
if __name__ == "__main__":
    analyze_modules([
        'vwt_monitor.ssh_manager',
        'vwt_monitor.traffic_manager',
        'vwt_monitor.log_capture',
        'vwt_monitor.channel_manager',
        'vwt_monitor.iperf_manager',
    ], 'dynamic_knowledge_base.json') 