#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=wrong-import-position, redefined-outer-name, range-builtin-not-iterating, too-many-locals

"""
Instantiate Retro tables and find the max over the log-likelihood space.
"""

from __future__ import absolute_import, division, print_function

__all__ = [
    'PRI_UNIFORM',
    'PRI_LOG_UNIFORM',
    'PRI_LOG_NORMAL',
    'PRI_COSINE',
    'PRI_GAUSSIAN',
    'PRI_SPEFIT2',
    'PRI_CAUCHY',
    'reco',
    'parse_args'
]

__author__ = 'J.L. Lanfranchi, P. Eller'
__license__ = '''Copyright 2017 Justin L. Lanfranchi

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.'''

from argparse import ArgumentParser
from collections import OrderedDict
from math import acos, exp

from os.path import abspath, dirname, join
import pickle
import sys
import time

import numpy as np
from scipy import stats

if __name__ == '__main__' and __package__ is None:
    RETRO_DIR = dirname(dirname(abspath(__file__)))
    if RETRO_DIR not in sys.path:
        sys.path.append(RETRO_DIR)
from retro import LLHP_T, init_obj
from retro.const import TWO_PI, ALL_STRS_DOMS_SET, EMPTY_SOURCES
from retro.retro_types import HypoParams8D, HypoParams10D
from retro.utils.misc import expand, mkdir, sort_dict


PRI_UNIFORM = 'uniform'
PRI_LOG_UNIFORM = 'log_uniform'
PRI_LOG_NORMAL = 'log_normal'
PRI_COSINE = 'cosine'
PRI_GAUSSIAN = 'gaussian'
PRI_SPEFIT2 = 'spefit2'
PRI_CAUCHY = 'cauchy'


class reco(object):

    def init(self, dom_tables_kw, hypo_kw, events_kw, reco_kw):
        """Script "main" function"""
        t00 = time.time()

        self.dom_tables = init_obj.setup_dom_tables(**dom_tables_kw)
        self.hypo_handler = init_obj.setup_discrete_hypo(**hypo_kw)
        self.events_iterator = init_obj.get_events(**events_kw)

        print('Running reconstructions...')

        spatial_prior_orig = reco_kw.pop('spatial_prior').strip()
        spatial_prior_name = spatial_prior_orig.lower()
        if spatial_prior_name == 'ic':
            x_prior = (PRI_UNIFORM, (-860, 870))
            y_prior = (PRI_UNIFORM, (-780, 770))
            z_prior = (PRI_UNIFORM, (-780, 790))
        elif spatial_prior_name == 'dc':
            x_prior = (PRI_UNIFORM, (-150, 270))
            y_prior = (PRI_UNIFORM, (-210, 150))
            z_prior = (PRI_UNIFORM, (-770, 760))
        elif spatial_prior_name == 'dc_subdust':
            x_prior = (PRI_UNIFORM, (-150, 270))
            y_prior = (PRI_UNIFORM, (-210, 150))
            z_prior = (PRI_UNIFORM, (-610, -60))
        elif spatial_prior_name == 'spefit2':
            x_prior = (
                PRI_SPEFIT2,
                (
                    # scipy.stats.cauchy loc, scale parameters
                    -0.19687812829978152, 14.282171566308806,
                    # Hard limits
                    -600, 750
                )
            )
            y_prior = (
                PRI_SPEFIT2,
                (
                    # scipy.stats.cauchy loc, scale parameters
                    -0.2393645701205161, 15.049528023495354,
                    # Hard limits
                    -750, 650
                )
            )
            z_prior = (
                PRI_SPEFIT2,
                (
                    # scipy.stats.cauchy loc, scale parameters
                    -5.9170661027492546, 12.089399308036718,
                    # Hard limits
                    -1200, 200
                )
            )
        else:
            raise ValueError('Spatial prior "{}" not recognized'
                             .format(spatial_prior_orig))

        temporal_prior_orig = reco_kw.pop('temporal_prior').strip()
        temporal_prior_name = temporal_prior_orig.lower()
        if temporal_prior_name == PRI_UNIFORM:
            time_prior = (PRI_UNIFORM, (-4e3, 0.0))
        elif temporal_prior_name == PRI_SPEFIT2:
            time_prior = (
                PRI_SPEFIT2,
                (
                    # scipy.stats.cauchy loc (rel to SPEFit2 time), scale
                    -82.631395081663754, 75.619895703067343,
                    # Hard limits (relative to left, right edges of window,
                    # respectively)
                    -4e3, 0.0
                )
            )
        else:
            raise ValueError('Temporal prior "{}" not recognized'
                             .format(temporal_prior_orig))

        cascade_energy_prior_name = reco_kw.pop('cascade_energy_prior')
        cascade_energy_lims = reco_kw.pop('cascade_energy_lims')
        if cascade_energy_prior_name == PRI_UNIFORM:
            cascade_energy_prior = (PRI_UNIFORM, (np.min(cascade_energy_lims), np.max(cascade_energy_lims)))
        elif cascade_energy_prior_name == PRI_LOG_UNIFORM:
            cascade_energy_prior = (PRI_LOG_UNIFORM, (np.min(cascade_energy_lims), np.max(cascade_energy_lims)))
        elif cascade_energy_prior_name == PRI_LOG_NORMAL:
            cascade_energy_prior = (
                PRI_LOG_NORMAL,
                (
                    # scipy.stats.lognorm 3 paramters
                    0.96251341305506233, 0.4175592980195757, 17.543915051586644,
                    # hard limits
                    np.min(cascade_energy_lims), np.max(cascade_energy_lims)
                )
            )
        else:
            raise ValueError(str(cascade_energy_prior_name))

        track_energy_prior_name = reco_kw.pop('track_energy_prior')
        track_energy_lims = reco_kw.pop('track_energy_lims')
        if track_energy_prior_name == PRI_UNIFORM:
            track_energy_prior = (PRI_UNIFORM, (np.min(track_energy_lims), np.max(track_energy_lims)))
        elif track_energy_prior_name == PRI_LOG_UNIFORM:
            track_energy_prior = (PRI_LOG_UNIFORM, (np.min(track_energy_lims), np.max(track_energy_lims)))
        elif track_energy_prior_name == PRI_LOG_NORMAL:
            track_energy_prior = (
                PRI_LOG_NORMAL,
                (
                    # scipy.stats.lognorm 3 paramters
                    0.96251341305506233, 0.4175592980195757, 17.543915051586644,
                    # hard limits
                    np.min(track_energy_lims), np.max(track_energy_lims)
                )
            )
        else:
            raise ValueError(str(track_energy_prior_name))


        self.priors = OrderedDict()
        for param in hypo_params:
            if param == 'time': self.priors[param] = time_prior
            elif param == 'x': self.priors[param] = x_prior
            elif param == 'y': self.priors[param] = y_prior
            elif param == 'z': self.priors[param] = z_prior
            elif 'zenith' in param: self.priors[param] = (PRI_COSINE, (-1, 1))
            elif 'azimuth' in param: self.priors[param] = (PRI_UNIFORM, (0, TWO_PI))
            elif param == 'track_energy': self.priors[param] = track_energy_prior
            elif param == 'cascade_energy': self.priors[param] = cascade_energy_prior

    def run(self):
        for event_idx, event in self.events_iterator: # pylint: disable=unused-variable
            t1 = time.time()
            if 'mc_truth' in event:
                print(event['mc_truth'])
            llhp, _ = self.run_multinest(
                event_idx=event_idx,
                event=event,
                **reco_kw
            )
            dt = time.time() - t1
            n_points = llhp.size
            print('  ---> {:.3f} s, {:d} points ({:.3f} ms per LLH)'
                  .format(dt, n_points, dt / n_points * 1e3))

        print('Total script run time is {:.3f} s'.format(time.time() - t00))

    def run_multinest(
            self,
            outdir,
            event_idx,
            event,
            importance_sampling,
            max_modes,
            const_eff,
            n_live,
            evidence_tol,
            sampling_eff,
            max_iter,
            seed,
        ):
        """Setup and run MultiNest on an event.

        See the README file from MultiNest for greater detail on parameters
        specific to to MultiNest (parameters from `importance_sampling` on).

        Parameters
        ----------
        outdir
        event_idx
        event
        importance_sampling
        max_modes
        const_eff
        n_live
        evidence_tol
        sampling_eff
        max_iter
            Note that this limit is the maximum number of sample replacements and
            _not_ max number of likelihoods evaluated. A replacement only occurs
            when a likelihood is found that exceeds the minimum likelihood among
            the live points.
        seed

        Returns
        -------
        llhp : shape (num_llh,) structured array of dtype retro.LLHP_T
            LLH and the corresponding parameter values.

        mn_meta : OrderedDict
            Metadata used for running MultiNest, including priors, parameters, and
            the keyword args used to invoke the `pymultinest.run` function.

        """
        # pylint: disable=missing-docstring
        # Import pymultinest here; it's a less common dependency, so other
        # functions / constants in this module will still be import-able w/o it.
        import pymultinest

        hits = event['hits']
        hits_indexer = event['hits_indexer']
        hits_summary = event['hits_summary']

        hypo_params = self.hypo_handler.params

        priors_used = OrderedDict()

        prior_funcs = []
        for dim_num, dim_name in enumerate(hypo_params):
            prior_kind, prior_params = self.priors[dim_name]
            if prior_kind is PRI_UNIFORM:
                # Time is special since prior is relative to hits in the event
                if dim_name == T:
                    prior_params = (
                        hits_summary['earliest_hit_time'] + prior_params[0],
                        hits_summary['latest_hit_time'] + prior_params[1]
                    )
                priors_used[dim_name] = (prior_kind, prior_params)

                if prior_params == (0, 1):
                    continue
                    #def prior_func(cube): # pylint: disable=unused-argument
                    #    pass
                elif np.min(prior_params[0]) == 0:
                    maxval = np.max(prior_params)
                    def prior_func(cube, n=dim_num, maxval=maxval):
                        cube[n] = cube[n] * maxval
                else:
                    minval = np.min(prior_params)
                    width = np.max(prior_params) - minval
                    def prior_func(cube, n=dim_num, width=width, minval=minval):
                        cube[n] = cube[n] * width + minval

            elif prior_kind == PRI_LOG_UNIFORM:
                priors_used[dim_name] = (prior_kind, prior_params)
                log_min = np.log(np.min(prior_params))
                log_width = np.log(np.max(prior_params) / np.min(prior_params))
                def prior_func(cube, n=dim_num, log_width=log_width, log_min=log_min):
                    cube[n] = exp(cube[n] * log_width + log_min)

            elif prior_kind == PRI_COSINE:
                priors_used[dim_name] = (prior_kind, prior_params)
                cos_min = np.min(prior_params)
                cos_width = np.max(prior_params) - cos_min
                def prior_func(cube, n=dim_num, cos_width=cos_width, cos_min=cos_min):
                    cube[n] = acos(cube[n] * cos_width + cos_min)

            elif prior_kind == PRI_GAUSSIAN:
                priors_used[dim_name] = (prior_kind, prior_params)
                mean, stddev = prior_params
                norm = 1 / (stddev * np.sqrt(TWO_PI))
                def prior_func(cube, n=dim_num, norm=norm, mean=mean, stddev=stddev):
                    cube[n] = norm * exp(-((cube[n] - mean) / stddev)**2)

            elif prior_kind == PRI_LOG_NORMAL:
                priors_used[dim_name] = (prior_kind, prior_params)
                shape, loc, scale, low, high = prior_params
                lognorm = stats.lognorm(shape, loc, scale)
                def prior_func(cube, lognorm=lognorm, n=dim_num, low=low, high=high):
                    cube[n] = np.clip(lognorm.isf(cube[n]), a_min=low, a_max=high)

            elif prior_kind == PRI_SPEFIT2:
                spe_fit_val = event['recos']['SPEFit2'][dim_name]
                rel_loc, scale, low, high = prior_params
                loc = spe_fit_val + rel_loc
                cauchy = stats.cauchy(loc=loc, scale=scale)
                if dim_name == T:
                    low += hits_summary['time_window_start']
                    high += hits_summary['time_window_stop']
                priors_used[dim_name] = (PRI_CAUCHY, (loc, scale, low, high))
                def prior_func(cube, cauchy=cauchy, n=dim_num, low=low, high=high):
                    cube[n] = np.clip(cauchy.isf(cube[n]), a_min=low, a_max=high)

            else:
                raise NotImplementedError('Prior "{}" not implemented.'
                                          .format(prior_kind))

            prior_funcs.append(prior_func)

        param_values = []
        log_likelihoods = []
        t_start = []

        report_after = 1000

        def prior(cube, ndim, nparams): # pylint: disable=unused-argument
            """Function for pymultinest to translate the hypercube MultiNest uses
            (each value is in [0, 1]) into the dimensions of the parameter space.

            Note that the cube dimension names are defined in module variable
            `CUBE_DIMS` for reference elsewhere.

            """
            for prior_func in prior_funcs:
                prior_func(cube)

        get_llh = self.dom_tables._get_llh # pylint: disable=protected-access
        dom_info = self.dom_tables.dom_info
        tables = self.dom_tables.tables
        table_norm = self.dom_tables.table_norm
        t_indep_tables = self.dom_tables.t_indep_tables
        t_indep_table_norm = self.dom_tables.t_indep_table_norm
        sd_idx_table_indexer = self.dom_tables.sd_idx_table_indexer
        time_window = np.float32(
            hits_summary['time_window_stop'] - hits_summary['time_window_start']
        )
        # TODO: implement logic allowing for not all DOMs to be used
        #hit_sd_indices = np.array(
        #    sorted(dom_tables.use_sd_indices_set.union(hits_indexer['sd_idx'])),
        #    dtype=np.uint32
        #)
        hit_sd_indices = hits_indexer['sd_idx']
        unhit_sd_indices = np.array(
            sorted(ALL_STRS_DOMS_SET.difference(hit_sd_indices)),
            dtype=np.uint32
        )

        def loglike(cube, ndim, nparams): # pylint: disable=unused-argument
            """Function pymultinest calls to get llh values.

            Note that this is called _after_ `prior` has been called, so `cube`
            alsready contains the parameter values scaled to be in their physical
            ranges.

            """
            if not t_start:
                t_start.append(time.time())

            t0 = time.time()

            total_energy = cube[CUBE_ENERGY_IDX]
            track_fraction = cube[CUBE_TRACK_FRAC_IDX]

            hypo = dict(zip(hypo_params, cube))

            sources = hypo_handler.get_sources(hypo)
            pegleg_sources = hypo_handler.get_pegleg_sources(hypo)
            llh, pegleg_idx = get_llh(
                sources=sources,
                pegleg_sources=pegleg_sources,
                hits=hits,
                hits_indexer=hits_indexer,
                unhit_sd_indices=unhit_sd_indices,
                sd_idx_table_indexer=sd_idx_table_indexer,
                time_window=time_window,
                dom_info=dom_info,
                tables=tables,
                table_norm=table_norm,
                t_indep_tables=t_indep_tables,
                t_indep_table_norm=t_indep_table_norm,
            )

            t1 = time.time()

            param_values.append(cube)
            log_likelihoods.append(llh)

            n_calls = len(log_likelihoods)

            if n_calls % report_after == 0:
                t_now = time.time()
                best_idx = np.argmax(log_likelihoods)
                best_llh = log_likelihoods[best_idx]
                best_p = param_values[best_idx]
                print('')
                    msg = 'best llh = {:.3f} @ '.format(best_llh)
                    for key, val in zip(hypo_params, best_p):
                        msg += ' %s=%.1f'%(key, val)
                    print(msg)
                print('{} LLH computed'.format(n_calls))
                print('avg time per llh: {:.3f} ms'.format((t_now - t_start[0])/n_calls*1000))
                print('this llh took:    {:.3f} ms'.format((t1 - t0)*1000))
                print('')

            return llh

        n_dims = len(hypo_params)
        mn_kw = OrderedDict([
            ('n_dims', n_dims),
            ('n_params', n_dims),
            ('n_clustering_params', n_dims),
            ('wrapped_params', [int('azimuth' in p.lower()) for p in hypo_params]),
            ('importance_nested_sampling', importance_sampling),
            ('multimodal', max_modes > 1),
            ('const_efficiency_mode', const_eff),
            ('n_live_points', n_live),
            ('evidence_tolerance', evidence_tol),
            ('sampling_efficiency', sampling_eff),
            ('null_log_evidence', -1e90),
            ('max_modes', max_modes),
            ('mode_tolerance', -1e90),
            ('seed', seed),
            ('log_zero', -1e100),
            ('max_iter', max_iter),
        ])

        mn_meta = OrderedDict([
            ('params', hypo_params),
            ('original_prior_specs', self.priors),
            ('priors_used', priors_used),
            ('time_window', time_window),
            ('kwargs', sort_dict(mn_kw)),
        ])

        outdir = expand(outdir)
        mkdir(outdir)

        out_prefix = join(outdir, 'evt{}-'.format(event_idx))
        print('Output files prefix: "{}"\n'.format(out_prefix))

        print('Runing MultiNest...')
        t0 = time.time()
        pymultinest.run(
            LogLikelihood=loglike,
            Prior=prior,
            verbose=True,
            outputfiles_basename=out_prefix,
            resume=False,
            write_output=False,
            n_iter_before_update=5000,
            **mn_kw
        )
        t1 = time.time()

        llhp = np.empty(shape=len(param_values), dtype=LLHP_T)
        llhp['llh'] = log_likelihoods
        llhp[hypo_params] = param_values

        llhp_outf = out_prefix + 'llhp.npy'
        print('Saving llhp to "{}"...'.format(llhp_outf))
        np.save(llhp_outf, llhp)

        mn_meta['num_llhp'] = len(param_values)
        mn_meta['run_time'] = t1 - t0
        mn_meta_outf = out_prefix + 'multinest_meta.pkl'
        print('Saving MultiNest metadata to "{}"'.format(mn_meta_outf))
        pickle.dump(
            mn_meta,
            open(mn_meta_outf, 'wb'),
            protocol=pickle.HIGHEST_PROTOCOL
        )

        return llhp, mn_meta



def parse_args(description=__doc__):
    """Parse command-line arguments.

    Returns
    -------
    split_kwargs : dict of dicts
        Contains keys "dom_tables_kw", "hypo_kw", "events_kw", and "reco_kw",
        where values are kwargs dicts usable to instantiate or call each of the
        corresponding objects or functions.

    """
    parser = ArgumentParser(description=description)

    parser.add_argument(
        '--outdir', required=True
    )

    group = parser.add_argument_group(
        title='Hypothesis parameter priors',
    )

    group.add_argument(
        '--spatial-prior',
        choices='dc dc_subdust ic SPEFit2'.split(),
        required=True,
        help='''Choose a prior for choosing spatial samples. "dc", "dc_subdust"
        and "ic" are uniform priors with hard cut-offs at the extents of the
        respective volumes, while "SPEFit2" samples from Cauchy distributions
        around the SPEFit2 (x, y, z) best-fit values.'''
    )
    group.add_argument(
        '--temporal-prior',
        choices='uniform SPEFit2'.split(),
        required=True,
        help='''Choose a prior for choosing temporal samples. "uniform" chooses
        uniformly from 4000 ns prior to the first hit up to the last hit, while
        "SPEFit2" samples from a Cauchy distribution near (not *at* due to
        bias) the SPEFit2 time best-fit value.'''
    )
    group.add_argument(
        '--cascade_energy-prior',
        choices=[PRI_UNIFORM, PRI_LOG_UNIFORM, PRI_LOG_NORMAL],
        required=True,
        help='''Prior to put on _total_ event cascade_energy. Must specify
        --cascade_energy-lims.'''
    )
    group.add_argument(
        '--cascade_energy-lims', nargs='+',
        required=True,
        help='''Lower and upper cascade_energy limits, in GeV. E.g.: --cascade_energy-lims=1,100
        Required if --cascade_energy-prior is {}, {}, or {}'''
        .format(PRI_UNIFORM, PRI_LOG_UNIFORM, PRI_LOG_NORMAL)
    )

    group.add_argument(
        '--track_energy-prior',
        choices=[PRI_UNIFORM, PRI_LOG_UNIFORM, PRI_LOG_NORMAL],
        required=True,
        help='''Prior to put on _total_ event track_energy. Must specify
        --track_energy-lims.'''
    )
    group.add_argument(
        '--track_energy-lims', nargs='+',
        required=True,
        help='''Lower and upper track_energy limits, in GeV. E.g.: --track_energy-lims=1,100
        Required if --track_energy-prior is {}, {}, or {}'''
        .format(PRI_UNIFORM, PRI_LOG_UNIFORM, PRI_LOG_NORMAL)
    )

    group = parser.add_argument_group(
        title='MultiNest parameters',
    )

    group.add_argument(
        '--importance-sampling', action='store_true',
        help='''Importance nested sampling (INS) mode. Could be more efficient,
        but also can be unstable. Does not work with multimodal.'''
    )
    group.add_argument(
        '--max-modes', type=int, required=True,
        help='''Set to 1 to disable multi-modal search. Must be 1 if --importance-sampling is
        specified.'''
    )
    group.add_argument(
        '--const-eff', action='store_true',
        help='''Constant efficiency mode.'''
    )
    group.add_argument(
        '--n-live', type=int, required=True
    )
    group.add_argument(
        '--evidence-tol', type=float, required=True
    )
    group.add_argument(
        '--sampling-eff', type=float, required=True
    )
    group.add_argument(
        '--max-iter', type=int, required=True,
        help='''Note that iterations of the MultiNest algorithm are _not_ the
        number of likelihood evaluations. An iteration comes when one live
        point is discarded by finding a sample with higher likelihood than at
        least one other live point. Such a point can take many likelihood
        evaluatsions to find.'''
    )
    group.add_argument(
        '--seed', type=int, required=True,
        help='''Integer seed for MultiNest's random number generator.'''
    )

    split_kwargs = init_obj.parse_args(
        dom_tables=True, hypo=True, events=True, parser=parser
    )

    split_kwargs['reco_kw'] = reco_kw = split_kwargs.pop('other_kw')

    if reco_kw['cascade_energy_prior'] in [PRI_UNIFORM, PRI_LOG_UNIFORM, PRI_LOG_NORMAL]:
        assert reco_kw['cascade_energy_lims'] is not None
        elims = ''.join(reco_kw['cascade_energy_lims'])
        elims = [float(l) for l in elims.split(',')]
        reco_kw['cascade_energy_lims'] = elims
    elif reco_kw['cascade_energy_lims'] is not None:
        raise ValueError('--cascade_energy-limits not used with cascade_energy prior {}'
                         .format(reco_kw['cascade_energy_prior']))

    if reco_kw['track_energy_prior'] in [PRI_UNIFORM, PRI_LOG_UNIFORM, PRI_LOG_NORMAL]:
        assert reco_kw['track_energy_lims'] is not None
        elims = ''.join(reco_kw['track_energy_lims'])
        elims = [float(l) for l in elims.split(',')]
        reco_kw['track_energy_lims'] = elims
    elif reco_kw['track_energy_lims'] is not None:
        raise ValueError('--track_energy-limits not used with track_energy prior {}'
                         .format(reco_kw['track_energy_prior']))


    return split_kwargs


if __name__ == '__main__':
    my_reco = reco(**parse_args())
    my_reco.run()
