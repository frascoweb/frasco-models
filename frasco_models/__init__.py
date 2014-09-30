from frasco import Feature, action, current_app, request, abort, listens_to, current_context
from frasco.utils import (AttrDict, import_string, populate_obj, RequirementMissingError,\
                          find_classes_in_module, slugify)
from frasco.expression import compile_expr, eval_expr
from .backend import Backend
from .query import Query, QueryFilter, QueryFilterGroup, and_, or_
from .utils import *
import inspect


class ModelsFeature(Feature):
    name = "models"
    defaults = {"backend": "frasco_models.backends.persistpy.PersistpyBackend",
                "pagination_per_page": 10,
                "scopes": {}}
    
    def init_app(self, app):
        self.backend_cls = self.get_backend_class(self.options["backend"])
        self.backend = self.backend_cls(app, self.options)
        self.scopes = compile_expr(self.options["scopes"])
        self.connected = False
        self.models = {}

        @listens_to("before_task")
        @listens_to("before_command")
        @app.before_request
        def before_request(*args, **kwargs):
            if not self.connected:
                self.backend.connect()
                self.connected = True
        @listens_to("after_task")
        @listens_to("after_command")
        @app.teardown_request
        def teardown_request(*args, **kwargs):
            if self.connected:
                self.backend.close()
                self.connected = False

        models_pkg = "models"
        if app.import_name != "__main__":
            models_pkg = app.import_name + "." + models_pkg
        try:
            __import__(models_pkg)
        except ImportError:
            pass

    def get_backend_class(self, name):
        try:
            backend_cls = import_string(name)
        except ImportError as e:
            try:
                backend_cls = import_string("frasco_models.backends.%s" % name)
            except ImportError:
                raise e

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
        if fields:
            for k, v in fields.iteritems():
                if not isinstance(v, dict):
                    fields[k] = dict(type=v)
            self.backend.ensure_fields(model_name, fields)
        return self.models[model_name]

    def __getitem__(self, name):
        return self.ensure_model(name)

    def __contains__(self, name):
        return name in self.models

    def query(self, model):
        return Query(self.ensure_model(model), self.backend)

    def q(self, model):
        return self.query(model)

    @action("build_model_query")
    def build_query(self, model, scope=None, filter_from=None, order_by=None, limit=None, offset=None, **kwargs):
        q = self.query(model)

        filters = dict()
        if scope:
            scopes = scope if isinstance(scope, list) else list([scope])
            for s in scopes:
                if s not in self.scopes:
                    raise Exception("Missing model scope '%s'" % s)
                filters.update(eval_expr(self.scopes[s], current_context.vars))
        if "model_scopes" in current_context.data:
            filters.update(current_context.data.model_scopes.get(model.__name__, {}))

        if filter_from == "form":
            filters.update(dict([(f.name, f.data) for f in current_context.data.form]))
        elif filter_from == "url":
            filters.update(dict([(k, v) for k, v in request.values.items()]))
        elif filter_from == "args":
            filters.update(dict([(k, v) for k, v in request.view_args.items()]))

        filters.update(kwargs.get("filters", kwargs))

        if filters:
            q = q.filter_by(**filters)
        if order_by:
            q = q.order_by(order_by)
        if limit:
            q = q.limit(limit)
        if offset:
            q = q.offset(offset)

        return q

    @action("paginate_query")
    def paginate(self, query, page=1, per_page=None, check_bounds=True):
        if per_page is None:
            per_page = self.options["pagination_per_page"]
        total = query.order_by(None).offset(None).limit(None).count()
        pagination = Pagination(page, per_page, total)
        if check_bounds and (page < 1 or page > pagination.nb_pages):
            raise PageOutOfBoundError()
        return query.offset(pagination.offset).limit(per_page), pagination

    @action("find_model")
    def find_one(self, model, not_found_404=True, **query):
        model = self[model]
        q = self.build_query(model, **query)
        obj = q.first()
        if obj is None and not_found_404:
            abort(404)
        if not self.find_one.as_:
            self.find_one.as_ = as_single_model(model)
        current_context.data.model = obj
        return obj

    @action("find_models", default_option="model")
    def find(self, model, paginate=False, page=None, pagination_var="pagination", **query):
        model = self[model]
        q = self.build_query(model, **query)

        if paginate:
            page = int(page or request.values.get("page", 1))
            per_page = paginate if isinstance(paginate, int) else None
            try:
                q, pagination = self.paginate(q, page, per_page)
            except PageOutOfBoundError:
                abort(404)
            current_context.vars[pagination_var] = pagination

        if not self.find.as_:
            self.find.as_ = as_many_models(model)
        current_context.data.models = q
        return q

    @action("create_model", default_option="model")
    def create(self, model, **attrs):
        obj = self[model](**clean_kwargs_proxy(attrs))
        if not self.create.as_:
            self.create.as_ = as_single_model(obj.__class__)
        return obj

    @action("save_model", default_option="obj")
    def save(self, obj=None, model=None, **attrs):
        auto_assign = False
        obj = clean_proxy(obj)
        if obj is None:
            obj = self[model]()
            auto_assign = True
        if attrs:
            populate_obj(obj, clean_kwargs_proxy(attrs))
        self.backend.save(obj)
        if not self.save.as_ and auto_assign:
            self.save.as_ = as_single_model(obj.__class__)
        return obj

    @action("create_form_model", default_option="model", requires=["form"])
    def create_from_form(self, model, form=None, **attrs):
        form = form or current_context.data.form
        obj = self[model]()
        form.populate_obj(obj)
        populate_obj(obj, clean_kwargs_proxy(attrs))
        if not self.create_from_form.as_:
            self.create_from_form.as_ = as_single_model(obj.__class__)
        return obj

    @action("save_form_model", default_option="model", requires=["form"])
    def save_form(self, obj=None, model=None, form=None, **attrs):
        form = form or current_context.data.form
        obj = clean_proxy(obj)
        auto_assign = False
        if obj is None:
            if isinstance(model, str):
                obj = self[model]()
                auto_assign = True
            else:
                obj = model()
        form.populate_obj(obj)
        populate_obj(obj, clean_kwargs_proxy(attrs))
        self.backend.save(obj)
        if not self.save_form.as_ and auto_assign:
            self.save_form.as_ = as_single_model(obj.__class__)
        return obj

    @action("delete_model", default_option="obj")
    def delete(self, obj):
        self.backend.delete(clean_proxy(obj))

    @action("add_child_model")
    def add_child(self, obj, **opts):
        obj = clean_proxy(obj)
        for attr, value in opts.iteritems():
            if not isinstance(value, list):
                value = [value]
            if attr not in obj:
                obj.__class__.ensure_column(attr, list)
            elif getattr(obj, attr) is None:
                setattr(obj, attr, [])
            getattr(obj, attr).extend(map(clean_proxy, value))
        self.backend.save(obj)

    @action("remove_child_model")
    def remove_child(self, obj, **opts):
        obj = clean_proxy(obj)
        for attr, value in opts.iteritems():
            if not isinstance(value, list):
                value = [value]
            if attr in obj and getattr(obj, attr):
                for v in value:
                    getattr(obj, attr).remove(clean_proxy(v))
        self.backend.save(obj)

    @action("check_model_not_exists")
    def check_not_exists(self, model, error_message=None, **filters):
        q = self.query(self[model]).filter_by_dict(filters)
        if q.count() > 0:
            if error_message:
                flash(error_message, "error")
            current_context.exit(trigger_action_group="model_not_unique")

    @action("define_model_scope")
    def define_scope(self, model, **filters):
        ctx.data.setdefault("model_scopes", {})
        ctx.data.model_scopes.setdefault(model, {})
        ctx.data.model_scopes[model].update(filters)

    @action(as_="slug")
    def create_unique_slug(self, value, model, column="slug"):
        baseslug = slug = slugify(value)
        model = self[model]
        counter = 1
        while self.query(model).filter_by(**dict([(column, slug)])).count() > 0:
            slug = "%s-%s" % (baseslug, counter)
            counter += 1
        return slug