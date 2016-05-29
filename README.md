# Frasco-Models

Integrate an ORM or ODM to save data to databases. Frasco-Models provides actions that
interfaces with your own ORM.

## Installation

    pip install frasco-models

## Setup

Feature name: models

Options:

 - *backend*: the backend class name
 - *pagination_per_page*: default number of items per page when using the pagination
 - *scopes*: named scopes (see further)

## Backends

Frasco-Models exposes a generic interface that uses backend to perform operations.

Backends options are provided as part of the feature's options.

### mongoengine

[Mongoengine](http://mongoengine.org/) is a powerful ODM which is better suited at
larger applications. This backend uses [Flask-MongoEngine](http://flask-mongoengine.readthedocs.org/en/latest/).

This backend requires that you define your models in advance. Some features requires
custom fields and an exception of type `frasco_models.ModelSchemaError` will be triggered
if they are missing.

Options:

 - *db*: the database name (mandatory)
 - *host*
 - *port*
 - *username*
 - *password*

### sqlalchemy

need docs :(

## Querying

Frasco-Models exposes a generic query interface. It provides only basic needs but should
be enough for distributed features to interface with the model layer.

When querying through the actions, the following options are available:

 - *scope*: a single or a list of scope names
 - *filter_from*: build filters from the given source, possible values:
   - *form*: use data from the current form
   - *url*: uses `flask.request.values`
   - *args*: uses `flask.request.view_args`
 - *filters*: a dict of filters
 - *order_by*: orders the query using the specified field in the form of `field_name DIRECTION`
   where *DIRECTION* can be *ASC* or *DESC*
 - *limit*: limits the number of return results
 - *offset*: return results from this offset

All other options will be considered as filters

### Filters

Filters are dicts query keys are field names. For example, `{"username": "john"}` will search
for objects which *username* field matches *john*.

You can use other operators than equality py suffixing the field name with the operator name
separated by double underscores. For example, `{"price__lt": 10}` would search for objects
which price is under 10. Available operators:

 - *ne*: not equal
 - *lt*: less than
 - *lte*: less than or equal
 - *gt*: greater than
 - *gte*: greate than or equal
 - *in*: in
 - *nin*: not in
 - *contains*: contains (to check if the provided item exists in the field, the field's value
   being a list)

By default, filters will be joined using AND. This can be changed using filter groups.
These are dicts with only one item which keys can either be *$or* or *$and* and its
value a dict of filters.

    {"$or": {"price__lt": 10, "ratings__gt": 4}}

### Scopes

Scopes are a way to apply default filters to queries. There are two type of scopes: named
one and request-based scopes.

Named scopes are defined in the configuration under the *scopes* option. It must be a dict
where keys are scope names and their values some filters.

    features:
      - models:
          scopes:
            current_user: { user: $current_user }

As you can notice, you can use context variables.

The second kind of scopes is limited to the time of the request and can be defined using
the *define_model_scope* action. They will be automatically applied to all queries.

### Query object

Under the hood, the query is represented as an object of type `frasco_models.Query`.
The following methods are available:

 - `filter(*filters)`: apply a list of filters
 - `order_by(field)`: orders the results using the specified field
 - `limit(limit)`: limit the number of return results
 - `offset(offset)`: return results from this offset

Each methods returns a copy of the query object.  
To execute the query, the following methods are available:

 - `all()`: returns a list of results
 - `first()`: returns the first result
 - `first_or_404()`: same as first but aborts the request with a 404 HTTPException
 - `one()`: returns the first result and triggers an exception if none or many results are returns
 - `count()`: performs a count query
 - `update(data)`: updates all matching objects with the data
 - `delete()`: deletes all matching objects

To query a single object based on its id, two shortcut methods exist: `get(id)` and `get_or_404(id)`.

The `update(data)` method supports a few operators:

 - *incr*: increments the value
 - *push*: adds an item to a list

## Pagination

Queries returning multiple results can be paginated, either using the *paginate_query* action or
with the *paginate* option of the *find_models* action. Pagination information are stored in a
pagination object.

The pagination objects has the following properties:

 - *page*: current page
 - *offset*: the query offset for this page
 - *per_page*: nomber of items per page
 - *total*: total number of results
 - *nb_pages*: total number of pages
 - *prev_page*: the previous page number or None
 - *next_page*: the next page number or None
 - *prev*: returns a new pagination object for the previous page
 - *next*: returns a new pagination object for the next page

Finally there is an `iter_pages()` method which iterates over the page numbers. The four parameters
control the thresholds how many numbers should be produced from the sides. Skipped page numbers are
represented as None. This is how you could render such a pagination in the templates:

## Actions

### find\_model

Executes a query and returns a single object.  
Unless overrided with *as*, a variable named after the model in lower case is
automatically assigned (eq: *Post* becomes *post*).

Options:

 - *model*: name of the model
 - *not_found_or_404*: whether to trigger a 404 error if the model is not found (default: true)
 - all query options

Returns a model object

### find\_models

Executes a query and returns all objects found.  
Unless overrided with *as*, a variable named after the model in lower case and pluralized is
automatically assigned (eg: *Post* becomes *posts*)

Options:

 - *model*: model name (default option)
 - *paginate*: whether to paginate, can be a boolean or the number of items per page (default: false)
 - *page*: current page number. If None, will look for a *page* argument in `request.values` or will default to 1.
 - *pagination_var*: the name of the context variable where the pagination object will be stored
 - all query options

Returns a query object

### count\_models

Executes a query and returns the number of objects it should return.  
Unless overrided with *as*, a variable named after the model in lower case suffixed with *_count*
is automatically assigned (eg: *Post* becomes *post_count*)

Options:

 - *model*: model name (default option)
 - all query options

### create\_model

Creates a new model object but do not saves it.  
Unless overrided with *as*, a variable named after the model in lower case is
automatically assigned (eq: *Post* becomes *post*).

Options:

 - *model* model name (default option)
 - all other options will be pass to the model constructor

Returns a model object

### save\_model

Creates a model and saves it or saves an existing object.

Unless overrided with *as*, a variable named after the model in lower case is
automatically assigned (eq: *Post* becomes *post*).  
Either the *obj* or the *model* option is needed.

Options:

 - *obj*: a model object (default option)
 - *model*: model name (will create a new object)
 - all other options will be set as attributes of the object

Returns a model object

### create\_from\_form

Creates a new model object using data from a form but do not saves it.  
Unless overrided with *as*, a variable named after the model in lower case is
automatically assigned (eq: *Post* becomes *post*).

Options:

 - *model*: model name (default option)
 - *form*: a form object. If not provided, it will use the current form
 - all other options will be set as attributes of the object

Returns a model object

### save\_form\_model

Populates an existing model object with form data or creates a new model object
using form data and saves it.

Unless overrided with *as*, a variable named after the model in lower case is
automatically assigned (eq: *Post* becomes *post*).  
Either the *obj* or the *model* option is needed.

Options:

 - *model*: model name (default option)
 - *obj*: a model object
 - *form*: a form object. If not provided, it will use the current form
 - all other options will be set as attributes of the object

Returns a model object

### delete\_model

Deletes a model object

Options:

 - *obj*: a model object (default option)

### check\_model\_exists

Executes a query and if a model exists will exit the context, triggering the
*model_exists* action group.

Options:

 - *model*: model name
 - *error_message*: optionally flash a message
 - all query options

### create\_unique\_slug

Returns a slug which is guaranteed to be unique in your model.

Options:

 - *value*: the value to convert to a slug
 - *model*: model name
 - *column*: the column to check for existing slugs (default: slug)

Default variable assignment: `$slug`

### paginate\_query

Paginate an existing query

Options:

 - *query*: query object
 - *page*: page number. If None, will look for a *page* argument in `request.values` or will default to 1.
 - *per_page*: number of items per page (default: see configuration)
 - *check_bounds*: whether to raise a `PageOutOfBoundError` if the page does not exist

Returns a tuple with the paginated query object and the pagination object

### define\_model\_scope

Defines filters to apply automatically to queries of the given model during
the current request.

Options:

 - *model*: model name
 - *filters*: some filters

All other options will be considered as filters