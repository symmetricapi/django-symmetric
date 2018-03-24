import hashlib
import hmac

from django.apps import apps
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db import IntegrityError
from django.db.models.signals import post_delete
from django.db.utils import DEFAULT_DB_ALIAS
from django.http import HttpResponse
from django.utils.http import urlencode
from django.views.decorators.csrf import csrf_exempt

from symmetric.filters import filter_as_authorization
from symmetric.functions import set_object_data, save_object, _get_api_model
from symmetric.response import render_error, render_data, render_empty, set_response_headers
from symmetric.exceptions import InsufficientRoleApiException


get_model = apps.get_model


class ApiAction(object):
    _UNKNOWN = 0
    READ = 1
    CREATE = 2
    UPDATE = 4
    DELETE = 8
    ALL = 15


class ApiRequirement(object):
    LOGIN = 1
    STAFF = 2
    SUPERUSER = 4
    JSONP = 8
    ANONYMOUS_READ = 16
    HMAC = 32
    HTTPS = 64
    NON_USER_REQUIREMENTS = ANONYMOUS_READ | HMAC | HTTPS


__ERROR_BAD_REQUEST = 'Bad request'
__ERROR_NOT_ALLOWED = _ERROR_NOT_ALLOWED = 'Method not allowed'
__ERROR_NOT_AUTHORIZED = 'Not authorized'
__ERROR_NOT_FOUND = 'Not found'
__ERROR_VERIFICATION = 'One or more fields were set with incorrect or unauthorized values'
__ERROR_JSONP = 'JSONP requests on this resource are not allowed'
__ERROR_BAD_CREDENTIALS = 'Incorrect username or password'
__ERROR_INACTIVE_ACCOUNT = 'Account is not active'
__ERROR_AUTH_CHALLENGE = 'Further authentication is required'
__ERROR_HMAC = 'Invalid HMAC'
__ERROR_HTTPS = 'HTTPS is required'
__ERROR_USERNAME_TAKEN = 'Username is already taken'
__ERROR_PASSWORD_MISMATCH = 'Passwords do not match'

__X_HEADER_NEW_OBJECT_ID = 'X-New-Object-Id'
__X_HEADER_USER_ID = 'X-User-Id'


def __exception_error_message(e):
    # NOTE: ValidationError has a message_dict property that could be inspected more deeply but it also has a
    # messages list - just return the first reported error from messages.
    if hasattr(e, 'message') and e.message:
        return e.message
    elif hasattr(e, 'messages') and e.messages:
        return e.messages[0]
    elif e.args:
        return e.args[0]
    else:
        return 'An unknown error occured'


# HMAC key and salt both as encoded byte strings that hmac requires
__API_HMAC_KEY = getattr(settings, 'API_HMAC_KEY', settings.SECRET_KEY)
if type(__API_HMAC_KEY) is unicode:
    __API_HMAC_KEY = __API_HMAC_KEY.encode('utf-8')
__API_HMAC_SALT = getattr(settings, 'API_HMAC_SALT', '')
if type(__API_HMAC_SALT) is unicode:
    __API_HMAC_SALT = __API_HMAC_SALT.encode('utf-8')


def __check_hmac(request):
    """Perform the hmac check."""
    if request.META.has_key('HTTP_X_HMAC'):
        # NOTE: request.body is already a raw byte string (that hmac requires) not a unicode object
        nonce = request.META.get('HTTP_X_HMAC_NONCE', '')
        if type(nonce) is unicode:
            nonce = nonce.encode('utf-8')
        message = request.body + __API_HMAC_SALT + nonce
        code = hmac.new(__API_HMAC_KEY, message, hashlib.sha256)
        if code.hexdigest() == request.META['HTTP_X_HMAC']:
            return True
    return False


def _check_requirements(request, requirements):
    if requirements & ApiRequirement.ANONYMOUS_READ and request.api_action == ApiAction.READ:
        # For an anonymous read, ignore any other user requirements and regardless of request.user.is_anonymous()
        requirements = requirements & ApiRequirement.NON_USER_REQUIREMENTS
    if requirements & ApiRequirement.LOGIN:
        if not request.user.is_authenticated():
            return render_error(request, __ERROR_NOT_AUTHORIZED, 401)
        elif not request.user.is_active:
            return render_error(request, __ERROR_INACTIVE_ACCOUNT, 403)
    if requirements & ApiRequirement.STAFF and (not request.user.is_staff or not request.user.is_active):
        return render_error(request, __ERROR_NOT_AUTHORIZED, 403)
    if requirements & ApiRequirement.SUPERUSER and (not request.user.is_superuser or not request.user.is_active):
        return render_error(request, __ERROR_NOT_AUTHORIZED, 403)
    if type(request.api_json) is not bool and not requirements & ApiRequirement.JSONP:
        return render_error(request, __ERROR_JSONP, 403)
    if requirements & ApiRequirement.HMAC and (request.api_action == ApiAction.CREATE or request.api_action == ApiAction.UPDATE) and not __check_hmac(request):
        return render_error(request, __ERROR_HMAC, 403)
    if requirements & ApiRequirement.HTTPS and not request.is_secure() and not settings.DEBUG:
        if request.api_action == ApiAction.READ:
            response = render_error(request, __ERROR_HTTPS, 301)
            response['Location'] = request.build_absolute_uri(request.get_full_path()).replace('http://', 'https://')
        else:
            # Information may have been compromised, so don't redirect
            response = render_error(request, __ERROR_HTTPS, 403)
        return response
    return None


class BasicApiView(object):
    """Basic api view, that allows custom actions to mapped to instance methods of: read, create, update, and delete."""

    _ACTION_DICT = {
        ApiAction.READ: 'read',
        ApiAction.CREATE: 'create',
        ApiAction.UPDATE: 'update',
        ApiAction.DELETE: 'delete'
    }

    # Set single_object to True if the view only returns on object instead of an collection
    # when there is no object_id or slug argument in the URL - used only for management scripts to inspect
    single_object = False
    requirements = 0

    def __call__(self, request, object_id=None, slug=None):
        # Is the action allowed
        action_method = getattr(self, BasicApiView._ACTION_DICT.get(request.api_action, ''), None)
        if not callable(action_method):
            return render_error(request, _ERROR_NOT_ALLOWED, 405)

        # Does the user pass the requirements
        if self.requirements:
            response = _check_requirements(request, self.requirements)
            if response:
                return response

        return action_method(request, object_id, slug)

    @property
    def actions(self):
        """Actions for management scripts to inspect."""
        actions = 0
        for action, method in BasicApiView._ACTION_DICT.iteritems():
            if hasattr(self, method):
                actions |= action
        return actions

    @property
    def filter(self):
        """Override and return a filter for management scripts to inspect."""
        return None

    @property
    def authorization(self):
        """Override and return an authorization for management scripts to inspect."""
        return None

    @property
    def verification(self):
        """Override and return a verification for management scripts to inspect."""
        return None

    @property
    def parent_model(self):
        """
        Override and return a the parent model for management scripts to inspect and generate
        client connection code treated similar to an api_related_view.
        """
        return None

    @property
    def model(self):
        """Override and return a model for management scripts to inspect."""
        return None


def api_view(model, actions=ApiAction.READ, requirements=0, filter=None, authorization=None, verification=None):
    """Generate an api_view with certain requirements and options."""
    if isinstance(model, (str, unicode)):
        model = model.split('.')
        model = get_model(model[0], model[1])
    slug_field = 'slug'
    deleted_field = None
    nonce_field = None
    request_user_field = None
    request_ip_field = None
    if not authorization and filter:
        authorization = filter_as_authorization(model, filter)
    if hasattr(model, 'API'):
        if hasattr(model.API, 'slug_field'):
            slug_field = model.API.slug_field
        if hasattr(model.API, 'deleted_field'):
            deleted_field = model.API.deleted_field
        if hasattr(model.API, 'nonce_field') and requirements & ApiRequirement.HMAC:
            nonce_field = model.API.nonce_field
        if hasattr(model.API, 'request_user_field'):
            request_user_field = model.API.request_user_field
        if hasattr(model.API, 'request_ip_field'):
            request_ip_field = model.API.request_ip_field

    def api_view_inner(request, object_id=None, slug=None):
        """The api view that automatically processes RESTful requests."""
        if object_id:
            object_id = int(object_id)

        # Is the action allowed
        if not request.api_action & actions:
            return render_error(request, __ERROR_NOT_ALLOWED, 405)

        # Does the user pass the requirements
        if requirements:
            response = _check_requirements(request, requirements)
            if response:
                return response

        if not request.api:
            return render_error(request, __ERROR_BAD_REQUEST, 400)
        elif request.api_action == ApiAction.READ:
            # Get an existing object or collection
            if object_id or slug:
                try:
                    select_related_args = _get_api_model(model).select_related_args
                    if select_related_args:
                        if object_id:
                            obj = model.objects.select_related(*select_related_args).get(id=object_id)
                        else:
                            obj = model.objects.select_related(*select_related_args).get(**{slug_field: slug})
                    else:
                        if object_id:
                            obj = model.objects.get(id=object_id)
                        else:
                            obj = model.objects.get(**{slug_field: slug})
                    if deleted_field and getattr(obj, deleted_field):
                        return render_error(request, __ERROR_NOT_FOUND, 404)
                    if callable(authorization) and not authorization(request, obj):
                        return render_error(request, __ERROR_NOT_AUTHORIZED, 403)
                except InsufficientRoleApiException as e:
                    return render_error(request, e.message, 401)
                except:
                    return render_error(request, __ERROR_NOT_FOUND, 404)
                else:
                    return render_data(request, obj)
            else:
                # Get a collection
                select_related_args = _get_api_model(model).select_related_args
                if select_related_args:
                    if callable(filter):
                        queryset = filter(request, model.objects.select_related(*select_related_args))
                    else:
                        queryset = model.objects.select_related(*select_related_args).all()
                else:
                    if callable(filter):
                        queryset = filter(request, model.objects.all())
                    else:
                        queryset = model.objects.all()
                if deleted_field:
                    queryset = queryset.filter(**{deleted_field: False})
                return render_data(request, queryset)
        elif request.api_action == ApiAction.CREATE:
            # Create a new object on a collection only
            if object_id or slug:
                return render_error(request, __ERROR_NOT_ALLOWED, 405)
            else:
                try:
                    obj = model()
                    set_object_data(obj, request.POST)
                    if nonce_field:
                        nonce = request.META.get('HTTP_X_HMAC_NONCE', None)
                        if nonce:
                            setattr(obj, nonce_field, nonce)
                        else:
                            return render_error(request, __ERROR_HMAC, 403)
                    if request_user_field and not request.user.is_anonymous():
                        setattr(obj, request_user_field, request.user)
                    if request_ip_field:
                        setattr(obj, request_ip_field, request.META['REMOTE_ADDR'])
                    if request.POST.get('_data'):
                        obj._data = request.POST['_data']
                    if callable(verification) and not verification(request, obj):
                        return render_error(request, __ERROR_VERIFICATION, 500)
                    save_object(obj)
                except InsufficientRoleApiException as e:
                    return render_error(request, e.message, 401)
                except Exception as e:
                    return render_error(request, '%s: %s' % (e.__class__.__name__, __exception_error_message(e)), 500)
                set_response_headers(request, **{__X_HEADER_NEW_OBJECT_ID: obj.id})
                return render_data(request, {_get_api_model(model).id_field[1]: obj.id}, 201)
        elif request.api_action == ApiAction.UPDATE:
            # Update an existing object only
            if object_id or slug:
                try:
                    select_related_args = _get_api_model(model).select_related_args
                    if select_related_args:
                        if object_id:
                            obj = model.objects.select_related(*select_related_args).get(id=object_id)
                        else:
                            obj = model.objects.select_related(*select_related_args).get(**{slug_field: slug})
                    else:
                        if object_id:
                            obj = model.objects.get(id=object_id)
                        else:
                            obj = model.objects.get(**{slug_field: slug})
                    if callable(authorization) and not authorization(request, obj):
                        return render_error(request, __ERROR_NOT_AUTHORIZED, 403)
                except InsufficientRoleApiException as e:
                    return render_error(request, e.message, 401)
                except:
                    return render_error(request, __ERROR_NOT_FOUND, 404)
                else:
                    try:
                        set_object_data(obj, request.PUT)
                        if request_user_field and not request.user.is_anonymous():
                            setattr(obj, request_user_field, request.user)
                        if request_ip_field:
                            setattr(obj, request_ip_field, request.META['REMOTE_ADDR'])
                        if request.PUT.get('_data'):
                            obj._data = request.PUT['_data']
                        if callable(verification) and not verification(request, obj):
                            return render_error(request, __ERROR_VERIFICATION, 500)
                        save_object(obj)
                    except InsufficientRoleApiException as e:
                        return render_error(request, e.message, 401)
                    except Exception as e:
                        return render_error(request, '%s: %s' % (e.__class__.__name__, __exception_error_message(e)), 500)
                    return render_empty(request)
            else:
                return render_error(request, __ERROR_NOT_ALLOWED, 405)
        elif request.api_action == ApiAction.DELETE:
            # Delete an existing object only
            if object_id or slug:
                try:
                    if object_id:
                        obj = model.objects.get(id=object_id)
                    else:
                        obj = model.objects.get(**{slug_field: slug})
                    if callable(authorization) and not authorization(request, obj):
                        return render_error(request, __ERROR_NOT_AUTHORIZED, 403)
                except InsufficientRoleApiException as e:
                    return render_error(request, e.message, 401)
                except Exception:
                    return render_error(request, __ERROR_NOT_FOUND, 404)
                else:
                    if deleted_field:
                        # Set as deleted only if it is not already
                        if not getattr(obj, deleted_field):
                            setattr(obj, deleted_field, True)
                            obj.save(update_fields=(deleted_field,))
                            # Send the post_delete signal
                            post_delete.send_robust(sender=obj.__class__, instance=obj, using=DEFAULT_DB_ALIAS)
                    else:
                        obj.delete()
                    return render_empty(request)
            else:
                return render_error(request, __ERROR_NOT_ALLOWED, 405)

    return api_view_inner


def api_related_view(model, related_model, related_field, actions=ApiAction.READ, requirements=0, filter=None, authorization=None, verification=None):
    """
    Returns a view got getting a collection of related elements, or POSTing a new one. Other operations are not allowed.
    """

    # Do not allow UPDATE or DELETE
    if actions & ApiAction.UPDATE:
        actions -= ApiAction.UPDATE
    if actions & ApiAction.DELETE:
        actions -= ApiAction.DELETE

    if isinstance(model, (str, unicode)):
        model = model.split('.')
        model = get_model(model[0], model[1])
    if isinstance(related_model, (str, unicode)):
        related_model = related_model.split('.')
        related_model = get_model(related_model[0], related_model[1])
    slug_field = 'slug'
    deleted_field = None
    if hasattr(model, 'API'):
        if hasattr(model.API, 'slug_field'):
            slug_field = model.API.slug_field
        if hasattr(model.API, 'deleted_field'):
            deleted_field = model.API.deleted_field

    nonce_field = None
    request_user_field = None
    request_ip_field = None
    if hasattr(related_model, 'API'):
        if hasattr(related_model.API, 'nonce_field') and requirements & ApiRequirement.HMAC:
            nonce_field = related_model.API.nonce_field
        if hasattr(related_model.API, 'request_user_field'):
            request_user_field = related_model.API.request_user_field
        if hasattr(related_model.API, 'request_ip_field'):
            request_ip_field = related_model.API.request_ip_field

    def api_related_view_filter(request, queryset):
        if request.api_related_id:
            queryset = queryset.filter(**{related_field + '_id': request.api_related_id})
        else:
            queryset = queryset.filter(**{related_field + '__' + slug_field: request.api_related_slug})
        if callable(filter):
            queryset = filter(request, queryset)
        return queryset

    related_view = api_view(related_model, actions, requirements=0, filter=api_related_view_filter)

    def api_related_view_inner(request, object_id=None, slug=None):
        if object_id:
            object_id = int(object_id)

        # Is the action allowed, will be repeated in related_view, but that is ok
        if not request.api_action & actions:
            return render_error(request, __ERROR_NOT_ALLOWED, 405)

        # Does the user pass the requirements, won't be repeated in related_view, because requirements=0
        if requirements:
            response = _check_requirements(request, requirements)
            if response:
                return response

        if not request.api:
            return render_error(request, __ERROR_BAD_REQUEST, 400)
        else:
            # Check for object existence and authorization first
            try:
                if object_id:
                    obj = model.objects.get(id=object_id)
                else:
                    obj = model.objects.get(**{slug_field: slug})
                if deleted_field and getattr(obj, deleted_field):
                    return render_error(request, __ERROR_NOT_FOUND, 404)
                if callable(authorization) and not authorization(request, obj):
                    return render_error(request, __ERROR_NOT_AUTHORIZED, 403)
            except InsufficientRoleApiException as e:
                return render_error(request, e.message, 401)
            except:
                return render_error(request, __ERROR_NOT_FOUND, 404)
            if request.api_action == ApiAction.CREATE:
                try:
                    # Create a new related object
                    related_obj = related_model()
                    set_object_data(related_obj, request.POST)
                    setattr(related_obj, related_field, obj)
                    if nonce_field:
                        nonce = request.META.get('HTTP_X_HMAC_NONCE', None)
                        if nonce:
                            setattr(related_obj, nonce_field, nonce)
                        else:
                            return render_error(request, __ERROR_HMAC, 403)
                    if request_user_field and not request.user.is_anonymous():
                        setattr(related_obj, request_user_field, request.user)
                    if request_ip_field:
                        setattr(related_obj, request_ip_field, request.META['REMOTE_ADDR'])
                    if request.POST.has_key('_data'):
                        related_obj._data = request.POST['_data']
                    if callable(verification) and not verification(request, related_obj):
                        return render_error(request, __ERROR_VERIFICATION, 500)
                    save_object(related_obj)
                except Exception as e:
                    return render_error(request, '%s: %s' % (e.__class__.__name__, __exception_error_message(e)), 500)
                set_response_headers(request, **{__X_HEADER_NEW_OBJECT_ID: related_obj.id})
                return render_data(request, {_get_api_model(related_model).id_field[1]: related_obj.id}, 201)
            else:
                # Do not pass on the model object_id or slug to read the related objects, but save them in the
                # request for access in the filters
                request.api_related_id = object_id
                request.api_related_slug = slug
                return related_view(request)

    return api_related_view_inner


class ApiView(object):
    actions = ApiAction.READ
    requirements = 0

    @classmethod
    def as_view(cls, **initkwargs):
        instance = cls(**initkwargs)
        if hasattr(instance, 'filter') and callable(instance.filter):
            filter = instance.filter
        else:
            filter = None
        if hasattr(instance, 'authorization') and callable(instance.authorization):
            authorization = instance.authorization
        else:
            authorization = None
        if hasattr(instance, 'verification') and callable(instance.verification):
            verification = instance.verification
        else:
            verification = None
        return api_view(instance.model, instance.actions, instance.requirements, filter, authorization, verification)


class ApiRelatedView(object):
    actions = ApiAction.READ
    requirements = 0

    @classmethod
    def as_view(cls, **initkwargs):
        instance = cls(**initkwargs)
        if hasattr(instance, 'filter') and callable(instance.filter):
            filter = instance.filter
        else:
            filter = None
        if hasattr(instance, 'authorization') and callable(instance.authorization):
            authorization = instance.authorization
        else:
            authorization = None
        if hasattr(instance, 'verification') and callable(instance.verification):
            verification = instance.verification
        else:
            verification = None
        return api_related_view(instance.model, instance.related_model, instance.related_field, instance.actions, instance.requirements, filter, authorization, verification)


class AuthChallenge(Exception):
    """The authentication request needs more info."""
    def __init__(self, **kwargs):
        self.args = kwargs

    def __str__(self):
        return repr(self.args)


@csrf_exempt
def api_login_view(request):
    """
    Login a user based on some credentials.

    POST with HTTPS: args that correspond to credentials passed to the authentication backends.
    """
    if request.method != 'POST':
        return render_error(request, __ERROR_NOT_ALLOWED, 405)
    if not request.is_secure() and not settings.DEBUG:
        return render_error(request, __ERROR_HTTPS, 403)
    try:
        user = authenticate(**request.POST.dict())
    except AuthChallenge as challenge:
        set_response_headers(request, **challenge.args)
        return render_error(request, __ERROR_AUTH_CHALLENGE, 401)
    else:
        if user is None:
            return render_error(request, __ERROR_BAD_CREDENTIALS, 403)
        elif not user.is_active:
            return render_error(request, __ERROR_INACTIVE_ACCOUNT, 403)
        else:
            login(request, user)
            set_response_headers(request, **{__X_HEADER_USER_ID: user.id})
            # Tell the CsrfViewMiddleware to add the csrftoken cookie to the
            # response (see Django's @ensure_csrf_cookie and get_token())
            if getattr(settings, 'API_CSRF', True):
                request.META['CSRF_COOKIE_USED'] = True
            return render_empty(request)


def api_logout_view(request):
    """Logout the current user."""
    logout(request)
    return render_empty(request)


class ApiCurrentUserView(BasicApiView):
    single_object = True

    def __init__(self, actions=ApiAction.READ|ApiAction.UPDATE, requirements=ApiRequirement.LOGIN):
        self._actions = actions
        self.requirements = requirements
        if hasattr(self, 'verification') and callable(self.verification):
            verification = self.verification
        else:
            verification = None
        self.api_view = api_view(get_user_model(), self._actions, self.requirements, verification=verification)

    def __call__(self, request):
        """Return the current user object."""
        return self.api_view(request, request.user.id)

    @property
    def actions(self):
        return self._actions

    @property
    def model(self):
        return get_user_model()


class ApiCurrentUserRelatedView(BasicApiView):
    single_object = False

    def __init__(self, related_model, related_field, actions=ApiAction.READ|ApiAction.CREATE, requirements=ApiRequirement.LOGIN):
        if isinstance(related_model, (str, unicode)):
            related_model = related_model.split('.')
            related_model = get_model(related_model[0], related_model[1])
        self.related_model = related_model
        self.related_field = related_field
        self._actions = actions
        self.requirements = requirements
        if hasattr(self, 'filter') and callable(self.filter):
            filter = self.filter
        else:
            filter = None
        if hasattr(self, 'authorization') and callable(self.authorization):
            authorization = self.authorization
        else:
            authorization = None
        if hasattr(self, 'verification') and callable(self.verification):
            verfication = self.verification
        else:
            verification = None
        self.api_related_view = api_related_view(get_user_model(), self.related_model, self.related_field, self._actions, self.requirements, filter, authorization, verification)

    def __call__(self, request):
        """Only return objects associated with the current user."""
        return self.api_related_view(request, request.user.id)

    @property
    def actions(self):
        return self._actions

    @property
    def parent_model(self):
        return get_user_model()

    @property
    def model(self):
        return self.related_model


def api_filter_contacts_view(requirements=ApiRequirement.LOGIN|ApiRequirement.HTTPS, fields=('email',)):
    """
    Filter a list of contacts based on an arbitrary user model fields such as email.

    POST with LOGIN and HTTPS: args are arrays of values keyed with the field names.
    The response should be the same just filtered.
    """
    def api_filter_contacts_view_inner(request):
        if request.method != 'POST':
            return render_error(request, __ERROR_NOT_ALLOWED, 405)
        response = _check_requirements(request, requirements)
        if response:
            return response
        filtered = {}
        UserModel = get_user_model()
        for field in fields:
            values = request.POST.get(field)
            if values:
                filtered[field] = UserModel.objects.filter(**{field + '__in': values}).values_list(field, flat=True)
        if request.META.get('HTTP_ACCEPT', '').startswith('text/csv'):
            values = filtered.values()[0]
            if len(values):
                return HttpResponse(','.join([str(v) for v in values]), content_type='text/csv')
            else:
                return HttpResponse()
        else:
            return render_data(request, filtered)
    return api_filter_contacts_view_inner


@csrf_exempt
def api_create_user_view(request):
    """
    Create a new user with a password and optional email. If successful will login that user and return their new user id.

    POST with HTTPS and HMAC: username, password1, password2, email
    """
    if request.method != 'POST':
        return render_error(request, __ERROR_NOT_ALLOWED, 405)
    response = _check_requirements(request, ApiRequirement.HTTPS | ApiRequirement.HMAC)
    if response:
        return response
    username = request.POST.get('username')
    email = request.POST.get('email')
    password1 = request.POST.get('password1')
    password2 = request.POST.get('password2')
    UserModel = get_user_model()
    user = UserModel(**{UserModel.USERNAME_FIELD: username})
    if email:
        user.email = email
    user.clean()
    try:
        existing_user = UserModel._default_manager.get_by_natural_key(getattr(user, UserModel.USERNAME_FIELD))
        return render_error(request, __ERROR_USERNAME_TAKEN, 409)
    except UserModel.DoesNotExist:
        try:
            if not password1 or password1 != password2:
                return render_error(request, __ERROR_PASSWORD_MISMATCH, 400)
            user.set_password(password1)
            user.save()
        except IntegrityError:
            # Improbable race condition, where the username is now taken
            return render_error(request, __ERROR_USERNAME_TAKEN, 409)
        except Exception as e:
            return render_error(request, '%s: %s' % (e.__class__.__name__, __exception_error_message(e)), 500)
        else:
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            set_response_headers(request, **{__X_HEADER_USER_ID: user.id})
            # Tell the CsrfViewMiddleware to add the csrftoken cookie to the response
            if getattr(settings, 'API_CSRF', True):
                request.META['CSRF_COOKIE_USED'] = True
            return render_empty(request)


def api_set_password_view(request):
    """
    Change the current user's password.

    POST with LOGIN and HTTPS: password, password1, password2
    """
    if request.method != 'POST':
        return render_error(request, __ERROR_NOT_ALLOWED, 405)
    response = _check_requirements(request, ApiRequirement.LOGIN | ApiRequirement.HTTPS)
    if response:
        return response
    user = request.user
    old_password = request.POST.get('password')
    password1 = request.POST.get('password1')
    password2 = request.POST.get('password2')
    if user.has_usable_password() and not user.check_password(old_password):
        return render_error(request, __ERROR_BAD_CREDENTIALS, 400)
    elif not password1 or password1 != password2:
        return render_error(request, __ERROR_PASSWORD_MISMATCH, 400)
    user.set_password(password1)
    user.save()
    return render_empty(request)


@csrf_exempt
def api_reset_password_view(request):
    """Send in a password reset request, where a link will be emailed to the email specified in the POST and recipient will need to set their password in a browser.

    POST with HMAC: email
    """
    if request.method != 'POST':
        return render_error(request, __ERROR_NOT_ALLOWED, 405)
    response = _check_requirements(request, ApiRequirement.HMAC)
    if response:
        return response
    from django.contrib.auth.forms import PasswordResetForm
    form = PasswordResetForm(request.POST)
    form.save()
    return render_empty(request)


def api_require_login_js(request):
    """
    Return a piece of javascript to redirect a user first thing if they are not logged in when
    loading up a statically hosted SPA.
    """
    if request.user.is_authenticated() and request.user.is_active:
        response = HttpResponse('void(0);', content_type='text/javascript')
    else:
        login_href = "%s?%s" % (settings.LOGIN_URL, urlencode({'next': settings.LOGIN_REDIRECT_URL}))
        response = HttpResponse('window.location.href = "%s";' % login_href, content_type='text/javascript')
    return response
