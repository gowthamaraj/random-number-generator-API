from flask import Flask, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter, HEADERS
from flask_limiter.util import get_remote_address
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps
import requests

#initiating the APP
app = Flask(__name__)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
app.config['RATELIMIT_HEADERS_ENABLED'] = True
app.config['Remaining_quota'] = dict({})

app.config['SECRET_KEY'] = 'gowthamaraj'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

#initiating the DB
db = SQLAlchemy(app)


#flask_limiter - rate limiting configuration 
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.header_mapping = {
    HEADERS.LIMIT : "X-My-Limit",
    HEADERS.RESET : "X-My-Reset",
    HEADERS.REMAINING: "X-My-Remaining"
}

#User model for storing user info such as name,password,public_id
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(50),unique=True)
    password = db.Column(db.String(80))
db.create_all()

# quota renews every 1 hour, user will be given 100 requests to do in the 1hr time.
HOUR = datetime.timedelta(hours=1)
last_update = datetime.datetime.now()

# function which runs every 1hr
def renew_quota():
    for k in app.config['Remaining_quota'].iterkeys():
        app.config['Remaining_quota'][k] = 100

now = datetime.datetime.now()
if now-last_update > HOUR:
    renew_quota()
    last_update = now

# wrapper for receiving the header and decoding jwt. It also auth the user. 
# it passes the data of the user onto the wrapped function as a parameter
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        if 'x-access-token' in request.headers:
            token = request.headers['x-access-token']

        if not token:
            return jsonify({'message' : ' user is not authenticated!'}), 403

        try: 
            data = jwt.decode(token, app.config['SECRET_KEY'])
            current_user = User.query.filter_by(public_id=data['public_id']).first()
        except:
            return jsonify({'message' : 'Token is invalid!'}), 403

        return f(current_user, *args, **kwargs)

    return decorated

# it displays all the signed up users in the database.
@app.route('/',methods=['GET'])
def index():
    users = User.query.all()
    data =[]
    for user in users:
        data.append({'id':user.id,'public_id':user.public_id,'name':user.name,'password':user.password})
    return jsonify({'Users':data})


# route to login, it takes json data as the input.
@app.route('/login',methods=["POST"])
def login():
    auth = request.get_json()

    if not auth or not auth['username'] or not auth["password"]:
        return make_response('Could not verify', 403, {'WWW-Authenticate' : 'Basic realm="Login required!. Kindly check username and password"'})

    user = User.query.filter_by(name=auth['username']).first()

    if not user:
        return make_response('Could not verify', 403, {'WWW-Authenticate' : 'Basic realm="Login required!. Kindly create an account"'})

    if check_password_hash(user.password, auth['password']):
        token = jwt.encode({'public_id' : user.public_id, 'exp' : datetime.datetime.utcnow() + datetime.timedelta(minutes=60)}, app.config['SECRET_KEY'])

        return jsonify({'token' : token.decode('UTF-8')})

    return make_response('Could not verify', 403, {'WWW-Authenticate' : 'Basic realm="Login required!. Something is wrong. Visit later."'})


# route to signup : new users. JSON data is passed using the POST method
@app.route('/signup',methods=["POST"])
def signup():
    data = request.get_json()
    data = dict(data)
    if not data or not data["username"] or not data["password"]:
        return jsonify({'messgae':'Please provide username and password'})

    #making hash to store in the database
    hashed_password = generate_password_hash(data['password'], method='sha256')
    #making a record in the user table of sqlite DB
    user = User(public_id=str(uuid.uuid4()), name=data['username'], password=hashed_password)
    app.config['Remaining_quota'][data["username"]] = 100
    db.session.add(user)
    try:
        db.session.commit()
    except:
        return jsonify({'message' : 'Username already exists!. Kindly change it.'})
    return jsonify({'message' : 'New user created!'})


# endpoint for getting the random number from API A(fastapi)
@app.route('/call_api', methods=['GET'])
@limiter.limit("5/minute")
@token_required
def call_api(current_user):
    user = User.query.filter_by(public_id=current_user.public_id).first()
    if not user:
        return jsonify({'message' : 'No user found. Kindly Signup and Login'})

    if app.config['Remaining_quota'] == 0:
        return jsonify({'message' : 'Your Quota got over. Wait for renewal 1hr'})
    
    #making GET request to FASTAPI
    URL = "http://127.0.0.1:8000/get_number"
    data = requests.get(url = URL).json()

    #Updating QUOTA
    if app.config['Remaining_quota'][user.name] > 0:
        app.config['Remaining_quota'][user.name]-= 1
    return data


#For custom error from flask_limiter
@app.errorhandler(429)
def ratelimit_handler(e):
    return make_response(jsonify(error="ratelimit exceeded and does not have api calls left"), 403)


#To get the information about Limited available Quota for the user.
@app.route('/see_remaining_limits', methods=['GET'])
@token_required
def see_remaining_limits(current_user):
    user = User.query.filter_by(public_id=current_user.public_id).first()
    user_name = user.name
    if not user:
        return jsonify({'message' : 'No user found. Kindly Signup and Login'})
    return jsonify({'Remaining_quota':app.config['Remaining_quota'][user_name]})


# To run the flask app
if __name__ == '__main__':
    app.run(debug=True)