import glob
import os
import yaml
import helper
from generator import ecs_helpers

# File loading stuff


def ecs_files():
    """Return the schema file list to load"""
    schema_glob = os.path.join(os.path.dirname(__file__), '../schemas/*.yml')
    return sorted(glob.glob(schema_glob))


def read_schema_file(file):
    """Read a raw schema yml into a map, removing the wrapping array in each file"""
    with open(file) as f:
        raw = yaml.safe_load(f.read())
    fields = {}
    for field_set in raw:
        fields[field_set['name']] = field_set
    return fields


def load_schema_files(files=ecs_files()):
    fields_nested = {}
    for f in files:
        new_fields = read_schema_file(f)
        fields_nested.update(new_fields)
    return fields_nested


def load_use_case_files(files):
    merged_fields = {}
    for f in files:
        fields = helper.read_use_case_file(f)
        merged_fields = ecs_helpers.merge_dict_overwrite(merged_fields, fields)

    fields_flat = {}
    finalize_schemas(merged_fields, fields_flat)
    return merged_fields, fields_flat


# Generic helpers


def dict_clean_string_values(dict):
    """Remove superfluous spacing in all field values of a dict"""
    for key in dict:
        value = dict[key]
        if isinstance(value, str):
            dict[key] = value.strip()


def dict_set_default(dict, key, default):
    if key not in dict:
        dict[key] = default


# Finalize in memory representation of ECS field definitions (e.g. defaults, cleanup)

# Schema level (data about the field sets)


def schema_cleanup_values(schema):
    dict_clean_string_values(schema)
    schema_set_default_values(schema)
    schema_set_fieldset_prefix(schema)
    schema_fields_as_dictionary(schema)


def schema_set_default_values(schema):
    schema['type'] = 'group'
    dict_set_default(schema, 'group', 2)
    dict_set_default(schema, 'short', schema['description'])
    if "\n" in schema['short']:
        raise ValueError("Short descriptions must be single line.\nFieldset: {}\n{}".format(schema['name'], schema))


def schema_set_fieldset_prefix(schema):
    if 'root' in schema and schema['root']:
        schema['prefix'] = ''
    else:
        schema['prefix'] = schema['name'] + '.'


def schema_fields_as_dictionary(schema):
    """Re-nest the array of field names as a dictionary of 'fieldname' => { field definition }"""
    field_array = schema.pop('fields')
    schema['fields'] = {}
    for order, field in enumerate(field_array):
        field['order'] = order
        schema['fields'][field['name']] = field

# Field definitions


def field_cleanup_values(field, prefix):
    dict_clean_string_values(field)
    field_name_representations(field, prefix)
    field_set_defaults(field)


def field_name_representations(field, prefix):
    field['flat_name'] = prefix + field['name']
    field['dashed_name'] = field['flat_name'].replace('.', '-').replace('_', '-')


def field_set_defaults(field):
    if field['type'] == 'keyword':
        dict_set_default(field, 'ignore_above', 1024)
    if field['type'] == 'text':
        dict_set_default(field, 'norms', False)
    if field['type'] == 'object':
        dict_set_default(field, 'object_type', 'keyword')

    dict_set_default(field, 'short', field['description'])
    if "\n" in field['short']:
        raise ValueError("Short descriptions must be single line.\nField: {}\n{}".format(field['flat_name'], field))
        # print("  Short descriptions must be single line. Field: {}".format(field['flat_name']))

    if 'index' in field and not field['index']:
        dict_set_default(field, 'doc_values', False)
    if 'multi_fields' in field:
        field_set_multi_field_defaults(field)


def field_set_multi_field_defaults(parent_field):
    """Sets defaults for each nested field in the multi_fields array"""
    for mf in parent_field['multi_fields']:
        dict_set_default(mf, 'name', mf['type'])
        if mf['type'] == 'text':
            dict_set_default(mf, 'norms', False)
        mf['flat_name'] = parent_field['flat_name'] + '.' + mf['name']


def duplicate_reusable_fieldsets(schema, fields_flat, fields_nested):
    """Copies reusable field definitions to their expected places"""
    # Note: across this schema reader, functions are modifying dictionaries passed
    # as arguments, which is usually a risk of unintended side effects.
    # Here it simplifies the nesting of 'group' under 'user',
    # which is in turn reusable in a few places.
    if 'reusable' in schema:
        for new_nesting in sorted(schema['reusable']['expected']):

            # List field set names expected under another field set.
            # E.g. host.nestings = [ 'geo', 'os', 'user' ]
            nestings = fields_nested[new_nesting].setdefault('nestings', [])
            nestings.append(schema['name'])
            nestings.sort()

            # Explicitly list all leaf fields coming from field set reuse.
            for (name, field) in schema['fields'].items():
                # Poor folks deepcopy, sorry -- A Rubyist
                copied_field = field.copy()
                if 'multi_fields' in copied_field:
                    copied_field['multi_fields'] = list(map(lambda mf: mf.copy(), copied_field['multi_fields']))

                destination_name = new_nesting + '.' + field['flat_name']
                copied_field['flat_name'] = destination_name
                copied_field['original_fieldset'] = schema['name']

                fields_flat[destination_name] = copied_field

                # Nested: use original flat name under the destination fieldset
                fields_nested[new_nesting]['fields'][field['flat_name']] = copied_field

# Main


def finalize_schemas(fields_nested, fields_flat):
    for schema_name in fields_nested:
        schema = fields_nested[schema_name]

        schema_cleanup_values(schema)

        for (name, field) in schema['fields'].items():
            field_cleanup_values(field, schema['prefix'])

            fields_flat[field['flat_name']] = field

    # This happens as a second pass, so that all fieldsets have their
    # fields array replaced with a fields dictionary.
    for schema_name in fields_nested:
        schema = fields_nested[schema_name]

        duplicate_reusable_fieldsets(schema, fields_flat, fields_nested)


def load_schemas(files=ecs_files()):
    """Loads the given list of files"""
    fields_nested = load_schema_files(files)
    fields_flat = {}
    finalize_schemas(fields_nested, fields_flat)
    return fields_nested, fields_flat
