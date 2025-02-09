from chalice import UnauthorizedError, AuthResponse, Blueprint
import requests
import jwt
from jwt.algorithms import RSAAlgorithm
import os

JWKS_URL = 'https://cognito-idp.' + os.environ.get('REGION') + '.amazonaws.com/' + os.environ.get('USER_POOL_ID') + '/.well-known/jwks.json'
JWT_ALGORITHM = 'RS256'  # Or RS256 if using a public/private key pair
auth_functions = Blueprint(__name__)
# Cache for JWKS keys
_jwks_cache = None


def get_jwks():
    """Fetches and caches the JWKS from the given URL."""
    global _jwks_cache
    if not _jwks_cache:
        response = requests.get(JWKS_URL)
        if response.status_code != 200:
            raise UnauthorizedError("Unable to fetch JWKS")
        _jwks_cache = response.json()
    return _jwks_cache


def get_signing_key(token):
    """Gets the signing key from the JWKS based on the token's kid."""
    jwks = get_jwks()
    headers = jwt.get_unverified_header(token)
    kid = headers.get('kid')
    if not kid:
        raise UnauthorizedError("Missing kid in token header")

    for key in jwks.get('keys', []):
        if key['kid'] == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(key)

    raise UnauthorizedError("Unable to find matching key for kid")


def decode_jwt(token):
    """Decodes the JWT token and verifies its validity using JWKS."""
    try:
        signing_key = get_signing_key(token)
        decoded_token = jwt.decode(token, signing_key, algorithms=['RS256'], options={"verify_aud": False})
        return decoded_token
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid token")
    except UnauthorizedError:
        raise UnauthorizedError("Unable to decode token")

@auth_functions.authorizer()
def admin_authorizer(auth_request):
    """Authorizer to validate JWT tokens and check user group membership."""
    token = auth_request.token
    if not token:
        raise UnauthorizedError("Missing authorization token")

    try:
        # Decode and validate the JWT
        decoded_token = decode_jwt(token)
    except UnauthorizedError as e:
        return AuthResponse(routes=[], principal_id='user')

    # Check if the user belongs to the required group
    user_groups = decoded_token.get('cognito:groups', [])  # Ensure 'groups' is part of your token payload
    if "Admin" not in user_groups:
        return AuthResponse(routes=[], principal_id='user')

    # Return the AuthResponse with user context
    return AuthResponse(routes=['*'], principal_id=decoded_token['username'])