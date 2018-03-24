from django.contrib.contenttypes.models import ContentType
from django.db.models.query import QuerySet


__METHOD_PERM_DICT = {
    'POST': 'add',
    'PUT': 'change',
    'PATCH': 'change',
    'DELETE': 'delete'
}


def default_permission_authorization(request, obj):
    """Check default permissions based on the object's model."""
    perm = __METHOD_PERM_DICT.get(request.method, None)
    if perm:
        content_type = ContentType.objects.get_for_model(obj.__class__)
        perm = '%s.%s_%s' % (content_type.app_label, perm, content_type.model)
        return request.user.has_perm(perm)
    return True


def superuser_exempt(filter_authorization_verification):
    """Decorator to exempt any superuser from filtering, authorization, or verification functions."""
    def superuser_exempt_fun(request, arg):
        if request.user.is_superuser:
            if isinstance(arg, QuerySet):
                return arg
            else:
                return True
        return filter_authorization_verification(request, arg)
    return superuser_exempt_fun
