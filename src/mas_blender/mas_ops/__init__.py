#!$BLENDER_PATH/python/bin python

"""
MAS Blender - OPS (Operators)

.. code-block:: python

    # Import MAS Blender - OPS
    from mas_blender.mas_ops import ops_proj

"""

# for ANIM update
# mas_scripts.script_update_asset()
# mas_scripts.script_import_keying_set()

# for RNDR setup
# mas_scripts.script_append_anim_for_render()

# for RNDR
# mas_scripts.script_update_render_template()

# for batch RNDR
# mas_scripts.script_batch_render()

# from mas_blender.mas_ops import OpsSessionData

# proj = OpsSessionData.project
# proj_paths = OpsSessionData.proj_pipeline_paths(
#     root_dir_path=proj.path,
#     project_pipeline=proj.pipeline
# )

import pathlib
import typing

import sqlalchemy

from mas_blender.mas_db import db_sql


class OpsSessionDataMeta(type):
    """
    Metaclass for OpsSessionData class.
    """
    def __init__(cls, *args, **kwargs):
        """
        Constructor method.
        """
        cls._db_engine = sqlalchemy.engine.base.Engine(None, None, '')
        cls._project = db_sql.DBProject(
            code='',
            name='',
            path='',
            pipeline={},
        )
        cls._project_path = pathlib.Path(cls._project.path)

    @property
    def db_engine(cls) -> sqlalchemy.engine.base.Engine:
        """
        Persistent Database Engine property for the Blender session.
        """
        return cls._db_engine

    @db_engine.setter
    def db_engine(cls, db_engine: sqlalchemy.engine.base.Engine):
        """
        Persistent Database Engine setter for the Blender session.
        """
        cls._db_engine = db_engine

    @property
    def project(cls) -> db_sql.DBProject:
        """
        Persistent Database Project property for the Blender session.
        """
        return cls._project

    @project.setter
    def project(cls, project: db_sql.DBProject):
        """
        Persistent Database Project setter for the Blender session.
        """
        cls._project = project

    @property
    def project_path(cls) -> pathlib.Path:
        """
        Persistent Project Path property for the Blender session.
        """
        return pathlib.Path(cls.project.path)


class OpsSessionData(dict, metaclass=OpsSessionDataMeta):
    """
    Global class with persistent class properties available for the duration of the Blender session.
    """
    @classmethod
    def proj_pipeline_paths(
        cls,
        project_pipeline: dict,
        sub_dir_str: str = ''
    ) -> typing.Dict[str, pathlib.Path]:
        """
        Creates a list of Paths for all folders in a project.

        :param project_pipeline: Project pipeline heirarchy data.
        :returns: A dictionary of Paths for each folder in the pipeline data.
        """
        sub_dir_path = cls.project_path.joinpath(sub_dir_str)
        project_dir_paths = {sub_dir_str: sub_dir_path}

        for key, val in project_pipeline.items():
            sub_dir_str_ext = '/'.join((sub_dir_str, key)).strip('/')
            project_dir_paths.update(
                cls.proj_pipeline_paths(
                    project_pipeline=val,
                    sub_dir_str=sub_dir_str_ext
                )
            )

        return project_dir_paths
