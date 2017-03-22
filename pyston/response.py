class HeadersResponse(object):

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
        super(RESTResponse, self).__init__(result={'messages': msg}, http_headers=http_headers, code=code)


class RESTOkResponse(NoFieldsetResponse):

    def __init__(self, msg, http_headers=None, code=200):
        http_headers = {} if http_headers is None else http_headers
        super(RESTOkResponse, self).__init__(result={'messages': {'success': msg}}, http_headers=http_headers,
                                             code=code)


class RESTCreatedResponse(HeadersResponse):

    def __init__(self, result, http_headers=None, code=201):
        http_headers = {} if http_headers is None else http_headers
        super(RESTCreatedResponse, self).__init__(result=result, http_headers=http_headers, code=code)


class RESTNoConetentResponse(NoFieldsetResponse):

    def __init__(self, http_headers=None, code=204):
        http_headers = {} if http_headers is None else http_headers
        super(RESTNoConetentResponse, self).__init__(result='', http_headers=http_headers, code=code)


class RESTErrorsResponse(HeadersResponse):

    def __init__(self, msg, http_headers=None, code=400):
        http_headers = {} if http_headers is None else http_headers
        super(RESTErrorsResponse, self).__init__(result={'messages': {'errors': msg}}, http_headers=http_headers,
                                                 code=code)


class RESTErrorResponse(NoFieldsetResponse):

    def __init__(self, msg, http_headers=None, code=400):
        http_headers = {} if http_headers is None else http_headers
        super(RESTErrorResponse, self).__init__(result={'messages': {'error': msg}}, http_headers=http_headers,
                                                code=code)
