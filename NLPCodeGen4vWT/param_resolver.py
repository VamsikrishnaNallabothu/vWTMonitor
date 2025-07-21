import json
import os

PARAM_MAP_PATH = os.path.join(os.path.dirname(__file__), 'param_source_map.json')

class ParamResolver:
    """
    Resolves parameters for function calls by checking config, a learned parameter map, or prompting the user.
    Supports interactive training to remember how to fetch parameters in the future.
    Used after parameter filling to ensure all required parameters are available for code generation.
    """
    def __init__(self, config, param_source_map_path=PARAM_MAP_PATH, training_mode=False, user_prompt_fn=None, web_context=None):
        """
        Initialize the ParamResolver with config, parameter map, and training/user prompt options.
        """
        self.config = config
        self.param_source_map_path = param_source_map_path
        self.training_mode = training_mode
        self.user_prompt_fn = user_prompt_fn  # function to call for user input (CLI or web)
        self.web_context = web_context  # for web UI, a dict to store pending params
        self._load_param_map()

    def _load_param_map(self):
        """
        Load the parameter source map from disk, or initialize an empty map if not present.
        """
        if os.path.exists(self.param_source_map_path):
            with open(self.param_source_map_path) as f:
                self.param_map = json.load(f)
        else:
            self.param_map = {}

    def _save_param_map(self):
        """
        Save the parameter source map to disk.
        """
        with open(self.param_source_map_path, 'w') as f:
            json.dump(self.param_map, f, indent=2)

    def resolve(self, param, func_name=None, extra_context=None):
        """
        Resolve a parameter by checking config, the parameter map, or prompting the user.
        In training mode, learns how to fetch missing parameters for future runs.
        Returns the resolved value or None if unresolved (for web UI interaction).
        """
        # 1. Try config
        if param in self.config:
            return self.config[param]
        # 2. Try param map (function provider)
        if param in self.param_map:
            entry = self.param_map[param]
            if entry['source'] == 'function':
                provider_func = entry['function']
                provider_args = entry.get('args', {})
                # Here, you would call the function dynamically (stubbed for now)
                return f"CALL({provider_func}, {provider_args})"
            elif entry['source'] == 'user':
                return entry['last_value']
        # 3. Ask user
        if self.user_prompt_fn:
            value = self.user_prompt_fn(param, func_name, extra_context)
        elif self.web_context is not None:
            # For web UI, store pending param and return None
            self.web_context['pending_param'] = param
            return None
        else:
            value = input(f"Please provide a value for '{param}': ")
        if self.training_mode:
            # Ask user how to fetch in future
            how = input(f"How should I fetch '{param}' in the future? (config/function/user): ")
            entry = {'source': how}
            if how == 'function':
                func = input("Function name to call for this param: ")
                args = input("Arguments as JSON (or leave blank): ")
                entry['function'] = func
                if args:
                    entry['args'] = json.loads(args)
            elif how == 'user':
                entry['last_value'] = value
            self.param_map[param] = entry
            self._save_param_map()
        return value 