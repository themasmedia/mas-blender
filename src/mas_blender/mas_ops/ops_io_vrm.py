#!$BLENDER_PATH/python/bin python

import copy
import json
import os
import pathlib
import re
import typing

import bpy

from mas_blender.mas_bpy._bpy_core import bpy_io, bpy_obj, bpy_scn
from mas_blender.mas_bpy import bpy_ani, bpy_mdl, bpy_mtl, bpy_node
from mas_blender.mas_py import py_util
from mas_blender.mas_qt import qt_ui


#
import importlib 

for module in (bpy_io, bpy_scn, bpy_ani, bpy_mdl, bpy_mtl, bpy_node, py_util, qt_ui):
    importlib.reload(module)


# This is a temporary file for exporting VRM files.
# It must be integrated into ops_io.py (which also needs to be updated to collection processes for Belnder 4.0).

# Load default data from config file.
ops_io_config_file_path = pathlib.Path(__file__).parent.joinpath('ops_io.config.json')
with ops_io_config_file_path.open('r', encoding='UTF-8') as readfile:
    IO_CONFIG_DATA = json.load(readfile)


def io_resize_images_for_object(
    obj: bpy.types.Object,
    scale_factor: float = 1.0,
    minimum_dimensions: tuple = (0, 0),
    # rename_format: str = '<name>_<width>x<height>',
    reset: bool = False,
) -> list:
    """"""
    #
    images = []

    #
    mtls = bpy_mtl.mtl_get_mtls_from_obj(obj=obj)
    for mtl in mtls:

        nodes = bpy_node.node_get_nodes_from_node_tree(
            node_tree=mtl.node_tree,
            node_types=(bpy.types.ShaderNodeTexImage,),
        )
        images.extend(n.image for n in nodes if n.image is not None)

    img_texs = bpy_mdl.mdl_get_inputs_from_modifiers(
        obj=obj,
        input_types=(bpy.types.ImageTexture,)
    ).values()

    images.extend(img_tex.image for img_tex in img_texs if img_tex.image is not None)
    images = list({img for img in images if not img.is_dirty})

    #
    for img in images:

        if reset:
            img.reload()
        
        # 
        elif scale_factor != 1.0:
            scale_w, scale_h = int(img.size[0] * scale_factor), int(img.size[1] * scale_factor)
            dimensions = (max((scale_w, minimum_dimensions[0])), max((scale_h, minimum_dimensions[1])))
            if dimensions[0] != img.size[0] or dimensions[1] != img.size[1]:
                # Set image width & height scale.
                img.scale(dimensions[0], dimensions[1])
    
    return images

    # Rename image file
    if rename_with_suffix:

        # Factor in Image names that have file suffixes before renaming.
        img_file_name = pathlib.Path(img.name)

        # Rename the Node if the Node's name doesn't already end with the given suffix.
        if not img_file_name.stem.endswith(rename_with_suffix):
            img.name = f'{img_file_name.stem}{rename_with_suffix}{img_file_name.suffix}'


def io_save_mtl_images(
    dir_path: typing.Union[pathlib.Path, str],
    mtls: typing.Iterable[bpy.types.Material],
    use_node_name: bool = False,
) -> None:
    """TODO"""
    dir_path = pathlib.Path(dir_path)
    images = []

    for mtl in mtls:

        nodes = bpy_node.node_get_nodes_from_node_tree(
            node_tree=mtl.node_tree,
            node_types=(bpy.types.ShaderNodeTexImage,),
        )
        for n in nodes:
            if n.image is not None and n.image not in images:
                images.append(n.image)
    
    for img in images:

        src_img_file_path = pathlib.Path(img.filepath).resolve()

        if use_node_name:
            img_file_stem = pathlib.Path(img.name).stem
        else:
            img_file_stem = src_img_file_path.stem

        img_file_path = dir_path.joinpath(f'{img_file_stem}{src_img_file_path.suffix}')

        if not img_file_path.exists():
            img.save(
                filepath=img_file_path.as_posix(),
                quality=100,
            )
            img.filepath = f'//{img_file_path.name}'


class IOExporter(object):
    """
    TODO
    """

    def __init__(
        self,
        root_export_dir_path: typing.Union[pathlib.Path, str],
        lyr_cols: typing.Sequence = (),
    ):
        """TODO"""
        #
        self.layer_collections = self._set_layer_collections(lyr_cols)

        #
        root_export_dir_path = pathlib.Path(root_export_dir_path)
        self.export_dir_path = root_export_dir_path.joinpath(bpy_io.io_get_current_file_path().stem)

        # Create the export directory if it does not yet exist.
        self.export_dir_path.mkdir(exist_ok=True, parents=True)

    def _set_layer_collections(self, lyr_cols: typing.Sequence = ()) -> dict:
        """"""
        _lyr_cols = {lyr_col.name: {} for lyr_col in lyr_cols}
        col_name_pattern = re.compile('^(COL_)?(?P<descriptor>(?P<prefix>[A-Z1-9]+)?_?\w+)$')

        for lyr_col in lyr_cols:

            #
            _lyr_cols[lyr_col.name]['lyr_col'] = lyr_col
            _lyr_cols[lyr_col.name]['col'] = lyr_col.collection

            #
            col_name_match = col_name_pattern.match(lyr_col.name)
            _lyr_cols[lyr_col.name]['name_grps'] = col_name_match.groups()

            # Detect the Armature Object for the Layer Collection, if there is one (and only one).
            armature_objs = [obj for obj in lyr_col.collection.objects if isinstance(obj.data, bpy.types.Armature)]
            assert(0 <= len(armature_objs) <= 1, 'Layer Collection can contain 0-1 Armature Object(s).')
            _lyr_cols[lyr_col.name]['armature_obj'] = armature_objs[0] if armature_objs else None

            # Create a list of all Mesh Objects in the Layer Collection.
            # mesh_objs = [obj for obj in lyr_col.collection.objects if isinstance(obj.data, bpy.types.Mesh)]
            mesh_objs = bpy_scn.scn_get_objects_of_type('MESH', lyr_col.collection.name)
            _lyr_cols[lyr_col.name]['mesh_objs'] = mesh_objs
        
        return _lyr_cols

    def adjust_materials(
        self,
        lyr_col_names: typing.Iterable[str] = (),
        mtl_swap_index_pairs: typing.Tuple[typing.Tuple[int, int]] = (),
        mtl_prop_overrides: dict = {},
    ):
        """"""
        # Default to self.layer_collections if the lyr_col_names arg is not given.
        lyr_col_names = lyr_col_names or self.layer_collections.keys()

        # Create a set from the Mesh Objects to ensure that each Object is only affected once (if in multiple Collections).
        mesh_objs = set(
            sum(
                (self.layer_collections[lyr_col_name]['mesh_objs'] for lyr_col_name in lyr_col_names),
                list()
            )
        )

        # Iterate through each Mesh Object
        for mesh_obj in mesh_objs:

            # Swap Materials for the given pair of index(es) (note that sequence of the pair(s) affects functionality).
            for mtl_swap_index_pair in mtl_swap_index_pairs:
                bpy_mtl.mtl_swap_materials_at_indexes(
                    obj=mesh_obj,
                    index1=mtl_swap_index_pair[0],
                    index2=mtl_swap_index_pair[1]
                )

            # Set Material property overrides.
            bpy_mtl.mtl_set_material_properties(
                mtls=mesh_obj.data.materials,
                props=mtl_prop_overrides
            )


    def apply_modifiers(
        self,
        lyr_col_names: typing.Iterable[str] = (),
        mdfr_types: typing.Iterable[bpy.types.Modifier] = (),
        keep_shp_keys: bool = True,
        remove_unapplied: bool = False,
        perm_mdfr_types: typing.Iterable[bpy.types.Modifier] = (bpy.types.ArmatureModifier, bpy.types.NodesModifier)
    ) -> None:
        """TODO"""
        #
        lyr_col_names = lyr_col_names or self.layer_collections.keys()
        for lyr_col_name in lyr_col_names:

            #
            lyr_col_state = self.layer_collections[lyr_col_name]['lyr_col'].exclude
            lyr_col = self.layer_collections[lyr_col_name]['lyr_col']
            lyr_col.exclude = False

            # Get VRM shape key data.
            vrm_shape_key_data = self.get_vrm_shape_key_data(lyr_col_name=lyr_col_name)
                
            #
            mesh_objs = self.layer_collections[lyr_col_name]['mesh_objs']
            for mesh_obj in mesh_objs:

                # Set the current Mesh Object to active and record its name.
                bpy_scn.scn_select_items(items=[mesh_obj])
                mesh_obj_name = mesh_obj.name

                # Iterate through each Modifier on the Mesh Object.
                mdfr_list = []
                for mdfr in mesh_obj.modifiers:

                    #
                    if all((
                        remove_unapplied,
                        not isinstance(mdfr, mdfr_types),
                        not isinstance(mdfr, perm_mdfr_types)
                    )):
                        mesh_obj.modifiers.remove(mdfr)
                        
                    #
                    elif isinstance(mdfr, mdfr_types):
                        mdfr.show_render = True
                        mdfr.show_viewport = True
                        mdfr_list.append(mdfr)
                
                # Recreate Shape Keys after Modifiers are applied.
                if keep_shp_keys:

                    # Pop the Mesh Object from all Collections in self.layer_collections it is associated with.
                    # Save its position in each collection in self.layer_collections.
                    mesh_obj_cols = {
                        col: 0 for col in mesh_obj.users_collection if col.name in self.layer_collections
                    }
                    for mesh_obj_col in mesh_obj_cols:
                        mesh_obj_index = self.layer_collections[mesh_obj_col.name]['mesh_objs'].index(mesh_obj)
                        self.layer_collections[mesh_obj_col.name]['mesh_objs'].pop(mesh_obj_index)
                        mesh_obj_cols[mesh_obj_col] = mesh_obj_index

                    # The process that applies modifiers to the mesh creates a new Mesh Object.
                    mesh_obj = bpy_mdl.mdl_apply_modifiers_to_object(
                        obj=mesh_obj,
                        mdfr_list=mdfr_list,
                        all_users=mesh_obj.data.users > 1
                    )

                    # Update self.layer_collections to point to the new Mesh Object.
                    for mesh_obj_col, mesh_obj_index in mesh_obj_cols.items():
                        self.layer_collections[mesh_obj_col.name]['mesh_objs'].insert(mesh_obj_index, mesh_obj)
                    
                    # Reconnect the Shape Keys to the VRM Blendshape groups with the same bind data.
                    for shape_key_grp_index, shape_key_grp_data in vrm_shape_key_data['groups'].items():
                        if shape_key_grp_data['mesh_obj_name'] == mesh_obj_name:
                            shape_key_bind = vrm_shape_key_data['master'].blend_shape_groups[shape_key_grp_index].binds[shape_key_grp_data['index']]
                            shape_key_bind.mesh.mesh_object_name = mesh_obj_name
                            shape_key_bind.index = shape_key_grp_data['value']

                # Remove Shape Keys before applying Modifiers.
                else:

                    # Get the Armature Object for the Collection, if it has one.
                    armature_obj = self.layer_collections[lyr_col_name]['armature_obj']
                    vrm_armature = armature_obj.data if armature_obj else None
                    
                    #  Clear all Shape Keys for the Mesh Object.
                    bpy_mdl.mdl_clear_shape_keys(
                        obj=mesh_obj,
                        vrm_armature=vrm_armature,
                    )

                    # Apply the Modifiers in mdfr_list
                    bpy_mdl.mdl_apply_modifiers_to_object(
                        obj=mesh_obj,
                        mdfr_list=mdfr_list,
                        all_users=mesh_obj.data.users > 1
                    )

            lyr_col.exclude = lyr_col_state


    def export(
        self,
        export_file_suffix: str,
        export_file_prefix: str = '',
        copy_imgs: bool = False,
        current_pose: bool = False,
        vrm_meta: dict = {},
        **export_settings
    ) -> None:
        """TODO export each action as a separate glb"""
        #
        export_file_format = IO_CONFIG_DATA['export']['file_formats'][export_file_suffix]
        export_function = getattr(bpy.ops.export_scene, export_file_format)

        # Exclude all child Layer Collections initially (they will be included one by one).
        for lyr_col_name in self.layer_collections:
            self.layer_collections[lyr_col_name]['lyr_col'].exclude = True

        # Iterate through the child Layer Collections for individual export.
        for lyr_col_name, lyr_col_data in self.layer_collections.items():

            #
            export_file_descriptor = lyr_col_data['name_grps'][1]
            export_file_stem = f'{export_file_prefix}_{export_file_descriptor}'.strip('_')
            export_file_path = self.export_dir_path.joinpath(export_file_stem).with_suffix(export_file_suffix)
            export_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Include the child Layer Collection and set it to active.
            lyr_col_data['lyr_col'].exclude = False
            bpy.context.view_layer.active_layer_collection = lyr_col_data['lyr_col']

            # 
            export_settings_copy = copy.deepcopy(export_settings)
            if lyr_col_data['armature_obj'] is not None:
            
                # Reset the armature.
                bpy_ani.ani_reset_armature_transforms(
                    armature_obj=lyr_col_data['armature_obj'],
                    reset_pose=not current_pose,
                    set_to_rest=not current_pose
                )

                for export_k in ('armature_object_name',):
                    if export_k in export_settings_copy:
                        export_settings_copy[export_k] = lyr_col_data['armature_obj'].name

                # Set VRM Metadata
                if vrm_meta:

                    #
                    vrm_meta_texture = vrm_meta.get('texture', None)
                    vrm_meta_texture_orig = py_util.util_get_attr_recur(
                        lyr_col_data['armature_obj'].data,
                        'vrm_addon_extension.vrm0.meta.texture'
                    )
                    if isinstance(vrm_meta_texture_orig, bpy.types.Image):
                        vrm_meta_texture_dir_path = pathlib.Path(bpy.path.abspath(vrm_meta_texture_orig.filepath)).parent
                        if vrm_meta_texture_dir_path.is_dir():
                            export_file_prefix = lyr_col_data['name_grps'][2]
                            for texture_file_path in vrm_meta_texture_dir_path.glob(f'{export_file_prefix}.*'):
                                vrm_meta_texture = bpy.data.images.load(
                                    filepath=bpy.path.relpath(texture_file_path.as_posix()),
                                    check_existing=True
                                )
                                break
                    if vrm_meta_texture is None:
                        vrm_meta_texture = vrm_meta_texture_orig

                    #
                    vrm_meta_title = vrm_meta.get('title', '')
                    vrm_meta_title_orig = py_util.util_get_attr_recur(
                        lyr_col_data['armature_obj'].data,
                        'vrm_addon_extension.vrm0.meta.title'
                    )
                    if vrm_meta_title_orig is not None:
                        vrm_meta_title = f'{vrm_meta_title_orig} ({export_file_descriptor})'

                    #
                    self.set_vrm_metadata(
                        armature=lyr_col_data['armature_obj'].data,
                        metadata=vrm_meta,
                        texture=vrm_meta_texture,
                        title=vrm_meta_title
                    )
                
            # Save image textures into export folder
            if copy_imgs:

                # 
                mtls = []
                for mesh_obj in lyr_col_data['mesh_objs']:
                    for mtl in bpy_mtl.mtl_get_mtls_from_obj(obj=mesh_obj):
                        if mtl not in mtls:
                            mtls.append(mtl)
                
                # 
                io_save_mtl_images(
                    dir_path=export_file_path.parent,
                    mtls=mtls,
                    use_node_name=True,
                )

            # Clear Object selection before export.
            bpy_scn.scn_select_items(items=[])

            export_function(
                filepath=export_file_path.as_posix(),
                **export_settings_copy
            )

            # Reset VRM metadata
            if lyr_col_data['armature_obj'] is not None:
                if vrm_meta:
                    py_util.util_set_attr_recur(
                        lyr_col_data['armature_obj'].data,
                        'vrm_addon_extension.vrm0.meta.texture',
                        vrm_meta_texture_orig
                    )
                    py_util.util_set_attr_recur(
                        lyr_col_data['armature_obj'].data,
                        'vrm_addon_extension.vrm0.meta.title',
                        vrm_meta_title_orig
                    )

            # Exclude the current child Layer Collection.
            lyr_col_data['lyr_col'].exclude = True
    
    def get_vrm_shape_key_data(
            self,
            lyr_col_name: str
        ):
        """TODO"""

        # Initialize the VRM shape key data object.
        vrm_shape_key_data = {
            'groups': {},
            'master': None
        }

        # Assign the VRM add-on Blendshaoe Proxy data to the shape_key_master variable.
        armature_obj = self.layer_collections[lyr_col_name]['armature_obj']
        mesh_obj_names = [
            mesh_obj.name for mesh_obj in self.layer_collections[lyr_col_name]['mesh_objs']
        ]
        if armature_obj is not None:
            vrm_shape_key_data['master'] = py_util.util_get_attr_recur(
                armature_obj, 'data.vrm_addon_extension.vrm0.blend_shape_master'
            )

        # Iterate through the VRM Blendshape groups and record the bind data, which becomes lost after the Modifiers are applied.
        if vrm_shape_key_data['master'] is not None:
            for i, shape_key_grp in enumerate(vrm_shape_key_data['master'].blend_shape_groups):
                for j, bind in enumerate(shape_key_grp.binds):
                    if bind.mesh.mesh_object_name in mesh_obj_names:
                        vrm_shape_key_data['groups'][i] = {
                            'index': j,
                            'mesh_obj_name': bind.mesh.mesh_object_name,
                            'value': bind.index
                        }
        
        return vrm_shape_key_data


    def optimize(
        self,
        lyr_col_names: typing.Iterable[str] = (),
        opt_img_size: typing.Tuple[float, typing.Tuple[int, int]] = (1.0, (0, 0)),
        opt_mtl_slots: typing.Tuple[bool, None] = (True, None),
        opt_num_objs: typing.Tuple[bool, str] = (True, ''),
        opt_objs_incl_instances: bool= False,
        opt_objs_name_prefix: str = 'GEO_',
        opt_vtx_grps: typing.Tuple[bool, float] = (True, 0.001, ('', '')),
        flatten_hierarchy: bool = True,
        keep_inst_hierarchy: bool = True
    ) -> None:
        """TODO"""

        # Iterate through collections.
        lyr_col_names = lyr_col_names or self.layer_collections.keys()
        new_objs = []

        for lyr_col_name in lyr_col_names:

            col = self.layer_collections[lyr_col_name]['col']
            copied_objs = []
            mesh_objs = py_util.util_copy(
                compound_obj=self.layer_collections[lyr_col_name]['mesh_objs'],
            )

            # If instanced Object(s) are to be exclusded from the optimization,
            # get a list of all instanced Mesh Objects in the collection (use an empty list otherwise).
            inst_obj_data = {} if opt_objs_incl_instances else bpy_scn.scn_get_instance_objects(mesh_objs) 
            inst_objs = sum(inst_obj_data.values(), [])

            # Remove unused Material Slots from Object(s).
            for mesh_obj in mesh_objs:

                #
                if opt_mtl_slots[0]:
                    bpy_mtl.mtl_remove_unused_material_slots(obj=mesh_obj)

                #
                bpy_obj.obj_remove_custom_props(
                    mesh_obj,
                    data=True,
                    materials=True,
                    exclude=['vrm_addon_extension']
                )

                #Remove vertex groups, first by name, then by weight threshold.
                # if opt_vtx_grps[0]:
                    # TODO Buggy
                    # bpy_mdl.mdl_delete_vertex_groups_by_weight(obj=mesh_obj, threshold=opt_vtx_grps[1])
                    # bpy_mdl.mdl_delete_vertex_groups_by_name(
                    #     obj=mesh_obj,
                    #     prefix=opt_vtx_grps[2][0],
                    #     suffix=opt_vtx_grps[2][1]
                    # )

                # Resize image(s).
                if opt_img_size[0] != 1.0:

                    images = io_resize_images_for_object(
                        obj=mesh_obj,
                        scale_factor=opt_img_size[0],
                        minimum_dimensions=opt_img_size[1]
                    )

                    for img in images:
                        # TODO breaks for some textures for some reason. See EDSN Game Engine Character export
                        # Factor in Image names that have file suffixes before renaming.
                        img_file_path = pathlib.Path(img.name)
                        img_file_name = f'{img_file_path.stem}_{img.size[0]}x{img.size[1]}{img_file_path.suffix}'

                        # Rename the Node if the Node's name doesn't already end with the given suffix.
                        img.name = img_file_name if img.name != img_file_name else img.name

                # Copy each Mesh Object in the Layer Collection.
                if opt_num_objs[0]:

                    # Omit if instanced Object(s) are to be exclusded from the optimization,
                    if (not opt_objs_incl_instances) and (mesh_obj in inst_objs):
                        continue

                    copied_obj = bpy_scn.scn_copy_object(
                        obj=mesh_obj,
                        cols=(col,)
                    )
                    copied_objs.append(copied_obj)

                    # Unlink the original Mesh Object(s) from the Layer Collection and update self.layer_collections.
                    col.objects.unlink(mesh_obj)
                    self.layer_collections[lyr_col_name]['mesh_objs'].remove(mesh_obj)

            #
            if copied_objs:

                # Get VRM shape key data.
                vrm_shape_key_data = self.get_vrm_shape_key_data(lyr_col_name=lyr_col_name)

                # If no name for the joined object is given, use the descriptor from the Collection name.
                joined_obj_name = opt_num_objs[1]
                if not opt_num_objs[1]:
                    name_descriptor = self.layer_collections[lyr_col_name]['name_grps'][1]
                    joined_obj_name = f'{opt_objs_name_prefix}{name_descriptor}'

                # Join copied Mesh(es) into a single Mesh Object.
                joined_obj = bpy_mdl.mdl_join_objects(
                    objects=copied_objs,
                    new_name=joined_obj_name,
                )
                bpy_scn.scn_link_objects_to_collection(
                    col=col,
                    objs=[joined_obj],
                    exclusive=True,
                )
                new_objs.append(joined_obj)

                # Update self.layer_collections
                self.layer_collections[lyr_col_name]['mesh_objs'].append(joined_obj)

                # Reconnect the Shape Keys of the new single Mesh Object to the VRM Blendshape groups with the same bind data.
                for shape_key_grp_index, shape_key_grp_data in vrm_shape_key_data['groups'].items():
                    shape_key_bind = vrm_shape_key_data['master'].blend_shape_groups[shape_key_grp_index].binds[shape_key_grp_data['index']]
                    shape_key_bind.mesh.mesh_object_name = joined_obj.name
                    shape_key_bind.index = shape_key_grp_data['value']
            
            # 
            if flatten_hierarchy:

                # Clear parent(s) for the Armature Object.
                if self.layer_collections[lyr_col_name]['armature_obj']:
                    bpy_scn.scn_clear_object_parent(self.layer_collections[lyr_col_name]['armature_obj'])

                # Clear parent(s) for Mesh Objects (including/excluding instanced Object(s)).
                if keep_inst_hierarchy:
                    mesh_objs = (
                        mesh_obj for mesh_obj in self.layer_collections[lyr_col_name]['mesh_objs'] if mesh_obj.data.users == 1
                    )
                else:
                    mesh_objs = self.layer_collections[lyr_col_name]['mesh_objs']
                for mesh_obj in mesh_objs:
                    bpy_scn.scn_clear_object_parent(mesh_obj)

                # Unlink Empty Object(s) that no longer have child Object(s).
                for null_obj in bpy_scn.scn_get_objects_of_type('EMPTY', col.name):
                    child_objs = [obj for obj in null_obj.children if col in obj.users_collection]
                    if len(child_objs) < 1:
                        col.objects.unlink(null_obj)

    def set_vrm_metadata(self, armature: bpy.types.Armature, metadata: dict, **kwargs):
        """TODO"""
        vrm_meta = py_util.util_get_attr_recur(armature, 'vrm_addon_extension.vrm0.meta')
        if vrm_meta is not None:
            _metadata = py_util.util_copy(metadata)

            for k, v in kwargs.items():
                _metadata[k] = v

            for k, v in _metadata.items():
                py_util.util_set_attr_recur(vrm_meta, k, v)

#
EXPORT_ARGS_OPTIONS = {

    #
    'TEMPLATE': {

        #
        'Example Type (Example Sub-Type)': {
            # 
            'copy_imgs': True,
            # If True, export using current pose; if False, export using rest pose.
            'current_pose': False,
            # If left empty, will be populated by all Layer Collections in the Scene that are not excluded (☑ not ☐).
            'lyr_cols': [],
            # Collection of Modifier types to apply to the Object data before exporting.
            'mdfr_types': (),
            # Iteration of Material Index pairs (tuples) to swap for Objects in the Collection, if swapping Materials for export.
            'mtl_index_pairs': (),
            # Material property value overrides for all Materials applied to Mesh Objects in the Collection.
            'mtl_props': {},
            # Scale multiplier to apply to image dimensions (width, height) in the Object's Material(s) node(s).
            'opt_img_size': (1.0, (0, 0)),
            #
            'opt_mtl_slots': (False, None),
            #
            'opt_num_objs': (False, ''),
            #
            'opt_vtx_grps': (True, 0.001, ('', '')),
            #
            'shp_keys': False,
            # TODO
            'vrm_meta': {},
        },
    },

    #
    'CC3D': {

        # FBX: Multiple PBR BDSF material(s). Multiple lo-res texture. Single triangulated mesh.
        # Apps: Mobile/XR 3D (SparkAR), Mocap/stock animation (Mixamo).
        'Humanoid Avatar (Lo-Res Shaded)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mtl_index_pairs': ((0, 3), (1, 4),),
            'mtl_props': {},
            'mdfr_types': (
                bpy.types.TriangulateModifier,
            ),
            'opt_img_size': (0.25, (1024, 1024)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': False,
            'vrm_meta': {},
        },

        # FBX: Multiple PBR BDSF material(s). Multiple hi-res texture(s). Multiple smoothed/triangulated meshes. Blend Shapes. Outline (via mesh).
        # Apps: Desktop/Web 3D (3D creation & game engines, including Blender, Maya, Unity, Unreal Engine, etc).
        'Humanoid Avatar (Hi-Res Unshaded)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.SolidifyModifier,
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
                bpy.types.VertexWeightMixModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (1.0, (2048, 2048)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (False, ''),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': True,
            'vrm_meta': {},
        },

        # VRM: Multiple emissive BDSF/MToon material(s). Multiple hi-res texture(s). Multiple smoothed/triangulated meshes. Blend Shapes. Outline (via MToon, where supported).
        # Apps: Hologram, HyperFy, Monaverse, Upstreet, VRoid Hub, VSeeFace.
        # Software: Blender (w/ add-on), Unity (w/ UniVRM package), Unreal (w/ VRM4U plug-in).
        'Virtual Avatar (VTube Toon Shaded)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': ((1, 5),),
            'mtl_props': {
                'vrm_addon_extension.mtoon1.extensions.vrmc_materials_mtoon.outline_width_mode': 'worldCoordinates',
            },
            'opt_img_size': (1.0, (2048, 2048)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (False, ''),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': True,
            'vrm_meta': {
                'allowed_user_name': 'ExplicitlyLicensedPerson',
                'author': 'm a s',
                'commercial_ussage_name': 'Allow',
                'contact_information': 'masangri.art@gmail.com',
                'license_name': 'Redistribution_Prohibited',
                'other_license_url': 'https://coolcats.com/terms-and-conditions',
                'other_permission_url': 'https://coolcats.com',
                'reference': 'https://x.com/masangri_art',
                'sexual_ussage_name': 'Disallow',
                'texture': None,
                'title': 'Cool Cats 3D Avatar',
                'version': '0.1.0',
                'violent_ussage_name': 'Disallow'
            },
        },

        # VRM: Multiple diffuse BDSF/MToon material(s). Multiple hi-res texture(s). Multiple smoothed/triangulated meshes. Blend Shapes. Outline (via MToon, where supported).
        # Apps: HyperFy, Monaverse, Upstreet, VRoid Hub, VSeeFace.
        'Virtual Avatar (VTube Toon Unshaded)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': ((1, 2),),
            'mtl_props': {
                'vrm_addon_extension.mtoon1.extensions.vrmc_materials_mtoon.outline_width_mode': 'worldCoordinates',
            },
            'opt_img_size': (1.0, (2048, 2048)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (False, ''),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': True,
            'vrm_meta': {
                'allowed_user_name': 'ExplicitlyLicensedPerson',
                'author': 'm a s',
                'commercial_ussage_name': 'Allow',
                'contact_information': 'masangri.art@gmail.com',
                'license_name': 'Redistribution_Prohibited',
                'other_license_url': 'https://coolcats.com/terms-and-conditions',
                'other_permission_url': 'https://coolcats.com',
                'reference': 'https://x.com/masangri_art',
                'sexual_ussage_name': 'Disallow',
                'texture': None,
                'title': 'Cool Cats 3D Avatar',
                'version': '0.1.0',
                'violent_ussage_name': 'Disallow'
            },
        },

        # VRM: Multiple diffuse BDSF/MToon material(s). Multiple hi-res texture(s). Multiple smoothed/triangulated meshes. Blend Shapes. Outline (via mesh).
        # Apps: 3tene.
        'Virtual Avatar (VTube Shaded)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.SolidifyModifier,
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
                bpy.types.VertexWeightMixModifier,
            ),
            'mtl_index_pairs': ((0, 3), (1, 4),),
            'mtl_props': {},
            'opt_img_size': (1.0, (2048, 2048)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (False, ''),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': True,
            'vrm_meta': {
                'allowed_user_name': 'ExplicitlyLicensedPerson',
                'author': 'm a s',
                'commercial_ussage_name': 'Allow',
                'contact_information': 'masangri.art@gmail.com',
                'license_name': 'Redistribution_Prohibited',
                'other_license_url': 'https://coolcats.com/terms-and-conditions',
                'other_permission_url': 'https://coolcats.com',
                'reference': 'https://x.com/masangri_art',
                'sexual_ussage_name': 'Disallow',
                'texture': None,
                'title': 'Cool Cats 3D Avatar',
                'version': '0.1.0',
                'violent_ussage_name': 'Disallow'
            },
        },

        # VRM: Multiple diffuse BDSF/MToon material(s). Multiple hi-res texture(s). Multiple smoothed/triangulated meshes. Blend Shapes. Outline (via mesh).
        # Apps: 3tene.
        'Virtual Avatar (VTube Unshaded)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.SolidifyModifier,
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
                bpy.types.VertexWeightMixModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (1.0, (2048, 2048)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (False, ''),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': True,
            'vrm_meta': {
                'allowed_user_name': 'ExplicitlyLicensedPerson',
                'author': 'm a s',
                'commercial_ussage_name': 'Allow',
                'contact_information': 'masangri.art@gmail.com',
                'license_name': 'Redistribution_Prohibited',
                'other_license_url': 'https://coolcats.com/terms-and-conditions',
                'other_permission_url': 'https://coolcats.com',
                'reference': 'https://x.com/masangri_art',
                'sexual_ussage_name': 'Disallow',
                'texture': None,
                'title': 'Cool Cats 3D Avatar',
                'version': '0.1.0',
                'violent_ussage_name': 'Disallow'
            },
        },

        # VRM: Multiple diffuse BDSF/MToon material(s). Multiple hi-res texture(s). Single triangulated mesh. Outline.
        # Apps: Nifty Island, OnCyber, ViPe.
        # TODO
        'Virtual Avatar (Metaverse Shaded)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.SolidifyModifier,
                bpy.types.TriangulateModifier,
                bpy.types.VertexWeightMixModifier,
            ),
            'mtl_index_pairs': ((1, 5),),
            'mtl_props': {},
            'opt_img_size': (0.5, (2048, 2048)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, ''),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': False,
            'vrm_meta': {
                'allowed_user_name': 'ExplicitlyLicensedPerson',
                'author': 'm a s',
                'commercial_ussage_name': 'Allow',
                'contact_information': 'masangri.art@gmail.com',
                'license_name': 'Redistribution_Prohibited',
                'other_license_url': 'https://coolcats.com/terms-and-conditions',
                'other_permission_url': 'https://coolcats.com',
                'reference': 'https://x.com/masangri_art',
                'sexual_ussage_name': 'Disallow',
                'texture': None,
                'title': 'Cool Cats 3D Avatar',
                'version': '0.1.0',
                'violent_ussage_name': 'Disallow'
            },
        },

        # VRM: Multiple diffuse BDSF/MToon material(s). Multiple hi-res texture(s). Single triangulated mesh. Outline.
        # Apps: Hyperfy, Monaverse, Upstreet
        # TODO
        'Virtual Avatar (Metaverse Unshaded)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.SolidifyModifier,
                bpy.types.TriangulateModifier,
                bpy.types.VertexWeightMixModifier,
            ),
            'mtl_index_pairs': ((1, 2),),
            'mtl_props': {},
            'opt_img_size': (0.5, (2048, 2048)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, ''),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': False,
            'vrm_meta': {
                'allowed_user_name': 'ExplicitlyLicensedPerson',
                'author': 'm a s',
                'commercial_ussage_name': 'Allow',
                'contact_information': 'masangri.art@gmail.com',
                'license_name': 'Redistribution_Prohibited',
                'other_license_url': 'https://coolcats.com/terms-and-conditions',
                'other_permission_url': 'https://coolcats.com',
                'reference': 'https://x.com/masangri_art',
                'sexual_ussage_name': 'Disallow',
                'texture': None,
                'title': 'Cool Cats 3D Avatar',
                'version': '0.1.0',
                'violent_ussage_name': 'Disallow'
            },
        },

    },

    'EDSN': {

        # FBX: Multiple PBR BDSF material(s). Multiple lo-res texture. Single triangulated mesh.
        # Apps: Maya, Unreal Engine.
        'Game Engine Character (Lo-Res)': {
            'copy_imgs': True,
            'current_pose': False,
            'lyr_cols': [],
            'mtl_index_pairs': (),
            'mtl_props': {},
            'mdfr_types': (
                bpy.types.TriangulateModifier,
            ),
            'opt_img_size': (0.25, (1024, 1024)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': False,
            'vrm_meta': {},
        },

        # FBX: Multiple PBR BDSF material(s). Multiple hi-res texture. Single triangulated mesh.
        # Apps: Maya, Unreal Engine.
        'Game Engine Character (Hi-Res)': {
            'copy_imgs': True,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (0.5, (2048, 2048)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': True,
            'vrm_meta': {},
        },

        # GLB: Multiple PBR BDSF material(s). Multiple lo-res texture(s). Single triangulated mesh.
        # Apps: MSquared.
        # Software: Unreal Engine 5.
        'M2 Character (Lo-Res)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (0.25, (1024, 1024)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': False,
            'vrm_meta': {},
        },

        # GLB: Multiple PBR BDSF material(s). Multiple hi-res texture(s). Single smoothed/triangulated meshes. Blend Shapes.
        # Apps: MSquared.
        # Software: Unreal Engine 5.
        'M2 Character (Hi-Res)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (0.5, (2048, 2048)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': True,
            'vrm_meta': {},
        },

        # GLB: Multiple PBR BDSF material(s). Multiple lo-res texture(s). Single triangulated mesh.
        # Apps: MSquared.
        # Software: Unreal Engine 5.
        'M2 Model (Lo-Res)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (0.25, (1024, 1024)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': False,
            'vrm_meta': {},
        },

        # GLB: Multiple PBR BDSF material(s). Multiple lo-res texture(s). Single triangulated mesh.
        # Apps: MSquared.
        # Software: Unreal Engine 5.
        'M2 Model (Lo-Res Proxy)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.DecimateModifier,
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (0.125, (512, 512)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': False,
            'vrm_meta': {},
        },

        # GLB: Multiple PBR BDSF material(s). Multiple hi-res texture(s). Single smoothed/triangulated meshes. Blend Shapes.
        # Apps: MSquared.
        # Software: Unreal Engine 5.
        'M2 Model (Hi-Res)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (0.5, (2048, 2048)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': True,
            'vrm_meta': {},
        },

    },

    # VRM: Multiple diffuse BDSF/MToon material(s). Multiple hi-res texture(s). Single smoothed/triangulated meshe. Outline (via MToon, where supported).
    'LD3D': {

        #
        'Virtual Avatar (Lo-Res Nifty Island)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.DisplaceModifier,
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (0.25, (1024, 1024)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, 'GEO_Lucky_001'),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': False,
            'vrm_meta': {},
        },

        #
        'Virtual Avatar (Hi-Res)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.DisplaceModifier,
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (0.5, (1024, 1024)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': True,
            'vrm_meta': {},
        },

        #
        'Virtual Avatar (Hi-Res Nifty Island)': {
            'copy_imgs': False,
            'current_pose': False,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.DisplaceModifier,
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': (),
            'mtl_props': {},
            'opt_img_size': (0.5, (1024, 1024)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': False,
            'vrm_meta': {},
        },

    },

    'LL3D' : {

        # VRM: Multiple diffuse BDSF material(s). Multiple lo-res texture(s). Single triangulated mesh.
        # Apps: Nifty Island, OnCyber, ViPe.
        # TODO
        'Virtual Avatar (Metaverse Shaded)': {
            'copy_imgs': False,
            'current_pose': True,
            'lyr_cols': [],
            'mdfr_types': (
                bpy.types.LatticeModifier,
                bpy.types.SubsurfModifier,
                bpy.types.TriangulateModifier,
            ),
            'mtl_index_pairs': ((0, 1),),
            'mtl_props': {},
            'opt_img_size': (0.25, (1024, 1024)),
            'opt_mtl_slots': (True, None),
            'opt_num_objs': (True, None),
            'opt_vtx_grps': (True, 0.001, ('', '')),
            'shp_keys': False,
            'vrm_meta': {
                'allowed_user_name': 'ExplicitlyLicensedPerson',
                'author': 'Little Lemon Friends',
                'commercial_ussage_name': 'Allow',
                'contact_information': 'https://x.com/LittlelemonsNFT',
                'license_name': 'Redistribution_Prohibited',
                'other_license_url': 'https://littlelemonfriends.medium.com/terms-of-service-little-lemon-friends-f1a92ad255bd',
                'other_permission_url': 'https://discord.com/invite/littlelemons',
                'reference': 'https://www.littlelemonfriendsnft.com/',
                'sexual_ussage_name': 'Disallow',
                'texture': None,
                'title': 'Little Lemon Friends 3D Avatar',
                'version': '0.1.0',
                'violent_ussage_name': 'Disallow'
            },
        },

    },

}


def io_export(
    # TODO Derive data from Project data in mas_blender
    export_platform_type: str,
    export_platform_subtype: str,
    project_code: str,
    project_name: str,
):
    """Temp placeholder function"""
    os.system('cls')

    current_file_path = bpy_io.io_get_current_file_path()
    root_export_dir = f'D:/Projects/Blender/{project_name}/models/'

    export_platform_name = f'{export_platform_type} ({export_platform_subtype})'
    export_platform_name_subbed = re.sub('\W+', '', export_platform_name).strip('_')
    export_platform_data = IO_CONFIG_DATA['export']['platforms'][export_platform_type]
    export_settings = export_platform_data['settings']
    for type_k, type_v in export_platform_data['convert'].items():
        export_settings[type_k] = dict(__builtins__)[type_v](export_settings[type_k])
    export_file_suffix = export_platform_data['suffix']
    export_file_prefix = f'{project_code}_{export_platform_name_subbed}'

    export_args = EXPORT_ARGS_OPTIONS[project_code][export_platform_name]

    if not export_args['lyr_cols']:
        for lyr_col in bpy_scn.scn_get_view_layer_collections(bpy.context.view_layer):
            if not lyr_col.exclude:
                export_args['lyr_cols'].append(lyr_col)

    #
    b3d_exporter = IOExporter(
        root_export_dir_path=root_export_dir,
        lyr_cols=export_args['lyr_cols'],
    )

    #
    b3d_exporter.apply_modifiers(
        mdfr_types=export_args['mdfr_types'],
        keep_shp_keys=export_args['shp_keys'],
        remove_unapplied=True,
    )

    #
    b3d_exporter.adjust_materials(
        mtl_swap_index_pairs=export_args['mtl_index_pairs'],
        mtl_prop_overrides=export_args['mtl_props'],
    )

    #
    b3d_exporter.optimize(
        opt_img_size=export_args['opt_img_size'],
        opt_mtl_slots=export_args['opt_mtl_slots'],
        opt_num_objs=export_args['opt_num_objs'],
        opt_vtx_grps=export_args['opt_vtx_grps']
    )

    #
    b3d_exporter.export(
        export_file_suffix=export_file_suffix,
        export_file_prefix=export_file_prefix,
        copy_imgs=export_args['copy_imgs'],
        current_pose=export_args['current_pose'],
        vrm_meta=export_args['vrm_meta'],
        **export_settings
    )

    # Prompt the user to reopen the original file used for the export, if desired.
    open_original_file = qt_ui.ui_message_box(
        title='Export Complete',
        text=f'{export_platform_name} export completed successfully.\n' + \
            f'Reopen {current_file_path.name}?',
        message_box_type='question'
    )
    if open_original_file:
        # Reopen original file
        bpy.ops.wm.open_mainfile(filepath=current_file_path.as_posix())
        #TODO clean up unused nodes that were generated in prev code


if __name__ == '__main__':

    io_export()
