import glob
import yaml
import copy

# This script takes all ECS and custom fields already loaded, and lets users
# filter out the ones they don't need.


def combine_all_subsets(subsets):
    '''Merges N subsets into one. Strips top level 'name' and 'fields' keys as well as non-ECS field options since we can't know how to merge those.'''
    merged_subset = {}
    for subset in subsets:
        strip_non_ecs_options(subset['fields'])
        merge_subsets(merged_subset, subset['fields'])
    return merged_subset


def load_subset_definitions(file_globs):
    if not file_globs:
        return []
    subsets = []
    for f in eval_globs(file_globs):
        raw = load_yaml_file(f)
        subsets.append(raw)
    if not subsets:
        raise ValueError('--subset specified, but no subsets found in {}'.format(file_globs))
    return subsets


def load_yaml_file(file_name):
    with open(file_name) as f:
        return yaml.safe_load(f.read())


def eval_globs(globs):
    '''Accepts an array of glob patterns or file names, returns the array of actual files'''
    all_files = []
    for g in globs:
        new_files = glob.glob(g)
        if len(new_files) == 0:
            warn("{} did not match any files".format(g))
        else:
            all_files.extend(new_files)
    return all_files


# You know, for silent tests
def warn(message):
    print(message)


ecs_options = ['fields']


def strip_non_ecs_options(subset):
    for key in subset:
        subset[key] = {x: subset[key][x] for x in subset[key] if x in ecs_options}
        if 'fields' in subset[key] and isinstance(subset[key]['fields'], dict):
            strip_non_ecs_options(subset[key]['fields'])


def merge_subsets(a, b):
    '''Merges field subset definitions together. The b subset is merged into the a subset. Assumes that subsets have been stripped of non-ecs options.'''
    for key in b:
        if key not in a:
            a[key] = b[key]
        elif 'fields' in a[key] and 'fields' in b[key]:
            if b[key]['fields'] == '*':
                a[key]['fields'] = '*'
            elif isinstance(a[key]['fields'], dict) and isinstance(b[key]['fields'], dict):
                merge_subsets(a[key]['fields'], b[key]['fields'])
        elif 'fields' in a[key] or 'fields' in b[key]:
            raise ValueError("Subsets unmergeable: 'fields' found in key '{}' in only one subset".format(key))


def extract_matching_fields(fields, subset_definitions):
    '''Removes fields that are not in the subset definition. Returns a copy without modifying the input fields dict.'''
    retained_fields = {x: fields[x].copy() for x in subset_definitions}
    for key, val in subset_definitions.items():
        for option in val:
            if option not in ecs_options:
                new_field_details = fields[key].get('field_details', {}).copy()
                new_field_details[option] = val[option]
                retained_fields[key]['field_details'] = new_field_details
        # If the field in the schema has a 'fields' key, we expect a 'fields' key in the subset
        if 'fields' in fields[key]:
            if 'fields' not in val:
                raise ValueError("'fields' key expected, not found in subset for {}".format(key))
            elif isinstance(val['fields'], dict):
                retained_fields[key]['fields'] = extract_matching_fields(fields[key]['fields'], val['fields'])
            elif val['fields'] != "*":
                raise ValueError("Unexpected value '{}' found in 'fields' key".format(val['fields']))
        # If the field in the schema does not have a 'fields' key, there should not be a 'fields' key in the subset
        elif 'fields' in val:
            raise ValueError("'fields' key not expected, found in subset for {}".format(key))
    return retained_fields
