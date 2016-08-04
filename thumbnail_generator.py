#! /usr/bin/env python
# -*- coding: utf-8 -*

import os
import glob
import textwrap
import numpy as np
import matplotlib as mpl
import multiprocessing as mp
from skimage.external import tifffile as tif
from dphplotting import display_grid

# TODO: we could make a subclass of dict that would only contain
# keys. But when __getitem__ was called it would load the data
# associated with value. This way values would be available for
# gc once they've been used


def find_paths(home='.', key='SIM'):
    '''
    Utility function to return path names of folders
    whose name match key, starting at home
    '''
    # walk the directory starting a root
    for dirpath, dirnames, fnames in os.walk(home):
        # if SIM in the path then kill root and return directory
        if key in dirpath:
            dirnames.clear()
            yield dirpath


def load_data(dirname, key):
    '''
    Function to load all specified data matching glob into a dict
    and return the dict
    '''

    def better_imread(fname):
        '''
        Small utility to side step OME parsing error.
        '''
        with tif.TiffFile(fname) as mytif:
            return np.squeeze(np.array([page.asarray()
                                        for page in mytif.pages]))

    return {fname: better_imread(fname)
            for fname in glob.iglob(dirname + os.path.sep + key)
            if '.tif' in fname}


def clean_dirname(dirname, figsize):
    '''
    We only want the last two entries of dirname

    Filename and folder name

    and we want to clean those as well
    '''
    path = dirname.split(os.path.sep)
    fontsize = mpl.rcParams['font.size']
    # 1/120 = inches/(fontsize*character)
    num_chars = int(figsize / fontsize * 100)
    foldername = textwrap.fill(path[-2], num_chars)
    filename = textwrap.fill(path[-1], num_chars)
    return foldername + '\n' + filename


def gen_thumbs(dirname, key='/*/*decon.tif', where='host', level=2, figsize=6,
               redo=True, **kwargs):
    '''
    Main function to generate and save thumbnail pngs
    '''
    # load data
    data = load_data(dirname, key)
    if data:
        # can clean the dirnames here
        foldername = os.path.abspath(dirname).split(os.path.sep)[-level]
        if where == 'host':
            save_name = 'Thumbs ' + foldername + '.png'
        elif where == 'in folder':
            save_name = os.path.abspath(
                os.path.join(dirname, 'Thumbs ' + foldername + '.png'))
        else:
            save_name = os.path.abspath(
                os.path.join(where, 'Thumbs ' + foldername + '.png'))
        if not redo and os.path.exists(save_name):
            print(save_name, "already exists, skipping")
            return dirname + os.path.sep + key
        data = {clean_dirname(k, figsize): v for k, v in data.items()}
        fig, ax = display_grid(data, figsize=figsize, **kwargs)
        # make the layout 'tight'
        fig.tight_layout()
        # save the figure
        print('Saving', save_name, 'on', os.getpid(), '...')
        fig.savefig(save_name, bbox_inches='tight')
        print('finished saving', save_name)
    # mark data for gc
    del data
    return dirname + os.path.sep + key


def gen_all_thumbs(home=".", path_key='SIM', **kwargs):
    '''
    '''
    with mp.Pool() as pool:
        # spread jobs over processors.
        results = [pool.apply_async(
            gen_thumbs, args=(path,), kwds=kwargs
        ) for path in find_paths(home, path_key)]
        for pp in results:
            # workers take care of output so nothing needs to be saved
            pp.get()


if __name__ == '__main__':
    # This would be a good place to try out click
    import click

    @click.command()
    @click.option("--home", default=".",
                  help="Home folder to start the search")
    @click.option("--key", default="/*/*decon.tif",
                  help="Key to choose images")
    @click.option("--path_key", default="SIM",
                  help="Key to choose image folders")
    @click.option("--where", default="host", help=" ".join(
        ['Where do you want to save the',
         'images? Use "host" to save them in the home folder, use "in folder"',
         'to save them where the images are. Or you can pass a path.']
    ))
    @click.option("--level", default=2, help="Level at which to make title")
    @click.option("--figsize", default=6, help="Subimage size in inches")
    @click.option("--redo", is_flag=True, help="Redo existing images")
    @click.option("--cmap", default="inferno", help="MPL registered colormap")
    def update_kwds(home, key, path_key, where, level, figsize, redo, cmap):
        """A CLI to make thumbnail images of folders of images
        """
        default_kwds = {
            "home": home,
            "key": key,
            "path_key": path_key,
            "where": where,
            "level": level,
            "figsize": figsize,
            "redo": redo,
            "cmap": cmap
        }
        click.echo("{: >10} ---> {}".format("Option", "Value"))
        click.echo("+" * 25)
        for k, v in default_kwds.items():
            click.echo("{: >10} ---> {}".format(k, v))
        gen_all_thumbs(**default_kwds)

    update_kwds()
