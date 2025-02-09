import boto3
import pymysql
import os

ssm_client = boto3.client('ssm')

app_name = os.environ.get('APP_NAME')

# Batch get parameters from SSM
response = ssm_client.get_parameters(Names=[f'/{app_name}/rds_host', f'/{app_name}/rds_user', f'/{app_name}/rds_password', f'/{app_name}/db_name'], WithDecryption=True)
ssm_dict = {param['Name']: param['Value'] for param in response['Parameters']}

def create_connection():
    # RDS connection details from environment variables
    HOST = ssm_dict[f'/{app_name}/rds_host']
    USER = ssm_dict[f'/{app_name}/rds_user']
    PASSWORD = ssm_dict[f'/{app_name}/rds_password']
    DB_NAME = ssm_dict[f'/{app_name}/db_name']

    connection = pymysql.connect(host=HOST, user=USER, password=PASSWORD, database=DB_NAME, charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor, autocommit=True)

    return connection
