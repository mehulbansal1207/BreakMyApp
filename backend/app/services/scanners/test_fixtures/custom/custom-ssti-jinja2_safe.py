# Safe SSTI fixture — uses render_template with static template files instead
# of render_template_string with user input

from flask import Flask, render_template, request

app = Flask(__name__)

@app.route('/safe')
def safe_template():
    # Safe: user input passed as a template variable, not as the template itself
    name = request.args.get('name', 'World')
    return render_template('greeting.html', name=name)

@app.route('/safe2')
def safe_static():
    # Safe: static template string, user input only in variables
    from flask import render_template_string
    user_name = request.args.get('name', 'World')
    safe_template = '<h1>Hello, {{ name }}!</h1>'
    return render_template_string(safe_template, name=user_name)
