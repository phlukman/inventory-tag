"""
Circuit Breaker pattern implementation for AWS API calls
"""

import time
import threading
import logging
from functools import wraps
from botocore.exceptions import ClientError
from logs import logger

logger = logging.getLogger(__name__)
# Error codes that should trigger circuit breaker
CIRCUIT_BREAKER_ERRORS = frozenset([
    "ThrottlingException",
    "RequestThrottled",
    "TooManyRequestsException",
    "ServiceUnavailable",
    "InternalError",
    "ConnectionError",
    "EndpointConnectionError",
])


def extract_error_code(error):
    """Extract error code from a ClientError"""
    if isinstance(error, ClientError):
        return error.response.get("Error", {}).get("Code", "Unknown")
    return "Unknown"


class CircuitBreaker:
    """
    Circuit Breaker pattern implementation to prevent cascading failures
    when AWS API calls fail repeatedly.

    The circuit breaker has three states:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit is tripped, requests fail fast without calling the API
    - HALF-OPEN: Testing if the service has recovered

    Args:
        name (str): Name of the circuit breaker for identification
        failure_threshold (int): Number of failures before opening the circuit
        recovery_timeout (int): Seconds to wait before trying again (half-open state)
        reset_timeout (int): Seconds after which to reset failure count if no failures occur
    """

    # Circuit states as class constants
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF-OPEN"

    __slots__ = ('name', 'failure_threshold', 'recovery_timeout', 'reset_timeout',
                'state', 'failure_count', 'last_failure_time', 'last_success_time', '_lock')

    def __init__(
        self, name, failure_threshold=5, recovery_timeout=30, reset_timeout=60
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.reset_timeout = reset_timeout

        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.last_success_time = time.time()

        # Thread safety
        self._lock = threading.RLock()

        logger.info("Circuit breaker %s initialized in %s state", name, self.state)

    def allow_request(self):
        """
        Check if a request should be allowed based on the circuit state

        Returns:
            bool: True if the request should be allowed, False otherwise
        """
        with self._lock:
            current_time = time.time()

            # Reset failure count if no failures for reset_timeout
            if (
                self.state == self.CLOSED
                and self.failure_count > 0
                and current_time - self.last_failure_time > self.reset_timeout
            ):
                self.failure_count = 0
                logger.debug(
                    "Circuit '%s': Reset failure count after %ss with no failures",
                    self.name, self.reset_timeout
                )

            # If circuit is open, check if recovery_timeout has elapsed
            if self.state == self.OPEN:
                if current_time - self.last_failure_time > self.recovery_timeout:
                    logger.info(
                        "Circuit %s: Transitioning from OPEN to HALF-OPEN", self.name
                    )
                    self.state = self.HALF_OPEN
                    return True
                return False

            # Always allow requests in CLOSED or HALF-OPEN state
            return True

    def record_success(self):
        """
        Record a successful request

        Returns:
            str: The current state of the circuit
        """
        with self._lock:
            self.last_success_time = time.time()

            if self.state == self.HALF_OPEN:
                logger.info(
                    "Circuit %s: Success in HALF-OPEN state, closing circuit", self.name
                )
                self.state = self.CLOSED
                self.failure_count = 0

            return self.state

    def record_failure(self, error=None):
        """
        Record a failed request and potentially open the circuit

        Args:
            error: The exception that caused the failure

        Returns:
            str: The current state of the circuit
        """
        with self._lock:
            current_time = time.time()
            self.last_failure_time = current_time

            # Check if this is a circuit-breaker triggering error
            should_trigger = True
            if error is not None and isinstance(error, ClientError):
                error_code = extract_error_code(error)
                should_trigger = error_code in CIRCUIT_BREAKER_ERRORS

            if should_trigger:
                self.failure_count += 1

                if (
                    self.state == self.CLOSED
                    and self.failure_count >= self.failure_threshold
                ):
                    logger.warning(
                        "Circuit %s: Threshold reached (%d failures), opening circuit",
                        self.name, self.failure_count
                    )
                    self.state = self.OPEN
                elif self.state == self.HALF_OPEN:
                    logger.warning(
                        "Circuit %s: Failed in HALF-OPEN state, reopening circuit", self.name
                    )
                    self.state = self.OPEN

            return self.state

    def get_state(self):
        """Get the current state of the circuit breaker"""
        return self.state

    def reset(self):
        """Reset the circuit breaker to closed state"""
        with self._lock:
            self.state = self.CLOSED
            self.failure_count = 0
            self.last_failure_time = 0
            self.last_success_time = time.time()
            logger.info("Circuit %s: Manually reset to %s",
                self.name, self.state)
            return self.state


class CircuitBreakerDecorator:
    """
    Decorator for AWS API calls to implement circuit breaker pattern

    Args:
        circuit_breaker (CircuitBreaker): The circuit breaker to use
        fallback_function (callable, optional): Function to call when circuit is open
    """

    __slots__ = ('circuit_breaker', 'fallback_function')

    def __init__(self, circuit_breaker, fallback_function=None):
        self.circuit_breaker = circuit_breaker
        self.fallback_function = fallback_function

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not self.circuit_breaker.allow_request():
                logger.warning(
                    "Circuit %s is OPEN, fast failing", self.circuit_breaker.name
                )
                if self.fallback_function:
                    return self.fallback_function(*args, **kwargs)
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.circuit_breaker.name}' is OPEN"
                )

            try:
                result = func(*args, **kwargs)
                self.circuit_breaker.record_success()
                return result
            except Exception as e:
                self.circuit_breaker.record_failure(e)
                raise

        return wrapper


class CircuitBreakerOpenError(Exception):
    """Exception raised when a circuit breaker is open"""
    pass
