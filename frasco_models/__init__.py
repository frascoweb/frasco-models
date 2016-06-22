from frasco import Feature, action, current_app, request, abort, listens_to, current_context
from frasco.utils import (AttrDict, import_string, populate_obj, RequirementMissingError,\
                          find_classes_in_module, slugify)
from frasco.expression import compile_expr, eval_expr
from frasco.templating import FileLoader, FileSystemLoader
from werkzeug.local import LocalProxy
from .backend import *
from .utils import *
from .query import *
from .transaction import *
import inspect
import os
import inflection


_db = None

def get_current_db():
    return _db

db = LocalProxy(get_current_db)


form_imported = False
try:
    from .form import *
    form_imported = True
except ImportError:
    pass


class ModelsFeature(Feature):
    name = "models"
    defaults = {"backend": None,
                "pagination_per_page": 10,
                "scopes": {},
                "import_models": True,
                "ensure_schema": True,
                "admin_models": []}
    
    def init_app(self, app):
        if not self.options["backend"]:
            raise Exception("Missing backend")
        self.backend_cls = self.get_backend_class(self.options["backend"])
        self.backend = self.backend_cls(app, self.options)
        self.scopes = compile_expr(self.options["scopes"])
        self.models = {}
        self.current_transaction = current_transaction

        global _db
        self.db = _db = self.backend.db

        if self.options["import_models"]:
            models_pkg = self.options['import_models']
            if not isinstance(self.options['import_models'], str):
                models_pkg = "models"
            if app.import_name != "__main__":
                models_pkg = app.import_name + "." + models_pkg
            try:
                __import__(models_pkg)
            except ImportError as e:
                if "No module named %s" % models_pkg.split('.')[-1] not in e.message:
                    raise

        if form_imported:
            app.jinja_env.loader.bottom_loaders.append(FileLoader(
                os.path.join(os.path.dirname(__file__), "form_template.html"), "model_form_template.html"))
            app.jinja_env.loader.bottom_loaders.append(FileLoader(
                os.path.join(os.path.dirname(__file__), "bs_form_template.html"), "model_bs_form_template.html"))

    def init_admin(self, admin, app):
        from .admin import create_model_admin_blueprint
        app.jinja_env.loader.bottom_loaders.append(FileSystemLoader(
            os.path.join(os.path.dirname(__file__), "admin/templates")))
        for model in self.options['admin_models']:
            kwargs = {}
            if isinstance(model, dict):
                model, kwargs = model.items()[0]
            model = self.ensure_model(model)
            with_counter = kwargs.pop('with_counter', False)
            counter_filters = kwargs.pop('counter_filters', {})
            title = inflection.pluralize(inflection.humanize(model.__name__))
            kwargs.setdefault('title', title)
            kwargs.setdefault('menu', title)
            name = inflection.pluralize(inflection.underscore(model.__name__))
            admin.register_blueprint(create_model_admin_blueprint(name, __name__, model, **kwargs))
            if with_counter:
                admin.register_dashboard_counter(title,
                    lambda: self.query(model).filter(**counter_filters).count(),
                    icon=kwargs.get('icon'))

    def get_backend_class(self, name):
        try:
            backend_cls = import_string("frasco_models.backends.%s" % name)
        except ImportError:
            backend_cls = import_string(name)

        if inspect.ismodule(backend_cls):
            # Gives the possibility to reference a module and auto-discover the Backend class
            classes = find_classes_in_module(backend_cls, (Backend,))
            if not classes:
                raise ImportError("Cannot find a Backend class in module '%s'" % name)
            if len(classes) > 1:
                raise ImportError("Model backend '%s' references a module with multiple backends" % name)
            backend_cls = classes[0]
        elif not issubclass(backend_cls, Backend):
            raise ImportError("Class '%s' is not a subclass of Backend" % name)

        return backend_cls

    def require_backend(self, name):
        if self.backend.name != name:
            raise RequirementMissingError("A models backend named '%s' is required but '%s' is used" % (name, self.backend.name))

    def ensure_model(self, model_name, **fields):
        if inspect.isclass(model_name):
            model_name = model_name.__name__
        if model_name not in self.models:
            self.models[model_name] = self.backend.ensure_model(model_name)
        if fields and self.options['ensure_schema']:
            for k, v in fields.iteritems():
                if not isinstance(v, dict):
                    fields[k] = dict(type=v)
            self.backend.ensure_schema(model_name, fields)
        return self.models[model_name]

    def __getitem__(self, name):
        return self.ensure_model(name)

    def __setitem__(self, name, model):
        self.models[name] = model

    def __contains__(self, name):
        return name in self.models

    def query(self, model):
        return Query(self.ensure_model(model), self.backend)

    def transaction(self, *args, **kwargs):
        return transaction(*args, **kwargs)

    def scoped_query(self, model, scope=None):
        q = self.query(model)
        if "model_scopes" in current_context.data:
            q = q.filter(**current_context.data.model_scopes.get(model.__name__, {}))
        if scope:
            scopes = scope if isinstance(scope, list) else list([scope])
            for s in scopes:
                if s not in self.scopes:
                    raise QueryError("Missing model scope '%s'" % s)
                q = q.filter(**eval_expr(self.scopes[s], current_context.vars))
        return q

    @action("build_model_query")
    def build_query(self, model, scope=None, filter_from=None, search_query=None, search_query_default_field=None,
                    order_by=None, limit=None, offset=None, **kwargs):
        q = self.scoped_query(model, scope)

        filters = {}
        if filter_from == "form":
            filters.update(dict([(f.name, f.data) for f in current_context.data.form]))
        elif filter_from == "url":
            filters.update(dict([(k, v) for k, v in request.values.items()]))
        elif filter_from == "args":
            filters.update(dict([(k, v) for k, v in request.view_args.items()]))
        if 'filters_or' in kwargs:
            q = q.filter(or_(*kwargs.pop('filters_or')))
        filters.update(kwargs.get("filters", kwargs))

        if filters:
            q = q.filter(**filters)
        if search_query:
            q = q.filter(*parse_search_query(search_query, search_query_default_field))
        if order_by:
            q = q.order_by(order_by)
        if limit:
            q = q.limit(limit)
        if offset:
            q = q.offset(offset)

        return q

    @action("paginate_query")
    def paginate(self, query, page=None, per_page=None, check_bounds=True):
        if page is None:
            page = int(page or request.values.get("page", 1))
        if per_page is None:
            per_page = self.options["pagination_per_page"]
        total = query.order_by(None).offset(None).limit(None).count()
        pagination = Pagination(page, per_page, total)
        if check_bounds and pagination.nb_pages > 0 and (page < 1 or page > pagination.nb_pages):
            raise PageOutOfBoundError()
        return query.offset(pagination.offset).limit(per_page), pagination

    @action("find_model")
    def find_first(self, model, not_found_404=True, **query):
        model = self.ensure_model(model)
        obj = self.build_query(model, **query).first()
        if obj is None and not_found_404:
            abort(404)
        if not self.find_first.as_:
            self.find_first.as_ = as_single_model(model)
        current_context.data.model = obj
        return obj

    @action("find_models", default_option="model")
    def find_all(self, model, paginate=False, page=None, pagination_var="pagination", **query):
        model = self.ensure_model(model)
        q = self.build_query(model, **query)

        if paginate:
            per_page = paginate if not isinstance(paginate, bool) else None
            try:
                q, pagination = self.paginate(q, page, per_page)
            except PageOutOfBoundError:
                abort(404)
            current_context.vars[pagination_var] = pagination

        if not self.find_all.as_:
            self.find_all.as_ = as_many_models(model)
        current_context.data.models = q
        return q

    @action("count_models", default_option="model")
    def count(self, model, **query):
        model = self.ensure_model(model)
        count = self.build_query(model, **query).count()
        if not self.count.as_:
            self.count.as_ = "%s_count" % as_single_model(model)
        return count

    @action("create_model", default_option="model")
    def create(self, model, **attrs):
        obj = self.ensure_model(model)(**clean_kwargs_proxy(attrs))
        if not self.create.as_:
            self.create.as_ = as_single_model(obj.__class__)
        return obj

    @action("save_model", default_option="obj")
    @as_transaction
    def save(self, obj=None, model=None, **attrs):
        auto_assign = False
        obj = clean_proxy(obj)
        if obj is None:
            obj = self.ensure_model(model)()
            auto_assign = True
        if attrs:
            populate_obj(obj, clean_kwargs_proxy(attrs))
        self.backend.add(obj)
        if not self.save.as_ and auto_assign:
            self.save.as_ = as_single_model(obj.__class__)
        return obj

    @action("create_model_from_form", default_option="model", requires=["form"])
    def create_from_form(self, model, form=None, **attrs):
        form = form or current_context.data.form
        obj = self.ensure_model(model)()
        form.populate_obj(obj)
        populate_obj(obj, clean_kwargs_proxy(attrs))
        if not self.create_from_form.as_:
            self.create_from_form.as_ = as_single_model(obj.__class__)
        return obj

    @action("save_form_model", default_option="model", requires=["form"])
    @as_transaction
    def save_from_form(self, obj=None, model=None, form=None, **attrs):
        form = form or current_context.data.form
        obj = clean_proxy(obj)
        auto_assign = False
        if obj is None:
            if isinstance(model, str):
                obj = self.ensure_model(model)()
                auto_assign = True
            else:
                obj = model()
        form.populate_obj(obj)
        populate_obj(obj, clean_kwargs_proxy(attrs))
        self.backend.add(obj)
        if not self.save_from_form.as_ and auto_assign:
            self.save_from_form.as_ = as_single_model(obj.__class__)
        return obj

    @action("delete_model", default_option="obj")
    @as_transaction
    def delete(self, obj):
        self.backend.remove(obj)

    @action("create_form_from_model", default_option="model", requires=["form"])
    def create_form_from_model(self, model, **kwargs):
        return create_form_from_model(model, **kwargs)

    @action("check_model_not_exists")
    def check_not_exists(self, model, error_message=None, **query):
        q = self.build_query(model, **query)
        if q.count() > 0:
            if error_message:
                flash(error_message, "error")
            current_context.exit(trigger_action_group="model_exists")

    @action("define_model_scope")
    def define_scope(self, model, **filters):
        current_context.data.setdefault("model_scopes", {})
        current_context.data.model_scopes.setdefault(model, {})
        current_context.data.model_scopes[model].update(filters.get('filters', filters))

    @action(as_="slug")
    def create_unique_slug(self, value, model, column="slug", **kwargs):
        slug = slugify(value)
        return ensure_unique_value(model, column, slug, **kwargs)


def save_model(model):
    current_app.features.models.backend.add(model)


def delete_model(model):
    current_app.features.models.backend.remove(model)