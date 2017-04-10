from germanium.rest import RESTTestCase


class PystonTestCase(RESTTestCase):

    USER_API_URL = '/api/user/'
    USER_WITH_FORM_API_URL = '/api/user-form/'
    ISSUE_API_URL = '/api/issue/'
    EXTRA_API_URL = '/api/extra/'
    COUNT_ISSUES_PER_USER = '/api/count-issues-per-user/'
    COUNT_WATCHERS_PER_ISSUE = '/api/count-watchers-per-issue/'
    TEST_CC_API_URL = '/api/test-cc/'

    user_id = 0
    issue_id = 0

    DATA_AMOUNT = 10

    def get_pk(self, resp):
        return self.deserialize(resp).get('id')

    def get_user_data(self, prefix=''):
        result = {'email': '%suser_%s@test.cz' % (prefix, self.user_id)}
        self.user_id += 1
        return result

    def get_issue_data(self, prefix=''):
        result = {'name': 'Issue %s' % self.issue_id, 'created_by': self.get_user_data(prefix),
                  'leader': self.get_user_data(prefix)}
        self.issue_id += 1
        return result

    def get_users_data(self, prefix='', flat=False):
        result = []
        for i in range(self.DATA_AMOUNT):
            if flat:
                result.append(self.get_user_data(prefix))
            else:
                result.append((i, self.get_user_data(prefix)))
        return result

    def get_issues_data(self, prefix='', flat=False):
        result = []
        for i in range(self.DATA_AMOUNT):
            result.append((i, self.get_issue_data(prefix)))
        return result

    def get_issues_and_users_data(self, prefix=''):
        result = []
        for i in range(self.DATA_AMOUNT):
            issue_data = self.get_issue_data(prefix)
            user_data = issue_data['created_by']
            del issue_data['created_by']
            result.append((i, issue_data, user_data))
        return result
