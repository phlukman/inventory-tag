def acquire_lock(s3_client, bucket_name, object_key, timeout=None, request_id=None):
    """
    Acquire a lock on an S3 object - only succeeds if lock doesn't exist
   
    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        object_key: S3 object key to lock
        timeout: Lock timeout in seconds (defaults to LOCK_TIMEOUT_SECONDS)
        request_id: Optional request ID for tracking
       
    Returns:
        tuple: (success, lock_id) - success is boolean, lock_id is str if successful
    """
    if timeout is None:
        timeout = LOCK_TIMEOUT_SECONDS
       
    lock_id = str(uuid.uuid4())
    lock_key = f"{object_key}.lock"
   
    lock_content = {
        "lock_id": lock_id,
        "timestamp": datetime.utcnow().isoformat(),
        "expires": (datetime.utcnow() + timedelta(seconds=timeout)).isoformat(),
        "request_id": request_id
    }
   
    log_event("info", "Attempting to acquire lock",
              request_id=request_id,
              bucket=bucket_name,
              lock_key=lock_key,
              lock_id=lock_id,
              timeout_seconds=timeout)
   
    # Check if lock already exists
    try:
        # Use head_object to check if the lock file exists
        s3_client.head_object(Bucket=bucket_name, Key=lock_key)
       
        # If we get here without an exception, the lock file exists
        log_event("info", "Cannot acquire lock - lock file already exists",
                  request_id=request_id,
                  bucket=bucket_name,
                  lock_key=lock_key)
        return False, None
       
    except s3_client.exceptions.ClientError as e:
        # If the error code is 404, the lock file doesn't exist
        if e.response['Error']['Code'] == '404':
            try:
                # File doesn't exist, create it
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=lock_key,
                    Body=json.dumps(lock_content),
                    ContentType="application/json"
                )
               
                log_event("info", "Successfully acquired lock",
                          request_id=request_id,
                          bucket=bucket_name,
                          lock_key=lock_key,
                          lock_id=lock_id)
                return True, lock_id
            except Exception as inner_e:
                log_event("error", "Error creating lock file",
                          request_id=request_id,
                          bucket=bucket_name,
                          lock_key=lock_key,
                          error=str(inner_e))
                return False, None
        else:
            # Some other error occurred
            log_event("error", "Error checking for existing lock",
                      request_id=request_id,
                      bucket=bucket_name,
                      lock_key=lock_key,
                      error=str(e))
            return False, None
    except Exception as e:
        log_event("error", "Unexpected error acquiring lock",
                  request_id=request_id,
                  bucket=bucket_name,
                  lock_key=lock_key,
                  error=str(e))
        return False, None
