About
===============================

* Requires Django 1.7+

Middleware
===============================

The api middleware is capable of processing requests and determining the following information based on the url and attach it to the request object.

* ``api`` - True if requested with /api, False otherwise.
* ``api_action`` - if api is True, the requested action either: ``READ, CREATE, UPDATE, DELETE``. ``HEAD`` requests are considered ``READ`` requests and should usually be handled the same as a ``GET``, and just allow Django to strip out the response body. ``PATCH`` requests are likewise just treated as an ``UPDATE``.
* ``api_json`` - if api is True, True or a string if a JSON response is requested, False otherwise.
* ``api_version`` - if api is True, The version of the api requested. Default is 1.
* ``api_callback`` - sets request.api_json = callback and request.api_callback = True and is meant render json wrapped in a callback

Extra data may be passed through on ``PUT`` and ``POST`` requests as a ``_data`` variable and then attached to the object. It is up to the implementor to interpret ``_data``, usually in the model's save method, doing JSON or some other decoding.

* ``_data`` - Extra data string.

The middleware will also process the views and set ``request.csrf_processing_done=True`` for api requests. Be sure to install the api middleware before the csrf middleware if you want the csrf exemption for /api methods. You can disable this bypass see **Cross-site request forgery** for more info.

URLs
===============================

* ``api_include`` is a method similar to ``include`` where it attempts to extract the apipatterns variable from the module first
* ``api_patterns`` is a method to help generate url patterns it takes the following three arguments.

* ``prefix`` - The api prefix to generate.
* ``include`` - The views file to include for this api path.
* ``versions`` - The latest version to generate. (optional)

e.g. ``urlpatterns += api_patterns('versioned', 'versioned.urls', 3)`` would create the following versioned urls: /api/versioned/, /api/1/versioned/, ..2, and ..3 as well as the non-api versions /versioned, /versioned/1, etc..

Api specific urls can coexist with urlpatterns in the same include files, so that an app's api urls can be included with an /api prefix and non-api urls can be included separately without the /api prefix. Simply define a special apipatterns list in the same app.urls module next to it's urlpatterns. ``api_include`` and ``api_patterns`` will then only include apipatterns, and ``include`` will only include urlpatterns. If apipatterns is missing all methods will simply use urlpatterns.

When including a list of urls from the same module only use ``include`` not ``api_include``. <https://docs.djangoproject.com/en/dev/topics/http/urls/#including-other-urlconfs>

Model API Class
===============================

Similar to the Meta class Django uses on models, the built-in API views rely on an API class with settings under each model.

API View Settings
-------------------------------

* ``include_fields`` - ('id', 'name', 'start', 'end', 'test_field') # fields in here take precedence over exclude_fields
* ``exclude_fields`` - ('id',) exclude these fields completely from both read and write access
* ``include_related`` - ('related_field',) # For these foreign keys, don't just serialize the id
* ``list_fields`` - ('id', 'name') # must be a subset of the calculated fields to include - limits the fields output when listing objects in a collection, this also applies if the object is a subobject included in a listing of the parent
* ``update_fields`` or ``readonly_fields`` - a list of update-able or readonly fields as a subset of the calculated fields. ``update_fields`` takes precedence over ``readonly_fields`` and setting the editable property to False on a field takes precedence over both.
* ``slug_field`` - The field to use when looking up an object by slug. The default value is 'slug'.
* ``deleted_field`` - if set, specifies a boolean field to set to True instead of deleting the object from the database
* ``request_user_field`` - force this field, e.g. 'user', to always be always be set to ``request.user`` upon a ``CREATE`` or ``UPDATE`` request, if more fields are needed, they can be copied in save()
* ``request_ip_field`` - force this field, e.g. 'ip', to always be set to ``request.META['REMOTE_ADDR']`` upon a ``CREATE`` or ``UPDATE`` request, if more ip fields are needed, they can be copied in save()

Use ``editable=False`` only for fields that also shouldn't be edited by a superuser etc. in the admin panel. auto_now and auto_now_add imply ``editable=False``.

The fields to include are calculated by taking all of the fields or include_fields if specified and then removing the exclude_fields. List fields are then calculated by including only the list_fields that are specified that are in the calculated fields. Defaults to all calculated if not specified.

API Search Filter Settings
-------------------------------

* ``search_fields`` = ('field', 'related_obj.field') # will allow searching with the q GET parameter and the search_filter. Must be set for searches to work.
* ``filter_fields`` = ('field', ...) # will allow filtering results by a set of attributes - must be given in camelCase if ``API_CAMELCASE`` is set.
* ``page_size`` = 500 # default/max page size for the paginate filter, will override global settings
* ``order_by_fields`` = ('first_name', 'date') # limits the fields which can be used to order_by, use the model's Meta.ordering to set a default order_by (<https://docs.djangoproject.com/en/dev/ref/models/options/#django.db.models.Options.ordering>)

HMAC Settings
-------------------------------

``nonce_field`` = 'nonce' # the field that has a unique constraint and will serve to store client-side generated nonces to secure CREATEs. See the notes below about the nonce

Inheritance
-------------------------------

The API inner class can be inherited just like Django's Meta class inheritance:
<https://docs.djangoproject.com/en/dev/topics/db/models/#meta-inheritance>

Supported Fields
-------------------------------

Most of the Django fields are supported. Additionally the following fields are supported.

* ``JSONField`` - https://github.com/bradjasper/django-jsonfield - for best compatibility, be sure to set the default to an {} and always store as a dictionary

Unsupported Fields
-------------------------------

* ``ManyToManyField`` - Currently many to many relationships aren't supported

API Views
===============================

Wrap the view in ``session_required`` etc. or whatever other decorator to establish authentication.

Use an authorization callback to establish authorization to access a specific object.

``filter`` = callable(request, queryset) # accept and return the same or filtered queryset to filter down a collection based on who the user is, in affect this performs authorization for getting a collection of objects

``authorization`` = callable(request, object) # for all non-collection requests, return True/False depending on if the user can access the requested object or not - called before any fields are updated

``verification`` = callable(request, object) # for all ``CREATE`` and ``UPDATE`` requests, return True/False depending on if the user has set fields in the object properly - called after all fields are updated or set. An exception may also be raised instead of returning False and a more descriptive error message will be returned to the client.

if filter is given, but authorization is not, then the authorization will be determined based upon if the requested object is part of the filtered queryset
authorization is not used when POSTing new objects, unless it is part of a related collection - use a related view to enforce authorization
verification should not be used to replace the clean method on models, rather it should be used just to check whether the user has the right to set fields the way they were, since request.user is not available in the clean method only the verification callback is used on ``CREATE`` requests.

``e.g. url(r'^modelobjects/(?P<object_id>\d+)/?$', api_view('djangoapp.ModelObject')),``

Callback Ordering
-------------------------------

* ``READ`` -> authorization
* ``READ`` Collection -> filter
* ``UPDATE`` -> authorization -> verification -> full_clean -> save
* ``CREATE`` -> verification -> full_clean -> save
* ``DELETE`` -> authorization
* ``READ`` Subcollection -> authorization -> auto-generated filter(subcollection)
* ``CREATE`` Subcollection -> authorization -> verification(subobject) -> full_clean(subobject) -> save(subobject)

Overriding Validation Error Messages
-------------------------------

Validation error messages can be overriden by specifying a message on any one of Django's field validators: <https://docs.djangoproject.com/en/1.9/ref/validators/> Or by the following model methods:

* ``validate_unique(self, exclude=None)`` - try/catch and throw a new ValidationError exception

X-Headers
-------------------------------

*Views*

* ``X-New-Object-Id`` - after a ``CREATE`` the newly created object id given along with a response containing an object with only the new object id. This header is a convenience that could be easier to use than the response.
* ``X-User-Id`` - after a successful login, this header is given along with an empty response

*Paginate Filter*

* ``X-Total`` - Total number of objects
* ``X-Total-Pages`` - Total number of pages given the page size
* ``X-Page`` - The page number
* ``X-Page-Size`` - The requested or overridden page size

*HMAC*

* ``X-Hmac`` - the HMAC of the post body, lowercase hex string
* ``X-Hmac-Nonce`` - uuid generated on the client, ONLY applies to CREATE (POST) when using a nonce, the model needs to specify a nonce_field and any side-effects needs to take place AFTER the object successfully saves when overriding the save method and calling the super save method to be sure there is no race condition with another copy request.

*Other*

* ``X-Native-App`` - tells the API middleware that this is a native app and csrf protection shouldn't be used similar to ajax requests. Should be formatted as ``OS; Device Model; App package``. Note: the csrf bypass only works when the ``API_CSRF`` setting is False.

Django Settings
-------------------------------

* ``API_RENAME_ID`` = True/False - default is True, rename the id field to modelname_id
* ``API_CAMELCASE`` = True/False - default is True, encode/decode field names as camelCase, Django fieldnames must be coded using underscore conventions for this setting to work
* ``API_JSONP`` = True/False - default is False (stop all jsonp requests at the middleware), if true jsonp is allowed but needs to be enabled on each view's requirements
* ``API_CSRF`` = True/False - default is True, if False then CSRF protection is bypassed with ajax or native app requests
* ``API_PAGE_SIZE`` = int - default is 100, for the paginate filter what is the default/max page size
* ``API_HMAC_KEY`` = a random uuid like settings.SECRET, that the client will use to generate hashes with
* ``API_HMAC_SALT`` = a random salt to append with the hashes to help stop man-in-the-middle interference 

Class-based Views
-------------------------------

Alternatively, instead of passing a long list of arguments to ``api_view`` and ``api_related_view``, you may subclass ``ApiView`` or ``ApiRelatedView``, two classes that wrap ``api_view`` and ``api_related_view`` and provide their arguments from attributes set in the object or class.  Callbacks like ``filter`` and ``verification`` can be defined as instance methods making it easier to group logic for a single api view.

Custom processing
-------------------------------

Any additional processing on new or updated objects can be done by the traditional ways of overriding the clean or save methods. See below for ways of detecting changes.
<http://stackoverflow.com/questions/1355150/django-when-saving-how-can-you-check-if-a-field-has-changed>

Control Data
-------------------------------

Some save methods for models may require additional control data that is not inline with the model's fields. To pass control data put it in the special ``_data`` argument.
The save method then receive it as ``self._data``, and will be responsible for decoding it, e.g. ``json.loads``

Included Objects
-------------------------------

When updating models with included objects, specified with the ``include_related`` API setting, any field excluding the id may be set on the related object and successfully saved with the same UPDATE request to the object.  To change the relationship and update the foreign key to a new entry, specify the special write-only ``related_obj_id`` field (where ``related_obj`` is the field name) and leave out the subobject as if the ``include_related`` API setting wasn't specified. This special write-only field is available to change the relationship regardless if the included object field is readonly or not. null may also be used to remove a relationship for ``null=True`` fields, since on the backend, setting ``related_obj_id`` to None has the same effect as settings ``related_obj`` to None.

Base Classes
-------------------------------

Fields from a base class will be included with an object as with any normal Django object. For non-abstract base classes the ptr field will be included in as a readonly field with the ptr suffix removed.

Subclass Collections
-------------------------------

A collection of heterogeneous subclasses can be read by using the ``subclass_filter(*subclasses, **names)`` filter. The name and name_plural parameters (must be CamelCase) are for naming the endpoint (like with Django models) to use when generating code for this endpoint, e.g. "places" may represent both restaurants and stores together. The subclasses filter is an array of Django model classes.

The response will have ``X-Mixed-Results`` header set to indicate that the response should be polymorphic and interpreted using some kind of reflection to map to the correct models. Only READ requests are supported when using this filter. Other request types my result in an error, since the API decodes the values for the parent class, not subclass. The client-side will need to use the Model-specific endpoints to create new objects. 

Note:

* Multiple-inheritance and multi-level-inheritance models are not supported.
* For heterogeneous subclass collections to work while generating Backbone.js models, the ``API_RENAME_ID`` setting must be True and each of the subclasses must have their own unique endpoints.

Multi-Level Access
-------------------------------

It's possible to provide access levels and hide potentially private information when reading individual objects.
For example, on your User model you may wish to provide all data when a user is requesting their own data, and a subset when requesting information about a friend, and a smaller subset when a stranger is requesting information.
This can be achieved dynamically in your authorization function by setting a special ``_exclude_data`` variable on the user object: ``obj._exclude_data = ('lastLogin', 'dateJoined', 'favoriteColor')``. When set, the values specified will be removed from the response. Since this removes information from the response, be sure to specify the fields as underscore or camelcase depending on your settings.

This feature is currently only supported when reading individual objects, not lists. Publicly accessible lists should instead take caution and return only the minimal information needed to display on the client.

Images and Files
-------------------------------

File uploads are not supported at all by this module.

Probably the most efficient way to upload files is to use S3 or other cloud storage and upload directly from the client after a successful API ``CREATE`` or ``UPDATE`` of a model that represents the image.

A good convention is to use the a format based off the associated object's id, after the object is created. Alternatively, files can be stored using their MD5 hash. For hashed filenames, if the path is specified by using multiple directories, e.g. /54/73/2b/1c/54732b1ccfbbcb35c35cd941547eeb32.jpg this would enable easy parallelization of processing many files like creating alternate image sizes, where each distributed worker could process a directory.

Cross-origin Resource Sharing (CORS)
-------------------------------

Security
===============================

By default the API module is setup without security, use settings and various callbacks to strengthen it to your project's needs.

Cross-site request forgery
-------------------------------

POSTs can be forged using normal HTML forms and include all valid cookies even cross-domain, which is why CSRF tokens or X-Headers are used. CSRF protection does not apply to ``GET, HEAD, OPTIONS or TRACE``.

If using CSRF protection, the API middleware MUST be installed before the Csrf middleware.

To bypass the csrf middleware with a request, an AJAX (``X-Requested-With``) or ``X-Native-App`` header must be sent with the request and ``API_CSRF`` must be False.  This bypass isn't 100% perfect as there are some vulnerabilities with plugins and redirects but could be good enough for some use cases, see the wikipedia entry for more information.

The ideal CSRF usage however is to X-CSRFToken header, where the CSRF token is taken from the cookies and placed into this customer header. This custom header is then checked instead of the csrfmiddlewaretoken as part of the POST data, meaning JSON and other APIs can use it and only the intended front-ends can access the cookies. The mobile libraries support this by default but web front-ends need to add the code for this. Example cookie code is available on the Django webpage as is the jQuery hooks, but a global hook should be used instead of the local one: $(document).ajaxSend(function(event, jqxhr, settings) {});

* <https://docs.djangoproject.com/en/dev/ref/contrib/csrf/>
* <http://en.wikipedia.org/wiki/Cross-site_request_forgery>

Malicious User
-------------------------------

An authorized user can always sniff their own traffic and generate fake requests. To prevent fake requests, require an HMAC, where only an approved client application can successfully generate requests.

HMAC doesn't prevent a replay, so make sure there are no side effects with HMAC protected requests.

Replay Attacks
-------------------------------

To prevent replay attacks, use a unique field (a nonce) in the model that is being updated, that way the same objects with side effects can't be created.

Other Measures
-------------------------------

**Content-Security Policy** - using a Content Security Policy for your site could help prevent any injected script from accessing resources they shouldn't. Read up more about it with the following: <http://www.html5rocks.com/en/tutorials/security/content-security-policy/>, <https://developer.mozilla.org/en-US/docs/Web/Security/CSP/CSP_policy_directives>.

**Clickjacking** - use Django's builtin ``django.middleware.clickjacking.XFrameOptionsMiddleware`` to help strengthen your site's security. <https://docs.djangoproject.com/en/dev/ref/clickjacking/>

User API Views
===============================

Authentication
-------------------------------

The following are built-in views for managing the authentication of users.

* ``api_login_view`` - Login a user based on some credentials. ``POST`` with HTTPS: args that correspond to credentials passed to the authentication backends.
* ``api_logout_view`` - Logout the current user.
* ``api_create_user_view`` - Create a new user with a password and optional email. If successful will login that user and return their new user id. ``POST`` with HTTPS and HMAC: username, password1, password2, email.

When using the login view, it will call Django's authenticate method to pass whatever matching credentials in the POST to the various backends. One special addition to this is any authentication backend may raise a ``AuthChallenge`` full of custom HTTP headers that will be send back to the client if further authentication is needed.

User Information
-------------------------------

* ``ApiCurrentUserView`` - an API view class that uses an api_view to return information about the current logged in user. When creating an instance you may customize it by passing actions and requirements. An optional verification method ``verification(self, request, object)`` can be provided if you create a subclass. Override ``__call__(self, request)`` and call super if you wish to wrap the invocation of the underlying ``api_view``.

* ``ApiCurrentUserView`` - an API view class that uses an api_related_view to access collection related to the user. When creating an instance you may customize it by passing related_model, related_field, actions and requirements. Optional callback methods ``filter(self, request, query)``, ``authorization(self, request, object)``, and ``verification(self, request, object)`` can be provided if you create a subclass. Override ``__call__(self, request)`` and call super if you wish to wrap the invocation of the underlying ``api_related_view``.

No built-in view is provided for requesting information about one or a list of users other than the current. Simply use the ``api_view`` with the user model to achieve this. Also read the section on *Multi-Level Access*.

Setting Passwords
-------------------------------

* ``api_set_password_view`` - Change the current user's password. POST with HTTPS: password, password1, password2.
* ``api_reset_password_view`` - Send in a password reset request, where a link will be emailed to the email specified in the POST and recipient will need to set their password in a browser. POST with HMAC: email.

Filtering Contacts
-------------------------------

* ``api_filter_contacts_view`` - Filter a list of contacts based on an arbitrary user model fields such as email. HTTPS is recommended but not required. POST: args are arrays of values keyed with the field names. The response should be the same just filtered.

User Model
-------------------------------

The base recommended API settings for your user model are:

.. code-block:: python
	class API:
		exclude_fields = ('password', 'is_staff', 'is_superuser')
		readonly_fields = ('username', 'date_joined', 'last_login')
		slug_field = 'username'
		search_fields = ('username', 'email')

It is also recommended to add a unique index to the email field of your User model:

.. code-block:: python
	User._meta.get_field('email')._unique = True
	User._meta.get_field('email').null = True

Singleton Views
===============================

To create a view that corresponds to a single row in the database, simply set default args on the url when defining your url pattern, such as: ``url(r'^currentdataset/?$', api_view('myapp.Dataset'), {'object_id': 1})``.

The other way to create a readonly singleton object, returning server stats or some other calculated object, is by creating a custom view, see ``Custom Views``.

Custom Views
===============================

The recommended way of making a custom view is by subclassing the ``BasicApiView`` class. The ``BasicApiView`` class will check for supported methods and api requirements before dispatching the action to the correct method where everything else must all be handled manually. The following actions are support. Each action must take request, object_id, and slug as arguments.

* ``read`` - read and head requests
* ``update`` - update requests
* ``create`` - create a new object request
* ``delete`` - delete an object request

``requirements`` is an attribute that can be set by the subclass specifying which requirements should be checked before calling any of the defined actions.

BasicApiView and Automatic Code Creation
-------------------------------

The following properties and attributes are ONLY used when creating documentation, client model, and connection classes.

* ``single_object`` - an attribute that specifies if there is no object_id or slug argument in the url pattern but this endpoint represents a single object if true otherwise a collection if false. default is false
* ``parent_model`` - a property that returns a model (not a string) if this view represents access to a related collection or object. default is None
* ``model`` - a property that returns a model (not a string) for the view's object or collection this view returns. default is None, this should be overridden.
* ``actions`` - a property that automatically checks for supported methods. default is auto calculated based on the available methods, this shouldn't be overridden.

For views that create non-database models it is recommended that inside the ``parent_model`` and ``model`` properties to check if ``settings.DEBUG`` is True and define a new abstract model class and return it. If creating a model using python's type() method, be sure to set the __module__ in the attributes. e.g.

.. code-block:: python
	module = __name__.split('.')[0] + '.models' # current __name__, like app.views
	return type('CategoryCount', (models.Model,), dict(__module__=module, category=models.CharField(max_length=255), count=models.IntegerField()))

Misc
===============================

HEAD methods
-------------------------------

Using HEAD requests you can test if a certain object exists, such as testing if a username is taken. You can also get the number of elements the would be returned from a search query.

PATCH methods
-------------------------------

PATCH requests are treated the same way as PUT requests, both being an UPDATE action.  Both methods may choose to update only a subset of fields available on a model. Specifying all fields for a PUT request is not required. The values from a PATCH request are placed under both request.PUT and request.PATCH as a convenience to handling UPDATE requests.

Not Thread Safe
-------------------------------

There is a reusable dictionary for each API model that has its fields instead of recreated from scratch.

Primary keys not supported
-------------------------------

Currently only objects that have an id field as their primary key are supported

Single-Page Applications
-------------------------------

If you're creating a single page application that is deployed on some static web host it's important to check to see if the user is logged in before proceeding.  You opt to use the ``ApiCurrentUserView`` over AJAX, checking for any errors as a result or you can use the built-in ``api_require_login_js`` view that generates Javascript to redirect the user to the login page if needed. This Javascript can then instead be loaded with a script tag.

Lowercase Usernames and/or Emails
-------------------------------

Django usernames by default are case-sensitive. It is good practice to instead make usernames lowercase only to avoid confusion.

By adding the following piece of code on your user model this will fix the username anytime a form or API method creates or updates a user.

.. code-block:: python
	def clean(self):
		self.username = self.username.lower()
		if self.email:
			self.email = self.email.lower()
		super(User, self).clean()

Instead of fixing the username in the clean method it would also work to raise a ``ValidationError``.

It is also recommended that on your front-end you validate any new or changing username/email address first on the front-end either with your own view or customizing the templates used with Django's builtin auth views.

Use the same validation for any forms with username or email or you could just force the information entered to be lowercase in the user interface.

There is no harm in not having backend validation of login credentials.

Code Generators
===============================

Most of the generators require that all of your URLs, apipatterns and urlpatterns are defined in the app's urls module.

Unsupported Views
-------------------------------

Currently it is not possible to export code for any views that use decorators or wrappers like csrf_exempt.

Calculated Properties
-------------------------------

By design, calculated readonly properties on a model aren't returned with READ responses. Instead, the calculations are more efficiently deferred to the client. To keep the calculations in-sync, model generators will auto-translate python code to Javascript, Objective-C, and Java. This is accomplished by the ``api_property(code, return_type=int, translations=None)`` function which creates a property and storing the raw code and other information needed for translation. The management commands then uses python's ast module to perform the translation. Most mathematical expressions (numeric, bitwise, boolean, etc.), conditionals (tertiary if only), string slicing, string length, and simple string formatting (% operator only) are supported.

Args for ``api_property`` are below:

* ``code`` - the raw python expression to return, given as a string
* ``return_type`` - a type indicating the desired return value, may be int, float, str, or bool
* ``translations`` - a dict with the correct translated code for expressions that cannot be auto-translated. The available keys are js, objc, and java.

A couple examples are below:

.. code-block:: python
	x = api_property('self.y + self.z/100')
	url = api_property('"http://example.com/%s" % self.slug', str)

**Remember** to be verbose, since languages like Java need explicit comparison operators and strings may be initialized to null outside of Django. So instead of writing ``1 if mystring else 2`` write ``1 if mystring != None and len(mystring) > 0 else 2``. However the boolean expression, ``1 if mybool else 2`` is acceptable.

Connections
-------------------------------

Note: Slug-based views only support READ and CREATE methods because generated methods for UPDATE and DELETE just use the provided object's id and it don't even bother with the slug field.

Note: Url modules currently must follow the convention of app.urls module naming for connections to generate properly.

Args

* dest - Sets the destination folder for all the output files.
* name=othername - The connection name can be changed from the app name to something else.
