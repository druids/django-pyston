.. _reverse_fields:

Reverse fields
==============

Pyston by default automaticaly creates reverse objects atomically if you add data to the request. For example if you add issue to the user creation request issue is automatically created::

    {
        "email": "user1@example.cz",
        "leading_issue": {
            "name": "example"
        }
    }

You can turn it off with parameter PYSTON_AUTO_REVERSE set to False.



Forms
-----

You can define reverse fields in your form manually (it works with turned off auto reverse too). As example we can use user form from example application::

    from pyston.forms import RESTModelForm, ReverseOneToOneField, ReverseStructuredManyField


    class UserForm(RESTModelForm):

        watched_issues = ReverseStructuredManyField('watched_issues')
        created_issues_renamed = ReverseStructuredManyField('created_issues')
        solving_issue_renamed = ReverseOneToOneField('solving_issue')
        leading_issue_renamed = ReverseOneToOneField('leading_issue')



Fields
------

There are several fields:

  * ReverseSingleField - For reverse one to many relation with posibility to add one object
  * ReverseOneToOneField - For reverse one to one relation
  * ReverseMultipleField - For reverse one to many relation with posibility to add more objects in list
  * ReverseStructuredMultipleField - For reverse one to many relation with posibility to add more objects in list or dictionary with parameters 'add', 'remove' or 'set'