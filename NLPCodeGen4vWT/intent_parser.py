import os
import json
from typing import List, Dict, Any
import yaml

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
import requests
# Ollama can be called via HTTP API or local client

ENHANCED_INDEX_PATH = os.path.join(os.path.dirname(__file__), 'enhanced_function_index.json')

class IntentParser:
    """
    Parses user natural language requests into structured actions (function calls + parameters)
    using an LLM and a SUT-aware, contextually restricted function index.
    The prompt includes a 'Python Functions and Function Calls Mapping' section
    to ensure the LLM only answers from the current SUT context.
    """
    def __init__(self, config_path: str, function_index_path: str = None):
        """
        Initialize the IntentParser with config and function index.
        Loads the SUT-aware function index and sets up the LLM provider and API keys.
        """
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        # Always use enhanced index if available
        if os.path.exists(ENHANCED_INDEX_PATH):
            with open(ENHANCED_INDEX_PATH) as f:
                self.function_index = json.load(f)
        else:
            with open(function_index_path) as f:
                self.function_index = json.load(f)
        self.provider = self.config['llm']['provider']
        self.model = self.config['llm']['model']
        self.base_url = self.config['llm'].get('base_url')
        # Set up API keys and clients
        if self.provider == 'openai' and openai:
            openai.api_key = self.config['llm']['openai_api_key']
            if self.base_url:
                openai.base_url = self.base_url
        elif self.provider == 'google' and genai:
            genai.configure(api_key=self.config['llm']['google_api_key'])
        elif self.provider == 'anthropic' and anthropic:
            self.anthropic_client = anthropic.Anthropic(api_key=self.config['llm']['anthropic_api_key'])
        # Ollama: no setup needed for local, but use base_url if provided

    def build_llm_prompt(self, user_input: str) -> str:
        """
        Build a prompt for the LLM that includes only the functions/classes
        from the current SUT-aware function index. The prompt explicitly
        includes a 'Python Functions and Function Calls Mapping' section.
        """
        func_blocks = []
        for name, info in self.function_index.items():
            block = f"{name}:\n  - Doc: {info.get('doc', '')}\n  - Args: {', '.join(info.get('args', []))}"
            if info.get('examples'):
                block += f"\n  - Example: {info['examples'][0]}"
            if info.get('called_in'):
                call = info['called_in'][0]
                block += f"\n  - Called in: {call.get('caller', '')} (with args: {', '.join(call.get('args', []))})"
            func_blocks.append(block)
        func_str = "\n\n".join(func_blocks[:10])  # Limit for prompt size
        prompt = f"""
You are an assistant that maps user requests to Python function calls.

Python Functions and Function Calls Mapping:
{func_str}

User request: {user_input}

Output a JSON list of actions, each with 'function' and 'params'.
"""
        return prompt

    def parse_intent(self, user_input: str) -> List[Dict[str, Any]]:
        """
        Parse a user request using the current SUT-aware function index and an LLM.
        Builds a prompt that includes only the functions/classes relevant to the selected SUT(s).
        Calls the LLM and returns a list of actions (function calls + parameters) as parsed from the LLM's output.
        """
        prompt = self.build_llm_prompt(user_input)
        if self.provider == 'openai' and openai:
            kwargs = dict(
                model=self.model,
                messages=[{"role": "system", "content": prompt}],
                temperature=0.2,
                max_tokens=512
            )
            if self.base_url:
                kwargs['base_url'] = self.base_url
            response = openai.ChatCompletion.create(**kwargs)
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
            base_url = self.base_url or "http://localhost:11434"
            r = requests.post(f"{base_url}/api/generate", json={"model": self.model, "prompt": prompt})
            content = r.json().get('response', '')
        else:
            raise NotImplementedError(f"Provider {self.provider} not supported or SDK not installed.")
        try:
            actions = json.loads(content)
        except Exception:
            actions = []
        return actions 