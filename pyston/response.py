from .forms import RestDictError, RestDictIndexError, RestListError, RestValidationError


class HeadersResponse:

    fieldset = True

    def __init__(self, result, http_headers=None, code=200):
        http_headers = {} if http_headers is None else http_headers
        self.result = result
        self.http_headers = http_headers
        self.status_code = code


class NoFieldsetResponse(HeadersResponse):

    fieldset = False


class RestResponse(NoFieldsetResponse):

    def __init__(self, msg, http_headers=None, code=200):
        http_headers = {} if http_headers is None else http_headers
        super().__init__(result={'messages': msg}, http_headers=http_headers, code=code)


class RestOkResponse(NoFieldsetResponse):

    def __init__(self, msg, http_headers=None, code=200):
        http_headers = {} if http_headers is None else http_headers
        super().__init__(
            result={'messages': {'success': msg}}, http_headers=http_headers, code=code
        )


class RestCreatedResponse(HeadersResponse):

    def __init__(self, result, http_headers=None, code=201):
        http_headers = {} if http_headers is None else http_headers
        super().__init__(result=result, http_headers=http_headers, code=code)


class RestNoContentResponse(NoFieldsetResponse):

    def __init__(self, http_headers=None, code=204):
        http_headers = {} if http_headers is None else http_headers
        super().__init__(result=None, http_headers=http_headers, code=code)


class RestErrorsResponseMixin:

    def _get_errors(self, data):
        if isinstance(data, RestDictIndexError):
            result = {
                '_index': data.index
            }
            result.update(self._get_errors(data.data))
            return result
        elif isinstance(data, (RestDictError, dict)):
            return {
                key: self._get_errors(val) for key, val in data.items()
            }
        elif isinstance(data, (RestListError, list, tuple)):
            return [self._get_errors(error) for error in data]
        else:
            return RestValidationError(data).message


class RestErrorsResponse(RestErrorsResponseMixin, NoFieldsetResponse):

    def __init__(self, msg, http_headers=None, code=400):
        http_headers = {} if http_headers is None else http_headers
        super(RestErrorsResponse, self).__init__(
            result={'messages': {'errors': self._get_errors(msg)}}, http_headers=http_headers, code=code
        )


class RestErrorResponse(RestErrorsResponseMixin, NoFieldsetResponse):

    def __init__(self, msg, http_headers=None, code=400):
        http_headers = {} if http_headers is None else http_headers
        super(RestErrorResponse, self).__init__(
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

    def __init__(self, msg, code, response_class=RestErrorResponse):
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
