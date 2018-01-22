.. _forms:


REST form
=========

Pyston REST form adds some features that improve usability of Django form for REST purposes.


RESTMeta
--------

Similary to Django form Meta you can use RESTMeta where you can set these attributes

.. attribute:: RestMeta.resource_typemapper

Defines which resources will be used for concrete model for updating or creating related objects.

.. attribute:: RestMeta.auto_related_direct_fields

Turns on generation of pyston direct related fields. Default value is `False`.

.. attribute:: RestMeta.auto_related_reverse_fields

Turns on generation of pyston reverse related fields. Default value is `False`.


Direct fields
-------------

Because pyston supports atomic update (object can be updated with one request via another object resource) pyston adds related fields. These fields are automatically generated for `RESTModelForm` if `RestMeta.auto_related_reverse_fields` is set to `True`.

Pyston resources by default generates REST forms with `RestMeta.auto_related_direct_fields` set to `True`. You can change this behavior with setting `AUTO_RELATED_DIRECT_FIELDS`.

You can define direct fields in your form manually too (it also works with automatic direct field generation turned off)::

    from pyston.forms import RESTModelForm, SingleRelatedField, MultipleRelatedField

    class IssueForm(RESTModelForm):

        created_by = SingleRelatedField('created_by')
        leader = SingleRelatedField('leader')
        another_users = MultipleRelatedField('watched_by', form_field=forms.ModelMultipleChoiceField(
            queryset=User.objects.all(), required=False
        ))


You can see that inside `MultipleRelatedField` there is defined a form field. This way you can add fields that are not automatically generated from the model.

Fields
^^^^^^

There are following related fields:

  * SingleRelatedField - For one to many or one to one relation
  * MultipleRelatedField - For many to many relation
  * MultipleStructuredRelatedField - For many to many relation that provides possibilities to use add, remove or update keys

Reverse fields
--------------

Pyston by default automatically creates reverse objects atomically if you add data to the request. For example if you add issue to the user creation request issue is automatically created::

    {
        "email": "user1@example.cz",
        "leading_issue": {
            "name": "example"
        }
    }

Pyston resources by default generates REST forms with `RestMeta.auto_related_reverse_fields` set to `True`. You can change this behavior with setting `AUTO_RELATED_REVERSE_FIELDS`.

You can define reverse fields in your form manually too (it works with turned off auto reverse fields too). As AN example we can use user form from the example application::

    from pyston.forms import RESTModelForm, ReverseOneToOneField, ReverseStructuredManyField


    class UserForm(RESTModelForm):

        watched_issues = ReverseStructuredManyField('watched_issues')
        created_issues_renamed = ReverseStructuredManyField('created_issues')
        solving_issue_renamed = ReverseOneToOneField('solving_issue')
        leading_issue_renamed = ReverseOneToOneField('leading_issue')

Fields
^^^^^^

There are following reverse related fields:

  * ReverseSingleField - For reverse one to many relation with possibility to add one object
  * ReverseOneToOneField - For reverse one to one relation
  * ReverseMultipleField - For reverse one to many relation with possibility to add more objects in list
  * ReverseStructuredMultipleField - For reverse one to many relation with possibility to add more objects in list or dictionary with parameters 'add', 'remove' or 'set'. For example we use can the `UserForm` with field `created_issues_renamed` defined above. If you can add two new created issues you can send update to user REST (PUT) with this content::

        {"created_issues_renamed": {"add": [{"name": "issue1"}, {"name": "issue2"}]}}

    Or remove two old issues::

        {"created_issues_renamed": {"remove": [{"id": 1}, {"name": 2}]}}

    Or combination of previous::

        {"created_issues_renamed": {"add": [{"name": "issue1"}, {"name": "issue2"}], "remove": [{"id": 1}, {"name": 2}]}}

    Finally you can set concrete values::

        {"created_issues_renamed": {"set": [{"name": "issue1"}, {"name": "issue2"}, {"id": 1}, {"name": 2}]}}
