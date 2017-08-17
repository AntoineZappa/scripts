#!/usr/bin/env python
# -*- coding: utf-8 -*-
# palm_utils.py
"""
Some utilities for PALM reconstruction.

Copyright (c) 2016, David Hoffman
"""

import numpy as np
import pandas as pd
from scipy.io import readsav
from numpy.core import atleast_1d, atleast_2d
from numba import njit


def peakselector_df(path, verbose=False):
    """Read a peakselector file into a pandas dataframe"""
    print("Reading {} into memory ... ".format(path))
    sav = readsav(path, verbose=verbose)
    df = pd.DataFrame(sav["cgroupparams"].byteswap().newbyteorder(),
                      columns=sav["rownames"].astype(str))
    return df


def grouped_peaks(df):
    """Return a DataFrame with only grouped peaks."""
    return df[df["Frame Index in Grp"] == 1]


class PALMData(object):
    """A simple class to manipulate peakselector data"""
    # columns we want to keep
    peak_col = {
        'X Position': "xpos",
        'Y Position': "ypos",
        '6 N Photons': "nphotons",
        'Frame Number': "framenum",
        'Sigma X Pos Full': "sigmax",
        'Sigma Y Pos Full': "sigmay",
        'Z Position': 'zpos',
        'Offset': 'offset',
        'Amplitude': 'amp'
    }

    group_col = {
        'Frame Number': 'framenum',
        'Group X Position': 'xpos',
        'Group Y Position': 'ypos',
        'Group Sigma X Pos': 'sigmax',
        'Group Sigma Y Pos': 'sigmay',
        'Group N Photons': 'nphotons',
        '24 Group Size': 'groupsize',
        'Group Z Position': 'zpos',
        'Offset': 'offset',
        'Amplitude': 'amp'
    }

    def __init__(self, path_to_sav, *args, verbose=True, init=False, **kwargs):
        """To initialize the experiment we need to know where the raw data is
        and where the peakselector processed data is
        
        Assumes paths_to_raw are properly sorted"""
            
        # load peakselector data
        raw_df = peakselector_df(path_to_sav, verbose=verbose)
        # convert Frame number to int
        self.processed = raw_df[list(self.peak_col.keys())]
        self.processed = self.processed.astype(float)
        self.grouped = grouped_peaks(raw_df)[list(self.group_col.keys())]
        # normalize column names
        self.processed = self.processed.rename(columns=self.peak_col)
        self.grouped = self.grouped.rename(columns=self.group_col)
        self.processed["framenum"] = self.processed["framenum"].astype(int)
        self.grouped["framenum"] = self.grouped["framenum"].astype(int)
        self.grouped["groupsize"] = self.grouped["groupsize"].astype(int)
        # initialize filtered ones
        self.processed_filtered = None
        self.grouped_filtered = None

    def filter_peaks(self, offset=1000, sigma_max=3, nphotons=0, groupsize=5000):
        """Filter internal dataframes"""
        for df_title in ("processed", "grouped"):
            df = self.__dict__[df_title]
            filter_series = (
                (df.offset > 0) & # we know that offset should be around this value.
                (df.offset < offset) &
                (df.sigmax < sigma_max) &
                (df.sigmay < sigma_max) &
                (df.nphotons > nphotons)
            )
            if "groupsize" in df.keys():
                filter_series &= df.groupsize < groupsize
            self.__dict__[df_title + "_filtered"] = df[filter_series]

    def hist(self, data_type="grouped", filtered=False):
        if data_type == "grouped":
            if filtered:
                df = self.grouped_filtered
            else:
                df = self.grouped
        elif data_type == "processed":
            if filtered:
                df = self.processed_filtered
            else:
                df = self.processed
        else:
            raise TypeError("Data type {} is of unknown type".format(data_type))
        return df[['offset', 'amp', 'xpos', 'ypos', 'nphotons',
            'sigmax', 'sigmay', 'zpos']].hist(bins=128, figsize=(12, 12), log=True)


@njit
def jit_hist3d(zpositions, ypositions, xpositions, shape):
    """Generate a histogram of points in 3D

    Parameters
    ----------

    Returns
    -------
    res : ndarray
    """
    nz, ny, nx = shape
    res = np.zeros(shape, np.uint32)
    # need to add ability for arbitraty accumulation
    for z, y, x in zip(zpositions, ypositions, xpositions):
        # bounds check
        if x < nx and y < ny and z < nz:
            res[z, y, x] += 1
    return res


@njit
def jit_hist3d_with_weights(zpositions, ypositions, xpositions, weights,
                            shape):
    """Generate a histogram of points in 3D

    Parameters
    ----------

    Returns
    -------
    res : ndarray
    """
    nz, ny, nx = shape
    res = np.zeros(shape, weights.dtype)
    # need to add ability for arbitraty accumulation
    for z, y, x, w in zip(zpositions, ypositions, xpositions, weights):
        # bounds check
        if x < nx and y < ny and z < nz:
            res[z, y, x] += w
    return res


def fast_hist3d(sample, bins, myrange=None, weights=None):
    """Modified from numpy histogramdd
    Make a 3d histogram, fast, lower memory footprint"""
    try:
        # Sample is an ND-array.
        N, D = sample.shape
    except (AttributeError, ValueError):
        # Sample is a sequence of 1D arrays.
        sample = atleast_2d(sample).T
        N, D = sample.shape

    nbin = np.empty(D, int)
    edges = D * [None]
    dedges = D * [None]

    try:
        M = len(bins)
        if M != D:
            raise ValueError(
                'The dimension of bins must be equal to the dimension of the'
                ' sample x.')
    except TypeError:
        # bins is an integer
        bins = D * [bins]

    # Select range for each dimension
    # Used only if number of bins is given.
    if myrange is None:
        # Handle empty input. Range can't be determined in that case, use 0-1.
        if N == 0:
            smin = np.zeros(D)
            smax = np.ones(D)
        else:
            smin = atleast_1d(np.array(sample.min(0), float))
            smax = atleast_1d(np.array(sample.max(0), float))
    else:
        if not np.all(np.isfinite(myrange)):
            raise ValueError(
                'myrange parameter must be finite.')
        smin = np.zeros(D)
        smax = np.zeros(D)
        for i in range(D):
            smin[i], smax[i] = myrange[i]

    # Make sure the bins have a finite width.
    for i in range(len(smin)):
        if smin[i] == smax[i]:
            smin[i] = smin[i] - .5
            smax[i] = smax[i] + .5

    # avoid rounding issues for comparisons when dealing with inexact types
    if np.issubdtype(sample.dtype, np.inexact):
        edge_dt = sample.dtype
    else:
        edge_dt = float
    # Create edge arrays
    for i in range(D):
        if np.isscalar(bins[i]):
            if bins[i] < 1:
                raise ValueError(
                    "Element at index %s in `bins` should be a positive "
                    "integer." % i)
            nbin[i] = bins[i] + 2  # +2 for outlier bins
            edges[i] = np.linspace(smin[i], smax[i], nbin[i] - 1, dtype=edge_dt)
        else:
            edges[i] = np.asarray(bins[i], edge_dt)
            nbin[i] = len(edges[i]) + 1  # +1 for outlier bins
        dedges[i] = np.diff(edges[i]).min()
        if np.any(np.asarray(dedges[i]) <= 0):
            raise ValueError(
                "Found bin edge of size <= 0. Did you specify `bins` with"
                "non-monotonic sequence?")

    nbin = np.asarray(nbin)

    # Handle empty input.
    if N == 0:
        return np.zeros(nbin - 2), edges

    # Compute the bin number each sample falls into.
    # np.digitize returns an int64 array when it only needs to be uint32
    Ncount = [np.digitize(sample[:, i], edges[i]).astype(np.uint32) for i in range(D)]
    shape = tuple(len(edges[i]) - 1 for i in range(D))  # -1 for outliers

    # Using digitize, values that fall on an edge are put in the right bin.
    # For the rightmost bin, we want values equal to the right edge to be
    # counted in the last bin, and not as an outlier.
    for i in range(D):
        # Rounding precision
        mindiff = dedges[i]
        if not np.isinf(mindiff):
            decimal = int(-np.log10(mindiff)) + 6
            # Find which points are on the rightmost edge.
            not_smaller_than_edge = (sample[:, i] >= edges[i][-1])
            on_edge = (np.around(sample[:, i], decimal) ==
                       np.around(edges[i][-1], decimal))
            # Shift these points one bin to the left.
            Ncount[i][np.where(on_edge & not_smaller_than_edge)[0]] -= 1

    # Flattened histogram matrix (1D)
    # Reshape is used so that overlarge arrays
    # will raise an error.
    # hist = zeros(nbin, float).reshape(-1)

    # # Compute the sample indices in the flattened histogram matrix.
    # ni = nbin.argsort()
    # xy = zeros(N, int)
    # for i in arange(0, D-1):
    #     xy += Ncount[ni[i]] * nbin[ni[i+1:]].prod()
    # xy += Ncount[ni[-1]]

    # # Compute the number of repetitions in xy and assign it to the
    # # flattened histmat.
    # if len(xy) == 0:
    #     return zeros(nbin-2, int), edges

    # flatcount = bincount(xy, weights)
    # a = arange(len(flatcount))
    # hist[a] = flatcount

    # # Shape into a proper matrix
    # hist = hist.reshape(sort(nbin))
    # for i in arange(nbin.size):
    #     j = ni.argsort()[i]
    #     hist = hist.swapaxes(i, j)
    #     ni[i], ni[j] = ni[j], ni[i]

    # # Remove outliers (indices 0 and -1 for each dimension).
    # core = D*[slice(1, -1)]
    # hist = hist[core]

    # # Normalize if normed is True
    # if normed:
    #     s = hist.sum()
    #     for i in arange(D):
    #         shape = ones(D, int)
    #         shape[i] = nbin[i] - 2
    #         hist = hist / dedges[i].reshape(shape)
    #     hist /= s

    # if (hist.shape != nbin - 2).any():
    #     raise RuntimeError(
    #         "Internal Shape Error")
    # for n in Ncount:
    #     print(n.shape)
    #     print(n.dtype)
    if weights is not None:
        weights = np.asarray(weights)
        hist = jit_hist3d_with_weights(*Ncount, weights=weights, shape=shape)
    else:
        hist = jit_hist3d(*Ncount, shape=shape)
    return hist, edges


class QuickPALM():
    pass
    """
    # This class will be designed to use PeakFinder and dask delayed to do a quickpalm analysis

    def pf_func(data):
    ...:     pf = PeakFinder(data, 1.3, "mode")
    ...:     pf.thresh=10
    ...:     pf.find_blobs()
    ...:     return pf.fit_blobs(8, quiet=True)

    Probably better to use explicit multiprocessing with Pool and apply_async
    than use dask, but using dask might allow for easier transfer to distributed
    computing
    
    pfs = dask.delayed([dask.delayed(pf_func)(x) for x in data])
    junk = pfs.compute(get=dask.multiprocessing.get, num_workers=48)
    """