"""Live, shape-driven sampling. No handlers, scene scans or triangle targets.

Keep the scalar policy mirrored by resolution.shape_voxel for checked generation.
Statistics run on the subdivided surface, before the expensive SDF conversion.
"""
import math

from ...core import gn

DIMENSION_SAMPLES = 128.0
CURVATURE_SAMPLES = 4.0
THICKNESS_SAMPLES = 6.0
MAX_SURFACE_SAMPLES = 2000000.0
AUTOMATIC_ADAPTIVITY = 0.001


def build(group, geometry, crease_angle):
    """Return scalar voxel and work-limited sockets for one evaluated mesh."""
    nodes, links = group.nodes, group.links
    row = 0

    def node(kind, **settings):
        nonlocal row
        result = gn.add_node(nodes, kind, -1200 + (row % 8) * 210,
                             -2000 - (row // 8) * 200, **settings)
        row += 1
        return result

    def wire(value, socket):
        if isinstance(value, (float, int)):
            socket.default_value = value
        else:
            links.new(value, socket)

    def math_node(operation, a, b=None):
        result = node('ShaderNodeMath', operation=operation)
        wire(a, result.inputs[0])
        if b is not None:
            wire(b, result.inputs[1])
        return result.outputs[0]

    def vector(operation, a, b=None, scale=None):
        result = node('ShaderNodeVectorMath', operation=operation)
        wire(a, result.inputs[0])
        if b is not None:
            wire(b, result.inputs[1])
        if scale is not None:
            wire(scale, result.inputs['Scale'])
        return result.outputs['Value' if operation in {'DISTANCE', 'DOT_PRODUCT'} else 'Vector']

    def stat(field, domain, selection=None, output='Sum'):
        result = node('GeometryNodeAttributeStatistic', data_type='FLOAT', domain=domain)
        wire(geometry, result.inputs['Geometry'])
        wire(field, result.inputs['Attribute'])
        if selection is not None:
            wire(selection, result.inputs['Selection'])
        return result.outputs[output]

    def choose(condition, yes, no):
        result = node('GeometryNodeSwitch', input_type='FLOAT')
        wire(condition, result.inputs['Switch'])
        wire(yes, result.inputs['True'])
        wire(no, result.inputs['False'])
        return result.outputs['Output']

    bounds = node('GeometryNodeBoundBox')
    wire(geometry, bounds.inputs['Geometry'])
    diagonal = vector('DISTANCE', bounds.outputs['Min'], bounds.outputs['Max'])
    epsilon = math_node('MAXIMUM', math_node('MULTIPLY', diagonal, 1e-6), 1e-10)
    baseline = math_node('DIVIDE', diagonal, DIMENSION_SAMPLES)
    area = node('GeometryNodeInputMeshFaceArea').outputs['Area']
    total_area = stat(area, 'FACE')

    # FACE area -> EDGE interpolation is made explicit. area / edge length is
    # transverse face width; dividing by smooth dihedral angle estimates radius.
    face_domain = node('GeometryNodeFieldOnDomain', data_type='FLOAT', domain='FACE')
    wire(area, face_domain.inputs['Value'])
    edge = node('GeometryNodeInputMeshEdgeVertices')
    length = vector('DISTANCE', edge.outputs['Position 1'], edge.outputs['Position 2'])
    angle = node('GeometryNodeInputMeshEdgeAngle').outputs['Unsigned Angle']
    crease_radians = math_node('RADIANS', crease_angle)
    smooth = math_node('MULTIPLY', math_node('GREATER_THAN', angle, 0.01),
                       math_node('LESS_THAN', angle, math_node('MINIMUM', crease_radians, math.radians(60))))
    weight = math_node('MULTIPLY', length, angle)
    radius = math_node('DIVIDE', face_domain.outputs['Value'],
                       math_node('MAXIMUM', math_node('MULTIPLY', length, angle), 1e-20))
    # Weighted harmonic mean: repeated curvature matters, one short edge doesn't
    # force the smallest radius across an otherwise simple object.
    inverse_radius = math_node('DIVIDE', weight, math_node('MAXIMUM', radius, epsilon))
    weight_sum = stat(weight, 'EDGE', smooth)
    inverse_sum = stat(inverse_radius, 'EDGE', smooth)
    curvature = math_node('DIVIDE', weight_sum, math_node('MAXIMUM', inverse_sum, 1e-20))
    curvature = choose(math_node('GREATER_THAN', weight_sum, 0),
                       math_node('DIVIDE', curvature, CURVATURE_SAMPLES), baseline)

    # Face-center inward/outward rays detect walls and gaps. Reject near/self hits
    # and require opposing face normals. Two directions share Blender's BVH.
    position = node('GeometryNodeInputPosition').outputs['Position']
    normal = node('GeometryNodeInputNormal').outputs['Normal']
    candidates = [baseline, curvature]
    for direction in (-1.0, 1.0):
        ray_direction = vector('SCALE', normal, scale=direction)
        origin = vector('ADD', position, vector('SCALE', ray_direction, scale=epsilon))
        ray = node('GeometryNodeRaycast', data_type='FLOAT')
        wire(geometry, ray.inputs['Target Geometry'])
        wire(origin, ray.inputs['Source Position'])
        wire(ray_direction, ray.inputs['Ray Direction'])
        wire(diagonal, ray.inputs['Ray Length'])
        opposite = math_node('LESS_THAN', vector('DOT_PRODUCT', normal, ray.outputs['Hit Normal']), -0.5)
        valid = math_node('MULTIPLY', ray.outputs['Is Hit'], opposite)
        valid = math_node('MULTIPLY', valid,
                          math_node('GREATER_THAN', ray.outputs['Hit Distance'], math_node('MULTIPLY', epsilon, 10)))
        distance = math_node('ADD', ray.outputs['Hit Distance'], epsilon)
        selected_area = stat(area, 'FACE', valid)
        inverse_distance = stat(math_node('DIVIDE', area, math_node('MAXIMUM', distance, epsilon)), 'FACE', valid)
        thickness = math_node('DIVIDE', selected_area, math_node('MAXIMUM', inverse_distance, 1e-20))
        candidates.append(choose(math_node('GREATER_THAN', selected_area, 0),
                                 math_node('DIVIDE', thickness, THICKNESS_SAMPLES), baseline))
    desired = candidates[0]
    for candidate in candidates[1:]:
        desired = math_node('MINIMUM', desired, candidate)
    # This is a maximum work allowance, NOT a density target. It only coarsens
    # pathological cases and emits an observable warning attribute upstream.
    floor = math_node('MAXIMUM', math_node('DIVIDE', diagonal, 4096),
                      math_node('SQRT', math_node('DIVIDE', total_area, MAX_SURFACE_SAMPLES)))
    limited = math_node('LESS_THAN', desired, floor)
    voxel = math_node('MAXIMUM', math_node('MAXIMUM', desired, floor), 1e-8)
    return voxel, limited