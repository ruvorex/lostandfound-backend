import os
from chalice import Chalice
from chalicelib.itemRoutes import item_routes
from chalicelib.authorizers import auth_functions, admin_authorizer
from chalicelib.userRoutes import user_routes
from chalicelib.notificationService import notification_service

app = Chalice(app_name='lostandfound')
app.register_blueprint(item_routes)
app.register_blueprint(auth_functions)
app.register_blueprint(user_routes)
app.register_blueprint(notification_service)

app.api.binary_types.append("multipart/form-data")

@app.route('/')
def index():
    return {'hello': 'world'}


@app.route('/test/admin', authorizer=admin_authorizer, cors=True)
def test_admin():
    return {'message': 'You have access to admin routes!'}

@app.route('/test/env', cors=True)
def test_env():
    test = os.environ.get('TEST')
    return {'message': test}


# The view function above will return {"hello": "world"}
# whenever you make an HTTP GET request to '/'.
#
# Here are a few more examples:
#
# @app.route('/hello/{name}')
# def hello_name(name):
#    # '/hello/james' -> {"hello": "james"}
#    return {'hello': name}
#
# @app.route('/users', methods=['POST'])
# def create_user():
#     # This is the JSON body the user sent in their POST request.
#     user_as_json = app.current_request.json_body
#     # We'll echo the json body back to the user in a 'user' key.
#     return {'user': user_as_json}
#
# See the README documentation for more examples.
#
