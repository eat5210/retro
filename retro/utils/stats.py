# -*- coding: utf-8 -*-
# pylint: disable=wrong-import-position, invalid-name

"""
Statistics
"""

from __future__ import absolute_import, division, print_function

__all__ = [
    'poisson_llh',
    'partial_poisson_llh',
    'weighted_average',
    'estimate_from_llhp',
]

__author__ = 'P. Eller, J.L. Lanfranchi'
__license__ = '''Copyright 2017 Philipp Eller and Justin L. Lanfranchi

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.'''

from copy import copy
from os.path import abspath, dirname
import sys

import numpy as np
from scipy.special import gammaln
from scipy import stats
import xarray as xr

if __name__ == '__main__' and __package__ is None:
    RETRO_DIR = dirname(dirname(dirname(abspath(__file__))))
    if RETRO_DIR not in sys.path:
        sys.path.append(RETRO_DIR)
import retro
from retro.utils.misc import sort_dict

DELTA_LLH_CUTOFF = 15.5
"""What values of the llhp space to include relative to the max-LLH point"""

def poisson_llh(expected, observed):
    r"""Compute the log Poisson likelihood.

    .. math::
        observed \times \log expected - expected \log \Gamma(observed)

    Parameters
    ----------
    expected
        Expected value(s)

    observed
        Observed value(s)

    Returns
    -------
    llh
        Log likelihood(s)

    """
    llh = observed * np.log(expected) - expected - gammaln(observed + 1)
    return llh


def partial_poisson_llh(expected, observed):
    r"""Compute the log Poisson likelihood _excluding_ subtracting off
    expected. This part, which constitutes an expected-but-not-observed
    penalty, is intended to be taken care of outside this function.

    .. math::
        {\rm observed} \cdot \log {\rm expected} - \log \Gamma({\rm observed})

    Parameters
    ----------
    expected
        Expected value(s)

    observed
        Observed value(s)

    Returns
    -------
    llh
        Log likelihood(s)

    """
    llh = observed * np.log(expected) - expected - gammaln(observed)
    return llh


@retro.numba_jit(**retro.DFLT_NUMBA_JIT_KWARGS)
def weighted_average(x, w):
    """Average of elements in `x` weighted by `w`.

    Parameters
    ----------
    x : numpy.ndarray
        Values to average

    w : numpy.ndarray
        Weights, same shape as `x`

    Returns
    -------
    avg : numpy.ndarray
        Weighted average, same shape as `x`

    """
    sum_xw = 0.0
    sum_w = 0.0
    for x_i, w_i in zip(x, w):
        sum_xw += x_i * w_i
        sum_w += w_i
    return sum_xw / sum_w


def weighted_percentile(data, percentile, weights=None):
    """

    Parameters
    ----------
    data : array
    percentile : scalar in [0, 100]
    weights
        Frequency (count) of data

    Returns
    -------
    wtd_pct : scalar

    """
    percentile = np.asarray(percentile)
    if weights is None:
        return np.percentile(data, percentile)
    ind = np.argsort(data)
    sorted_data = data[ind]
    sorted_weights = weights[ind]
    # Samples from unnormed cdf via cumulative sum of sorted samples of pdf
    cdf_samples = sorted_weights.cumsum()
    tot = cdf_samples[-1]
    return np.interp(
        percentile/100 * tot,
        cdf_samples,  # "x" coords come from unnormed CDF
        sorted_data,  # "y" coords come from data values
    )


def estimate_from_llhp(
    llhp,
    treat_dims_independently,
    use_prob_weights,
    priors_used=None,
):
    """Evaluate estimate for reconstruction quantities given the MultiNest
    points of LLH space exploration. .

    Paranters
    ---------
    llhp : shape (num_llh,) array of custom dtype llhp_t
        Fields of the structured array must contain 'llh' and any reconstructed
        quantities (aka parameters or dimensions)

    treat_dims_independently : boolean
        treat each dimension individually (not yet sure how much sense that
        makes)

    use_prob_weights : boolean
        use LLH weights in computing estimates

    priors_used : dict, optional
        Specify the priors used to remove their effects on the posterior LLH
        distributions; if not specified, effects of priors will not be removed

    Returns
    -------
    estimate : xarray
        Dims are "kind" (coords "max", "mean", "median", "lower_bound", and
        "upper_bound") and "param" (one coord per parameter).
        "lower_bound" and "upper_bound" come from the `percentile` bounds.

    """
    # currently spherical averages are not supported if dimensions are treated
    # independently (how would this even work?)
    averages_spherically_aware = not treat_dims_independently
    remove_priors = bool(priors_used)

    names = list(llhp.dtype.names)
    for name in ('llh', 'track_energy', 'cascade_energy'):
        if name not in names:
            raise ValueError(
                '"{}" not a field in `llhp.dtype.names` = {}'
                .format(name, names)
            )

    params = copy(names)
    params.remove('llh')

    num_params = len(params)
    num_llh = len(llhp)

    # cut away extremely low llh (30 or more below max llh)
    max_llh = np.nanmax(llhp['llh'])
    llhp = llhp[llhp['llh'] >= max_llh - 30]
    if len(llhp) == 0:
        raise ValueError('no points')
    llh = llhp['llh']

    if use_prob_weights:
        # weight points by their likelihood (_not_ log likelihood) relative to
        # max; keep prob_weights around for later use
        prob_weights = np.exp(llh - max_llh)
        weights = copy(prob_weights)
    else:
        prob_weights = None
        weights = np.ones(shape=len(llh))

    if treat_dims_independently:
        weights = {d: copy(weights) for d in priors_used.keys()}

    if remove_priors:
        # calculate the prior weights from the priors used
        for dim, (prior_kind, prior_params) in priors_used.items():
            if prior_kind == 'uniform':
                w = None
            elif prior_kind in ('cauchy', 'spefit2'):
                w = 1 / stats.cauchy.pdf(llhp[dim], *prior_params[:2])
            elif prior_kind == 'log_normal' and dim == 'energy':
                w = 1 / stats.lognorm.pdf(
                    llhp['track_energy'] + llhp['cascade_energy'],
                    *prior_params[:3]
                )
            elif prior_kind == 'log_uniform' and dim == 'energy':
                w = llhp['track_energy'] + llhp['cascade_energy']
            elif prior_kind == 'log_uniform' and dim == 'cascade_energy':
                w = llhp['cascade_energy']
            elif prior_kind == 'log_uniform' and dim == 'track_energy':
                w = llhp['track_energy']
            elif prior_kind == 'cosine':
                w = None
            elif prior_kind == 'log_normal' and dim == 'cascade_d_zenith':
                w = None
            else:
                raise NotImplementedError(
                    'Prior %s for dimension %s unknown' % (prior_kind, dim)
                )

            if w is not None:
                if treat_dims_independently:
                    weights[dim] *= w
                else:
                    weights *= w

        if treat_dims_independently:
            if 'energy' in weights:
                w = prob_weights if use_prob_weights else 1
                weights['track_energy'] = w * (
                    llhp['track_energy']
                    / (llhp['track_energy'] + llhp['cascade_energy'])
                    * weights['energy']
                )
                weights['cascade_energy'] = w * (
                    llhp['cascade_energy']
                    / (llhp['track_energy'] + llhp['cascade_energy'])
                    * weights['energy']
                )

    if treat_dims_independently:
        postproc_llh = {}
        for dim, weights in weights.items():
            if use_prob_weights or remove_priors:
                postproc_llh[dim] = np.log(weights)
            else:
                postproc_llh[dim] = llh
        # simply report `max_llh` for `max_postproc_llh` since each dimension
        # will have a different max since each gets weighted independently
        max_postproc_llh = max_llh
    else:
        postproc_llh = max_llh + np.log(weights)
        max_idx = np.nanargmax(postproc_llh)
        max_postproc_llh = postproc_llh[max_idx]
        params_at_max_llh = llhp[max_idx]
        cut = postproc_llh > max_postproc_llh - DELTA_LLH_CUTOFF
        cut_llhp = llhp[cut]
        cut_postproc_llh = postproc_llh[cut]

    # -- Construct xarray.DataArray for storing estimates & metadata -- #

    # Note that xarray requires list for `coords` (e.g. tuple fails)
    est_kinds = ['max', 'mean', 'median', 'lower_bound', 'upper_bound']

    estimate = xr.DataArray(
        data=np.full(
            fill_value=np.nan,
            shape=(len(est_kinds), num_params),
            dtype=np.float32,
        ),
        dims=('kind', 'param'),
        coords=dict(kind=est_kinds, param=params),
        attrs=sort_dict(dict(
            estimation_settings=sort_dict(dict(
                treat_dims_independently=treat_dims_independently,
                use_prob_weights=use_prob_weights,
                remove_priors=remove_priors,
                averages_spherically_aware=averages_spherically_aware,
            )),
            num_llh=num_llh,
            max_llh=max_llh,
            max_postproc_llh=max_postproc_llh,
        ))
    )

    # -- Calculate each kind of estimate for each param -- #

    percentiles = np.array([13.35, 86.65])

    for param in params:
        if treat_dims_independently:
            this_postproc_llh = postproc_llh[param]
            max_idx = np.nanargmax(this_postproc_llh)
            max_postproc_llh = this_postproc_llh[max_idx]
            param_vals = llhp[param]
            param_at_max_llh = param_vals[max_idx]
            cut = this_postproc_llh > max_postproc_llh - DELTA_LLH_CUTOFF
            this_postproc_llh = this_postproc_llh[cut]
            param_vals = param_vals[cut]
        else:
            param_at_max_llh = params_at_max_llh[param]
            this_postproc_llh = cut_postproc_llh
            param_vals = cut_llhp[param]

        estimate.loc[dict(kind='max', param=param)] = param_at_max_llh

        if 'azimuth' in param:
            # azimuth is a cyclic function, so need some special treatment to
            # get correct mean: shift everything such that the best-fit point is
            # in the middle (pi)
            shift = param_at_max_llh
            shifted_vals = (param_vals - shift + np.pi) % (2*np.pi)

            mean = (stats.circmean(shifted_vals) + shift - np.pi) % (2*np.pi)
            median = (np.median(shifted_vals) + shift - np.pi) % (2*np.pi)
            lower_bound, upper_bound = (
                weighted_percentile(
                    data=shifted_vals,
                    percentile=percentiles,
                    weights=this_postproc_llh,
                )
                + shift - np.pi
            ) % (2*np.pi)
        else:
            mean = np.mean(param_vals)
            median = np.median(param_vals)
            lower_bound, upper_bound = weighted_percentile(
                data=param_vals,
                percentile=percentiles,
                weights=this_postproc_llh,
            )

        estimate.loc[dict(kind='mean', param=param)] = mean
        estimate.loc[dict(kind='median', param=param)] = median
        estimate.loc[dict(kind='lower_bound', param=param)] = lower_bound
        estimate.loc[dict(kind='upper_bound', param=param)] = upper_bound

    if not averages_spherically_aware:
        return estimate

    # Idea: calculate the medians on the sphere for az and zen combined
    #
    # currently the below duplicates work done above but aware of spherical
    # coords, but just allowing this inefficiency for now since we're still
    # testing what's best
    for angle in ['', 'track_', 'cascade_']:
        zen_name = angle + 'zenith'
        az_name = angle + 'azimuth'

        if not (zen_name in params and az_name in params):
            continue

        az = cut_llhp[az_name]
        zen = cut_llhp[zen_name]

        # calculate the average of Cartesian coords
        # first need to create (x,y,z) array
        cart = np.empty(shape=(3, len(cut_llhp)))
        cart[0, :] = np.cos(az) * np.sin(zen)
        cart[1, :] = np.sin(az) * np.sin(zen)
        cart[2, :] = np.cos(zen)

        if use_prob_weights or remove_priors:
            cart_mean = np.average(cart, axis=1, weights=cut_postproc_llh)
        else:
            cart_mean = np.average(cart, axis=1)

        # normalize if r > 0
        r = np.sqrt(np.sum(np.square(cart_mean)))
        if r == 0:
            estimate.loc[dict(kind='mean', param=zen_name)] = 0
            estimate.loc[dict(kind='mean', param=az_name)] = 0
        else:
            estimate.loc[dict(kind='mean', param=zen_name)] = (
                np.arccos(cart_mean[2] / r)
            )
            estimate.loc[dict(kind='mean', param=az_name)] = np.arctan2(
                cart_mean[1], cart_mean[0]
            ) % (2 * np.pi)

    return estimate
