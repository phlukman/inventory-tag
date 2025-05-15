"""
S3 Locking Utility Module

This module provides S3 locking functionality to prevent concurrent access issues
when multiple Lambda instances try to write to the same S3 object.
"""
import json
import time
import uuid
import random
import logging
import os
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Lock configuration with defaults (can be overridden by env vars)
LOCK_TIMEOUT_SECONDS = int(os.environ.get('LOCK_TIMEOUT_SECONDS', 60))
LOCK_MAX_ATTEMPTS = int(os.environ.get('LOCK_MAX_ATTEMPTS', 5))
LOCK_BASE_BACKOFF_SECONDS = float(os.environ.get('LOCK_BASE_BACKOFF_SECONDS', 2.0))
LOCK_JITTER_FACTOR = float(os.environ.get('LOCK_JITTER_FACTOR', 1.0))

def log_event(level, message, **kwargs):
    """
    Log an event with structured data
    
    Args:
        level: Log level ('debug', 'info', 'warning', 'error', 'critical')
        message: Log message
        **kwargs: Additional fields to include in log
    """
    log_data = {
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
        **kwargs
    }
    
    log_method = getattr(logger, level.lower())
    log_method(json.dumps(log_data))

def acquire_lock(s3_client, bucket_name, object_key, timeout=None, request_id=None):
    """
    Acquire a lock on an S3 object
    
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
    
    try:
        # Try to create the lock file
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
    except Exception as e:
        log_event("error", "Error acquiring lock", 
                  request_id=request_id,
                  bucket=bucket_name, 
                  lock_key=lock_key, 
                  error=str(e))
        return False, None

def release_lock(s3_client, bucket_name, object_key, lock_id, request_id=None):
    """
    Release a lock if we own it
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        object_key: S3 object key that was locked
        lock_id: ID of the lock to release
        request_id: Optional request ID for tracking
        
    Returns:
        bool: True if lock was released successfully
    """
    lock_key = f"{object_key}.lock"
    
    log_event("info", "Attempting to release lock", 
              request_id=request_id,
              bucket=bucket_name, 
              lock_key=lock_key, 
              lock_id=lock_id)
    
    try:
        # Check if we own the lock
        response = s3_client.get_object(Bucket=bucket_name, Key=lock_key)
        lock_content = json.loads(response['Body'].read().decode('utf-8'))
        
        if lock_content.get('lock_id') == lock_id:
            # We own the lock, delete it
            s3_client.delete_object(Bucket=bucket_name, Key=lock_key)
            log_event("info", "Successfully released lock", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      lock_key=lock_key, 
                      lock_id=lock_id)
            return True
        else:
            current_owner = lock_content.get('lock_id', 'unknown')
            current_owner_request = lock_content.get('request_id', 'unknown')
            log_event("warning", "Cannot release lock - not the owner", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      lock_key=lock_key, 
                      lock_id=lock_id,
                      current_owner=current_owner,
                      current_owner_request=current_owner_request)
            return False
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            log_event("warning", "Cannot release lock - lock file does not exist", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      lock_key=lock_key, 
                      lock_id=lock_id)
        else:
            log_event("error", "Error releasing lock", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      lock_key=lock_key, 
                      lock_id=lock_id,
                      error=str(e))
        return False
    except Exception as e:
        log_event("error", "Error releasing lock", 
                  request_id=request_id,
                  bucket=bucket_name, 
                  lock_key=lock_key, 
                  lock_id=lock_id,
                  error=str(e))
        return False

def check_stale_lock(s3_client, bucket_name, object_key, request_id=None):
    """
    Check if a lock is stale (expired)
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        object_key: S3 object key that was locked
        request_id: Optional request ID for tracking
        
    Returns:
        tuple: (is_stale, lock_content) - is_stale is boolean, lock_content is dict if lock exists
    """
    lock_key = f"{object_key}.lock"
    
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=lock_key)
        lock_content = json.loads(response['Body'].read().decode('utf-8'))
        
        if 'expires' in lock_content:
            expiration_time = datetime.fromisoformat(lock_content['expires'])
            current_time = datetime.utcnow()
            
            if current_time > expiration_time:
                seconds_expired = (current_time - expiration_time).total_seconds()
                log_event("info", "Found stale lock", 
                          request_id=request_id,
                          bucket=bucket_name, 
                          lock_key=lock_key, 
                          lock_id=lock_content.get('lock_id'),
                          owner_request_id=lock_content.get('request_id'),
                          expired_seconds=round(seconds_expired, 1))
                return True, lock_content
                
        log_event("info", "Lock is still valid", 
                  request_id=request_id,
                  bucket=bucket_name, 
                  lock_key=lock_key, 
                  lock_id=lock_content.get('lock_id'),
                  owner_request_id=lock_content.get('request_id'))
        return False, lock_content
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            log_event("info", "No lock file exists", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      lock_key=lock_key)
        else:
            log_event("error", "Error checking lock", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      lock_key=lock_key,
                      error=str(e))
        return False, None
    except Exception as e:
        log_event("error", "Error checking lock", 
                  request_id=request_id,
                  bucket=bucket_name, 
                  lock_key=lock_key,
                  error=str(e))
        return False, None

def break_stale_lock(s3_client, bucket_name, object_key, request_id=None):
    """
    Break a stale lock if it exists
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        object_key: S3 object key that was locked
        request_id: Optional request ID for tracking
        
    Returns:
        bool: True if stale lock was broken
    """
    lock_key = f"{object_key}.lock"
    
    is_stale, lock_content = check_stale_lock(s3_client, bucket_name, object_key, request_id)
    
    if is_stale and lock_content:
        try:
            s3_client.delete_object(Bucket=bucket_name, Key=lock_key)
            log_event("info", "Successfully broke stale lock", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      lock_key=lock_key,
                      stale_lock_id=lock_content.get('lock_id'),
                      stale_owner_request_id=lock_content.get('request_id'))
            return True
        except Exception as e:
            log_event("error", "Error breaking stale lock", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      lock_key=lock_key,
                      error=str(e))
    
    return False

def write_with_lock(s3_client, bucket_name, object_key, writer_func, max_attempts=None, request_id=None):
    """
    Execute a writer function with S3 locking
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: S3 bucket name
        object_key: S3 object key to lock
        writer_func: Function that performs the write operation (takes lock_id as an argument)
        max_attempts: Maximum number of retry attempts (defaults to LOCK_MAX_ATTEMPTS)
        request_id: Optional request ID for tracking
        
    Returns:
        Any: The result of the writer_func
    """
    if max_attempts is None:
        max_attempts = LOCK_MAX_ATTEMPTS
        
    log_event("info", "Attempting write operation with locking", 
              request_id=request_id,
              bucket=bucket_name, 
              object_key=object_key, 
              max_attempts=max_attempts,
              lock_config={
                  "timeout_seconds": LOCK_TIMEOUT_SECONDS,
                  "max_attempts": LOCK_MAX_ATTEMPTS,
                  "base_backoff": LOCK_BASE_BACKOFF_SECONDS,
                  "jitter_factor": LOCK_JITTER_FACTOR
              })
    
    total_wait_time = 0
    
    for attempt in range(max_attempts):
        # Try to break any stale locks first (except on first attempt)
        if attempt > 0:
            log_event("info", "Lock acquisition retry attempt", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      object_key=object_key, 
                      attempt=attempt+1, 
                      max_attempts=max_attempts)
                      
            stale_lock_broken = break_stale_lock(s3_client, bucket_name, object_key, request_id)
            if stale_lock_broken:
                log_event("info", "Broke stale lock before retry attempt", 
                          request_id=request_id,
                          bucket=bucket_name, 
                          object_key=object_key, 
                          attempt=attempt+1)
            
            # Add a delay with exponential backoff and jitter
            wait_time = (LOCK_BASE_BACKOFF_SECONDS ** attempt) + (random.uniform(0, LOCK_JITTER_FACTOR))
            log_event("info", "Waiting before retry attempt", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      object_key=object_key, 
                      wait_time_seconds=round(wait_time, 2), 
                      attempt=attempt+1, 
                      max_attempts=max_attempts)
                      
            time.sleep(wait_time)
            total_wait_time += wait_time
            
        # Try to acquire lock
        start_time = time.time()
        success, lock_id = acquire_lock(s3_client, bucket_name, object_key, timeout=LOCK_TIMEOUT_SECONDS, request_id=request_id)
        lock_acquisition_time = time.time() - start_time
        
        if success:
            log_event("info", "Successfully acquired lock", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      object_key=object_key, 
                      lock_id=lock_id, 
                      acquisition_time_seconds=round(lock_acquisition_time, 3),
                      attempt=attempt+1)
            try:
                # Proceed with write operation
                result = writer_func(lock_id)
                return result
            finally:
                # Always release the lock
                release_start = time.time()
                release_success = release_lock(s3_client, bucket_name, object_key, lock_id, request_id)
                release_time = time.time() - release_start
                
                if release_success:
                    log_event("info", "Successfully released lock", 
                              request_id=request_id,
                              bucket=bucket_name, 
                              object_key=object_key, 
                              lock_id=lock_id, 
                              release_time_seconds=round(release_time, 3))
                else:
                    log_event("warning", "Failed to release lock", 
                              request_id=request_id,
                              bucket=bucket_name, 
                              object_key=object_key, 
                              lock_id=lock_id, 
                              release_time_seconds=round(release_time, 3))
        else:
            log_event("warning", "Could not acquire lock", 
                      request_id=request_id,
                      bucket=bucket_name, 
                      object_key=object_key, 
                      attempt=attempt+1, 
                      max_attempts=max_attempts,
                      acquisition_attempt_time=round(lock_acquisition_time, 3))
    
    # If we get here, all attempts to acquire the lock have failed
    log_event("error", "Failed to acquire lock after all attempts", 
              request_id=request_id,
              bucket=bucket_name, 
              object_key=object_key, 
              max_attempts=max_attempts,
              total_wait_time_seconds=round(total_wait_time, 2))
    
    return {
        "status": "error",
        "message": f"Failed to acquire lock on {object_key} after {max_attempts} attempts",
        "bucket": bucket_name,
        "object_key": object_key
    }
