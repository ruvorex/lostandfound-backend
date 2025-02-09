import os
from chalice import Blueprint, BadRequestError
import boto3
import json
from .authorizers import admin_authorizer
from strgen import StringGenerator as SG

user_routes = Blueprint(__name__)
idp_client = boto3.client('cognito-idp')

pool_id = os.environ.get('USER_POOL_ID')


@user_routes.route('/admin/users', authorizer=admin_authorizer, cors=True, methods=['GET'])
def get_users():
    users = idp_client.list_users(
        UserPoolId=pool_id,
        AttributesToGet=[
            'name',
            'phone_number',
            'email'
        ]
    )["Users"]

    output_users = []

    for user in users:
        output_user = {"username": user["Username"], "create_at": user["UserCreateDate"],
                       "modified_at": user["UserLastModifiedDate"], "enabled": user["Enabled"],
                       "user_status": user["UserStatus"]}

        for a in user["Attributes"]:
            output_user[a["Name"]] = a["Value"]

        output_users.append(output_user)

    return json.loads(json.dumps(output_users, default=str))


@user_routes.route('/admin/users/{username}', cors=True, methods=['GET'])
def get_user(username):
    user = idp_client.admin_get_user(
        UserPoolId=pool_id,
        Username=username
    )

    user_groups = idp_client.admin_list_groups_for_user(
        Username=username,
        UserPoolId=pool_id
    )["Groups"]

    output_user = {"username": user["Username"], "create_at": user["UserCreateDate"],
                   "modified_at": user["UserLastModifiedDate"], "enabled": user["Enabled"],
                   "user_status": user["UserStatus"]}

    for a in user["UserAttributes"]:
        output_user[a["Name"]] = a["Value"]

    output_user["groups"] = [group["GroupName"] for group in user_groups]

    return json.loads(json.dumps(output_user, default=str))


@user_routes.route('/admin/users/{username}', authorizer=admin_authorizer, cors=True, methods=['PUT'])
def update_user(username):
    request = user_routes.current_request
    body = request.json_body
    group = body["group"]
    userAttributes = []

    for key in body:
        if body[key] == "":
            raise BadRequestError(f"{key} cannot be empty")

        if key not in ["name", "email", "phone_number", "birthdate"]:
            continue

        userAttributes.append({
            'Name': key,
            'Value': body[key]
        })

    user = idp_client.admin_update_user_attributes(
        UserPoolId=pool_id,
        Username=username,
        UserAttributes=userAttributes
    )

    # Update user groups
    groups = idp_client.admin_list_groups_for_user(
        Username=username,
        UserPoolId=pool_id
    )["Groups"]

    for g in groups:
        # check if user is in the group
        if g["GroupName"] == group:
            return {"message": "User updated successfully"}

        idp_client.admin_remove_user_from_group(
            UserPoolId=pool_id,
            Username=username,
            GroupName=g["GroupName"]
        )

    if group != "normal" and (group in ["admin"]):
        group_res = idp_client.admin_add_user_to_group(
            UserPoolId=pool_id,
            Username=username,
            GroupName=group
        )

    return {"message": "User updated successfully"}


@user_routes.route('/admin/users', authorizer=admin_authorizer, cors=True, methods=['POST'])
def create_user():
    request = user_routes.current_request
    body = request.json_body

    username = body["username"]
    name = body["name"]
    email = body["email"]
    group = body["group"]

    try:
        created_user = idp_client.admin_create_user(
            UserPoolId=pool_id,
            Username=username,
            UserAttributes=[
                {
                    'Name': 'name',
                    'Value': name
                },
                {
                    'Name': 'email',
                    'Value': email
                },
            ],
            DesiredDeliveryMediums=[
                'EMAIL'
            ],
            TemporaryPassword=SG(r"[\w\p]{20}").render()
        )
    except idp_client.exceptions.UsernameExistsException:
        raise BadRequestError("Username already exists")

    if group != "normal" and (group in ["admin"]):
        group_res = idp_client.admin_add_user_to_group(
            UserPoolId=pool_id,
            Username=username,
            GroupName=group
        )

    return {"message": "User created successfully"}