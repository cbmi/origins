from string import Template as T
from origins.exceptions import ValidationError, DoesNotExist
from .core import nodes, edges
from .model import Node
from . import neo4j, utils, resources


COMPONENT_MODEL = 'origins:Component'
COMPONENT_TYPE = 'Component'


GET_COMPONENT_BY_ID = T('''
MATCH (:`origins:Node` {`origins:uuid`: { resource }})<-[:managed_by]-(n$model {`origins:id`: { id }})
RETURN n
''')  # noqa


get = nodes.get
set = nodes.set
remove = nodes.remove


def match(predicate=None, type=None, limit=None, skip=None, tx=neo4j.tx):
    return nodes.match(predicate,
                       limit=limit,
                       skip=skip,
                       type=type,
                       model=COMPONENT_MODEL,
                       tx=tx)


def get_by_id(resource, id, tx=neo4j.tx):
    statement = utils.prep(GET_COMPONENT_BY_ID, model=COMPONENT_MODEL)

    query = {
        'statement': statement,
        'parameters': {
            'resource': resource,
            'id': id,
        }
    }

    result = tx.send(query)

    if not result:
        raise DoesNotExist('component does not exist')

    return Node.parse(result[0][0])


def add(resource, id=None, label=None, description=None, type=None,
        properties=None, tx=neo4j.tx):

    if not type:
        type = COMPONENT_TYPE

    with tx as tx:
        try:
            resource = resources.get(resource)
        except DoesNotExist:
            raise ValidationError('resource does not exist')

        # Check for conflict
        if id is not None:
            try:
                node = get_by_id(resource.uuid, id=id, tx=tx)
            except DoesNotExist:
                node = None

            if node:
                raise ValidationError('component already exists with id')

        # Create component
        node = nodes.add(id=id,
                         label=label,
                         description=description,
                         type=type,
                         model=COMPONENT_MODEL,
                         tx=tx)

        # Define managing relationship
        edges.add(start=node,
                  end=resource,
                  type='managed_by',
                  tx=tx)

        # Defining inclusion to resource
        edges.add(start=resource,
                  end=node,
                  type='includes',
                  tx=tx)

        return node


def set(uuid, label=None, description=None, properties=None, type=None,
        tx=neo4j.tx):

    if not type:
        type = COMPONENT_TYPE

    return nodes.set(uuid=uuid,
                     label=label,
                     description=description,
                     properties=properties,
                     type=type,
                     model=COMPONENT_MODEL,
                     tx=tx)
