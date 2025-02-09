from chalice import Blueprint, BadRequestError
import json
import os
from .connectHelper import create_connection
from .helpers import json_serial
import boto3

notification_service = Blueprint(__name__)
ses = boto3.client('ses')
sqs = boto3.client('sqs')
cognito_idp = boto3.client('cognito-idp')


def create_notification(itemId):
    # Create SQS message
    print("Creating notification it was called")
    message = {
        'type': 'item',
        'id': itemId
    }

    # Send SQS message
    response = sqs.send_message(
        QueueUrl=os.environ.get('SQS_URL'),
        MessageBody=json.dumps(message)
    )


@notification_service.route('/subscriptions', cors=True, methods=['GET'])
def get_subscriptions():
    if notification_service.current_request.query_params:
        email = notification_service.current_request.query_params.get('email')

        if email:
            sql = "SELECT * FROM notification_subscriptions WHERE email = %s"
            with create_connection().cursor() as cursor:
                cursor.execute(sql, (email))
                result = cursor.fetchall()

                return json.loads(json.dumps(result, default=json_serial))
        else:
            raise BadRequestError("Missing required parameters email")
    else:
        raise BadRequestError("Missing required parameters email")


@notification_service.route('/subscriptions', cors=True, methods=['POST'])
def create_subscription():
    if notification_service.current_request.query_params:
        email = notification_service.current_request.query_params.get('email')
        print(email)

        if email:
            body = notification_service.current_request.json_body
            print(body)
            categoryIds = body['categoryIds']

            with create_connection().cursor() as cursor:
                # Delete existing subscriptions
                del_sql = "DELETE FROM notification_subscriptions WHERE email = %s"
                cursor.execute(del_sql, (email))

                # Insert new subscriptions
                for categoryId in categoryIds:
                    sql = "INSERT INTO notification_subscriptions (email, categoryId) VALUES (%s, %s)"
                    cursor.execute(sql, (email, categoryId))

            sql = "SELECT * FROM lostandfound.email_verifications WHERE email = %s"

            with create_connection().cursor() as cursor:
                cursor.execute(sql, (email))
                result = cursor.fetchone()

                with create_connection().cursor() as cursor:
                    if result:
                        sql = "DELETE FROM email_verifications WHERE email = %s"
                        cursor.execute(sql, (email))

                    recreate_sql = "INSERT INTO email_verifications (email, token) VALUES (%s, %s)"
                    token = os.urandom(16).hex()
                    cursor.execute(recreate_sql, (email, token))

                    # Send email verification
                    response = ses.send_email(
                        Source=os.environ.get('SES_EMAIL'),
                        Destination={
                            'ToAddresses': [email]
                        },
                        Message={
                            'Subject': {
                                'Data': 'NYP Lost and Found Email Verification'
                            },
                            'Body': {
                                'Text': {
                                    'Data': 'Please verify your email by pasting the code below in the NYP Lost and Found website: \n\n' + token
                                }
                            }
                        }
                    )

                    return json.loads(json.dumps({'message': 'Email verification sent'}, default=json_serial))
        else:
            raise BadRequestError("Missing required parameters email")
    else:
        raise BadRequestError("Missing required parameters email")


@notification_service.route('/subscriptions/verify', cors=True, methods=['GET'])
def verify_subscription():
    if notification_service.current_request.query_params:
        email = notification_service.current_request.query_params.get('email')
        token = notification_service.current_request.query_params.get('token')

        if email and token:
            sql = "SELECT * FROM email_verifications WHERE email = %s AND token = %s"

            with create_connection().cursor() as cursor:
                cursor.execute(sql, (email, token))
                result = cursor.fetchone()

                if result:
                    # Set email as verified
                    sql = "UPDATE email_verifications SET verified = 1 WHERE email = %s"
                    with create_connection().cursor() as cursor:
                        cursor.execute(sql, (email))

                    return json.loads(json.dumps({'message': 'Email verified'}, default=json_serial))
                else:
                    raise BadRequestError("Invalid token")
        else:
            raise BadRequestError("Missing required parameters email")
    else:
        raise BadRequestError("Missing required parameters email")


@notification_service.on_sqs_message(queue='lostandfound-queue', batch_size=5)
def handle_sqs_message(event):
    print("Handling SQS message...")
    for record in event:
        try:
            # Parse the record
            print(f"Raw SQS message: {record.body}")
            data = json.loads(record.body)
            print(f"Parsed message: {data}")

            # Check if required fields exist
            if 'type' not in data or 'id' not in data:
                print("Error: 'type' or 'id' field missing in message")
                continue

            item_id = data['id']
            print(f"Item ID: {item_id}")

            # Query the item by id
            sql_item = "SELECT * FROM items WHERE id = %s"
            with create_connection().cursor() as cursor:
                cursor.execute(sql_item, (item_id,))
                item = cursor.fetchone()

                if item is None:
                    print(f"No item found for ID: {item_id}")
                    continue

                print(f"Item details: {json.dumps(item, default=json_serial)}")

                category_name = item.get('category')
                if not category_name:
                    print("Error: 'category' field missing in item")
                    continue
                print(f"Category name: {category_name}")

                # Match the category name with the name in the category table
                sql_category = "SELECT id FROM category WHERE name = %s"
                cursor.execute(sql_category, (category_name,))
                category_result = cursor.fetchone()

                if category_result is None:
                    print(f"No category found for name: {category_name}")
                    continue

                category_id = category_result['id']
                print(f"Category ID: {category_id}")

                # Query notification subscribers for the matched category ID
                sql_subscribers = '''
                SELECT ns.email FROM notification_subscriptions ns
                INNER JOIN email_verifications ev ON ns.email = ev.email
                WHERE ns.categoryId = %s AND ev.verified = 1
                '''
                cursor.execute(sql_subscribers, (category_id,))
                subscribers = cursor.fetchall()

                if not subscribers:
                    print(f"No subscribers found for category ID: {category_id}")
                    continue

                print(f"Subscribers: {json.dumps(subscribers, default=json_serial)}")

                emails = [subscriber['email'] for subscriber in subscribers]
                print(f"Emails to notify: {emails}")

                # Send email to users
                if emails:
                    response = ses.send_email(
                        Source=os.environ.get('SES_EMAIL'),
                        Destination={'ToAddresses': emails},
                        Message={
                            'Subject': {'Data': 'Lost and Found Notification - New Item Added'},
                            'Body': {
                                'Text': {
                                    'Data': (
                                        f"New item added to category:\n\n"
                                        f"Name: {item['item_name']}\n"
                                        f"Description: {item['description']}\n"
                                        f"Location: {item['location']}\n"
                                        f"Found at: {item['found_at']}\n\n"
                                        "Please check the NYP Lost and Found website for more details: "
                                        "https://main.dthcvv5pro4em.amplifyapp.com/\n"
                                    )
                                }
                            }
                        }
                    )
                    print(f"SES response: {response}")
                    for email in emails:
                        print(f'Email sent to: {email}')

        except Exception as e:
            print(f"Error handling message: {e}")
