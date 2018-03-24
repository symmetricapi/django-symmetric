
def api_property(code, return_type=int, translations=None):
    def api_property_fun(self):
        return eval(code)
    api_property_fun.api_code = code
    api_property_fun.api_type = return_type
    api_property_fun.api_translations = translations
    return property(api_property_fun)


def create_model(name, fields):
    from django.db import models
    """Create a model with a dict of named fields."""
    fields = dict(fields)
    fields['__module__'] = 'api.models'
    return type(name, (models.Model,), fields)


def clone_model(model, name):
    """Clone a model with same fields and subclasses, just changing the name. Requires 1.7+ for field.clone()"""
    fields = {'__module__': model.__module__}
    for field in model._meta.fields:
        if field.model is model and not field.auto_created:
            fields[field.name] = field.clone()
    # Clone the api properties
    for cls in [model] + list(model._meta.get_parent_list()):
        for field_name in cls.__dict__:
            attr = cls.__dict__[field_name]
            if type(attr) is property and attr.fget and hasattr(attr.fget, 'api_code'):
                fields[field_name] = api_property(attr.fget.api_code, attr.fget.api_type, attr.fget.api_translations)
    return type(name, model.__bases__, fields)


def get_related_model(field):
    try:
        return field.related.parent_model
    except AttributeError:
        # Django 1.8+
        return field.related.model
