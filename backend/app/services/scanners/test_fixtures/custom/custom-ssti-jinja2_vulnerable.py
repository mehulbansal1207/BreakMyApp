# Vulnerable SSTI fixture — all 4 sub-cases must trigger custom-ssti-jinja2

# ---------- Sub-case 1: Qualified + variable-assigned ----------
import flask

app = flask.Flask(__name__)

@app.route('/vuln1')
def vuln_qualified_assigned():
    tmpl = flask.request.args.get('template')
    return flask.render_template_string(tmpl)


# ---------- Sub-case 2: Qualified + inline ----------
@app.route('/vuln2')
def vuln_qualified_inline():
    return flask.render_template_string(flask.request.args.get('template'))


# ---------- Sub-case 3: Unqualified + variable-assigned ----------
from flask import render_template_string, request

@app.route('/vuln3')
def vuln_unqualified_assigned():
    tmpl = request.args.get('template')
    return render_template_string(tmpl)


# ---------- Sub-case 4: Unqualified + inline ----------
@app.route('/vuln4')
def vuln_unqualified_inline():
    return render_template_string(request.args.get('template'))
