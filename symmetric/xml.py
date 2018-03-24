import StringIO

from django.db.models import Model
from django.db.models.query import QuerySet
from django.utils.html import escape


def __get_array_tag(array, tag='values'):
    if isinstance(array, QuerySet):
        return array.model._meta.verbose_name_plural.replace(' ', '').lower()
    return tag


def __dump_value(t, value, tag, file, default=None):
    if issubclass(t, (str, unicode)):
        file.write('<%s>%s</%s>' % (tag, escape(value), tag))
    elif issubclass(t, bool):
        file.write('<%s>%s</%s>' % (tag, str(value).lower(), tag))
    elif issubclass(t, (int, long, float)):
        file.write('<%s>%s</%s>' % (tag, str(value), tag))
    elif value is None:
        file.write('<%s></%s>' % (tag, tag))
    else:
        # Unknown value
        if default:
            new_value = default(value)
            if new_value:
                t = type(new_value)
                if issubclass(t, dict):
                    tag = value.__class__.__name__.lower()
                    file.write('<%s>' % tag)
                    __dump_dict(new_value, file, default)
                    file.write('</%s>' % tag)
                elif issubclass(t, (tuple, list, set, QuerySet)):
                    tag = __get_array_tag(new_value, tag)
                    file.write('<%s>' % tag)
                    __dump_array(new_value, file, default)
                    file.write('</%s>' % tag)
                else:
                    __dump_value(t, new_value, tag, file, default)
        else:
            raise TypeError(repr(obj) + " is not serializable")


def __dump_dict(dictionary, file, default=None):
    """Output a dict."""
    for key, value in dictionary.items():
        t = type(value)
        if issubclass(t, dict):
            file.write('<%s>' % key)
            __dump_dict(value, file, default)
            file.write('</%s>' % key)
        elif issubclass(t, (tuple, list, set, QuerySet)):
            file.write('<%s>' % key)
            __dump_array(value, file, default)
            file.write('</%s>' % key)
        else:
            __dump_value(t, value, key, file, default)


def __dump_array(array, file, default=None):
    """Output an array."""
    for value in array:
        t = type(value)
        if issubclass(t, dict):
            file.write('<values>')
            __dump_dict(value, file, default)
            file.write('</values>')
        elif issubclass(t, (tuple, list, set, QuerySet)):
            tag = __get_array_tag(value)
            file.write('<%s>' % tag)
            __dump_array(value, file, default)
            file.write('</%s>' % tag)
        else:
            __dump_value(t, value, 'value', file, default)


def dumps(data, file=None, default=None):
    """Similar to json.dumps, will return an xml string."""
    if file:
        output = file
    else:
        output = StringIO.StringIO()
    output.write('<?xml version="1.0" encoding="UTF-8" ?>')
    t = type(data)
    if issubclass(t, dict):
        output.write('<data>')
        __dump_dict(data, output, default)
        output.write('</data>')
    elif issubclass(t, (tuple, list, set, QuerySet)):
        output.write('<data>')
        __dump_array(data, output, default)
        output.write('</data>')
    else:
        __dump_value(t, data, 'data', output, default)
    if not file:
        return output.getvalue()
