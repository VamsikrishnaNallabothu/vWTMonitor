import json
import yaml
import os
# Import LLM SDKs as needed
try:
    import openai
except ImportError:
    openai = None
try:
    import google.generativeai as genai
except ImportError:
    genai = None
try:
    import anthropic
except ImportError:
    anthropic = None
# Ollama can be called via HTTP API or local client

ENHANCED_INDEX_PATH = os.path.join(os.path.dirname(__file__), 'enhanced_function_index.json')

class ParamFiller:
    """
    Fills in parameters for function calls using an LLM and the current SUT-aware function index.
    Builds a context-rich prompt for the LLM, including docstrings, examples, and call graph info.
    Used after intent parsing to resolve parameters for each action.
    """
    def __init__(self, config):
        """
        Initialize the ParamFiller with config and LLM provider.
        Loads the SUT-aware function index and sets up the LLM API keys.
        """
        self.config = config
        self.provider = config['llm']['provider']
        self.model = config['llm']['model']
        if self.provider == 'openai' and openai:
            openai.api_key = config['llm']['openai_api_key']
        elif self.provider == 'google' and genai:
            genai.configure(api_key=config['llm']['google_api_key'])
        elif self.provider == 'anthropic' and anthropic:
            self.anthropic_client = anthropic.Anthropic(api_key=config['llm']['anthropic_api_key'])
        # Ollama: no setup needed for local
        if os.path.exists(ENHANCED_INDEX_PATH):
            with open(ENHANCED_INDEX_PATH) as f:
                self.function_index = json.load(f)
        else:
            self.function_index = {}

    def build_llm_prompt(self, func_name, func_info, user_input, function_index):
        """
        Build a prompt for the LLM to fill in parameters for a given function.
        Includes docstring, arguments, and a mapping of available functions/classes for the current SUT(s).
        """
        doc = func_info.get('doc', '')
        args = func_info.get('args', [])
        func_blocks = []
        for name, info in function_index.items():
            block = f"{name}:\n  - Doc: {info.get('doc', '')}\n  - Args: {', '.join(info.get('args', []))}"
            if info.get('examples'):
                block += f"\n  - Example: {info['examples'][0]}"
            if info.get('called_in'):
                call = info['called_in'][0]
                block += f"\n  - Called in: {call.get('caller', '')} (with args: {', '.join(call.get('args', []))})"
            func_blocks.append(block)
        func_str = "\n\n".join(func_blocks[:10])  # Limit for prompt size
        prompt = f"""
Given the function '{func_name}' with docstring: {doc}\nArguments: {args}\nHere are some available functions and their usage patterns:\n\n{func_str}\n\nUser request: {user_input}\nIf any argument is missing, suggest a function from this list that can provide it.\nOutput a JSON dict of parameter values. If a param needs another function, output as {{'param': {{'call': 'other_func', 'params': {{...}} }} }}.\n"""
        return prompt

    def fill_params(self, func_name: str, func_info, user_input, function_index):
        """
        Use the LLM to fill in parameters for the given function, using the SUT-aware function index.
        Returns a dict of parameter values, possibly including calls to other functions for missing params.
        """
        prompt = self.build_llm_prompt(func_name, func_info, user_input, function_index)
        if self.provider == 'openai' and openai:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[{"role": "system", "content": prompt}],
                temperature=0.2,
                max_tokens=512
            )
            content = response['choices'][0]['message']['content']
        elif self.provider == 'google' and genai:
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(prompt)
            content = response.text
        elif self.provider == 'anthropic' and anthropic:
            response = self.anthropic_client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.content[0].text
        elif self.provider == 'ollama':
            import requests
            r = requests.post("http://localhost:11434/api/generate", json={"model": self.model, "prompt": prompt})
            content = r.json().get('response', '')
        else:
            raise NotImplementedError(f"Provider {self.provider} not supported or SDK not installed.")
        try:
            params = json.loads(content)
        except Exception:
            params = {}
        return params 