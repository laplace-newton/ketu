#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import division, print_function

import os
import json
import gzip
import time
import fitsio
import numpy as np
import cPickle
from scipy.stats import beta
from IPython.parallel import Client, require

import turnstile


def setup_pipeline(cache=False):
    pipe = turnstile.Download(cache=cache)
    pipe = turnstile.Inject(pipe, cache=cache)
    pipe = turnstile.Prepare(pipe, cache=cache)
    pipe = turnstile.GPLikelihood(pipe, cache=cache)
    pipe = turnstile.Hypotheses(pipe, cache=cache)
    pipe = turnstile.Search(pipe, cache=cache)
    return pipe


def load_stars():
    fn = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "42k.fits.gz")
    return fitsio.read(fn)


def generate_system(K, mstar=1.0, rstar=1.0):
    labels = ["period", "t0", "radius", "b", "e", "pomega", "q1", "q2"]

    periods = np.exp(np.random.uniform(np.log(50), np.log(450), K))
    t0s = np.array([np.random.uniform(0, p) for p in periods])
    radii = np.random.uniform(0.005, 0.04, K)
    b = np.random.uniform(0, 1, K)
    e = beta.rvs(0.867, 3.03, size=K)
    pomega = np.random.uniform(0, 2*np.pi, K)
    q1 = np.random.uniform(0, 1)
    q2 = np.random.uniform(0, 1)

    return dict(q1=q1, q2=q2, mstar=mstar, rstar=rstar,
                injections=[dict(zip(labels, _))
                            for _ in zip(periods, t0s, radii, b, e, pomega)])


@require(os, json, cPickle, gzip)
def run_query(args):
    # Parse the input arguments.
    pipe, q = args

    # Set up the directory for the output.
    dirname = "{0}/{1}".format(q["kicid"], pipe.get_key(**q))
    try:
        os.makedirs(dirname)
    except os.error:
        pass

    # Save the query parameters.
    with open(os.path.join(dirname, "query.json"), "w") as f:
        json.dump(q, f, indent=2, sort_keys=True)

    # Run the query.
    results = pipe.query(**q)

    # Save the output.
    fn = os.path.join(dirname, "results.pkl.gz")
    with gzip.open(fn, "wb") as f:
        cPickle.dump(results, f, -1)

    return fn


def main(N, profile_dir=None):
    # Choose some search parameters. There be a lot of MAGIC here.
    duration, depths = 0.3, [0.005**2, 0.01**2, 0.02**2]
    pmin, pmax = 100, 400
    periods = np.exp(np.arange(np.log(pmin), np.log(pmax),
                               0.3*duration/(4.1*365.)))
    base_query = dict(
        durations=duration, depths=depths,
        periods=periods.tolist(), dt=0.2 * duration,
        time_spacing=0.05,
    )

    # Load the stellar dataset.
    stars = load_stars()

    # Set up the pipeline.
    pipe = setup_pipeline()

    # Generate N queries for the pipeline with injections in each one.
    queries = []
    for i in np.random.randint(len(stars), size=N):
        q = generate_system(np.random.poisson(7),
                            mstar=stars[i]["mstar"],
                            rstar=stars[i]["rstar"])
        q["kicid"] = stars[i]["kic"]
        queries.append((pipe, dict(base_query, **q)))

    # Set up the interface to the cluster.
    c = Client(profile_dir=profile_dir)
    pool = c[:]
    results = pool.map(run_query, queries)
    return [r for r in results]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("N", type=int,
                        help="the number of simulations to run "
                             "(per iteration)")
    parser.add_argument("-i", "--iterations", default=1, type=int,
                        help="the number of iterations to run")
    parser.add_argument("-p", "--profile-dir", default=None,
                        help="the IPython profile dir")
    parser.add_argument("-s", "--seed", default=None, type=int,
                        help="the random number seed")
    args = parser.parse_args()

    if args.seed is not None:
        np.random.seed(args.seed)

    for i in range(args.iterations):
        strt = time.time()
        main(args.N, profile_dir=args.profile_dir)
        print("Iteration {0} took {1:.2f}s".format(i+1, time.time()-strt))
