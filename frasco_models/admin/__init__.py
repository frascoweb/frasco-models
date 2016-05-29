from frasco_admin import AdminBlueprint
from frasco import current_app, current_context, abort, request, redirect, url_for
from frasco_models.form import create_form_class_from_model
import inflection


def create_model_admin_blueprint(name, package, model, title=None, menu=None, icon=None, template_folder=None,
                                 list_columns=None, search_query_default_field=None, edit_actions=None,
                                 with_create=True, with_edit=True, with_delete=True, url_prefix=None,
                                 form_fields=None, form_fields_specs=None, form_exclude_fields=None,
                                 filters=None, list_actions=None, can_edit=None, can_create=None):
    if not url_prefix:
        url_prefix = "/%s" % name
    bp = AdminBlueprint("admin_%s" % name, package, url_prefix=url_prefix,
            template_folder=template_folder)
    tpl_dir = name if template_folder else "models_default"

    def get_form_class():
        if not getattr(model, '__admin_form__', None):
            model.__admin_form__ = create_form_class_from_model(model,
                fields=getattr(model, '__admin_form_fields__', form_fields),
                fields_specs=getattr(model, '__admin_form_fields_specs__', form_fields_specs),
                exclude_fields=getattr(model, '__admin_form_exclude_fields__', form_exclude_fields))
        return model.__admin_form__
    bp.get_form_class = get_form_class

    if hasattr(model, '__admin_search_query_default_field__'):
        search_query_default_field = model.__admin_search_query_default_field__
    if hasattr(model, '__admin_list_columns__'):
        list_columns = model.__admin_list_columns__
    if hasattr(model, '__admin_filters__'):
        filters = model.__admin_filters__

    if not edit_actions:
        edit_actions = []
    if not list_actions:
        list_actions = []
    if not filters:
        filters = {}
    if can_create is True or (can_create is None and with_create):
        can_create = ".create"
    if can_edit is True or (can_edit is None and with_edit):
        can_edit = ".edit"
    if with_delete:
        edit_actions.append(('Delete', '.delete', {'style': 'danger'}))

    @bp.view("/", template="admin/%s/index.html" % tpl_dir, admin_title=title, admin_menu=menu, admin_menu_icon=icon)
    def index():
        columns = list_columns
        if not columns:
            columns = []
            for name, _ in current_app.features.models.backend.inspect_fields(model):
                columns.append((name, inflection.humanize(name)))
        q = dict(order_by=request.args.get('sort', 'id'), **filters)
        s = request.args.get('search')
        if s:
            if s.startswith('#'):
                q['id'] = s[1:]
            else:
                q['search_query'] = s
                q['search_query_default_field'] = search_query_default_field
        current_context['actions'] = []
        if can_create:
            current_context['actions'].append(('Create', url_for(can_create)))
        for label, url in list_actions:
            if callable(url):
                url = url()
            current_context['actions'].append((label, url))
        current_context['objs'] = current_app.features.models.find_all(model, paginate=15, **q)
        current_context['model_fields'] = [i[0] if isinstance(i, tuple) else i for i in columns]
        current_context['table_headers'] = [i[1] if isinstance(i, tuple) else inflection.humanize(i) for i in columns]
        current_context['can_create'] = can_create
        current_context['can_edit'] = can_edit

    if with_create:
        @bp.view("/create", template="admin/%s/create.html" % tpl_dir, methods=['GET', 'POST'])
        def create():
            form = get_form_class()()
            current_context['form'] = form
            if form.validate_on_submit():
                obj = current_app.features.models.save_from_form(model=model, form=form)
                return redirect(url_for('.edit', id=obj.id))

    if with_edit:
        @bp.view("/<id>", template="admin/%s/edit.html" % tpl_dir, methods=['GET', 'POST'])
        def edit(id):
            obj = current_app.features.models.query(model).get_or_404(id)
            form = get_form_class()(obj=obj)
            current_context['obj'] = obj
            current_context['admin_section_title'] = "Edit #%s" % obj.id
            current_context['form'] = form
            current_context['edit_actions'] = edit_actions
            if form.validate_on_submit():
                current_app.features.models.save_from_form(obj=obj, form=form)

    if with_delete:
        @bp.route("/<id>/delete")
        def delete(id):
            obj = current_app.features.models.query(model).get_or_404(id)
            current_app.features.models.backend.remove(obj)
            return redirect(url_for('.index'))

    return bp