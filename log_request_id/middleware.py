import logging
import uuid

from django.conf import settings

from log_request_id import local, REQUEST_ID_HEADER_SETTING, LOG_REQUESTS_SETTING, DEFAULT_NO_REQUEST_ID, \
    REQUEST_ID_RESPONSE_HEADER_SETTING, GENERATE_REQUEST_ID_IF_NOT_IN_HEADER_SETTING, LOG_REQUESTS_NO_SETTING, \
    LOG_USER_ATTRIBUTE_SETTING


logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

        # `LOG_USER_ATTRIBUTE_SETTING` accepts False/None to skip setting attribute
        #  but falls back to 'pk' if value is not set
        self.log_user_attribute = getattr(settings, LOG_USER_ATTRIBUTE_SETTING, "pk")

        self.request_id_header = getattr(settings, REQUEST_ID_HEADER_SETTING, None)
        self.request_id_response_header = getattr(settings, REQUEST_ID_RESPONSE_HEADER_SETTING, False)
        self.log_requests = getattr(settings, LOG_REQUESTS_SETTING, False)

        # fallback to NO_REQUEST_ID if settings asked to use the
        # header request_id but none provided
        self.default_request_id = getattr(settings, LOG_REQUESTS_NO_SETTING, DEFAULT_NO_REQUEST_ID)

        # unless the setting GENERATE_REQUEST_ID_IF_NOT_IN_HEADER
        # was set, in which case generate an id as normal if it wasn't
        # passed in via the header
        self.generate_request_id_if_not_in_header = getattr(
            settings, GENERATE_REQUEST_ID_IF_NOT_IN_HEADER_SETTING, False
        )

    def __call__(self, request):
        local.request_id = request.id = request_id = self._get_request_id(request)

        response = self.get_response(request)

        if self.request_id_response_header:
            response[self.request_id_response_header] = request_id

        if self.log_requests and "favicon" not in request.path:
            logger.info(self.get_log_message(request, response))

        try:
            del local.request_id
        except AttributeError:
            pass

        return response

    def get_log_message(self, request, response):
        message = f"method={request.method} path={request.path} status={response.status_code}"

        if not self.log_user_attribute:
            return message

        # avoid accessing session if it is empty
        if getattr(request, "session", None) and request.session.is_empty():
            return message

        if not (user := getattr(request, "user", None)):
            return message

        user_id = getattr(user, self.log_user_attribute, None) or getattr(user, "id", None)
        message += f" user={user_id}"
        return message

    def _get_request_id(self, request):
        if self.request_id_header:
            default_request_id = self.default_request_id

            if self.generate_request_id_if_not_in_header:
                default_request_id = self._generate_id()

            return request.META.get(self.request_id_header, default_request_id)

        return self._generate_id()

    def _generate_id(self):
        return uuid.uuid4().hex
