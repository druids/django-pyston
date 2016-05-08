class HeadersResponse(object):

    fieldset = True

    def __init__(self, result, http_headers={}, code=200):
        self.result = result
        self.http_headers = http_headers
        self.status_code = code


class NoFieldsetResponse(HeadersResponse):

    fieldset = False


class RESTResponse(NoFieldsetResponse):

    def __init__(self, msg, http_headers={}, code=200):
        super(RESTResponse, self).__init__(result={'messages': msg}, http_headers=http_headers, code=code)


class RESTOkResponse(NoFieldsetResponse):

    def __init__(self, msg, http_headers={}, code=200):
        super(RESTOkResponse, self).__init__(result={'messages': {'success': msg}}, http_headers=http_headers,
                                             code=code)


class RESTCreatedResponse(HeadersResponse):

    def __init__(self, result, http_headers={}, code=201):
        super(RESTCreatedResponse, self).__init__(result=result, http_headers=http_headers, code=code)


class RESTNoConetentResponse(NoFieldsetResponse):

    def __init__(self, http_headers={}, code=204):
        super(RESTNoConetentResponse, self).__init__(result='', http_headers=http_headers, code=code)


class RESTErrorsResponse(HeadersResponse):

    def __init__(self, msg, http_headers={}, code=400):
        super(RESTErrorsResponse, self).__init__(result={'messages': {'errors': msg}}, http_headers=http_headers,
                                                 code=code)


class RESTErrorResponse(NoFieldsetResponse):

    def __init__(self, msg, http_headers={}, code=400):
        super(RESTErrorResponse, self).__init__(result={'messages': {'error': msg}}, http_headers=http_headers,
                                                code=code)
