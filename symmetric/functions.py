import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone

def underscore_to_camel_case(string):
    words = [word.capitalize() for word in string.split('_')]
    words[0] = words[0].lower()
    return ''.join(words)

def camel_case_to_underscore(string):
    words = []
    start_index = 0
    for index, c in enumerate(string):
        # Ignore the first character regardless of case
        if c.isupper() and index:
            words.append(string[start_index:index].lower())
            start_index = index
    words.append(string[start_index:].lower())
    return '_'.join(words)

def sanitize_order_by(string):
    """Make sure the string has no double underscores, also convert from camelcase."""
    if string and string.find('__') == -1 and string.find('?') == -1:
        return camel_case_to_underscore(string)
    return ''

def iso_8601_to_time(iso):
    """Parse an iso 8601 date into a datetime.time."""
    if not iso:
        return None
    return datetime.datetime.strptime(iso, '%H:%M:%S').time()

def iso_8601_to_date(iso):
    """Parse an iso 8601 date into a datetime.date."""
    if not iso:
        return None
    return datetime.datetime.strptime(iso[:10], '%Y-%m-%d').date()

def iso_8601_to_datetime(iso):
    """Parse an iso 8601 string into a timezone aware datetime, ignoring and fractional seconds."""
    if not iso:
        return None
    dt = datetime.datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S')
    # strptime doesn't seem to handle timezones, parse them here
    if len(iso) == 19:
        return timezone.make_aware(dt, timezone.get_current_timezone())
    else:
        # Make the datetime UTC if Z is the timezone, ignoring fractional seconds in between
        if (len(iso) == 20 or iso[19] == '.') and iso[-1] == 'Z':
            return timezone.make_aware(dt, timezone.UTC())
        # Parse a complete timezone e.g. +00:00, checking for the correct length or ignored fractional seconds
        if (len(iso) == 25 or iso[19] == '.') and iso[-6] in ('+', '-') and iso[-3] == ':':
            try:
                hours = int(iso[-5:-3])
                minutes = int(iso[-2:])
                minutes += hours * 60
                if iso[-6] == '-':
                    minutes = -minutes
                return timezone.make_aware(dt, timezone.get_fixed_timezone(minutes))
            except:
                # drop through and raise the exception
                pass
        raise ValueError('Invalid timezone %s.' % iso[19:])

def time_to_iso_8601(t):
    """Format a datetime.time as an iso 8601 string - HH:MM:SS."""
    if t:
        return t.replace(microsecond=0).isoformat()
    else:
        return None

def date_to_iso_8601(d):
    """Format a datetime.date as an iso 8601 string - YYYY-MM-DD."""
    if d:
        return d.isoformat()
    else:
        return None

def datetime_to_iso_8601(dt):
    """Format a datetime as an iso 8601 string - YYYY-MM-DDTHH:MM:SS with optional timezone +HH:MM."""
    if dt:
        return dt.replace(microsecond=0).isoformat()
    else:
        return None

def decode_int(value):
    """Decode an int after checking to make sure it is not already a int, 0.0, or empty."""
    if isinstance(value, (int, long)):
        return value
    elif value == 0.0:
        return 0
    elif not value:
        return None
    return int(value)

def decode_float(value):
    """Decode a float after checking to make sure it is not already a float, 0, or empty."""
    if type(value) is float:
        return value
    elif value == 0:
        return 0.0
    elif not value:
        return None
    return float(value)

def decode_bool(value):
    """Decode a bool after checking to make sure it is not already a bool, int, or empty.

    If value is 0.0, None is returned because floats shouldn't be used.
    """
    t = type(value)
    if t is bool:
        return value
    elif t is int:
        return bool(value)
    elif not value:
        return None
    elif t in (str, unicode) and value.lower() in ('false', 'f', 'off', 'no'):
        return False
    return True

_api_models = {}

class _ApiModel(object):
    def __init__(self, model):
        # Tuples of (name, encoded_name, encode, decode)
        self.fields = []
        self.list_fields = []
        self.encoded_fields = {}
        self.id_field = None
        self.select_related_args = []
        # data dictionary, set fields instead of creating a new dictionary for each get_data
        self._data = {}
        self._list_data = {}
        include_fields = None
        exclude_fields = None
        include_related = ()
        list_fields = None
        update_fields = None
        readonly_fields = None
        camelcase = getattr(settings, 'API_CAMELCASE', True)
        renameid = getattr(settings, 'API_RENAME_ID', True)
        if hasattr(model, 'API'):
            if hasattr(model.API, 'include_fields'):
                include_fields = model.API.include_fields
            if hasattr(model.API, 'exclude_fields'):
                exclude_fields = model.API.exclude_fields
            if hasattr(model.API, 'include_related'):
                include_related = model.API.include_related
            if hasattr(model.API, 'list_fields'):
                list_fields = model.API.list_fields
            if hasattr(model.API, 'update_fields'):
                update_fields = model.API.update_fields
            if hasattr(model.API, 'readonly_fields'):
                readonly_fields = model.API.readonly_fields

        # Calculate all of the fields and list fields
        for field in model._meta.fields:
            if include_fields and field.name not in include_fields:
                continue
            elif exclude_fields and field.name in exclude_fields:
                continue
            else:
                name = field.name
                if field.name == 'id' and renameid:
                    encoded_name = camel_case_to_underscore(model.__name__) + '_id'
                else:
                    encoded_name = field.name
                if isinstance(field, models.IntegerField):
                    encode = None
                    decode = decode_int
                elif isinstance(field, models.FloatField):
                    encode = None
                    decode = decode_float
                elif isinstance(field, models.BooleanField):
                    encode = None
                    decode = decode_bool
                elif isinstance(field, models.DateTimeField):
                    encode = datetime_to_iso_8601
                    decode = iso_8601_to_datetime
                elif isinstance(field, models.TimeField):
                    encode = time_to_iso_8601
                    decode = iso_8601_to_time
                elif isinstance(field, models.DateField):
                    encode = date_to_iso_8601
                    decode = iso_8601_to_date
                elif isinstance(field, models.ForeignKey):
                    if field.name in include_related:
                        encode = get_object_data
                        decode = set_object_data
                        # Calculate the select_related_args
                        related_model = _get_api_model(field.rel.to)
                        if related_model.select_related_args:
                            for arg in related_model.select_related_args:
                                self.select_related_args.append('%s__%s' % (field.name, arg))
                        else:
                            self.select_related_args.append(field.name)
                        # For include related fields, also add an encoded_field entry for the option of updating the foreign key to another entry
                        # Setting the name_id attribute to None has the same effect as setting name to None, it will set the foreign key to null in the db
                        field_coding = (name + '_id', underscore_to_camel_case(encoded_name + '_id') if camelcase else encoded_name + '_id', None, decode_int)
                        self.encoded_fields[field_coding[1]] = field_coding
                    else:
                        name += '_id'
                        encoded_name += '_id'
                        encode = None
                        decode = decode_int
                        # For pointers to parent models, add as readonly field without the ptr suffix
                        if isinstance(field, models.OneToOneField) and encoded_name.endswith('_ptr_id'):
                            encoded_name = encoded_name[:-7] + '_id'
                            field_coding = (name, underscore_to_camel_case(encoded_name) if camelcase else encoded_name, None, decode_int)
                            self.fields.append(field_coding)
                            self.list_fields.append(field_coding)
                            continue
                elif isinstance(field, models.AutoField):
                    encode = None
                    decode = decode_int
                elif isinstance(field, (models.FileField, models.ManyToManyField)):
                    continue
                else:
                    encode = None
                    decode = None

                if camelcase:
                    field_coding = (name, underscore_to_camel_case(encoded_name), encode, decode)
                else:
                    field_coding = (name, encoded_name, encode, decode)
                self.fields.append(field_coding)
                if field.name == 'id':
                    self.id_field = field_coding
                if not field.editable or field.primary_key:
                    pass
                elif update_fields and field.name not in update_fields:
                    pass
                elif readonly_fields and field.name in readonly_fields:
                    pass
                else:
                    self.encoded_fields[field_coding[1]] = field_coding
                if list_fields is None or field.name in list_fields:
                    if field_coding[2] == get_object_data:
                        self.list_fields.append((field_coding[0], field_coding[1], get_object_list_data, field_coding[3]))
                    else:
                        self.list_fields.append(field_coding)

    def get_list_data(self, obj):
        for name, encoded_name, encode, decode in self.list_fields:
            if encode:
                self._list_data[encoded_name] = encode(getattr(obj, name))
            else:
                self._list_data[encoded_name] = getattr(obj, name)
        return self._list_data

    def get_data(self, obj):
        for name, encoded_name, encode, decode in self.fields:
            if encode:
                self._data[encoded_name] = encode(getattr(obj, name))
            else:
                self._data[encoded_name] = getattr(obj, name)
        return self._data

    def set_data(self, obj, data):
        for key, value in data.iteritems():
            if self.encoded_fields.has_key(key):
                name, encoded_name, encode, decode = self.encoded_fields[key]
                if decode:
                    if decode is set_object_data:
                        decode(getattr(obj, name), value)
                    else:
                        setattr(obj, name, decode(value))
                else:
                    setattr(obj, name, value)

def _get_api_model(model):
    key = model.__module__ + model.__name__
    if not _api_models.has_key(key):
        _api_models[key] = _ApiModel(model)
    return _api_models[key]

def get_object_list_data(obj):
    if obj is None:
        return None
    model = _get_api_model(type(obj))
    return model.get_list_data(obj)

def get_object_data(obj):
    if obj is None:
        return None
    model = _get_api_model(type(obj))
    data = model.get_data(obj)
    if hasattr(obj, '_exclude_data'):
        # Return a copy with specific data fields removed
        data = dict(data)
        for excluded in obj._exclude_data:
            del data[excluded]
    return data

def set_object_data(obj, data):
    model = _get_api_model(type(obj))
    model.set_data(obj, data)

def save_object(obj):
    model = type(obj)
    if hasattr(model, 'API') and hasattr(model.API, 'include_related'):
        for field in model.API.include_related:
            # Do a quick check for readonly status - this is for a slight performance boost only
            # There are other settings that can cause the sub-object to be readonly, but it's not enforced here
            if hasattr(model.API, 'readonly_fields') and field in model.API.readonly_fields:
                continue
            subobj = getattr(obj, field, None)
            if subobj:
                save_object(subobj)
    obj.full_clean()
    obj.save()
