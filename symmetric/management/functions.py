def get_doc_str(fun):
    """Get the doc string for a function and return a default if none is found."""
    if fun.__doc__:
        return '\n'.join([line.strip() for line in fun.__doc__.split('\n')])
    else:
        return 'No documentation provided for %s()' % fun.__name__


def get_base_classes(c):
    """Given a class, return all of its base classes as a list."""
    base_classes = list(c.__bases__)
    for b in list(base_classes):
        base_classes.extend(get_base_classes(b))
    return base_classes


def get_base_models(c):
    from django.db import models
    base_classes = get_base_classes(c)
    bases = []
    for cls in base_classes:
        if issubclass(cls, models.Model) and cls is not models.Model and not cls._meta.abstract:
            bases.append(cls)
    return bases


def get_base_model(c):
    bases = get_base_models(c)
    if bases:
        return bases[0]


def get_api_properties(model):
    """Given a model, gather all of its api properties."""
    properties = {}
    for cls in [model] + list(model._meta.get_parent_list()):
        for field_name in cls.__dict__:
            attr = cls.__dict__[field_name]
            if type(attr) is property and attr.fget and hasattr(attr.fget, 'api_code'):
                properties[field_name] = attr
    return properties


def get_resource_type(regex_stack, pattern):
    """Given a pattern, determine its type of 'Single Object', 'Object', or 'Collection'."""
    from symmetric.views import BasicApiView
    url = ''.join(regex_stack)
    view = pattern.callback
    single_object = False
    if getattr(view, 'parent_model', None):
        # For api_related_view, ApiRelatedView, or BasicApiView
        if isinstance(view, BasicApiView) and view.single_object:
            return 'Single Object'
        else:
            return 'Collection'
    else:
        # For api_view, ApiView, or BasicApiView (without a parent_model)
        if (url.find('<object_id>') == -1 and url.find('<slug>') == -1):
            if (isinstance(view, BasicApiView) and view.single_object) or (pattern.default_args.has_key('object_id') or pattern.default_args.has_key('slug')):
                return 'Single Object'
            else:
                return 'Collection'
        else:
            return 'Object'


def get_app_url_prefix(app_name, app_patterns):
    """Get the url prefix for an app's urls."""
    from importlib import import_module
    from django.conf import settings
    module_name = app_name.lower() + '.urls'
    module = import_module(settings.ROOT_URLCONF)
    for urlpattern in module.urlpatterns:
        # A RegexURLResolver object will have a _urlconf_module attribute that is either a module or a RegexURLPattern list matched up with the app_name or app_patterns
        if hasattr(urlpattern, '_urlconf_module'):
            if isinstance(urlpattern._urlconf_module, list):
                if urlpattern._urlconf_module is app_patterns:
                    return urlpattern._regex
            elif getattr(urlpattern._urlconf_module, '__name__', '').lower() == module_name:
                return urlpattern._regex
    return ''


def get_field(model, field_name):
    """Run get_field on the model, but detect _id as a fallback."""
    try:
        return model._meta.get_field(field_name)
    except Exception as e:
        if field_name.endswith('_id'):
            return model._meta.get_field(field_name[:-3])
        else:
            raise e


def has_field(model, field_name, include_inherited=True):
    try:
        field = model._meta.get_field(field_name)
        if include_inherited:
            return True
        else:
            return field.model is model
    except:
        return False


def get_subclass_filter(view):
    from symmetric.filters import subclass_filter, combine_filters
    filter = None
    def _from_combined(combined):
        for temp in combined.filters:
            if isinstance(temp, combine_filters):
                temp = _from_combined(temp)
            if isinstance(temp, subclass_filter):
                return temp
    if hasattr(view, 'filter'):
        if isinstance(view.filter, subclass_filter):
            filter = view.filter
        elif isinstance(view.filter, combine_filters):
            filter = _from_combined(view.filter)
    return filter


def get_model_name(model):
    """Given a model, return its CamelCase singular name."""
    return model.__name__


def get_model_name_plural(model):
    """Given a model, return its CamelCase plural name."""
    return verbose_to_camel_case(model._meta.verbose_name_plural)


def get_collection_name(view):
    """Given a view, return the CamelCase singular name of the collection."""
    filter = get_subclass_filter(view)
    if filter and filter.names and filter.names.has_key('name'):
        return filter.names['name']
    return get_model_name(view.model)


def get_collection_name_plural(view):
    """Given a view, return the CamelCase plural name of the collection."""
    filter = get_subclass_filter(view)
    if filter and filter.names:
        if filter.names.has_key('name_plural'):
            return filter.names['name_plural']
        elif filter.names.has_key('name'):
            return filter.names['name'] + 's'
    return get_model_name_plural(view.model)


def is_sublist(list, sublist):
    """Take a list and potential sublist and compare for membership."""
    # l = The length of each comparison
    # n = The number of equal length sublists in list
    l = len(sublist)
    n = len(list) - l + 1
    if n >= 1:
        for i in range(n):
            if sublist == list[i:i+l]:
                return True
    return False


def is_anonymous(view):
    """Returns True/False depending on if the view allows anonymous access or not."""
    from symmetric.views import ApiRequirement
    if hasattr(view, 'requirements'):
        if view.requirements & ApiRequirement.LOGIN and not view.requirements & ApiRequirement.ANONYMOUS_READ:
            return False
    return True


def is_auto_now(field_name, view):
    """Return True/False depending on if the field in this view is auto_now."""
    for field in view.model._meta.fields:
        if field.name == field_name:
            if hasattr(field, 'auto_now_add') and field.auto_now_add:
                return True
            if hasattr(field, 'auto_now') and field.auto_now:
                return True
    return False


def is_readonly(model, field_name):
    from symmetric.functions import _ApiModel
    api_model = _ApiModel(model)
    for decoded_name, encoded_name, encode, decode in api_model.fields:
        if field_name == decoded_name:
            return encoded_name not in api_model.encoded_fields
    return True


def is_excluded(model, field_name, flat=True):
    # Skip any ptr field to base models
    if field_name.endswith('_ptr_id'):
        return True
    # Skip any field that is not directly on model and is not the primary id field (which could be on the base too)
    if not flat:
        field = get_field(model, field_name)
        if field.model is not model and not field.primary_key:
            return True
    # Skip anything that is not an api field
    from symmetric.functions import _ApiModel
    api_model = _ApiModel(model)
    found = False
    for decoded_name, encoded_name, encode, decode in api_model.fields:
        if field_name == decoded_name:
            found = True
            break
    return not found


def is_included(model, field_name):
    from django.db.models.fields.related import ForeignKey
    include_related = hasattr(model, 'API') and hasattr(model.API, 'include_related') and field_name in model.API.include_related
    field = get_field(model, field_name)
    return (isinstance(field, ForeignKey) and include_related)


def format_regex_stack(regex_stack):
    """Format a list or tuple of regex url patterns into a single path."""
    import re
    formatted = ''.join(regex_stack)
    formatted = re.sub('\([^<]*(<[^>]*>).*?\)', '\\1', formatted)
    formatted = formatted.replace('^$','/')
    formatted = formatted.replace('^','/')
    formatted = formatted.replace('?$','/')
    formatted = formatted.replace('$','/')
    formatted = formatted.replace('//','/')
    return formatted


def lower_first(string):
    """Lower the first character of the string."""
    return string[0].lower() + string[1:]


def verbose_to_camel_case(string):
    """Covert a Verbose Model Name to CamelCaseModelName."""
    return ''.join([word.capitalize() for word in string.split(' ')])


def camel_case_to_verbose(string):
    """Convert a CamelCaseModelName to Verbose Model Name."""
    words = []
    start_index = 0
    for index, c in enumerate(string):
        # Ignore the first character
        if c.isupper() and index:
            words.append(string[start_index:index])
            start_index = index
    words.append(string[start_index:])
    return ' '.join(words)
