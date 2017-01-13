from pyston.serializer import Serializable, SerializableObj

from .models import User


class CountIssuesPerUserTable(Serializable):

    def serialize(self, serialization_format, **kwargs):
        return [
            {
                'email': user.email,
                'created_issues_count': user.created_issues.count(),
            }
            for user in User.objects.all()
        ]


class CountWatchersPerIssue(SerializableObj):

    def __init__(self, issue):
        super(SerializableObj, self).__init__()
        self.name = issue.name
        self.watchers_count = issue.watched_by.count()

    class RESTMeta:
        fields = ('name', 'watchers_count')
