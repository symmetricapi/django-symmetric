from django.apps import apps

import symmetric.filters
import symmetric.views
from symmetric.views import ApiAction, ApiRequirement


get_model = apps.get_model


"""
Override most of the api views to collect information about project's API.
This file must be imported before accessing any of the views getting overridden!
"""


class _api_view(object):

    def __init__(self, model, actions=ApiAction.READ, requirements=0, filter=None, authorization=None, verification=None):
        if isinstance(model, (str, unicode)):
            model = model.split('.')
            self.model = get_model(model[0], model[1])
        else:
            self.model = model
        self.actions = actions
        self.requirements = requirements
        self.filter = filter
        self.authorization = authorization
        self.verification = verification

    def __call__(self):
        # Empty call so that django will accept is as a view
        pass


class _subclass_filter(object):

    def __init__(self, *subclasses, **names):
        subclasses = list(subclasses)
        for i, subclass in enumerate(subclasses):
            if isinstance(subclass, (str, unicode)):
                subclass = subclass.split('.')
                subclasses[i] = get_model(subclass[0], subclass[1])
        self.subclasses = subclasses
        self.names = names

    def __str__(self):
        subclass_names = [cls.__name__ for cls in self.subclasses]
        return 'Generate a mixed result set of ' + ', '.join(subclass_names) + ' objects'


class _combine_filters(object):

    def __init__(self, *filters):
        self.filters = filters

    def __str__(self):
        info = []
        for filter in self.filters:
            if isinstance(filter, (_combine_filters, _subclass_filter)):
                info.extend(str(filter).split('\n'))
            else:
                info.append(get_doc_str(filter))
        return '\n'.join(info)


class _api_related_view(_api_view):

    def __init__(self, model, related_model, related_field, actions=ApiAction.READ, requirements=0, filter=None, authorization=None, verification=None):
        if isinstance(model, (str, unicode)):
            model = model.split('.')
            self.parent_model = get_model(model[0], model[1])
        else:
            self.parent_model = model
        self.related_field = related_field
        def related_view_filter():
            """Only return objects associated with the parent model."""
            pass
        if filter:
            filter = _combine_filters(related_view_filter, filter)
        else:
            filter = related_view_filter
        super(_api_related_view, self).__init__(related_model, actions, requirements, filter, authorization, verification)

    def __call__(self):
        # Empty call so that django will accept is as a view
        pass


class _api_filter_contacts_view(object):

    def __init__(self, requirements=ApiRequirement.LOGIN|ApiRequirement.HTTPS, fields=('email',)):
        self.requirements = requirements
        self.fields = fields
        self.__doc__ = _api_filter_contacts_view.doc

    def __call__(self):
        # Empty call so that django will accept is as a view
        pass


symmetric.views.api_view = _api_view
symmetric.views.api_related_view = _api_related_view
_api_filter_contacts_view.doc = symmetric.views.api_filter_contacts_view.__doc__
symmetric.views.api_filter_contacts_view = _api_filter_contacts_view
symmetric.filters.subclass_filter = _subclass_filter
symmetric.filters.combine_filters = _combine_filters
