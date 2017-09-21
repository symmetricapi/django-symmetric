from django.apps import apps
from django.conf import settings
from django.db.models import Q, QuerySet

from .functions import sanitize_order_by, _get_api_model
from .response import set_response_headers

get_model = apps.get_model


"""
In Django 1.9 _clone method no longer allows a different class. Instead need to subclass the ModelIterable class
Differences described below when the queryset is iterated:
1.8:
__iter__ -> _fetch_all -> list(self.iterator()) -> key generator code (QuerySet.iterator) -> the remainder code provided below to cast objects (SubclassQuerySet.iterator)
1.9:
__iter__ -> _fetch_all -> list(self.iterator()) -> return iter(self._iterable_class(self)) -> key generator code (ModelIterable.__iter__()) is almost identical to the key generator code from 1.8 and can be wrapped the same

Since the Iterable class is not created until needed it is possible to simly replace it.
See for example the values() method:
clone._iterable_class = ValuesIterable
"""

class SubclassQuerySet(QuerySet):
	"""QuerySet that returns subclasses automatically when iterating."""
	def _clone(self, **kwargs):
		clone = super(SubclassQuerySet, self)._clone(**kwargs)
		clone._subclass_attrs = getattr(self, '_subclass_attrs', None)
		return clone
	def iterator(self):
		iter = super(SubclassQuerySet, self).iterator()
		for obj in iter:
			sub_obj = None
			for attr in self._subclass_attrs:
				if hasattr(obj, attr):
					sub_obj = getattr(obj, attr)
					break
			if sub_obj:
				yield sub_obj
			else:
				yield obj


def subclass_filter(*subclasses, **names):
	"""
	Convert the QuerySet to a SubclassQuerySet, where only the specified subclasses are returned and each object is cast to its subclass.
	The keyword arguments, has the names for the collection when generating files. name and name_plural provided as CamelCase are required.
	"""
	# TODO: To support multi-level inheritance, subclass_attrs needs find the common parent of all subclasses and will either be a dict tree of keys only (multi-level) or list (single).
	# The iterator() will then do multi-level getattr if isinstance(self._subclass_attrs, dict) otherwise use the existing code.
	# The select_related() part will also need to specify multi-level inheritance using intermediate__subclass strings
	subclasses = list(subclasses)
	for i, subclass in enumerate(subclasses):
		if isinstance(subclass, (str, unicode)):
			subclass = subclass.split('.')
			subclasses[i] = get_model(subclass[0], subclass[1])
	subclass_attrs = [cls.__name__.lower() for cls in subclasses]
	def subclass_filter_inner(request, queryset):
		set_response_headers(request, **{'X-Mixed-Results': True})
		queryset = queryset._clone(SubclassQuerySet).select_related(*subclass_attrs)
		# Remember the subclass arguments, because the queryset.query.select_related dict may have other non-subclass attributes
		queryset._subclass_attrs = subclass_attrs
		return queryset
	return subclass_filter_inner


def search_filter(request, queryset):
	"""Filter down the result by using a q query parameter. API.search_fields MUST be set to use this."""
	query = request.GET.get('q')
	if query and hasattr(queryset.model, 'API') and hasattr(queryset.model.API, 'search_fields') and queryset.model.API.search_fields:
		params = None
		for field in queryset.model.API.search_fields:
			if field.find('.'):
				field = field.replace('.', '__')
			if not params:
				params = Q(**{field + '__icontains': query})
			else:
				params = params | Q(**{field + '__icontains': query})
		queryset = queryset.filter(params)
	return queryset


def field_filter(request, queryset):
	"""Filter the results by named fields in the query string. API.filter_fields MUST be set to use this."""
	if len(request.GET) and hasattr(queryset.model, 'API'):
		if hasattr(queryset.model.API, 'filter_fields'):
			model = _get_api_model(queryset.model)
			for field in queryset.model.API.filter_fields:
				value = request.GET.get(field)
				if value:
					encoded_field = model.encoded_fields[field]
					key = encoded_field[0]
					decode = encoded_field[3]
					if decode:
						value = decode(value)
					queryset = queryset.filter(**{key: value})
		if hasattr(queryset.model.API, 'filters'):
			model = _get_api_model(queryset.model)
			for key in queryset.model.API.filters:
				value = request.GET.get(key)
				if value:
					filtr = queryset.model.API.filters[key]
					decoder = filtr.get('decoder')
					lookup = filtr['lookup']
					if decoder:
						value = decoder(value)
					if isinstance(lookup, (list, tuple)):
						params = None
						for l in lookup:
							if not params:
								params = Q(**{l: value})
							else:
								params = params | Q(**{l: value})
						queryset = queryset.filter(params)
					else:
						queryset = queryset.filter(**{lookup: value})
	return queryset


def order_by_filter(request, queryset):
	"""Order the results by using an orderby parameter."""
	order_by = sanitize_order_by(request.GET.get('orderby', ''))
	if order_by:
		if hasattr(queryset.model, 'API') and hasattr(queryset.model.API, 'order_by_fields') and queryset.model.API.order_by_fields:
			if order_by.lstrip('-') in queryset.model.API.order_by_fields:
				queryset = queryset.order_by(order_by)
		else:
			queryset = queryset.order_by(order_by)
	return queryset


__API_PAGE_SIZE = getattr(settings, 'API_PAGE_SIZE', 100)


def paginate_filter(request, queryset):
	"""Paginate the results based on page and pagesize parameters. This should be the last filter applied."""
	page = request.GET.get('page', 0)
	if not isinstance(page, int):
		if page.isdigit():
			page = int(page)
		else:
			return queryset.none()
	if hasattr(queryset.model, 'API') and hasattr(queryset.model.API, 'page_size'):
		max_page_size = queryset.model.API.page_size
	else:
		max_page_size = __API_PAGE_SIZE
	page_size = request.GET.get('pagesize', max_page_size)
	if not isinstance(page_size, int):
		if page_size.isdigit():
			page_size = int(page_size)
		else:
			return queryset.none()
	if page_size > max_page_size or page_size < 0:
		page_size = max_page_size
	start_index = page * page_size
	end_index = start_index + page_size
	total = queryset.count()
	total_pages = total/page_size + (1 if total % page_size else 0)
	set_response_headers(request, **{'X-Total': total, 'X-Total-Pages': total_pages, 'X-Page': page, 'X-Page-Size': page_size})
	if (page + 1) < total_pages:
		set_response_headers(request, **{'X-Next-Page': page + 1})
	if page:
		set_response_headers(request, **{'X-Prev-Page': page - 1})
	return queryset[start_index:end_index]


def combine_filters(*filters):
	"""Combine multiple filters into one."""
	def combine_filters_inner(request, queryset):
		for filter in filters:
			queryset = filter(request, queryset)
		return queryset
	return combine_filters_inner


def filter_as_authorization(model, filter):
	"""Create an authorization function based on a collection filter."""
	if isinstance(model, (str, unicode)):
		model = model.split('.')
		model = get_model(model[0], model[1])
	def filter_as_authorization_fun(request, obj):
		return filter(request, model.objects.all()).filter(id=obj.id).exists()
	filter_as_authorization_fun.__doc__ = "Only allow access to objects in the filter: %s" % (filter.__doc__ if filter.__doc__ else filter.__name__ + '()')
	return filter_as_authorization_fun
