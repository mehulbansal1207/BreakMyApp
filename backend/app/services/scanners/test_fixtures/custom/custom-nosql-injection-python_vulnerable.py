# Vulnerable NoSQL injection fixture — user input directly in MongoDB query
import flask
from pymongo import MongoClient

app = flask.Flask(__name__)
client = MongoClient()
db = client.mydb
users = db.users

@app.route('/find')
def find_user():
    result = users.find({"username": flask.request.args.get("username")})
    return str(list(result))

@app.route('/find_one')
def find_one_user():
    result = users.find_one({"email": flask.request.json.get("email")})
    return str(result)
