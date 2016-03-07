#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Class that handles the whole preprocessing workflow, including:
    1) signal processing
    2) window selection
    3) adjoint sources

:copyright:
    Wenjie Lei (lei@princeton.edu), 2016
:license:
    GNU General Public License, Version 3
    (http://www.gnu.org/copyleft/gpl.html)
"""
from __future__ import (absolute_import, division, print_function)
from functools import partial

from .procbase import ProcASDFBase
from pytomo3d.signal.process import process
from pytomo3d.adjoint.adjsrc import calculate_adjsrc_on_stream
from pytomo3d.adjoint.adjsrc import postprocess_adjsrc
from pytomo3d.window.window import window_on_stream
from .adjoint_util import calculate_chan_weight, reshape_adj
from .adjoint_util import smart_transform_window
import pyflex
import pyadjoint
import copy


def load_window_config(param):
    config_dict = {}
    for key, value in param.iteritems():
        config_dict[key] = pyflex.Config(**value)
    return config_dict


def load_adjoint_config(param):
    adj_src_type = param["adj_src_type"]
    param.pop("adj_src_type", None)
    config = pyadjoint.Config(**param)
    return config, adj_src_type


def func_wrapper(obsd_station_group, synt_station_group, obsd_tag=None,
                 synt_tag=None, event=None, param=None, _verbose=False,
                 figure_mode=False, figure_dir=None):
    """
    combo function, including:
    1) observed data signal processing
    2) synthetic data signal processing
    3) window selection based on a pair of data
    4) adjoint source constructor
    """
    # Make sure everything thats required is there.
    _station_name = obsd_station_group._station_name
    if not hasattr(obsd_station_group, "StationXML"):
        raise ValueError("obsd station group '%s' missing 'StationXML'"
                         % _station_name)
    if not hasattr(synt_station_group, "StationXML"):
        raise ValueError("synt station group '%s' missing 'StationXML'"
                         % _station_name)
    if not hasattr(obsd_station_group, obsd_tag):
        raise ValueError("obsd station group '%s' missing '%s'"
                         % (_station_name, obsd_tag))
    if not hasattr(synt_station_group, synt_tag):
        raise ValueError("synt station group '%s' missing '%s'"
                         % (_station_name, synt_tag))

    param = copy.deepcopy(param)

    obsd_staxml = obsd_station_group.StationXML
    synt_staxml = synt_station_group.StationXML
    observed = getattr(obsd_station_group, obsd_tag)
    synthetic = getattr(synt_station_group, synt_tag)

    # keep a reference for construct adjoint source, which
    # should be same length and dt as raw synt
    _raw_synt_tr = synthetic[0].copy()

    obsd_param = param["proc_obsd_param"]
    new_obsd = process(observed, inventory=obsd_staxml, **obsd_param)

    synt_param = param["proc_synt_param"]
    new_synt = process(synthetic, inventory=synt_staxml, **synt_param)

    window_config = load_window_config(param["window_param"])
    windows = window_on_stream(new_obsd, new_synt, window_config,
                               station=synt_staxml, event=event,
                               figure_mode=figure_mode, figure_dir=figure_dir,
                               _verbose=_verbose)
    if len(windows) == 0:
        # No windows selected
        return

    windows = smart_transform_window(windows)

    adj_config, adj_src_type = load_adjoint_config(param["adjsrc_param"])
    adjsrcs = calculate_adjsrc_on_stream(
        new_obsd, new_synt, windows, adj_config, adj_src_type,
        figure_mode=figure_mode, figure_dir=figure_dir,
        adjoint_src_flag=True)

    chan_weight_dict = calculate_chan_weight(adjsrcs, windows)

    interp_starttime = _raw_synt_tr.stats.starttime
    interp_delta = _raw_synt_tr.stats.delta
    interp_npts = _raw_synt_tr.stats.npts
    pre_filt = obsd_param["pre_filt"]
    new_adjsrcs = postprocess_adjsrc(
        adjsrcs, interp_starttime, interp_delta, interp_npts,
        rotate_flag=True, inventory=synt_staxml, event=event,
        sum_over_comp_flag=True, weight_flag=True,
        weight_dict=chan_weight_dict, filter_flag=True,
        pre_filt=pre_filt)

    origin = event.preferred_origin() or event.origins[0]
    time_offset = interp_starttime - origin.time
    results = reshape_adj(new_adjsrcs, time_offset, synt_staxml)

    return results


class AdjPreASDF(ProcASDFBase):

    def __init__(self, path, param, components=["Z", "R", "T"],
                 verbose=False):

        ProcASDFBase.__init__(self, path, param, verbose=verbose)
        self.components = components

    def _parse_param(self):
        """
        Load param file
        """
        param = self.param
        param = self._parse_yaml(param)

        param_dict = {}
        keys = ["proc_obsd_param", "proc_synt_param", "adjsrc_param"]
        for key in keys:
            param_dict[key] = self._parse_yaml(param[key])

        param_dict["window_param"] = \
            self.__load_window_param(param["window_param"])

        return param_dict

    def __load_window_param(self, window_param):
        """
        load window param
        """
        if set(window_param.keys()) != set(self.components):
            raise ValueError("window param '%s' components(%s) is "
                             "inconsistent with init settings(%s)"
                             % (window_param, window_param.keys,
                                self.components))
        param_dict = {}
        for key, value in window_param.iteritems():
            param_dict[key] = self._parse_yaml(value)
        return param_dict

    def _validate_path(self, path):
        necessary_keys = ["obsd_asdf", "obsd_tag", "synt_asdf", "synt_tag",
                          "output_asdf", "figure_mode", "figure_dir"]
        self._missing_keys(necessary_keys, path)

    def _validate_param(self, param):
        necessary_keys = ["proc_obsd_param", "proc_synt_param", "adjsrc_param",
                          "window_param"]
        self._missing_keys(necessary_keys, param)

    @staticmethod
    def __refine_signalproc_param(param, event):
        origin = event.preferred_origin() or event.origin[0]
        event_time = origin.time
        event_latitude = origin.latitude
        event_longitude = origin.longitude
        param["starttime"] = event_time + param["relative_starttime"]
        param["endtime"] = event_time + param["relative_endtime"]
        param["event_latitude"] = event_latitude
        param["event_longitude"] = event_longitude

    def _refine_param(self, param, event):
        """
        Refine event-based parameter, for example, some parameters
        in signal processing stage
        """
        obsd_param = param["proc_obsd_param"]
        self.__refine_signalproc_param(obsd_param, event)
        synt_param = param["proc_synt_param"]
        self.__refine_signalproc_param(synt_param, event)

    def _core(self, path, param):

        self._validate_path(path)
        self._validate_param(param)

        self.print_info(path, "Path Info")
        self.print_info(param, "Param Info")

        obsd_file = path["obsd_asdf"]
        synt_file = path["synt_asdf"]
        output_file = path["output_asdf"]

        self.check_input_file(obsd_file)
        self.check_input_file(synt_file)
        self.check_output_file(output_file)

        obsd_ds = self.load_asdf(obsd_file, mode="r")
        synt_ds = self.load_asdf(synt_file, mode="r")
        synt_tag = path["synt_tag"]
        obsd_tag = path["obsd_tag"]

        event = obsd_ds.events[0]

        self._refine_param(param, event)

        proc_func = partial(func_wrapper, event=event, obsd_tag=obsd_tag,
                            synt_tag=synt_tag, param=param)

        obsd_ds.process_two_files(
            synt_ds, proc_func, output_filename=output_file)