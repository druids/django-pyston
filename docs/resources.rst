Resource
========

Pyston resource class is a django view class for the REST endpoints. The simplies pyston resource class is ``pyston.resource.BaseResource``::

    from pyston.resource import BaseResource
    from pyston.response import RestNoContentResponse

    class CustomBaseResource(BaseResource):

        def get(self):
            """custom GET HTTP request implementation"""
            return {
                'custom': 'response'
            }

        def post(self):
            """custom POST HTTP request implementation"""
            input_data = self.get_dict_data()
            return {
                'custom': 'response'
            }

        def patch(self):
            """custom PATCH HTTP request implementation"""
            input_data = self.get_dict_data()
            return {
                'custom': 'response'
            }

        def delete(self):
            """custom DELETE HTTP request implementation"""
            return RestNoContentResponse()

HTTP methods can be implemented like get, post, patch, delete, head or options methods in the view class. The HTTP request will be automatically send to the right class method. These methods should return response object (``pyston.response.RestResponse``) or data which will be converted to the response (for example dict, list, string, etc.)

Request URL kwargs you can find in the ``self.kwargs`` property (with the same way as the django view).


Model resource
--------------

Pyston provides django model resource implementation which generates automatic REST responses according to the Django model::

    from pyston.resource import DjangoResource
    from users.models import User

    class DjangoResource(DjangoResource):

        model = User  # source model class
        can_create_obj = True  # allowed to create new object instance and POST HTTP method
        can_read_obj = True  # allowed to get object data and GET HTTP method
        can_update_obj = True  # allowed to update object data and PUT and PATH HTTP methods
        can_delete_obj = True  # allowed to delete object and DELETE HTTP method
        fields = ('username', 'email')  # the model fields accepted in request and returned in response
        order_fields = ('email',)  # model fields which can be used for ordering
        filter_fields = ('email',)  # model fields which can be used for filters

todo urls
todo form_fields, form_class
todo serializer
todo paginator
toto relations

