from wtforms import widgets
from wtforms.compat import text_type, string_types
from wtforms.fields import SelectFieldBase
from wtforms.validators import ValidationError
from frasco import current_app
from frasco_forms.form import field_type_map
import operator


class ModelSelectField(SelectFieldBase):
    """
    Inspired by wtforms.ext.sqlalchemy.QuerySelectField
    """
    widget = widgets.Select()

    def __init__(self, model, label=None, validators=None, query_factory=None,
                 get_pk='id', get_label=None, get_value=None, allow_blank=False,
                 blank_text='', **kwargs):
        super(ModelSelectField, self).__init__(label, validators, **kwargs)

        if not query_factory:
            query_factory = lambda: current_app.features.models.query(model)

        self.model = current_app.features.models.ensure_model(model)
        self.query_factory = query_factory
        self.get_pk = operator.attrgetter(get_pk)
        if get_label is None:
            self.get_label = lambda x: x
        elif isinstance(get_label, string_types):
            self.get_label = operator.attrgetter(get_label)
        else:
            self.get_label = get_label
        if get_value is None:
            self.get_value = lambda o: o
        elif isinstance(get_value, string_types):
            self.get_value = operator.attrgetter(get_value)
        else:
            self.get_value = get_value

        self.allow_blank = allow_blank
        self.blank_text = blank_text
        self.query = None
        self._object_list = None

    def _get_data(self):
        if self._formdata is not None:
            for pk, obj in self._get_object_list():
                if pk == self._formdata:
                    self._set_data(self.get_value(obj))
                    break
        return self._data

    def _set_data(self, data):
        self._data = data
        self._formdata = None

    data = property(_get_data, _set_data)

    def _get_object_list(self):
        if self._object_list is None:
            query = self.query or self.query_factory()
            get_pk = self.get_pk
            self._object_list = list((text_type(get_pk(obj)), obj) for obj in query)
        return self._object_list

    def iter_choices(self):
        if self.allow_blank:
            yield ('__None', self.blank_text, self.data is None)

        for pk, obj in self._get_object_list():
            yield (pk, self.get_label(obj), self.get_value(obj) == self.data)

    def process_formdata(self, valuelist):
        if valuelist:
            if self.allow_blank and valuelist[0] == '__None':
                self.data = None
            else:
                self._data = None
                self._formdata = valuelist[0]

    def pre_validate(self, form):
        data = self.data
        if data is not None:
            for pk, obj in self._get_object_list():
                if data == self.get_value(obj):
                    break
            else:
                raise ValidationError(self.gettext('Not a valid choice'))
        elif self._formdata or not self.allow_blank:
            raise ValidationError(self.gettext('Not a valid choice'))


field_type_map.update({
    "model": ModelSelectField
})