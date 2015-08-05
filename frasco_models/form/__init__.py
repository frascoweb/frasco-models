from frasco import current_app
from frasco_forms import TemplateForm
from frasco_forms.form import field_type_map
from frasco.utils import unknown_value
from wtforms.fields.core import UnboundField
import inflection
import datetime
import inspect
import fields


__all__ = ('create_form_from_model', 'create_form_class_from_model')


class ModelFormGenerationError(Exception):
    pass


model_type_map = dict([(str, "text"), (unicode, "text"), (int, "int"),
    (float, "float"), (datetime.datetime, "datetime5"), (datetime.date, "date5"),
    (bool, "checkbox")])


def create_form_from_model(model, **kwargs):
    obj = None
    if not inspect.isclass(model):
        obj = model
    return create_form_class_from_model(model, **kwargs)(obj=obj)


def create_form_class_from_model(model, backend=None, template=unknown_value, fields=None,
                                 fields_specs=None, exclude_fields=None):
    if not backend:
        backend = current_app.features.models.backend
    if template is unknown_value:
        if 'bootstrap' in current_app.features:
            template = "model_bs_form_template.html"
        else:
            template = "model_form_template.html"

    model_name = model.__name__ if inspect.isclass(model) else model.__class__.__name__
    form_name = model_name + 'Form'
    form_class = type(form_name, (TemplateForm,), {"name": form_name, "template": template})

    names = []
    specs = fields_specs or {}
    inspected_fields = backend.inspect_fields(model)
    if fields:
        for f in fields:
            if isinstance(f, tuple):
                specs[f[0]] = f[1]
                names.append(f[0])
            else:
                names.append(f)
    else:
        names = [n for n, _ in inspected_fields]

    for name in names:
        if exclude_fields and name in exclude_fields:
            continue
        spec = specs.get(name)
        if not spec:
            spec = dict(inspected_fields).get(name)
        if not spec:
            raise ModelFormGenerationError("Unknown field '%s'" % name)
        setattr(form_class, name, create_form_field_from_model_field(model, name, spec))

    return form_class


def create_form_field_from_model_field(model, name, spec):
    if isinstance(spec, UnboundField):
        return spec
    field_type = 'text'
    if spec.get('form_field'):
        field_type = spec['form_field']
    elif spec.get('type'):
        field_type = model_type_map.get(spec['type'], "text")
    kwargs = {"label": spec.get('label', inflection.humanize(name))}
    if spec.get('description'):
        kwargs['description'] = spec['description']
    if 'form_field_kwargs' in spec:
        kwargs.update(spec['form_field_kwargs'])
    return field_type_map[field_type](**kwargs)


