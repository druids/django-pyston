from django.utils.translation import ugettext
from django.utils.encoding import force_text

from .forms import RESTDictError, RESTDictIndexError, RESTListError, RESTValidationError


class HeadersResponse:

    fieldset = True

    def __init__(self, result, http_headers=None, code=200):
        http_headers = {} if http_headers is None else http_headers
        self.result = result
        self.http_headers = http_headers
        self.status_code = code


class NoFieldsetResponse(HeadersResponse):

    fieldset = False


class RESTResponse(NoFieldsetResponse):

    def __init__(self, msg, http_headers=None, code=200):
        http_headers = {} if http_headers is None else http_headers
        super().__init__(result={'messages': msg}, http_headers=http_headers, code=code)


class RESTOkResponse(NoFieldsetResponse):

    def __init__(self, msg, http_headers=None, code=200):
        http_headers = {} if http_headers is None else http_headers
        super().__init__(
            result={'messages': {'success': msg}}, http_headers=http_headers, code=code
        )


class RESTCreatedResponse(HeadersResponse):

    def __init__(self, result, http_headers=None, code=201):
        http_headers = {} if http_headers is None else http_headers
        super().__init__(result=result, http_headers=http_headers, code=code)


class RESTNoContentResponse(NoFieldsetResponse):

    def __init__(self, http_headers=None, code=204):
        http_headers = {} if http_headers is None else http_headers
        super().__init__(result=None, http_headers=http_headers, code=code)


class RESTErrorsResponseMixin:

    def _get_errors(self, data):
        if isinstance(data, RESTDictIndexError):
            result = {
                '_index': data.index
            }
            result.update(self._get_errors(data.data))
            return result
        elif isinstance(data, (RESTDictError, dict)):
            return {
                key: self._get_errors(val) for key, val in data.items()
            }
        elif isinstance(data, (RESTListError, list, tuple)):
            return [self._get_errors(error) for error in data]
        else:
            return RESTValidationError(data).message


class RESTErrorsResponse(RESTErrorsResponseMixin, NoFieldsetResponse):

    def __init__(self, msg, http_headers=None, code=400):
        http_headers = {} if http_headers is None else http_headers
        super(RESTErrorsResponse, self).__init__(
            result={'messages': {'errors': self._get_errors(msg)}}, http_headers=http_headers, code=code
        )


class RESTErrorResponse(RESTErrorsResponseMixin, NoFieldsetResponse):

    def __init__(self, msg, http_headers=None, code=400):
        http_headers = {} if http_headers is None else http_headers
        super(RESTErrorResponse, self).__init__(
            result={'messages': {'error': self._get_errors(msg)}}, http_headers=http_headers, code=code
        )


class ResponseFactory:

    def __init__(self, response_class):
        self.response_class = response_class

    def get_response_kwargs(self, exception):
        raise NotImplementedError

    def get_response(self, exception):
        return self.response_class(**self.get_response_kwargs(exception))


class ResponseErrorFactory(ResponseFactory):

    def __init__(self, msg, code, response_class=RESTErrorResponse):
        super().__init__(response_class)
        self.msg = msg
        self.code = code

    def get_response_kwargs(self, exception):
        return {
            'msg': self.msg,
            'code': self.code,
        }


class ResponseExceptionFactory(ResponseFactory):

    def __init__(self, response_class, code=None):
        super().__init__(response_class)
        self.code = code

    def get_response_kwargs(self, exception):
        response_kwargs = {
            'msg': exception.message,
        }
        if self.code:
            response_kwargs['code'] = self.code
        return response_kwargs


class ResponseValidationExceptionFactory(ResponseFactory):

    def get_response_kwargs(self, exception):
        return {
            'msg': exception,
        }
