_TYPE_MAP = {
    'CharField': 'string',
    'TextField': 'string',
    'SmallIntegerField': 'int',
    'PositiveSmallIntegerField': 'int',
    'IntegerField': 'int',
    'PositiveIntegerField': 'int',
    'BigIntegerField': 'int',
    'DecimalField': 'float',
    'FloatField': 'float',
    'BooleanField': 'bool',
    'URLField': 'string',
    'EmailField': 'string',
    'DateField': 'date',
    'TimeField': 'date',
    'DateTimeField': 'date',
    'JSONField': 'object',
    'ArrayField': 'array',
    'IPAddressField': 'string',
    'GenericIPAddressField': 'string',
}


_FORMAT_MAP = {
    'URLField': 'url',
    'EmailField': 'email',
    'DateField': 'date',
    'TimeField': 'time',
    'DateTimeField': 'datetime',
    'IPAddressField': 'ip',
    'GenericIPAddressField': 'ip',
}


_MIN_MAP = {
    'SmallIntegerField': -32768,
    'PositiveSmallIntegerField': 0,
    'IntegerField': -2147483648,
    'PositiveIntegerField': 0,
    'BigIntegerField': -9223372036854775808,
}


_MAX_MAP = {
    'SmallIntegerField': 32767,
    'PositiveSmallIntegerField': 32767,
    'IntegerField': 2147483647,
    'PositiveIntegerField': 2147483647,
    'BigIntegerField': 9223372036854775807,
}


class ApiFieldRule(object):

    def __init__(self, field):
        # Only one rule set per field
        rule = {}
        type_name = field.__class__.__name__
        rule['type'] = _TYPE_MAP.get(type_name, 'string')
        if not field.choices:
            minimum = self._get_field_min(field)
            if minimum is not None:
                rule['min'] = minimum
            maximum = self._get_field_max(field)
            if maximum is not None:
                rule['max'] = maximum
            regex = self._get_regex(field)
            format = _FORMAT_MAP.get(type_name)
            if regex and format:
                rule['format'] = [format, regex]
            else:
                rule['format'] = format or regex

        if not field.blank:
            rule['required'] = True
        self.rule = rule

    def _get_regex(self, field):
        for validator in field.validators:
            if validator.__class__.__name__ == 'RegexValidator':
                return validator.regex.pattern

    def _get_field_min(self, field):
        for validator in field.validators:
            if validator.__class__.__name__ in ('MinValueValidator', 'MinLengthValidator'):
                return validator.limit_value
        type_name = field.__class__.__name__
        return _MIN_MAP.get(type_name)

    def _get_field_max(self, field):
        for validator in field.validators:
            if validator.__class__.__name__ in ('MaxValueValidator', 'MaxLengthValidator'):
                return validator.limit_value
        type_name = field.__class__.__name__
        return _MAX_MAP.get(type_name) or getattr(field, 'max_length', None)
