import ast
import os
import json
import yaml
import subprocess
from typing import Dict, Any, List
import re

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')
OUTPUT_TEMPLATE = os.path.join(os.path.dirname(__file__), 'enhanced_function_index_{}.json')
DYNAMIC_ANALYZER = os.path.join(os.path.dirname(__file__), 'dynamic_code_analyzer.py')

EXAMPLE_RE = re.compile(r'(?:Example(?: usage)?:\s*)([\s\S]+?)(?:\n\s*\n|$)', re.IGNORECASE)

def extract_examples_from_doc(doc: str) -> List[str]:
    """
    Extract example code snippets from a function's docstring using regex.
    Used to provide real usage context for LLM prompting and stub generation.
    """
    if not doc:
        return []
    return EXAMPLE_RE.findall(doc)

def parse_file(file_path: str, call_graph: Dict[str, Any], func_index: Dict[str, Any], file_tag: str):
    """
    Parse a Python file using AST to extract function definitions, arguments, docstrings, type hints,
    and call relationships. Updates the call graph and function index in place.
    Used as part of the static indexing step for each SUT codebase.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except Exception as e:
            print(f"Failed to parse {file_path}: {e}")
            return
        func_defs = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                args = [a.arg for a in node.args.args]
                doc = ast.get_docstring(node)
                type_hints = [ast.unparse(a.annotation) if a.annotation else None for a in node.args.args]
                func_defs[func_name] = {
                    'args': args,
                    'type_hints': type_hints,
                    'doc': doc,
                    'examples': extract_examples_from_doc(doc),
                    'module': file_tag
                }
                if func_name not in func_index:
                    func_index[func_name] = func_defs[func_name]
                else:
                    func_index[func_name]['examples'].extend(func_defs[func_name]['examples'])
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    callee = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    callee = node.func.attr
                else:
                    continue
                caller = None
                parent = node
                while parent:
                    parent = getattr(parent, 'parent', None)
                    if isinstance(parent, ast.FunctionDef):
                        caller = parent.name
                        break
                arg_strs = [ast.unparse(arg) for arg in node.args]
                kwarg_strs = {kw.arg: ast.unparse(kw.value) for kw in node.keywords}
                call_info = {
                    'file': file_tag,
                    'caller': caller,
                    'args': arg_strs,
                    'kwargs': kwarg_strs
                }
                if callee not in call_graph:
                    call_graph[callee] = []
                call_graph[callee].append(call_info)
                if caller:
                    if caller not in func_index:
                        func_index[caller] = {'calls': []}
                    if 'calls' not in func_index[caller]:
                        func_index[caller]['calls'] = []
                    func_index[caller]['calls'].append({'callee': callee, 'args': arg_strs, 'kwargs': kwarg_strs})

def add_parents(tree):
    """
    Add parent pointers to AST nodes for easier traversal and call graph extraction.
    """
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node

def index_codebase_for_sut(sut, codebase_path, dynamic_kb_path=None):
    """
    Index a single SUT or shared codebase by running AST parsing and merging with dynamic analysis results.
    Outputs an enhanced function index JSON file for the SUT.
    """
    func_index = {}
    call_graph = {}
    seen_files = set()
    for dirpath, _, files in os.walk(codebase_path):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(dirpath, file)
                if file_path in seen_files:
                    continue
                seen_files.add(file_path)
                file_tag = os.path.relpath(file_path, codebase_path).replace(os.sep, '.')[:-3]
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        tree = ast.parse(f.read(), filename=file_path)
                        add_parents(tree)
                    except Exception as e:
                        print(f"Failed to parse {file_path}: {e}")
                        continue
                    parse_file(file_path, call_graph, func_index, file_tag)
    for func, calls in call_graph.items():
        if func not in func_index:
            func_index[func] = {}
        func_index[func]['called_in'] = calls
    # Merge dynamic knowledge base if provided
    if dynamic_kb_path and os.path.exists(dynamic_kb_path):
        with open(dynamic_kb_path) as f:
            dyn_kb = json.load(f)
        for func, info in dyn_kb.get('functions', {}).items():
            if func not in func_index:
                func_index[func] = {}
            func_index[func]['capabilities'] = info.get('capabilities', [])
            func_index[func]['doc'] = info.get('docstring', func_index[func].get('doc', ''))
            func_index[func]['type_hints'] = [info['parameters'].get(arg, 'Any') for arg in func_index[func].get('args', [])]
            func_index[func]['module'] = info.get('module', func_index[func].get('module', ''))
    output_path = OUTPUT_TEMPLATE.format(sut)
    with open(output_path, 'w') as f:
        json.dump(func_index, f, indent=2)
    print(f"Enhanced function index for {sut} written to {output_path} with {len(func_index)} functions.")

def main():
    """
    Main entry point for the enhanced function indexer.
    Reads codebase paths from config.yaml, runs dynamic and static analysis for each SUT,
    and outputs SUT-specific enhanced function indexes.
    """
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    codebases = config.get('codebases', {})
    for sut, path in codebases.items():
        if not os.path.exists(path):
            print(f"Codebase path for {sut} does not exist: {path}")
            continue
        # Run dynamic analyzer for this SUT
        dynamic_kb_path = os.path.join(os.path.dirname(__file__), f'dynamic_knowledge_base_{sut}.json')
        print(f"Running dynamic analyzer for {sut}...")
        subprocess.run(['python', DYNAMIC_ANALYZER, path, dynamic_kb_path], check=False)
        index_codebase_for_sut(sut, path, dynamic_kb_path=dynamic_kb_path)

if __name__ == "__main__":
    main() 