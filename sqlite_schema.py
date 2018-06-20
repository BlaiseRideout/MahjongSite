#!/usr/bin/env python3

__doc__ = """
This collection of utilities parses the SQL accepted by SQLite to
create records describing the columns of tables and their associated
constraints.  It reads the pragma information from a SQLite database
and can compare the records to determine what parts of the schema
match and what don't.  It is designed to be used with schema
descriptions stored as lists of field descriptions and table
constraints. See mytable_schema below for an example.  The list of
strings forms a table specification that can be joined with commas to
form a table definition.
"""

mytable_schema = [
    'ID INTEGER PRIMARY KEY AUTOINCREMENT',
    'Field1 TEXT NOT NULL',
    'Field2 TEXT REFERENCES AnotherTable(ID) ON DELETE CASCADE',
    'Field3 REAL',
    'Field4 DATETIME DEFAULT CURRENT_TIMESTAMP',
    'CONSTRAINT KeepItReal UNIQUE(Field3, Field4)',
]

import sys
import collections
import sqlite3
import re

class sqliteCur():
    con = None
    cur = None
    def __init__(self, DBfile="sample_sqlite.db", autoCommit=False):
        self.__DBfile = DBfile
        self.__autoCommit = autoCommit
    def __enter__(self):
        self.con = sqlite3.connect(self.__DBfile)
        self.cur = self.con.cursor()
        self.cur.execute("PRAGMA foreign_keys = 1;")
        return self.cur
    def __exit__(self, type, value, traceback):
        if self.cur and self.con and not value:
            self.cur.close()
            if self.__autoCommit:
               self.con.commit()
            self.con.close()

        return False

# Regular expressions used in the CREATE TABLE column defintion and
# table constraint arguments for SQLite
# (see https://www.sqlite.org/lang_createtable.html)
col_def_pattern = re.compile(
    r'\b(?!CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|CHECK)(?P<name>\w+)\s+(?P<type>(?P<typename>\w+)(\s*\([+-]?\d+\s*(,\s*[+-]?\d+\s*)?\))?)?',
    re.IGNORECASE)

constraint_name_pattern = re.compile(
    r'\b(CONSTRAINT\s+(?P<cname>\w+)\s*\b)?', re.IGNORECASE)

col_pk_constraint_pattern = re.compile(
    r'\bPRIMARY\s+(?P<pk>KEY)(\s+(ASC|DESC))?\b',
    re.IGNORECASE)

col_conflict_clause_pattern = re.compile(
    r'\b(ON\s+CONFLICT\s+(?P<cresolution>\w+))?\b',
    re.IGNORECASE)

col_autoincrement_pattern = re.compile(
    r'\b(?P<autoincrement>AUTOINCREMENT)?\b',
    re.IGNORECASE)

col_notnull_constraint_pattern = re.compile(
    r'\b(?P<notnull>NOT\s+NULL)\b',
    re.IGNORECASE)

col_unique_constraint_pattern = re.compile(
    r'\b(?P<unique>UNIQUE)\b',
    re.IGNORECASE)

col_check_constraint_pattern = re.compile( # Can't handle nested parentheses
    r"\bCHECK\s*\((?P<checkexpr>[\w\s,'.+/*-]+)\)\s*\b",
    re.IGNORECASE)

col_default_constraint_pattern = re.compile(
    r"\bDEFAULT\b\s*(?P<dflt_value>[+-]?\d+(\.\d*\b)?|'[^']*'|(TRUE|FALSE|NULL|CURRENT_(DATE|TIME|TIMESTAMP)\b)|\((?P<expr>[\w\s,'.+/*-]+)\))",
    re.IGNORECASE)

col_collate_constraint_pattern = re.compile(
    r'\bCOLLATE\s+(?P<collate>\w+)\b',
    re.IGNORECASE)

fkey_constraint_pattern = re.compile(
    r'\bFOREIGN\s+KEY\s*\((?P<columns>(?P<column1>\w+)(\s*,\s*\w+)*\s*)\)',
    re.IGNORECASE)

fkey_clause_ref_pattern = re.compile(
    r'\bREFERENCES\s+(?P<table>\w+)\s*\((?P<columns>(?P<column1>\w+)(\s*,\s*\w+)*\s*)\)',
    re.IGNORECASE)

fkey_clause_conflict_pattern = re.compile(
    r'\b((ON\s+(?P<action>DELETE|UPDATE|)\s+(?P<reaction>SET\s+(NULL|DEFAULT)|CASCADE|RESTRICT|NO\s+ACTION))|MATCH\s+(?P<match>\w+))\b',
    re.IGNORECASE)

fkey_clause_defer_pattern = re.compile(
    r'\b(NOT\s+)?DEFERABLE(\s+INITIALLY\s+(DEFERRED|IMMEDIATE))?\b',
    re.IGNORECASE)

# This tree specifies sequences of regexes to try in parsing column
# definitions.  Table constraints are in a separate tree, which can be
# combined with this one.
# Each node in the tree has the form (regex, repeat, next_tree)
# The regex will be tested on the beginning of a string ignoring leading
# whitespace, if it succeeds the next_tree of patterns will be tried
# If repeat is true, after trying the next_tree, this node will be tried again
# until it fails or the string is fully parsed.
# The tree and next_tree are lists; failing a node in the tree moves on to
# the next element of the list which is a sibling node in the tree.
column_def_patterns = [
    (col_def_pattern, False,
     [(constraint_name_pattern, True,
       [(col_pk_constraint_pattern, False, [
            (col_conflict_clause_pattern, False, [
                (col_autoincrement_pattern, False, [])
            ]),
       ]),
        (col_notnull_constraint_pattern, False, [
            (col_conflict_clause_pattern, False, []),
        ]),
        (col_unique_constraint_pattern, False, [
            (col_conflict_clause_pattern, False, []),
        ]),
        (col_check_constraint_pattern, False, []),
        (col_default_constraint_pattern, False, []),
        (col_collate_constraint_pattern, False, []),
        (fkey_clause_ref_pattern, False, [
            (fkey_clause_conflict_pattern, True, []),
            (fkey_clause_defer_pattern, False, []),
        ]),
       ]
     ),
     ]
    ),
]

table_pkey_constraint_pattern = re.compile(
    r'\bPRIMARY\s+KEY\s*\((?P<columns>(?P<column1>\w+)(\s*,\s*\w+)*\s*)\)',
    re.IGNORECASE)

table_unique_constraint_pattern = re.compile(
    r'\bUNIQUE\s*\((?P<columns>(?P<column1>\w+)(\s*,\s*\w+)*\s*)\)',
    re.IGNORECASE)

# This can't handle nested parentheses
table_check_constraint_pattern = re.compile( 
    r'\bCHECK\s*\((?P<expr>[\w\s<=>,*/+-]+)\)', 
    re.IGNORECASE)

# The tree for table constraints below is similar to that for column
# definitions, except it will produce foreign key, primary key, uniqueness,
# and check constraint records
table_constraint_patterns = [
    (constraint_name_pattern, False,
     [(table_pkey_constraint_pattern, False,
       [(col_conflict_clause_pattern, False, [])
       ],
     ),
      (table_unique_constraint_pattern, False,
       [(col_conflict_clause_pattern, False, [])
       ],
      ),
      (table_check_constraint_pattern, False, []),
      (fkey_constraint_pattern, False,
        [(fkey_clause_ref_pattern, False, 
          [(fkey_clause_conflict_pattern, True, []),
           (fkey_clause_defer_pattern, False, []),
          ]
        ),
        ]
      ),
     ]
    ),
]

def parent_tables(table_spec):
    """Get the list of table names mentioned in foreign key specs of a table
    specification.  These are mentioned in the REFERENCES clause that
    can appear in column definitions or in table constraints
    """
    parents = []
    for spec in table_spec:
        match = fkey_clause_ref_pattern.search(spec)
        if match:
            parents.append(match.group('table'))
    return parents

def column_specs(table_spec):
    "Get the subset of table specification lines that define the columns"
    col_specs = []
    for spec in table_spec:
        if column_def_or_constraint_to_pragma_records(
                spec, patterns_to_try=table_constraint_patterns,
                throwexceptions=False, printto=None):
            break
        else:
            col_specs.append(spec)
    return col_specs

sqlite_column_record = collections.namedtuple(
    'Column',
    'cid, name, type, notnull, dflt_value, pk'
)
sqlite_fkey_record = collections.namedtuple(
    'Foreign_Key',
    # SQLite uses the field name 'from' but that's a Python keyword
    'id, seq, table, from_, to, on_update, on_delete, match'
)
sqlite_index_record = collections.namedtuple(
    'Index',
    'seq, name, unique, origin, partial'
)
# Make sample records with default values filled in
base_column_def_record = sqlite_column_record(None, None, None, 0, None, 0)
base_fkey_record = sqlite_fkey_record(
    None, None, None, None, None, 'NO_ACTION', 'NO_ACTION', None)
base_index_record = sqlite_index_record(None, None, 1, None, 0)
base_record_prototype = {
    col_def_pattern: base_column_def_record,
    fkey_constraint_pattern: base_fkey_record,
    table_pkey_constraint_pattern: base_index_record._replace(origin='pk'),
    table_unique_constraint_pattern: base_index_record._replace(origin='u'),
}

# Get pragma records for a particular table in a SQLite database
def pragma_records_for_table(tablename, DBfile='sample_sqlite.db'):
    records = []
    with sqliteCur(DBfile=DBfile) as cur:
        cur.execute("PRAGMA table_info('{0}')".format(tablename))
        records = [sqlite_column_record(*row) for row in cur.fetchall()]
        if records:
            cur.execute("PRAGMA foreign_key_list('{0}')".format(tablename))
            records.extend(sqlite_fkey_record(*row) 
                           for row in cur.fetchall())
            cur.execute("PRAGMA index_list('{0}')".format(tablename))
            records.extend(sqlite_index_record(*row) 
                           for row in cur.fetchall())
    return records

def words(spec):
    return re.findall(r'\w+', spec)

def dict_by_col_name(pragmas):
    result = {}
    for pragma in pragmas:
        if isinstance(pragma, sqlite_column_record):
            result[pragma.name.lower()] = pragma
    return result

def missing_fields(column_pragmas, actual_pragmas):
    actual_cols = dict_by_col_name(actual_pragmas)
    return [p for p in column_pragmas if 
            isinstance(p, sqlite_column_record) and 
            p.name.lower() not in actual_cols]

def deleted_fields(column_pragmas, actual_pragmas):
    return missing_fields(actual_pragmas, column_pragmas)

def common_fields(column_pragmas, actual_pragmas):
    actual_cols = dict_by_col_name(actual_pragmas)
    return [p for p in column_pragmas if 
            isinstance(p, sqlite_column_record) and 
            p.name.lower() in actual_cols]

def altered_fields(column_pragmas, actual_pragmas, ordermatters=False):
    result = []
    actual_cols = dict_by_col_name(actual_pragmas)
    for col in column_pragmas:
        if isinstance(col, sqlite_column_record) and col.name.lower() in actual_cols:
            actual = actual_cols[col.name.lower()]
            diff = record_differences(
                col, actual, exclude=([] if ordermatters else ['cid']))
            if diff:
                result.append((col, ["{} for field '{}'".format(d, col.name)
                                     for d in diff]))
    return result

def missing_constraints(table_pragmas, actual_pragmas):
    return [p for p in table_pragmas if 
            isinstance(p, (sqlite_fkey_record, sqlite_index_record)) and 
            not any(record_differences(p, a, exclude=['id', 'seq']) == []
                    for a in actual_pragmas)]

def deleted_constraints(table_pragmas, actual_pragmas):
    return missing_constraints(actual_pragmas, table_pragmas)

def column_def_or_constraint_to_pragma_records(
        spec, context=[], tablename='',
        patterns_to_try = column_def_patterns + table_constraint_patterns,
        throwexceptions=True, printto=sys.stderr):
    """Parse a line of a table specification that typically has one column
    definition or one table constraint specification.
    The context variable should have all the pragma records that have been
    parsed before this line, so references to columns that are defined
    earlier can be resolved.  Some pragma records in the context can be
    modified by later constraints such as PRIMARY KEY constraints.
    The tablename should be the name of the table in SQLite and will be
    used in naming constraints.
    The patterns_to_try is the grammar to use in parsing (in the form of a
    tree of regex tuples).
    If grammar errors are found, they can either cause exceptions, or be
    printed to a file (or be silently ignored if printto is None).
    """
    global base_record_prototype
    # Walk the tree of patterns, find matching regex's,
    # Create corresponding records while inserting values into named fields
    # as regex's match
    # Return a list of pragma records built from the spec
    pragmas = []
    stack = []
    indices = 0
    past_indices = 0
    for p in context:
        if isinstance(p, sqlite_index_record):
            past_indices += 1
    while patterns_to_try and len(spec) > 0:
        pattern, repeat, next_patterns = patterns_to_try[0]
        m = pattern.search(spec)  # Look for match at beginning of string
        if m and (m.start() == 0 or spec[0:m.start()].isspace()):
            if pattern in base_record_prototype and (
                len(pragmas) == 0 or 
                not isinstance(pragmas[-1], base_record_prototype[pattern])):
                pragmas.append(base_record_prototype[pattern])
            if len(pragmas) > 0:
                for field in pattern.groupindex:
                    if (m.group(field) is not None and
                        field in pragmas[-1]._fields):
                        kwargs = {field: m.group(field)}
                        pragmas[-1] = pragmas[-1]._replace(**kwargs)
                # Handle special case matches
                pragmas = update_pragma_record_stack_with_match(
                    pragmas, pattern, m)
            if repeat:
                state = (patterns_to_try, len(spec))
                if state not in stack:
                    stack.append(state)
            patterns_to_try = next_patterns
            spec = spec[m.end():]
        else:
            patterns_to_try = patterns_to_try[1:]
        if len(patterns_to_try) == 0 and stack and stack[-1][1] > len(spec):
            patterns_to_try, l = stack.pop()
    if len(spec) > 0 and not spec.isspace():
        msg = 'Unable to parse this part of the column definition: "{}"'.format(
            spec)
        if throwexceptions:
            raise Exception(msg)
        else:
            if printto:
                print(msg, file=printto)
            result = None
    else:
        # After first pass through specifications to build pragmas,
        # clean up pragmas where multiple columns were specified
        # and fix constraint names
        result = []
        for i, pragma in enumerate(pragmas):
            if isinstance(pragma, sqlite_column_record):
                result.append(pragma)
            elif isinstance(pragma, sqlite_fkey_record):
                if (isinstance(pragma.from_, str) and i+1 < len(pragmas) and
                    isinstance(pragmas[i+1], sqlite_column_record) and
                    pragma.from_ == pragmas[i+1].name):
                    if len(pragma.to) > 1:
                        msg = (('Foreign key refers to multiple columns '
                                '{} in table {} for field {}').format(
                                    pragma.to, pragma.table, pragma.from_))
                        if throwexceptions:
                            raise Exception(msg)
                        elif printto:
                            print(msg, file=printto)
                    else:
                        pragma = pragma._replace(to=pragma.to[0])
                    result.append(pragma)
                elif isinstance(pragma.from_, list):
                    if not (isinstance(pragma.to, list) and
                            len(pragma.from_) == len(pragma.to)):
                        msg = (('Foreign key constraint has mismatched number '
                                'of keys, {} vs. {} in table {}').format(
                                    pragma.from_, pragma.to, pragma.table))
                        if throwexceptions:
                            raise Exception(msg)
                        elif printto:
                            print(msg, file=printto)
                    else:
                        for i in range(len(pragma.from_)):
                            result.append(pragma._replace(
                                from_=pragma.from_[i], to=pragma.to[i]))
            elif isinstance(pragma, sqlite_index_record):
                for col in pragma.seq:
                    matching_col = [
                        p for p in context if
                        isinstance(p, sqlite_column_record) and
                        col.lower() == p.name.lower()]
                    if len(matching_col) != 1:
                        msg = ('{} constraint clause mentions {} which has '
                               '{} matches among the fields of {}').format(
                                   'UNIQUE' if pragma.origin == 'u' else
                                   'PRIMARY KEY',
                                   col, len(matching_col), tablename)
                        if throwexceptions:
                            raise Exception(msg)
                        elif printto:
                            print(msg, file=printto)
                    elif pragma.origin == 'pk': # Force PK flag to true
                        pk_field = matching_col[0]
                        pos = context.index(pk_field)
                        context[pos] = pk_field._replace(pk=1)
                pragma = pragma._replace(
                    seq=past_indices + indices,
                    name='sqlite_autoindex_{}_{}'.format(
                        tablename, past_indices + indices + 1))
                result.append(pragma)
                indices += 1
    return result

def update_pragma_record_stack_with_match(pragma_record_stack, pattern, match):
    """During parsing, the pragma record stack holds all the pragma records
    generated by the different clauses found so far in a specification.  This
    routine handles all the special value conversions for particular fields
    and manipulations between clauses.  The result is a revised stack.
    """
    top_record = pragma_record_stack[-1]
    if isinstance(top_record, sqlite_column_record):
        # Clean up values extracted via regexes
        for field in ['notnull', 'pk']:     # Coerce boolean fields to 0 or 1
            if field in pattern.groupindex:
                kwargs = {field: 1 if len(match.group(field)) > 0 else 0}
                top_record = top_record._replace(**kwargs)
        if 'dflt_value' in pattern.groupindex:
            val = match.group('dflt_value')
            kwargs = {'dflt_value': val}
            if val.upper() == 'NULL':
                kwargs['dflt_value'] = None
            elif val[0] == '(' and val[-1] == ')':
                kwargs['dflt_value'] = val[1:-1]
            if kwargs['dflt_value'] != top_record.dflt_value:
                top_record = top_record._replace(**kwargs)
        elif 'table' in pattern.groupindex and 'columns' in pattern.groupindex:
            if len(pragma_record_stack) <= 1 or not isinstance(
                    pragma_record_stack[-2], sqlite_fkey_record):
                pragma_record_stack[-1:-1] = [
                    base_fkey_record._replace(
                        table=match.group('table'),
                        from_=top_record.name,
                        to=words(match.group('columns')))]
        elif (('match' in pattern.groupindex or
               ('action' in pattern.groupindex and 
                'reaction' in pattern.groupindex)
               and len(pragma_record_stack) > 1 and 
               isinstance(pragma_record_stack[-2], sqlite_fkey_record))):
            if 'action' in pattern.groupindex and 'reaction' in pattern.groupindex:
                reaction = ' '.join([x.upper() 
                                     for x in words(match.group('reaction'))])
                if match.group('action').upper() == 'DELETE':
                    pragma_record_stack[-2] = pragma_record_stack[-2]._replace(
                        on_delete=reaction)
                else:
                    pragma_record_stack[-2] = pragma_record_stack[-2]._replace(
                        on_update=reaction)
            elif 'match' in pattern.groupindex:
                    pragma_record_stack[-2] = pragma_record_stack[-2]._replace(
                        match=match.group('match'))

    elif isinstance(top_record, sqlite_fkey_record):
        if 'columns' in pattern.groupindex and 'column1' in pattern.groupindex:
            clean_cols = words(match.group('columns'))
            if pattern == fkey_constraint_pattern:
                top_record = top_record._replace(from_=clean_cols)
            elif pattern == fkey_clause_ref_pattern:
                top_record = top_record._replace(to=clean_cols)
        elif 'action' in pattern.groupindex and 'reaction' in pattern.groupindex:
            reaction = ' '.join([x.upper() 
                                 for x in words(match.group('reaction'))])
            if match.group('action').upper() == 'DELETE':
                top_record = top_record._replace(on_delete=reaction)
            else:
                top_record = top_record._replace(on_update=reaction)
    elif isinstance(top_record, sqlite_index_record):
        if 'columns' in pattern.groupindex and 'column1' in pattern.groupindex:
            clean_cols = words(match.group('columns'))
            top_record = top_record._replace(seq=clean_cols)
    pragma_record_stack[-1] = top_record
    return pragma_record_stack

def record_differences(record1, record2, include=None, exclude=None,
                       exactfields=False):
    """Compare records by comparing some or all fields, ignoring case
    of fields with string values. Ignore missing fields if exactfields is
    false.  Returns a list of strings describing field differences.  The
    list is empty if no differences were found.
    """
    result = []
    fields = set(include if include else record1._fields)
    if exactfields:
        fields |= set(record2._fields)
    if exclude:
        fields -= set(exclude)
    for field in fields:
        in1 = field in record1._fields
        in2 = field in record2._fields
        if not (in1 and in2):
            if exactfields:
                if in1:
                    result.append("Field '{}' in first but not second".format(
                        field))
                else:
                    result.append("Field '{}' in second but not first".format(
                        field))
        else:
            v1 = getattr(record1, field)
            v2 = getattr(record2, field)
            str1 = isinstance(v1, str)
            str2 = isinstance(v2, str)
            if ((v1.lower() != v2.lower()) if (str1 and str2) else v1 != v2):
                result.append("Field '{}' differs".format(field))
    return result
    
def check_constraint_pattern_match(table, specification):
    """Test the constraint pattern grammar on a table specification
    showing what was and wasn't recognized."""
    
    print('\n', '='*60, '\n  In Table', table)
    matches = 0
    pragma_records = []
    for i, spec in enumerate(specification):
        print(' ', spec)
        p_records = column_def_or_constraint_to_pragma_records(
            spec, tablename=table, context=pragma_records)
        if len(p_records) == 0:
            print('!'*10, 'NO PRAGMA RECORDS PRODUCED', '!'*10)
        for p in p_records:
            print('  ->', 
                  p._replace(cid=i) if isinstance(p, sqlite_column_record)
                  else p)
        pragma_records.extend(p_records)
