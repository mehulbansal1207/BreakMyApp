# Safe NoSQL injection fixture — user input validated before use in query
import flask
from pymongo import MongoClient

app = flask.Flask(__name__)
client = MongoClient()
db = client.mydb
users = db.users

@app.route('/find')
def find_user():
    # Safe: extract and validate user input before passing to query
    username = str(flask.request.args.get("username", ""))
    if not isinstance(username, str):
        return "Invalid input", 400
    result = users.find({"username": username})
    return str(list(result))

@app.route('/find_one')
def find_one_user():
    email = str(flask.request.args.get("email", ""))
    result = users.find_one({"email": email})
    return str(result)
