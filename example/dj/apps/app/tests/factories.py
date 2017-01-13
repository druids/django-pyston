import factory
from factory import fuzzy

from app import models


class UserFactory(factory.django.DjangoModelFactory):

    first_name = factory.Sequence(lambda n: 'John{0}'.format(n))
    last_name = factory.Sequence(lambda n: 'Doe{0}'.format(n))
    email = factory.Sequence(lambda n: 'customer_{0}@example.com'.format(n).lower())

    class Meta:
        model = models.User


class IssueFactory(factory.django.DjangoModelFactory):

    name = factory.fuzzy.FuzzyText(length=100)
    created_by = factory.SubFactory('app.tests.factories.UserFactory')
    leader = factory.SubFactory('app.tests.factories.UserFactory')

    class Meta:
        model = models.Issue