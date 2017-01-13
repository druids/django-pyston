.. _serializers:

Serializers
===========

Returned data from resource is firstly serialized to python format via serializers. Serialization is performed recursively for complex data types (list, dict, tuple, django Model, django Queryset, etc.). Next step of serialization is converting python format response to the required format (JSON, XML, XLSX, etc.). For this purpose, :ref:`converters` are used.

There are several serializers -- each one is used to serialize a different data type to get the Python format:

 * ``StringSerializer`` - converts all string formats and escapes insecure HTML marks.
 * ``DateTimeSerializer`` - serialize datetime and date data, automatically add server timezone.
 * ``DictSerializer`` - recursively serializes dict content to the dict that contains only data in python format.
 * ``CollectionsSerializer`` - recursively serializes list, tuple or set content to the generator that contains only data in python format.
 * ``DecimalSerializer`` - serializes decimal data.
 * ``RawVerboseSerializer`` - Pyston allows return data in three formats RAW, VERBOSE or BOTH. RAW value is the value that is stored inside database, VERBOSE is hummanized (human readable) value. The format is selected via ``serialization_format`` property (can be set via HTTP header X-Serialization-Format header). The RawVerboseSerializer determines which of these formats should be used using RawVerboseValue class.
 * ``SerializableSerializer`` - this serializer is used for custom serialization formats :ref:`serializable`.
 * ``ModelSerializer`` - serializes Django Model and Queryset class. It is the most complex serializer in the Pyston. It allows serialize model or resource fields, methods and properties.
 * ``ResourceSerializer`` - serializer of the concrete resource. It can be used for the resource serialization results.
 * ``ModelResourceSerializer`` - resource serializer that inherit from ``ModelSerializer`` and is used for Django model resources.

Custom serializer
-----------------

Custom serializer can be added very easily with registration decorator that contains data type that you want to serialize::

    from pyston.serializer import Serializer, register

    @register(custom_data_type)
    class CustomSerializer(Serializer):

        def serialize(self, data, serialization_format, **kwargs):
            return # custom serialization



.. _serializable:

Serializable
------------

If you don't want to implement custom serializer you can use ``Serializable`` mixin for your class. You must only implement ``serialize`` method that returns data in pure python format. We can use serializable class from example application that serializes count issues per user in our Issue tracker::

    from pyston.serializer import Serializable

    class CountIssuesPerUserTable(Serializable):

        def serialize(self, serialization_format, **kwargs):
            return [
                {
                    'email': user.email,
                    'created_issues_count': user.created_issues.count(),
                }
                for user in User.objects.all()
            ]


SerializableObj
---------------

As simplification you can use SerializableObj that serializes data from class properties according to RESTMeta field parameter::


    from pyston.serializer import SerializableObj

    class CountWatchersPerIssue(SerializableObj):

        def __init__(self, issue):
            super(SerializableObj, self).__init__()
            self.name = issue.name
            self.watchers_count = issue.watched_by.count()

        class RESTMeta:
            fields = ('name', 'watchers_count')
