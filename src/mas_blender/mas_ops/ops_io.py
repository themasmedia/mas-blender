#!$BLENDER_PATH/python/bin python

"""
MAS Blender - UE - I/O

"""

import copy
import json
import os
import pathlib
import re
import typing

from PySide6 import QtCore, QtWidgets
# from __feature__ import snake_case, true_property

import bpy

from mas_blender.mas_bpy._bpy_core import bpy_ctx, bpy_io, bpy_scn
from mas_blender.mas_bpy import bpy_ani, bpy_mdl, bpy_mtl
from mas_blender.mas_qt import qt_ui
from mas_blender.mas_ops import OpsSessionData


# Load default data from config file.
ops_io_config_file_path = pathlib.Path(__file__).parent.joinpath('ops_io.config.json')
with ops_io_config_file_path.open('r', encoding='UTF-8') as readfile:
    IO_CONFIG_DATA = json.load(readfile)

# rigify_armature_obj = bpy_ani.ani_rigify_for_ue(
#     active_bone_layer_ids=(3, 4, 8, 11, 13, 14, 15, 16, 17, 18,)
# )
# bpy_ani.ani_reset_fcurve_modifiers(rigify_armature_obj)


class IOExportDialogUI(qt_ui.UIDialogBase):
    """
    Dialog Box UI for importing/exporting Object(s) for use in other platforms.
    """
    _UI_FILE_NAME = 'qt_io_export_dialog.ui'
    _UI_WINDOW_TITLE = 'MAS Blender - Export Tools'

    def __init__(
        self,
        parent: QtCore.QObject = None,
    ) -> None:
        """
        Constructor method.

        :param parent: Parent object (Application, UI Widget, etc.).
        """
        self._project = OpsSessionData.project
        self._project_path = OpsSessionData.project_path
        self._project_paths = OpsSessionData.proj_pipeline_paths(
            project_pipeline=self._project.pipeline
        )

        super().__init__(modality=False, parent=parent)


    def _set_up_ui(self) -> None:
        """"""
        # Create additional QObjects
        self._ui.io_export_method_btngrp = QtWidgets.QButtonGroup()
        self._ui.io_export_method_btngrp.setExclusive(True)

        self._ui.io_export_mdfr_type_btngrp = QtWidgets.QButtonGroup()
        self._ui.io_export_mdfr_type_btngrp.setExclusive(False)

        self._ui.io_export_platform_btngrp = QtWidgets.QButtonGroup()
        self._ui.io_export_platform_btngrp.setExclusive(True)

        self._ui.io_export_dir_btngrp = QtWidgets.QButtonGroup()
        self._ui.io_export_dir_btngrp.setExclusive(True)

        # Set properties
        file_format_finder = re.compile(r'^(\w+).*$')
        for grpbox in self._ui.io_export_options_frame.findChildren(QtWidgets.QGroupBox):
            file_format_match = file_format_finder.match(grpbox.title())
            grpbox.setProperty('file_format', file_format_match.group(1).lower())
            for label in grpbox.findChildren(QtWidgets.QLabel):
                setting_name = re.sub(r'[^\w\s]', '', label.text().lower())
                setting_name = re.sub(r'\s', '_', setting_name)
                label.setProperty('setting_name', setting_name)

        # Make connections
        self._ui.io_export_method_btngrp.buttonClicked[QtWidgets.QAbstractButton] \
            .connect(self.ui_update)
        self._ui.io_export_data_file_pshbtn.clicked.connect(self.ui_update_io_export_data_file)
        self._ui.io_export_dir_btngrp.buttonClicked[QtWidgets.QAbstractButton] \
            .connect(self.ui_update_io_export_dir)
        self._ui.io_export_export_pshbtn.clicked.connect(self.io_export)
        self._ui.io_export_mdfr_type_select_pshbtn.clicked \
            .connect(lambda: self.ui_update_io_export_mdfr(True))
        self._ui.io_export_mdfr_type_deselect_pshbtn.clicked \
            .connect(lambda: self.ui_update_io_export_mdfr(False))
        self._ui.io_export_platform_btngrp.buttonClicked[QtWidgets.QAbstractButton] \
            .connect(self.ui_update)
        self._ui.io_export_reset_pshbtn.clicked.connect(self.ui_update)

        self.ui_init()

    def io_export(self) -> None:
        """
        Performs the export operation based on options set in the UI.
        """
        current_file_path = bpy_io.io_get_current_file_path()

        export_dir_path = self._ui.io_proj_export_dir_lnedit.text()
        export_platform_name = self._ui.io_export_platform_btngrp.checkedButton().text()
        export_platform_data = IO_CONFIG_DATA['export']['platforms'][export_platform_name]
        export_settings = export_platform_data['settings']
        export_file_suffix = export_platform_data['suffix']
        for type_k, type_v in export_platform_data['convert'].items():
            # export_settings[type_k] = vars(__builtins__)[type_k](export_settings[type_v])
            export_settings[type_k] = dict(__builtins__)[type_v](export_settings[type_k])

        # Override export settings, if directed.
        for grpbox in self._ui.io_export_options_frame.findChildren(QtWidgets.QGroupBox):
            if grpbox.isEnabled() and grpbox.isVisible():
                for label in grpbox.findChildren(QtWidgets.QLabel):
                    setting_name = label.property('setting_name')
                    setting_value = label.buddy().text()
                    export_settings[setting_name] = setting_value

        # Customize the export based on method selected in by the user.
        export_method = self._ui.io_export_method_btngrp.checkedId()

        # Export based on customized JSON file (see ./ops_io_examples for template files).
        if export_method == 1:
            export_data_file_path_str = self._ui.io_export_data_file_label.text()
            export_data_file_path = pathlib.Path(export_data_file_path_str)
            with pathlib.Path(export_data_file_path).open('r', encoding='UTF-8') as r_file:
                export_data = json.load(r_file)

        # Export objects in active collection.
        elif export_method == 2:
            export_obj_name = bpy.context.collection.name
            export_data = {
                export_obj_name: {
                    'objects': {},
                    'overrides': {
                        'use_active_collection': True,
                        'use_selection': False
                    },
                    'textures': []
                }
            }

        # Export selected object(s).
        elif export_method == 3:
            export_obj_name = re.sub(r'\W', '_', bpy_io.io_get_current_file_path().stem)
            export_data = {
                export_obj_name: {
                    'objects': {obj.name: {} for obj in bpy.context.selected_objects},
                    'overrides': {
                        'use_active_collection': False,
                        'use_selection': True
                    },
                    'textures': []
                },
            }

        export_obj_names = sum(
            [list(export_data['objects']) for export_data in export_data.values()],
            list()
        )

        mdfrs_as_shape_keys = self._ui.io_export_mdfr_grpbox.isChecked()
        mdfr_start_frame = self._ui.io_export_mdfr_start_frame_spbox.value()
        mdfr_end_frame = self._ui.io_export_mdfr_end_frame_spbox.value()
        mdfr_frame_step = self._ui.io_export_mdfr_frame_step_spbox.value()
        mdfr_frame_range = (mdfr_start_frame, mdfr_end_frame, mdfr_frame_step)
        mdfr_name_prefix = self._ui.io_export_mdfr_name_lnedit.text()
        mdfr_names = [
            btn.text() for btn in self._ui.io_export_mdfr_type_btngrp.buttons() if btn.isChecked()
        ]
        mdfr_types = tuple(getattr(bpy.types, mdfr_name) for mdfr_name in mdfr_names)

        # Instanciate Exporter
        b3d_exporter = IOExporter(
            root_export_dir_path=export_dir_path
        )
        b3d_exporter.bake_ue2rigify_rig_to_source()

        if export_obj_names and mdfrs_as_shape_keys:
            b3d_exporter.prepare_shape_keys_from_modifiers(
                modifier_types=mdfr_types,
                keep_as_separate=False,
                object_names=export_obj_names,
                shape_key_name_prefix=mdfr_name_prefix,
                modifier_frame_range=mdfr_frame_range
            )
            b3d_exporter.apply_modifiers(
                object_names=export_obj_names
            )
            b3d_exporter.apply_shape_keys_from_modifiers(
                move_shape_keys_to_top=True
            )

        # Call export function
        b3d_exporter.export_objects(
            export_object_data=export_data,
            export_file_suffix=export_file_suffix,
            export_sub_dir=export_platform_name,
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

        self.done(0)

    def ui_init(self) -> None:
        """
        Initializes the UI.
        """
        export_data_names = ('Export Data File', 'Active Collection', 'Selected Object(s)')
        for i, export_data_name in enumerate(export_data_names, 1):
            export_data_radbtn = QtWidgets.QRadioButton(export_data_name)
            self._ui.io_export_method_frame.layout().addWidget(export_data_radbtn)
            self._ui.io_export_method_btngrp.addButton(export_data_radbtn, i)
            self._ui.io_export_method_btngrp.setId(export_data_radbtn, i)
        self._ui.io_export_method_btngrp.button(1).setChecked(True)

        for i, mdfr_name in enumerate(IO_CONFIG_DATA['export']['modifier_types'], 1):
            mdfr_type_chbox = QtWidgets.QCheckBox(mdfr_name)
            mdfr_type_chbox.setChecked(True)
            self._ui.io_export_mdfr_type_widget.layout().addWidget(mdfr_type_chbox)
            self._ui.io_export_mdfr_type_btngrp.addButton(mdfr_type_chbox)
            self._ui.io_export_mdfr_type_btngrp.setId(mdfr_type_chbox, i)

        for i, platform_name in enumerate(IO_CONFIG_DATA['export']['platforms'], 1):
            platform_radbtn = QtWidgets.QRadioButton(platform_name)
            self._ui.io_export_platform_grpbox.layout().addWidget(platform_radbtn)
            self._ui.io_export_platform_btngrp.addButton(platform_radbtn)
            self._ui.io_export_platform_btngrp.setId(platform_radbtn, i)
        self._ui.io_export_platform_btngrp.button(1).setChecked(True)

        for i, dir_radbtn in enumerate(
            self._ui.io_proj_export_dir_frame.findChildren(QtWidgets.QRadioButton), 1
        ):
            self._ui.io_export_dir_btngrp.addButton(dir_radbtn)
            self._ui.io_export_dir_btngrp.setId(dir_radbtn, i)
        self._ui.io_export_dir_btngrp.button(1).setChecked(True)

        self.ui_update_io_export_dir_proj()

        try:
            armature_msg = \
                'Control mode for ue2rigify detected.' + \
                f'Source Rig ({bpy.context.scene.ue2rigify.source_rig.name}) will be exported'
        except AttributeError:
            armature_msg = 'Armature objects modifying exported Mesh Object(s) will be exported.'
        self._ui.io_export_armature_detect.setText(armature_msg)

        self.ui_update()

    def ui_update(self) -> None:
        """
        Updates the UI section(s) based on the widget sender
        (or all sections if called by the script).
        """
        if self.sender() == self._ui.io_export_reset_pshbtn:
            self._ui.io_export_method_btngrp.button(1).setChecked(True)
            self._ui.io_export_data_file_label.setText('')
            self._ui.io_export_mdfr_end_frame_spbox.setValue(0)
            self._ui.io_export_mdfr_frame_step_spbox.setValue(1)
            self._ui.io_export_mdfr_name_lnedit.setText('')
            self._ui.io_export_mdfr_start_frame_spbox.setValue(0)

        export_platform_name = self._ui.io_export_platform_btngrp.checkedButton().text()
        export_file_suffix = IO_CONFIG_DATA['export']['platforms'][export_platform_name]['suffix']
        export_file_format = IO_CONFIG_DATA['export']['file_formats'][export_file_suffix]
        self._ui.io_export_format_label.setText(f'{export_file_format} ({export_file_suffix})')

        for grpbox in self._ui.io_export_options_frame.findChildren(QtWidgets.QGroupBox):
            options_enabled = grpbox.property('file_format') == export_file_format
            grpbox.setEnabled(options_enabled)
            grpbox.setVisible(options_enabled)

        if self.sender() in (None, self._ui.io_export_platform_btngrp):

            #
            proj_data_dir_path = self._project_paths.get('data/addons/mas_blender')
            if proj_data_dir_path is not None:
                export_platform = self._ui.io_export_platform_btngrp.checkedButton().text()
                file_pattern = re.sub(r'\W+', '*', export_platform, count=0, flags=re.I)
                for export_json_file_path in proj_data_dir_path.glob(f'*{file_pattern}.json'):
                    self._ui.io_export_data_file_label.setText(export_json_file_path.as_posix())
                    break

            export_file_path = pathlib.Path(self._ui.io_export_data_file_label.text())
            if export_file_path.is_file():
                export_config_file_path = export_file_path.with_suffix('.config.json')
                if export_config_file_path.is_file():
                    with export_config_file_path.open('r', encoding='UTF-8') as r_file:
                        export_config_data = json.load(r_file)

                    for config_k, widget_func in {
                        'gltf_copyright': self._ui.io_export_gltf_copyright_lnedit.setText,
                        'mdfr_enable': self._ui.io_export_mdfr_grpbox.setChecked,
                        'mdfr_end_frame': self._ui.io_export_mdfr_end_frame_spbox.setValue,
                        'mdfr_frame_step': self._ui.io_export_mdfr_frame_step_spbox.setValue,
                        'mdfr_name': self._ui.io_export_mdfr_name_lnedit.setText,
                        'mdfr_start_frame': self._ui.io_export_mdfr_start_frame_spbox.setValue
                    }.items():
                        if config_k in export_config_data:
                            widget_func(export_config_data[config_k])

        export_requirements = [pathlib.Path(self._ui.io_proj_export_dir_lnedit.text()).is_dir()]
        use_export_data_file = self._ui.io_export_method_btngrp.checkedId() == 1
        self._ui.io_export_data_file_pshbtn.setEnabled(use_export_data_file)
        self._ui.io_export_data_file_label.setEnabled(use_export_data_file)
        if use_export_data_file:
            export_requirements.append(
                pathlib.Path(self._ui.io_export_data_file_label.text()).is_file()
            )

        self._ui.io_export_export_pshbtn.setEnabled(all(export_requirements))


    def ui_update_io_export_data_file(self) -> None:
        """
        Sets the data file path to use for the export.
        """
        export_file_path = qt_ui.ui_get_file(
            caption='Select export data file',
            dir_str=self._project_paths.get('data', self._project_path).as_posix(),
            filter_str='JSON Files (*.json)'
        )
        if export_file_path is not None:
            self._ui.io_export_data_file_label.setText(export_file_path.as_posix())

        self.ui_update()

    def ui_update_io_export_dir(self) -> None:
        """
        Sets the export directory based on either the project or explicitly by the user.
        """
        if self._ui.io_export_dir_btngrp.checkedId() == 1:
            self.ui_update_io_export_dir_proj()

        elif self._ui.io_export_dir_btngrp.checkedId() == 2:
            export_dir = qt_ui.ui_get_directory(
                caption='Select Export Directory',
                dir_str=bpy_io.io_get_current_file_path().parent.as_posix()
            )
            if export_dir is not None:
                self._ui.io_proj_export_dir_lnedit.setText(export_dir.as_posix())
            else:
                self._ui.io_export_dir_btngrp.button(1).setChecked(True)

        self.ui_update()

    def ui_update_io_export_dir_proj(self) -> None:
        """
        Sets the export directory to the "models" subdirectory of the proiect.
        """
        self._ui.io_proj_name_lnedit.setText(self._project.name)
        self._ui.io_proj_export_dir_lnedit.setText(
            self._project_paths.get('models', self._project_path).as_posix()
        )

    def ui_update_io_export_mdfr(self, *args) -> None:
        """
        Sets the modifier setting based on the sender's True or False argument.
        """
        for mdfr_chbox in self._ui.io_export_mdfr_type_btngrp.buttons():
            mdfr_chbox.setChecked(args[0])


class IOExporter(object):
    """
    TODO
    """

    def __init__(
        self,
        root_export_dir_path: typing.Union[pathlib.Path, str]
    ):
        """TODO"""
        root_export_dir_path = pathlib.Path(root_export_dir_path)
        self.export_dir_path = root_export_dir_path.joinpath(bpy_io.io_get_current_file_path().stem)
        self.export_dir_path.mkdir(parents=True, exist_ok=True)
        #
        # Save as a separate file in the temp directory for the session.
        current_file_name = bpy_io.io_get_current_file_path().name
        temp_dir_path = bpy_io.io_get_temp_dir(context='session')
        save_file_path = temp_dir_path.joinpath(current_file_name)
        bpy_io.io_save_as(
            file_path=save_file_path,
            check_existing=False
        )
        #
        self.armature_obj = None
        self.control_rig = None
        self.shape_key_objs = {}
        self.shape_key_modifier_types = set()

        ue2rigify_loaded = all((
            bpy_ctx.ctx_get_addon('rigify'),
            bpy_ctx.ctx_get_addon('ue2rigify')
        ))
        if ue2rigify_loaded:
            import ue2rigify
            ue2rigify_extras_col = bpy.data.collections.get(
                ue2rigify.constants.Collections.EXTRAS_COLLECTION_NAME
            )
            self.armature_obj = bpy.context.scene.ue2rigify.source_rig
            if ue2rigify_extras_col:
                self.control_rig = ue2rigify_extras_col.objects.get(
                    ue2rigify.constants.Rigify.CONTROL_RIG_NAME
                )

    def _validate_for_shape_keys(
        self,
        object_to_validate: bpy.types.Object
    ):
        """TODO"""
        try:
            assert hasattr(object_to_validate, 'data')
            assert hasattr(object_to_validate.data, 'shape_keys')
        except AssertionError:
            return False
        return True

    def apply_modifiers(
        self,
        object_names: list = typing.Iterable[str]
    ):
        """
        Step 2 to apply deformation from modifier(a) as Shape Keys.
        An Object cannot be exported from Blender with Shape Keys if any modifiers are active.
        Sadly, most modifiers cannot be applied to an Object if it has any shape keys.
        apply_modifiers() work-around:
        1. Creates temporary Object duplicate(s) for each shape key on an Object.
        2. Removes all shape keys from source Object so that modifiers can be applied.
        3. Creates a new shape key from each temporary Object duplicate.
        IMPORTANT:
        To apply modifiers as Shape Keys, run the following methods in the following order:
        1. prepare_shape_keys_from_modifiers()
        2. apply_modifiers()
        3. apply_shape_keys_from_modifiers()
        """
        # Iterate through each Object
        for obj_name in object_names:
            orig_obj = bpy.data.objects.get(obj_name)
            if self._validate_for_shape_keys(orig_obj):

                bpy_scn.scn_set_all_hidden(orig_obj, False)
                dup_objs = {}

                if orig_obj.data.shape_keys:
                    # Clear drivers and/or keyframes driving shape keys and set their values to 0
                    # shape_key_data_name = orig_obj.active_shape_key.id_data.name
                    # anim_data = bpy.data.shape_keys[shape_key_data_name].animation_data
                    # if anim_data:
                    #     action_fcrvs = anim_data.action.fcurves if anim_data.action else []
                    #     for _ in action_fcrvs:
                    #         action_fcrvs.remove(action_fcrvs[0])
                    #     driver_fcrvs = anim_data.drivers
                    #     for _ in driver_fcrvs:
                    #         driver_fcrvs.remove(driver_fcrvs[0])
                    bpy_ani.ani_break_inputs(
                        target_object=orig_obj,
                        on_data=True
                    )

                    orig_shape_keys = orig_obj.data.shape_keys.key_blocks
                    for shape_key in orig_shape_keys:
                        shape_key.value = 0

                    # Create Object duplicate(s) for each shape key on the Object.
                    for shape_key in orig_shape_keys[1:]:
                        bpy_scn.scn_select_items(items=[orig_obj])
                        shape_key.value = 1
                        bpy.ops.object.duplicate(linked=False)
                        dup_obj = bpy.context.object
                        dup_objs[shape_key.name] = dup_obj
                        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
                        for dup_mod in dup_obj.modifiers:
                            if not isinstance(dup_mod, bpy.types.ArmatureModifier):
                                if isinstance(dup_mod, tuple(self.shape_key_modifier_types)):
                                    bpy.ops.object.modifier_remove(modifier=dup_mod.name)
                                else:
                                    try:
                                        bpy.ops.object.modifier_apply(modifier=dup_mod.name)
                                    except RuntimeError as r_e:
                                        print(r_e)
                        shape_key.value = 0

                bpy_scn.scn_select_items(items=[orig_obj])
                orig_obj.shape_key_clear()
                for mod in orig_obj.modifiers:
                    if not isinstance(mod, bpy.types.ArmatureModifier):
                        if isinstance(mod, tuple(self.shape_key_modifier_types)):
                            bpy.ops.object.modifier_remove(modifier=mod.name)
                        else:
                            try:
                                bpy.ops.object.modifier_apply(modifier=mod.name)
                            except RuntimeError as r_e:
                                print(r_e)

                for shape_key_name, dup_obj in dup_objs.items():
                    bpy_scn.scn_select_items(items=[dup_obj, orig_obj])
                    bpy.ops.object.join_shapes()
                    shape_key_index = len(orig_obj.data.shape_keys.key_blocks) - 1
                    orig_obj.active_shape_key_index = shape_key_index
                    orig_obj.active_shape_key.name = shape_key_name
                    bpy_scn.scn_select_items(items=[dup_obj])
                    bpy.ops.object.delete(use_global=False)
                    bpy.context.view_layer.objects.active = orig_obj
                orig_obj.active_shape_key_index = 0

    def apply_shape_keys_from_modifiers(
        self,
        move_shape_keys_to_top: bool = False,
    ):
        """
        Step 3 to apply deformation from modifier(a) as Shape Keys.
        Creates Shape Keys from mesh duplicates created with prepare_shape_keys_from_modifiers().
        See the apply_modifiers() method for more information.
        """
        for orig_obj, shape_key_objs in self.shape_key_objs.items():
            for i, (shape_key_name, shape_key_obj) in enumerate(shape_key_objs.items(), 1):
                bpy_scn.scn_select_items(items=[shape_key_obj, orig_obj])
                bpy.ops.object.join_shapes()
                bpy_scn.scn_select_items(items=[orig_obj])
                shape_key_index = len(orig_obj.data.shape_keys.key_blocks) - 1
                orig_obj.active_shape_key_index = shape_key_index
                orig_obj.active_shape_key.name = shape_key_name
                if move_shape_keys_to_top:
                    bpy.ops.object.shape_key_move(type='TOP')
                    while orig_obj.active_shape_key_index < i:
                        bpy.ops.object.shape_key_move(type='DOWN')

                bpy_scn.scn_select_items(items=[shape_key_obj])
                bpy.ops.object.delete(use_global=False)
            orig_obj.active_shape_key_index = 0

    def bake_ue2rigify_rig_to_source(self):
        """
        Note that ue2rigify will only bake actions present in the rig's NLA editor.
        Make sure to stash (or push down) all actions and
        set their frame range to include them before baking.
        """
        if self.control_rig is not None:

            # Create NLA strips for each action
            anim_data = self.control_rig.animation_data
            if anim_data is not None:
                bpy_scn.scn_select_items(items=[self.control_rig])
                bpy_ani.ani_reset_armature_transforms(self.control_rig)
                for nla_track in anim_data.nla_tracks:
                    anim_data.nla_tracks.remove(nla_track)

                for action in reversed(bpy.data.actions):
                    nla_track = anim_data.nla_tracks.new()
                    nla_track.lock = True
                    nla_track.mute = True
                    nla_track.name = action.name
                    nla_track.select = False

                    nla_strip = nla_track.strips.new(
                        name=action.name,
                        start=int(action.frame_range[0]),
                        action=action
                    )
                    nla_strip.action_frame_end = int(action.frame_range[1])
                    nla_strip.action_frame_start = int(action.frame_range[0])
                    nla_strip.select = False

                    bpy_scn.scn_select_items(items=[self.control_rig])
                    bpy_ani.ani_reset_armature_transforms(self.control_rig)

            # ue2rigify bake rig to source
            bpy.ops.ue2rigify.bake_from_rig_to_rig()

        # Clear current action and reset armature transforms
        if self.armature_obj:
            bpy_scn.scn_select_items(items=[self.armature_obj])
            bpy_ani.ani_reset_armature_transforms(armature_obj=self.armature_obj)

    def export_objects(
        self,
        export_object_data: dict,
        export_file_suffix: str,
        export_sub_dir: typing.Union[str, None] = None,
        **export_settings
    ):
        """
        TODO
        """
        export_dir_path = self.export_dir_path
        if export_sub_dir is not None:
            export_dir_path = export_dir_path.joinpath(export_sub_dir)
        export_dir_path.mkdir(parents=True, exist_ok=True)
        export_file_format = IO_CONFIG_DATA['export']['file_formats'][export_file_suffix]
        export_function = getattr(bpy.ops.export_scene, export_file_format) #TODO develop solution for vrm

        if self.armature_obj:
            bpy_scn.scn_select_items(items=[self.armature_obj])
            bpy_ani.ani_reset_armature_transforms(armature_obj=self.armature_obj)

        for export_obj_name, export_obj_data in export_object_data.items():

            export_file_path = \
                export_dir_path.joinpath(export_obj_name).with_suffix(export_file_suffix)

            export_settings_copy = copy.deepcopy(export_settings)
            for override_k, override_v in export_obj_data['overrides'].items():
                export_settings_copy[override_k] = override_v

            #
            for img_data in export_obj_data['textures']:
                images = [
                    bpy.data.images[img] for img in img_data['images'] if bpy.data.images.get(img)
                ]
                bpy_mtl.mtl_resize_image_textures(
                    images=images,
                    max_height=img_data['height'],
                    max_width=img_data['width'],
                )

            orig_obj_data_path_data = {}

            #
            if export_settings_copy['use_active_collection'] \
            and not export_settings_copy['use_selection']:

                for lyr_col in bpy.context.view_layer.layer_collection.children:
                    if lyr_col.name == export_obj_name:
                        bpy.context.view_layer.active_layer_collection = lyr_col
                        break

            #
            elif export_settings_copy['use_selection'] \
            and not export_settings_copy['use_active_collection']:

                export_objs = [self.armature_obj] if self.armature_obj is not None else []
                for obj_name, obj_data in export_obj_data['objects'].items():

                    obj = bpy.data.objects.get(obj_name)
                    if obj is not None:
                        export_objs.extend([
                            mdfr.object for mdfr in obj.modifiers if isinstance(
                                mdfr, bpy.types.ArmatureModifier
                            )
                        ])
                        export_objs.append(obj)

                        obj_data_modifiers = obj_data.get('modifiers', {})
                        obj_data_shape_keys = obj_data.get('shape_keys', {})
                        if obj_data_modifiers or obj_data_shape_keys:
                            bpy_ani.ani_break_inputs(
                                target_object=obj,
                                on_data=True,
                                on_object=True
                            )
                            orig_obj_data_path_data[obj] = bpy_ani.ani_set_data_path_values(
                                target_object=obj,
                                modifier_data=obj_data_modifiers,
                                shape_key_data=obj_data_shape_keys
                            )

                        obj_data_material = obj_data.get('material', '')
                        if obj_data_material:
                            bpy_scn.scn_select_items(items=[obj])
                            bpy_mtl.mtl_assign_material(
                                target_object=obj,
                                material_name=obj_data_material
                            )

                export_objs = list(set(export_objs))
                bpy_scn.scn_select_items(items=export_objs)

            else:
                return

            # Export the object(s)
            export_function(
                filepath=export_file_path.as_posix(),
                **export_settings_copy
            )

            # Reset data path values to pre-export settings
            for obj, orig_data_path_data in orig_obj_data_path_data.items():
                bpy_ani.ani_set_data_path_values(
                    target_object=obj,
                    modifier_data=orig_data_path_data[0],
                    shape_key_data=orig_data_path_data[1]
                )

            # Reset image texture sizes to pre-export sizes
            for img_data in export_obj_data['textures']:
                for img_name in img_data['images']:
                    img = bpy.data.images.get(img_name)
                    if img is not None:
                        img.reload()

    def prepare_shape_keys_from_modifiers(
        self,
        modifier_types: typing.Tuple[bpy.types.Modifier] = (bpy.types.Modifier,),
        keep_as_separate: bool = True,
        object_names: list = typing.Iterable[str],
        shape_key_name_prefix: str = '',
        modifier_frame_range: typing.Iterable[int] = (1, 2, 1)
    ):
        """
        Step 1 to apply deformation from modifier(a) as Shape Keys.
        Duplicates the mesh with the speicified modifier(s) applied,
        to be used as Shape Key source meshes in apply_shape_keys_from_modifiers().
        See the apply_modifiers() method for more information.
        """
        def _add_shape_key_obj(
            orig_obj: bpy.types.Object,
            shape_key_name: str,
            shape_key_obj: bpy.types.Object
        ):
            """
            Adds an entry for tracking temporary mesh(es) to be applied as Shape Key(s).
            """
            if orig_obj not in self.shape_key_objs:
                self.shape_key_objs[orig_obj] = {}
            self.shape_key_objs[orig_obj][shape_key_name] = shape_key_obj

        #
        for i in range(*modifier_frame_range):

            if len(range(*modifier_frame_range)) > 1:
                shape_key_name = f'{shape_key_name_prefix}_{i:02d}'
            else:
                shape_key_name = shape_key_name_prefix

            for obj_name in object_names:
                orig_obj = bpy.data.objects.get(obj_name)
                if self._validate_for_shape_keys(orig_obj):

                    # If the object does not have any modifiers of the given type(s), skip it
                    if not any((
                        isinstance(mod, modifier_types) for mod in orig_obj.modifiers
                    )):
                        continue

                    # Force driver updates
                    bpy.context.scene.frame_set(i)
                    anim_data = orig_obj.animation_data
                    if anim_data:
                        for fcrv in orig_obj.animation_data.drivers:
                            fcrv.driver.expression = fcrv.driver.expression
                            fcrv.update()

                    # If a separate shape key is needed for each modifier of the given type(s),
                    # create a duplicate object for each modifier.
                    if keep_as_separate:
                        for j, mod in enumerate(orig_obj.modifiers):
                            if isinstance(mod, modifier_types):
                                dup_obj_name = \
                                    f'{shape_key_name}_{j:03d}' if shape_key_name else mod.name
                                bpy_scn.scn_select_items(items=[orig_obj])
                                dup_obj = bpy_scn.scn_duplicate_object(
                                    obj=orig_obj,
                                    name=dup_obj_name
                                )
                                if dup_obj.data.shape_keys:
                                    bpy.ops.object.shape_key_clear()
                                    bpy.ops.object.shape_key_remove(all=True, apply_mix=False)
                                _add_shape_key_obj(
                                    orig_obj=orig_obj,
                                    shape_key_name=dup_obj_name,
                                    shape_key_obj=dup_obj
                                )

                                for dup_mod in dup_obj.modifiers:
                                    if isinstance(dup_mod, modifier_types):
                                        if dup_mod.name == mod.name:
                                            bpy_mdl.mdl_set_modifier_display(
                                                modifier=dup_mod, visibility=True
                                            )
                                        else:
                                            bpy.ops.object.modifier_remove(modifier=dup_mod.name)
                                    try:
                                        bpy.ops.object.modifier_apply(modifier=dup_mod.name)
                                    except RuntimeError as r_e:
                                        print(r_e)

                    # If a single shape key is needed for all the deformer(s),
                    # create a single duplicate object from all modifiers of the given type(s).
                    else:
                        bpy_scn.scn_select_items(items=[orig_obj])
                        dup_obj = bpy_scn.scn_duplicate_object(
                            obj=orig_obj,
                            name=shape_key_name
                        )
                        if dup_obj.data.shape_keys:
                            bpy.ops.object.shape_key_clear()
                            bpy.ops.object.shape_key_remove(all=True, apply_mix=False)
                        _add_shape_key_obj(
                            orig_obj=orig_obj,
                            shape_key_name=shape_key_name,
                            shape_key_obj=dup_obj
                        )

                        for dup_mod in dup_obj.modifiers:
                            if isinstance(dup_mod, modifier_types):
                                bpy_mdl.mdl_set_modifier_display(modifier=dup_mod, visibility=True)
                            try:
                                bpy.ops.object.modifier_apply(modifier=dup_mod.name)
                            except RuntimeError as r_e:
                                print(r_e)

            self.shape_key_modifier_types = self.shape_key_modifier_types.union(modifier_types)

        bpy.context.scene.frame_set(modifier_frame_range[0])


def io_launch_export_dialog_ui() -> None:
    """
    Launches the IO Export Dialog Box UI.
    """
    os.system('cls')

    qt_ui.ui_launch_dialog(IOExportDialogUI)
