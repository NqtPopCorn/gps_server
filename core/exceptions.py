# core/exceptions.py
from traceback import print_exc
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    # DRF đã handle (ValidationError, NotFound,...)
    if response is not None:
        return Response({
            "error": "Request failed",
            "details": response.data,
            "status_code": response.status_code
        }, status=response.status_code)

    # Unhandled exception (500)
    print_exc()
    return Response({
        "error": "Internal server error",
        "details": str(exc)
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)