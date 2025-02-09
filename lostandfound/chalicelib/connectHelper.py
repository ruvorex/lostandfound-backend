import boto3
import pymysql

ssm_client = boto3.client('ssm')

# Batch get parameters from SSM
response = ssm_client.get_parameters(Names=['/lostandfound/rds_host', '/lostandfound/rds_user', '/lostandfound/rds_password', '/lostandfound/db_name'], WithDecryption=True)
ssm_dict = {param['Name']: param['Value'] for param in response['Parameters']}

def create_connection():
    # RDS connection details from environment variables
    HOST = ssm_dict['/lostandfound/rds_host']
    USER = ssm_dict['/lostandfound/rds_user']
    PASSWORD = ssm_dict['/lostandfound/rds_password']
    DB_NAME = ssm_dict['/lostandfound/db_name']

    connection = pymysql.connect(host=HOST, user=USER, password=PASSWORD, database=DB_NAME, charset='utf8mb4',
                                     cursorclass=pymysql.cursors.DictCursor, autocommit=True)

    return connection