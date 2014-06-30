from __future__ import division, unicode_literals, absolute_import
from . import base, _database

import psycopg2


class Client(_database.Client):
    NUMERIC_TYPES = set([
        'integer',
        'bigint',
        'smallint',
        'numeric',
        'float',
        'real',
        'double precision',
    ])

    STRING_TYPES = set([
        'character varying',
        'character',
        'char',
        'name',
        'text',
    ])

    TIME_TYPES = set([
        'timestamp',
        'timestamp with time zone',
        'timestamp without time zone',
        'date',
        'time',
        'interval',
        'interval year to month',
        'interval day to second',
    ])

    BOOL_TYPES = set([
        'boolean',
    ])

    def __init__(self, database, **kwargs):
        self.name = database
        self.host = kwargs.get('host', 'localhost')
        self.port = kwargs.get('port', 5432)
        self.connect(user=kwargs.get('user'), password=kwargs.get('password'))

    def connect(self, user=None, password=None):
        self.connection = psycopg2.connect(database=self.name,
                                           host=self.host,
                                           port=self.port,
                                           user=user or None,
                                           password=password or None)

    def version(self):
        return self.fetchvalue('show server_version')

    def database(self):
        return {
            'name': self.name,
            'host': self.host,
            'port': self.port,
            'version': self.version(),
        }

    def schemas(self):
        query = '''
            SELECT nspname
            FROM pg_catalog.pg_namespace
            WHERE nspname <> 'information_schema'
                AND nspname NOT LIKE 'pg_%'
            ORDER BY nspname
        '''

        keys = ('name',)
        schemas = []

        for row in self.fetchall(query):
            attrs = dict(zip(keys, row))
            schemas.append(attrs)

        return schemas

    def tables(self, schema_name):
        query = '''
            SELECT table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
                AND table_schema = %s
            ORDER BY table_name
        '''

        keys = ('name',)
        tables = []

        for row in self.fetchall(query, [schema_name]):
            attrs = dict(zip(keys, row))
            tables.append(attrs)

        return tables

    def foreign_keys(self, schema_name, table_name, column_name):
        query = '''
            SELECT
                con.conname,
                ns.nspname,
                cl.relname,
                a1.attname
            FROM (
                SELECT
                    con1.conname,
                    -- pg_constraint stores oids in an array, unnest unpacks
                    -- the values so they can be joined on
                    unnest(con1.conkey) AS "origin",
                    unnest(con1.confkey) AS "target",
                    con1.confrelid,
                    con1.conrelid
                FROM pg_class cl
                    JOIN pg_namespace ns
                        ON cl.relnamespace = ns.oid
                    JOIN pg_constraint con1
                        ON con1.conrelid = cl.oid
                WHERE con1.contype = 'f'
                    AND ns.nspname = %s
                    AND cl.relname = %s
            ) con
            JOIN pg_class cl
                ON cl.oid = con.confrelid
            JOIN pg_namespace ns
                ON cl.relnamespace = ns.oid
            JOIN pg_attribute a1
               ON a1.attrelid = con.confrelid AND a1.attnum = con.target
            JOIN pg_attribute a2
               ON a2.attrelid = con.conrelid AND a2.attnum = con.origin
            WHERE a2.attname = %s
        '''

        keys = ('name', 'schema', 'table', 'column')
        fks = []
        for row in self.fetchall(query, [schema_name, table_name,
                                         column_name]):
            attrs = dict(zip(keys, row))
            fks.append(attrs)
        return fks

    def columns(self, schema_name, table_name):
        query = '''
            SELECT column_name,
                ordinal_position,
                is_nullable,
                data_type
            FROM information_schema.columns
            WHERE table_schema = %s
                AND table_name = %s
            ORDER BY ordinal_position
        '''

        keys = ('name', 'index', 'nullable', 'type')
        columns = []

        for row in self.fetchall(query, [schema_name, table_name]):
            attrs = dict(zip(keys, row))
            # Postgres column index are 1-based; this changes to 0-based
            attrs['index'] -= 1
            if attrs['nullable'] == 'YES':
                attrs['nullable'] = True
            else:
                attrs['nullable'] = False
            columns.append(attrs)

        return columns


class Database(base.Component):
    def sync(self):
        self.update(self.client.database())
        self.define(self.client.schemas(), Schema)

    @property
    def schemas(self):
        return self.definitions('schema', sort='name')

    @property
    def tables(self):
        # TODO, should this look up the user's search path?
        default_schema = self.schemas['public']
        return default_schema.tables


class Schema(base.Component):
    def sync(self):
        self.define(self.client.tables(self['name']), Table)

    @property
    def tables(self):
        return self.definitions('table', sort='name')


class Table(_database.Table):
    def sync(self):
        self.define(self.client.columns(self.parent['name'], self['name']),
                    Column)


class Column(_database.Column):
    @property
    def foreign_keys(self):
        if not self._foreign_keys_synced:
            root = self.root
            schema_name = self.parent.parent['name']
            table_name = self.parent['name']

            for attrs in self.client.foreign_keys(schema_name, table_name,
                                                  self['name']):
                # Find referenced node
                node = root\
                    .schemas[attrs['schema']]\
                    .tables[attrs['table']]\
                    .columns[attrs['column']]

                self.relate(node, 'REFERENCES', {
                    'name': attrs['name'],
                    'type': 'foreignkey',
                })

            self._foreign_keys_synced = True

        return self.rels(type='REFERENCES').filter('type', 'foreignkey')\
            .nodes()


# Export for API
Origin = Database
