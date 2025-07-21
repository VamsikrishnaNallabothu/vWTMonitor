from flask import Flask, render_template_string, request, session, redirect, url_for
import os
import json
from langgraph_workflow import build_langgraph_workflow
from metrics_memory import get_all_metrics

SUTS = ['ZIA', 'ZPA', 'ZTGW', 'SMCA']
SHARED_INDEX = 'enhanced_function_index_shared.json'

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

app = Flask(__name__)
app.secret_key = os.urandom(24)

TEMPLATE = '''
<!doctype html>
<title>NLPCodeGen4vWT - Conversational UI</title>
<h2>NLPCodeGen4vWT - Conversational Test Generator</h2>
<form method=post>
  {% if not session.get('sut_selected') %}
    <label>Select SUT(s) to test:</label><br>
    {% for sut in suts %}
      <input type="checkbox" name="sut" value="{{sut}}"> {{sut}}<br>
    {% endfor %}
    <input type=submit value="Select SUT(s)">
  {% else %}
    <input name=user_input style="width:60%" autofocus placeholder="Type your test request or follow-up question">
    <label><input type="checkbox" name="training_mode" {% if session.get('training_mode') %}checked{% endif %}> Training Mode</label>
    <input type=submit value=Send>
  {% endif %}
</form>
{% if pending_param %}
  <form method=post>
    <b>Parameter '{{ pending_param }}' is missing.</b><br>
    <input name=param_value placeholder="Enter value for {{ pending_param }}">
    {% if session.get('training_mode') %}
      <br>How should I fetch '{{ pending_param }}' in the future?
      <select name=how_fetch>
        <option value="user">Ask user</option>
        <option value="config">From config</option>
        <option value="function">From function</option>
      </select>
      <br>If function, function name: <input name=func_name>
      <br>Function args (JSON): <input name=func_args>
    {% endif %}
    <input type=submit value="Submit Param">
  </form>
{% endif %}
{% if history %}
  <h3>Conversation</h3>
  <div style="background:#f8f8f8;padding:1em;border-radius:8px;">
  {% for entry in history %}
    <b>You:</b> {{ entry['user'] }}<br>
    <b>System:</b><br>
    {% if entry['type'] == 'metrics' %}
      <pre>{{ entry['result'] }}</pre>
    {% else %}
      <b>Workflow Actions:</b> <pre>{{ entry['actions'] }}</pre>
      <b>Generated Code:</b> <pre>{{ entry['code'] }}</pre>
      <b>Execution Result:</b> <pre>{{ entry['result'] }}</pre>
    {% endif %}
    <hr>
  {% endfor %}
  </div>
{% endif %}
'''

web_context = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'history' not in session:
        session['history'] = []
    if request.method == 'POST':
        # SUT selection step
        if not session.get('sut_selected'):
            selected = request.form.getlist('sut')
            selected = [s for s in selected if s in SUTS]
            if not selected:
                return render_template_string(TEMPLATE, history=session.get('history', []), pending_param=None, suts=SUTS)
            session['sut_selected'] = selected
            session['function_index'] = load_sut_indexes(selected)
            session.modified = True
            return redirect(url_for('index'))
        session['training_mode'] = 'training_mode' in request.form or session.get('training_mode', False)
        if 'param_value' in request.form:
            param = web_context.get('pending_param')
            value = request.form['param_value']
            if session.get('training_mode'):
                import json
                from param_resolver import PARAM_MAP_PATH
                if os.path.exists(PARAM_MAP_PATH):
                    with open(PARAM_MAP_PATH) as f:
                        param_map = json.load(f)
                else:
                    param_map = {}
                how = request.form.get('how_fetch', 'user')
                entry = {'source': how}
                if how == 'function':
                    entry['function'] = request.form.get('func_name', '')
                    func_args = request.form.get('func_args', '')
                    if func_args:
                        try:
                            entry['args'] = json.loads(func_args)
                        except Exception:
                            entry['args'] = {}
                elif how == 'user':
                    entry['last_value'] = value
                param_map[param] = entry
                with open(PARAM_MAP_PATH, 'w') as f:
                    json.dump(param_map, f, indent=2)
            web_context['pending_param'] = None
            web_context['last_param_value'] = value
            return redirect(url_for('index'))
        user_input = request.form.get('user_input', '')
        if user_input:
            if 'metric' in user_input.lower():
                metrics = get_all_metrics()
                session['history'].append({'user': user_input, 'type': 'metrics', 'result': str(metrics)})
            else:
                function_index = session.get('function_index', {})
                g, state = build_langgraph_workflow(
                    'config.yaml',
                    user_input,
                    user_prompt_fn=None,
                    web_context=web_context,
                    training_mode=session.get('training_mode', False),
                    function_index=function_index
                )
                result_state = g.run(state)
                if web_context.get('pending_param'):
                    session.modified = True
                    return render_template_string(TEMPLATE, history=session.get('history', []), pending_param=web_context['pending_param'], suts=SUTS)
                session['history'].append({
                    'user': user_input,
                    'type': 'workflow',
                    'actions': result_state['final_result']['actions'],
                    'code': result_state['final_result']['code'],
                    'result': result_state['final_result']['result']
                })
            session.modified = True
            return redirect(url_for('index'))
    pending_param = web_context.get('pending_param')
    return render_template_string(TEMPLATE, history=session.get('history', []), pending_param=pending_param, suts=SUTS)

if __name__ == '__main__':
    app.run(debug=True) 