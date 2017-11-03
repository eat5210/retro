# coding: utf-8
# pylint: disable=wrong-import-position

"""
Generate single-DOM Retro tables binned in (t,r,theta).
"""


from __future__ import absolute_import, division, print_function

import numpy as np

import numba


__all__ = ['generate_t_r_theta_table']


@numba.jit(nopython=True, nogil=True, cache=True)
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


@numba.jit(nopython=True, nogil=True, cache=True)
def generate_t_r_theta_table(data, n_photons, p_theta_centers,
                             p_delta_phi_centers, theta_bin_edges):
    """Transform information from a raw single-DOM table (as output from CLSim)
    into a more compact representation, with probability and average direction
    (theta and phi) binned in (t, r, theta).

    Parameters
    ----------
    data
    n_photons
    p_theta_centers
    p_delta_phi_centers
    theta_bin_edges

    Returns
    -------
    n_photons
    average_thetas
    average_phis
    lengths

    """
    # Source tables are photon counts binned in
    # (r, theta, t, dir_theta, dir_phi)
    n_r_bins = n_photons.shape[0]
    n_theta_bins = n_photons.shape[1]
    n_t_bins = n_photons.shape[2]

    # Destination tables are to be binned in (t, r, costheta) (there are as
    # many costheta bins as theta bins in the original tables)
    dest_shape = (n_t_bins, n_r_bins, n_theta_bins)

    n_photons = np.empty(dest_shape, dtype=np.float32)
    average_thetas = np.empty(dest_shape, dtype=np.float32)
    average_phis = np.empty(dest_shape, dtype=np.float32)
    lengths = np.empty(dest_shape, dtype=np.float32)

    for r_i in range(n_r_bins):
        for theta_j in range(n_theta_bins):
            for t_k in range(n_t_bins):
                # flip coszen?
                weights = data[r_i, theta_j, t_k, ::-1, :].astype(np.float64)
                weights_tot = weights.sum()
                if weights_tot == 0:
                    # If no photons, just set the average direction to the
                    # theta of the bin center...
                    average_theta = 0.5 * (theta_bin_edges[theta_j]
                                           + theta_bin_edges[theta_j + 1])
                    # ... and lengths to 0
                    length = 0.0
                    average_phi = 0.0
                else:
                    # Average theta
                    weights_theta = weights.sum(axis=1)
                    average_theta = weighted_average(p_theta_centers,
                                                     weights_theta)

                    # Average delta phi
                    projected_n_photons = (
                        (weights.T * np.sin(p_theta_centers)).T
                    )
                    weights_phi = projected_n_photons.sum(axis=0)
                    average_phi = weighted_average(p_delta_phi_centers,
                                                   weights_phi)

                    # Length of vector (using projections from all vectors
                    # onto average vector cos(angle) between average vector
                    # and all angles)
                    coscos = np.cos(p_theta_centers)*np.cos(average_theta)
                    sinsin = np.sin(p_theta_centers)*np.sin(average_theta)
                    cosphi = np.cos(p_delta_phi_centers - average_phi)
                    # Other half of sphere
                    cospsi = (coscos + np.outer(sinsin, cosphi).T).T
                    cospsi_avg = (cospsi * weights).sum() / weights_tot
                    length = max(0.0, 2 * (cospsi_avg - 0.5))

                # Output tables are expected to be in (flip(t), r, costheta).
                # In addition to time being flipped, coszen is expected to be
                # ascending, and therefore its binning is also flipped as
                # compared to the theta binning in the original.
                # NEW >>>>
                dest_bin = (
                    n_t_bins - 1 - t_k,
                    r_i,
                    n_theta_bins - 1 - theta_j
                )

                n_photons[dest_bin] = n_photons[r_i, theta_j, t_k]
                average_thetas[dest_bin] = average_theta
                average_phis[dest_bin] = average_phi
                lengths[dest_bin] = length
                # NEW <<<<

    return n_photons, average_thetas, average_phis, lengths
