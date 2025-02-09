import uuid

from botocore.compat import file_type
from chalice import Blueprint, BadRequestError, Response
import json
import boto3
import os
import traceback
import urllib.parse as urllib
from .connectHelper import create_connection
from requests_toolbelt.multipart import decoder
from .helpers import json_serial
from .notificationService import create_notification
from PIL import Image
import io
import re
import base64

item_routes = Blueprint(__name__)
s3 = boto3.client('s3')

SUPPORTED_IMAGE_FORMATS = ['jpeg', 'png', 'jpg']

from PIL import Image, UnidentifiedImageError
import io
import re
import base64

SUPPORTED_IMAGE_FORMATS = ['jpeg', 'png', 'jpg']

def validate_image(file_content, filename=None):
    try:
        # Step 1: Check the file extension if provided
        if filename:
            extension = filename.split('.')[-1].lower()
            if extension not in SUPPORTED_IMAGE_FORMATS:
                raise ValueError(f"Unsupported image format: {extension}")

        # Step 2: Check for common encoding issues (base64 headers)
        if is_base64_encoded(file_content):
            print("Base64 header detected, decoding...")
            file_content = decode_base64_image(file_content)

        # Step 3: Verify that the image can be opened using Pillow
        image = Image.open(io.BytesIO(file_content))
        image.verify()  # Verify image integrity
        print("Image successfully verified.")

        # Step 4: Double-check if Pillow can read the image fully
        image = Image.open(io.BytesIO(file_content))  # Reopen to ensure no issues
        image.load()  # Force loading the entire image to catch issues
        return True

    except UnidentifiedImageError as e:
        print(f"UnidentifiedImageError: {str(e)} - The file content might be corrupted.")
    except ValueError as ve:
        print(f"Validation Error: {str(ve)}")
    except Exception as e:
        print(f"Unexpected error during image validation: {str(e)}")
    return False


def is_base64_encoded(data):
    """ Check if the image is base64 encoded. """
    try:
        # Detect common base64 headers (e.g., data:image/jpeg;base64)
        base64_header_pattern = re.compile(r'^data:image\/[a-zA-Z]+;base64,')
        if base64_header_pattern.match(data.decode('utf-8', errors='ignore')):
            return True
    except Exception:
        return False
    return False


def decode_base64_image(data):
    """ Decode base64-encoded image to binary format. """
    try:
        # Remove header and decode base64 content
        header, encoded = re.split(',', data.decode('utf-8'), 1)
        return base64.b64decode(encoded)
    except Exception as e:
        print(f"Failed to decode base64 image: {str(e)}")
        return data  # Return original data as fallback

def call_amazon_rekognition(bucket_name, object_key):
    """
    Call Amazon Rekognition to detect labels for the given image in an S3 bucket.
    :param bucket_name: S3 bucket where the image is stored.
    :param object_key: S3 key for the image.
    :return: List of labels or an empty list on failure.
    """
    try:
        # Print basic information for debugging
        print(f"Attempting to detect labels for image in bucket: {bucket_name}, key: {object_key}")

        rekognition_client = boto3.client('rekognition', region_name=os.environ['REGION'])

        # Fetching metadata of the S3 object for validation
        s3 = boto3.client('s3')
        metadata = s3.head_object(Bucket=bucket_name, Key=object_key)
        print(f"S3 Object Metadata: {metadata}")

        # Ensuring that the file is in a valid format
        if not object_key.lower().endswith(('.jpg', '.jpeg', '.png')):
            print("Error: The file is not a valid image format. Only JPEG and PNG are supported.")
            return []

        response = rekognition_client.detect_labels(
            Image={'S3Object': {'Bucket': bucket_name, 'Name': object_key}},
            MaxLabels=10,
            MinConfidence=70
        )

        # Extract label names
        labels = [label['Name'] for label in response['Labels']]
        print(f"Extracted labels: {labels}")

        return labels

    except Exception as e:
        print("Error occurred while calling Amazon Rekognition:")
        print(f"Exception: {str(e)}")
        traceback.print_exc()
        return []

@item_routes.route('/category', methods=['GET'], cors=True)
def get_category():
    # SQL query to get all items
    sql = """
        SELECT *
        FROM category
    """

    with create_connection().cursor() as cursor:
        cursor.execute(sql)
        result = cursor.fetchall()

        # Use json_serial to serialize date, time, and timedelta fields
        serialized_result = json.loads(json.dumps(result, default=json_serial))

        return {
            "category": serialized_result
        }

@item_routes.route('/items', methods=['GET'], cors=True)
def get_items():
    # SQL query to get all items
    sql = """
        SELECT *
        FROM items
    """

    with create_connection().cursor() as cursor:
        cursor.execute(sql)
        result = cursor.fetchall()

        # Use json_serial to serialize date, time, and timedelta fields
        serialized_result = json.loads(json.dumps(result, default=json_serial))

        return {
            "items": serialized_result
        }

@item_routes.route('/item/create', cors=True, methods=['POST'], content_types=['multipart/form-data'])
def create_item():
    try:
        print("Starting item creation process...")

        # Decode the multipart/form-data using requests-toolbelt
        print("Decoding multipart/form-data")
        request = item_routes.current_request
        content_type = request.headers['content-type']
        multipart_data = decoder.MultipartDecoder(request.raw_body, content_type)

        # Initialize form data and files
        form_data = {}
        image_files = []

        # Parse multipart form data
        for part in multipart_data.parts:
            content_disposition = part.headers.get(b'Content-Disposition', b'').decode('utf-8')
            print(f"Processing part: {content_disposition}")

            if 'filename=' in content_disposition:
                filename = content_disposition.split('filename=')[1].strip('"')
                content_type = part.headers[b'Content-Type'].decode('utf-8')
                print(f"Found file: {filename} with Content-Type: {content_type}")
                print(f"Size of uploaded image: {len(part.content)} bytes")
                file_content = io.BytesIO(part.content).getvalue()
                image_files.append((filename, file_content, content_type))
            else:
                name = content_disposition.split('name=')[1].strip('"')
                form_data[name] = part.text
                print(f"Found form field: {name} = {form_data[name]}")

        # Extract form data fields and handle defaults
        item_name = form_data.get('item_name', 'Unknown Item')
        description = form_data.get('description', 'No description provided')
        location = form_data.get('location', 'Unknown location')
        date_found = form_data.get('date_found', '1970-01-01')
        time_found = form_data.get('time_found', '00:00')
        brand = form_data.get('brand', 'Others').strip() or "Others"

        found_at = f"{date_found} {time_found}"
        print(f"Combined date and time: {found_at}")

        # Initialize arrays for image URLs and labels
        image_urls = []
        all_labels = []
        category_names = []

        # Fetch available categories from the database
        with create_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT name FROM category")
                categories_in_db = [row['name'] for row in cursor.fetchall()]
        print(f"Available categories: {categories_in_db}")

        # Process uploaded image files
        s3 = boto3.client('s3')
        for filename, file_content, content_type in image_files:
            validate_image(file_content, filename)
            s3_bucket = os.environ['S3_BUCKET_NAME']
            s3_key = f"items/{uuid.uuid4()}_{filename}"
            print(f"Uploading file to S3: Bucket = {s3_bucket}, Key = {s3_key}")

            # Upload image to S3 with the detected content type
            s3.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type  # Directly use the Content-Type from the multipart headers
            )

            # Generate image URL
            image_url = f"https://{s3_bucket}.s3.amazonaws.com/{urllib.quote(s3_key)}"
            image_urls.append(image_url)
            print(f"Uploaded image URL: {image_url}")

            # Call Rekognition to get labels
            labels = call_amazon_rekognition(s3_bucket, s3_key)
            print(f"Rekognition labels for {filename}: {labels}")
            all_labels.append(labels)

            # Match labels to categories
            for label in labels:
                category_match = next((cat for cat in categories_in_db if cat.lower() in label.lower()), None)
                if category_match:
                    category_names.append(category_match)
                else:
                    category_names.append("Others")

        final_category = category_names[0] if category_names else "Others"
        print(f"Final category selected: {final_category}")

        # Insert item details into the database
        sql_insert = """
            INSERT INTO items (item_name, description, location, found_at, image_url, category, brand, status, labels)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'unclaimed', %s)
        """
        with create_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql_insert, (
                    item_name, description, location, found_at,
                    json.dumps(image_urls), final_category, brand,
                    json.dumps(all_labels)
                ))

                # Fetch the last inserted item
                cursor.execute("SELECT * FROM items WHERE id = LAST_INSERT_ID()")
                inserted_item = cursor.fetchone()
                conn.commit()
                print(f"Inserted item: {inserted_item}")

        # Trigger notification
        create_notification(inserted_item['id'])
        print("Notification triggered for item creation.")

        # Return success response with item details
        return Response(
            body=json.dumps({'message': 'Item created successfully', 'item': inserted_item}, default=json_serial),
            status_code=201,
            headers={
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        )

    except Exception as e:
        print("Error during item creation:", e)
        traceback.print_exc()
        raise BadRequestError("Failed to create item. Please try again.")

@item_routes.route('/item/{id}', cors=True, methods=['GET'])
def get_item(id):
    try:
        print("this is working")
        # SQL query to get a specific item by id
        sql = """
            SELECT *
            FROM items
            WHERE id = %s
        """

        with create_connection().cursor() as cursor:
            cursor.execute(sql, (id,))
            result = cursor.fetchone()

            if result is None:
                return Response(
                    body=json.dumps({'message': 'Item not found'}),
                    status_code=404,
                    headers={'Content-Type': 'application/json'}
                )

            # Use json_serial to serialize date, time, and timedelta fields
            serialized_result = json.loads(json.dumps(result, default=json_serial))

            return {
                "item": serialized_result
            }

    except Exception as e:
        print("Error during item retrieval:", e)
        traceback.print_exc()
        raise BadRequestError("Failed to retrieve item. Please try again.")

@item_routes.route('/item/update/{id}', cors=True, methods=['PUT'], content_types=['multipart/form-data'])
def update_item(id):
    try:
        # Decode the multipart/form-data using requests-toolbelt
        request = item_routes.current_request
        content_type = request.headers['content-type']
        multipart_data = decoder.MultipartDecoder(request.raw_body, content_type)

        # Initialize form data and files
        form_data = {}
        new_image_files = []

        # Parse each part of the multipart form-data
        for part in multipart_data.parts:
            content_disposition = part.headers.get(b'Content-Disposition', b'').decode()
            if 'filename=' in content_disposition:  # Handle file uploads
                filename = content_disposition.split('filename=')[1].strip('"')
                new_image_files.append((filename, part.content))
            else:  # Handle form fields
                name = content_disposition.split('name=')[1].strip('"')
                # For array fields like `image_url[]`, aggregate them properly
                if name == 'image_url[]':
                    if name not in form_data:
                        form_data[name] = []
                    form_data[name].append(part.text.strip())
                else:
                    form_data[name] = part.text.strip()

        # Extract form fields
        item_name = form_data.get('item_name', '')
        description = form_data.get('description', '')
        location = form_data.get('location', '')
        found_at = form_data.get('found_at', '')
        category = form_data.get('category', '')
        brand = form_data.get('brand', 'Others')
        existing_image_urls = form_data.get('image_url[]', [])

        # Process uploaded images and store them in S3
        s3_bucket = os.environ['S3_BUCKET_NAME']
        new_image_urls = []
        for filename, file_content in new_image_files:

            s3_key = f"items/{category}/{uuid.uuid4()}_{filename}"

            # Upload the image to S3
            s3.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=file_content,
                ContentType='image/jpeg'
            )

            # Generate S3 URL
            image_url = f"https://{s3_bucket}.s3.amazonaws.com/{urllib.quote(s3_key)}"
            new_image_urls.append(image_url)

        # Combine existing and new image URLs
        final_image_urls = existing_image_urls + new_image_urls

        # SQL query to update the item details in the database
        sql_update = """
            UPDATE items
            SET item_name = %s, description = %s, location = %s, found_at = %s, image_url = %s, category = %s, brand = %s
            WHERE id = %s
        """

        # Connect to the database and execute the update query
        with create_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql_update, (
                    item_name, description, location, found_at,
                    json.dumps(final_image_urls), category, brand, id
                ))
            conn.commit()

        # Return success response
        return Response(
            body=json.dumps({'message': 'Item updated successfully'}),
            status_code=200,
            headers={
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        )

    except Exception as e:
        print("Error during item update:", e)
        traceback.print_exc()
        raise BadRequestError("Failed to update item. Please try again.")

@item_routes.route('/item/delete/{id}', cors=True, methods=['DELETE'])
def delete_item(id):
    try:
        # SQL query to delete the item based on the id
        sql = """
            DELETE FROM items
            WHERE id = %s
        """

        with create_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (id,))
                conn.commit()

        return Response(
            body=json.dumps({'message': 'Item deleted successfully'}),
            status_code=200,
            headers={'Content-Type': 'application/json'}
        )

    except Exception as e:
        print("Error during item deletion:", e)
        traceback.print_exc()
        raise BadRequestError("Failed to delete item. Please try again.")

@item_routes.route('/item/claim/{id}', cors=True, methods=['PUT'])
def claim_item(id):
    try:
        # SQL query to update the status of the item based on the id
        sql = """
            UPDATE items
            SET status = 'claimed'
            WHERE id = %s AND status = 'unclaimed'
        """

        with create_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (id,))
                conn.commit()

        return Response(
            body=json.dumps({'message': 'Item status updated to claimed successfully'}),
            status_code=200,
            headers={'Content-Type': 'application/json'}
        )

    except Exception as e:
        print("Error during item status update:", e)
        traceback.print_exc()
        raise BadRequestError("Failed to claim item. Please try again.")

@item_routes.route('/item/unclaim/{id}', cors=True, methods=['PUT'])
def unclaim_item(id):
    try:
        # SQL query to update the status of the item based on the id
        sql = """
            UPDATE items
            SET status = 'unclaimed'
            WHERE id = %s AND status = 'claimed'
        """

        with create_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (id,))
                conn.commit()

        return Response(
            body=json.dumps({'message': 'Item status updated to unclaimed successfully'}),
            status_code=200,
            headers={'Content-Type': 'application/json'}
        )

    except Exception as e:
        print("Error during item status update:", e)
        traceback.print_exc()
        raise BadRequestError("Failed to unclaim item. Please try again.")