.. _rest_meta:

RestMeta
========

Like Django Pyston allowes to define extra model configuration in meta class. For Pyston Meta class is named RestMeta. You can see its definition in short example::

    class User(models.Model):

        created_at = models.DateTimeField(verbose_name=_('created at'), null=False, blank=False, auto_now_add=True)
        email = models.EmailField(verbose_name=_('email'), null=False, blank=False, unique=True)
        contract = models.FileField(_('file'), null=True, blank=True, upload_to='documents/')
        is_superuser = models.BooleanField(_('is superuser'), default=True)
        first_name = models.CharField(_('first name'), null=True, blank=True, max_length=100)
        last_name = models.CharField(_('last name'), null=True, blank=True, max_length=100)

        class RestMeta:
            fields = ('created_at', 'email', 'contract', 'solving_issue', 'first_name', 'last_name', 'is_superuser')
            detailed_fields = ('created_at', '_obj_name', 'email', 'contract', 'solving_issue', 'first_name', 'last_name')
            general_fields = ('email', 'first_name', 'last_name')
            direct_serialization_fields = ('created_at', 'email', 'contract', 'solving_issue', 'first_name', 'last_name')


Access to rest meta values is throught ``rest_meta`` static parameter of the model::

    User._rest_meta.fields

.. attribute:: RestMeta.fields

With this attribute you can define which fields will be returned with the REST resource. If no ``detailed_fields``, ``general_fields`` or ``direct_serialization_fields`` these attributes are same as the ``fields`` attribute. ``fields`` attribute is not required.

.. attribute:: RestMeta.detailed_fields

The attribute defines witch fields will be returned from resource to request on the one concrete object by default. Client can define this fields itself with ``X-Fields`` header but if the header is empty is returned fields defined in ``detailed_fields``.

.. attribute:: RestMeta.general_fields

Defines default fields returned for client request to more objects of which fields can be serialized for object returned via foreign key.

.. attribute:: RestMeta.guest_fields

Defines fields that can be serialized for object to which the client has no right. It is used for situations when client has right to the object that has foreign key to forbidden object. By default it is::

    guest_fields = (OBJ_PK, '_obj_name')

.. attribute:: RestMeta.direct_serialization_fields

It defines fields that is serialized directly with ``serialize`` function without REST resource.

.. attribute:: RestMeta.default_fields

Attribute defines fields that must be returned always. These fields needn't be defined in ``detailed_fields``, ``general_fields`` or ``direct_serialization_fields`` but it is automatically added, by default it is::

    default_fields = (OBJ_PK, '_obj_name')

.. attribute:: RestMeta.extra_fields

Extra fields is used if you can allow to return more fields from REST but you don't want to return them by default. Client must sent request with ``X-Fields`` header for obtaining.

.. attribute:: RestMeta.filter_fields

Defines fields that is allowed for resource filtering.

.. attribute:: RestMeta.order_fields

Defines fields that is allowed for resource ordering.

.. attribute:: RestMeta.extra_filter_fields

Defines fields that extends default fields that is defined inside all model resources that is allowed for filtering.

.. attribute:: RestMeta.extra_order_fields

Defines fields that extends default fields that is defined inside all model resources that is allowed for ordering.