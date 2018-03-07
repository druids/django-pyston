class ResourceMetamodel:

    def __init__(self, resource):
        self.resource = resource

    def _request(self, obj):
        form = self.resource._get_form(inst=obj, initial=self.resource._get_form_initial(obj))
        result = {}
        for key, field in form.fields.items():

            choices = getattr(field, 'choices', None)
            if choices:
                choices = list(choices)

            result[key] = {
                'type': field.__class__.__name__,
                'is_required': field.required,
                'verbose_name': field.label,
                'initial': form[key].value(),
                'widget': field.widget.__class__.__name__,
                'help_text': field.help_text,
                'choices': choices,
            }
        return result

    def _get_resource_method_fields(self, fields):
        out = dict()
        # TODO
        for field in fields.flat():
            t = getattr(self.resource, str(field), None)
            if t and callable(t):
                out[field] = t
        return out

    def _get_model_fields(self):
        out = dict()
        for f in self.resource.model._meta.fields:
            out[f.name] = f
        return out

    def _get_m2m_fields(self):
        out = dict()
        for mf in self.resource.model._meta.many_to_many:
            if mf.serialize:
                out[mf.name] = mf
        return out

    def _response(self, obj):
        result = {}

        fields = self.resource.get_fields(obj)

        resource_method_fields = self._get_resource_method_fields(fields)
        model_fields = self._get_model_fields()
        m2m_fields = self._get_m2m_fields()
        for field_name in fields.flat():
            if field_name in resource_method_fields:
                result[field_name] = {
                    'type': 'method',
                    'verbose_name': getattr(resource_method_fields[field_name], 'short_description', None),
                }
            elif field_name in m2m_fields:
                result[field_name] = {
                    'type': m2m_fields[field_name].__class__.__name__,
                    'verbose_name': m2m_fields[field_name].verbose_name,
                }
            elif field_name in model_fields:
                result[field_name] = {
                    'type': model_fields[field_name].__class__.__name__,
                    'verbose_name': model_fields[field_name].verbose_name,
                }
            else:
                deskriptor = getattr(self.resource.model, field_name, None)
                if deskriptor and hasattr(deskriptor, 'related'):
                    result[field_name] = {
                        'type': deskriptor.__class__.__name__,
                    }
                else:
                    result[field_name] = {
                        'type': 'method',
                    }

        return result

    def get(self, obj):
        return {
            'RESPONSE': self._response(obj)
        }

    def post(self, obj):
        return {
            'REQUEST': self._request(obj),
            'RESPONSE': self._response(obj)
        }

    def put(self, obj):
        return {
            'REQUEST': self._request(obj),
            'RESPONSE': self._response(obj)
        }