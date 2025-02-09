# Backend Deployment Guide (Chalice)

This document details how to set up, configure, and deploy the backend using AWS Chalice.

---

## Prerequisites

- AWS CLI configured locally (`aws configure`)
- Python 3.7+ with **pip**
- Chalice installed (`pip install chalice`)

---

## Steps

### 1. Clone the Backend Repository

```bash
git clone <backend-repo-url>
cd backend-directory
```

### 2. Set Up a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Chalice

Edit **`.chalice/config.json`**:
```json
{
  "version": "2.0",
  "app_name": "lostandfound",
  "environment_variables": {
    "USER_POOL_ID": "your-user-pool-id",
    "S3_BUCKET_NAME": "your-s3-bucket",
    "SQS_URL": "your-sqs-url"
  }
}
```

### 5. Deploy the Chalice App

```bash
chalice deploy --stage dev
```

---

## Testing the API

Note the URL output by Chalice and test it using:
```bash
curl https://<api-url>/test
```
