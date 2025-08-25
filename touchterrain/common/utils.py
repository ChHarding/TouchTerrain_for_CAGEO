'''Utilities for touchterrain'''

import numpy
import imageio
import scipy.stats as stats
from scipy import ndimage  
from scipy.ndimage import binary_dilation, generic_filter
import os.path
import k3d
import random
from glob import glob
import zipfile
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.colors as mcolors
from matplotlib.colors import ListedColormap
np = numpy

from touchterrain.common.calculate_ticks import calculate_ticks # calculate nice ticks for elevation visualization
# Utility to save tile as binary png image
def save_tile_as_image(tile, name):
    tile_elev_raster_mask = ~numpy.isnan(tile) * 255
    imageio.imsave(name + '.png', tile_elev_raster_mask.astype(numpy.uint8))


def clean_up_diags(ras):
    '''clean up diagonal cells as these lead to non-manifold vertices where they meet
    These are defined as either  0 1   or   1 0  where 0 == NaN and 1 == non-NaN)
                                 1 0        0 1

    The operation uses a  binary hit & miss operation to identify these patterns and
    subtraction to removed one of the two. Then the mask is flipped to catch the other pattern

    This is repeated until no new changes occur any more.

    returns changed ras

    Example of mask data:
    mask = np.array([[0, 0, 1, 0],
                     [0, 1, 0, 1,],
                     [0, 1, 1, 1,],
                     [1, 0, 0, 1,],
                     [0, 1, 1, 0,]])

    '''
    # If there are NaNs in the raster there cannot by any diagonal patterns, so we're done!
    if not numpy.any(numpy.isnan(ras)):
        return ras

    cnt = 0
    #save_tile_as_image(ras, "before")
    while True:

        print("Diagonal pattern cleanup, round: ", cnt)
        # make a (inverse) mask raster (where 1 == NaN and 0 == non-NaN) (initially a bool raster)
        # invert it, and cast to int. This is a binary mask that we'll query for diagonal patterns and
        # modify accordingly (turn half the pattern from 1 to 0)
        mask = numpy.invert(numpy.isnan(ras)).astype(numpy.int8) # int8 is the cheapest possible int in numpy

        # how many 0s and 1s do we have before the potential cleanup?
        unique_pre, counts_pre = numpy.unique(mask, return_counts=True)
        pre = dict(zip(unique_pre, counts_pre))
        print("pre-cleanup masks stats: ", pre)

        # if the dictionary has only 1 key, we're done as there are either no NaNs or only NaNs
        if len(pre) == 1:
            print("only one type of cell in raster, no cleanup needed")
            return ras

        p = numpy.array([[1, 0],
                         [0, 1]]) # pattern to detect with hit-or-miss

        #print(mask, "input raster")
        hm = ndimage.binary_hit_or_miss(mask, structure1=p, origin1=-1).astype(numpy.int8) # shift origin to upper left corner
        # hm will have 1s where the upper-left 1 of the first pattern are

        #print(hm, "hit or miss with\n", p)
        mask = mask - hm # subtract hit-or-miss results to change the location of upper left pattern cell from in the mask 1 to 0
        #print(mask, "raster after 1. subtraction")

        # flip the mask vertically to catch the inverse of the pattern p and again set its upper-left 1 to 0
        mask = numpy.flip(mask, axis=1) #  flip
        #print(mask, "raster flipped before 2. subtraction")
        hm = ndimage.binary_hit_or_miss(mask, structure1=p, origin1=-1).astype(numpy.int8) # shift origin to upper left corner
        #print(hm, "hit or miss with")
        #print(p)
        mask = mask - hm
        #print(mask, "raster flipped after 2. subtraction")
        mask = numpy.flip(mask, axis=1) #  flip back
        #print(mask, "final raster")

        # how many 0s and 1s do we have after the cleanup?
        unique_post, counts_post = numpy.unique(mask, return_counts=True)
        post = dict(zip(unique_post, counts_post))
        print("post-cleanup masks stats:", post)

        # convert 0 to NaN so we can use the 0s in the mask to create NaN cells in the DEM raster
        mask = numpy.where(mask == 0, numpy.nan, 1)
        #print(mask, "after 0 => NaN")

        # multiply mask with original DEM raster
        ras = ras * mask

        # if there was not change, we're done, otherwise, run another round.
        if (pre[0] == post[0]) and (pre[1] == post[1]):
            #save_tile_as_image(ras, "after")
            return ras

        cnt += 1 # next round



def fillHoles(raster, num_iters=-1,  num_neighbors=7, NaN_are_holes=False):
    """Fills holes in a raster by replacing neagtive elevation values with the average elevation of its neighbors.
    If NaN_are_holes is set to True, NaN values will be filled instead of negative values. Does not fill holes on the edges of the raster.
     
    Args:
        raster (ndarray): The input raster array.
        num_iters (int, optional): The number of iterations to perform. Defaults to -1, which means iterate until no more holes are filled.
        num_neighbors (int, optional): The threshold for the number of neighbors with >= 0 elevation values to consider a hole. Must be in the range [1, 9]. Defaults to 7.
    Returns:
        ndarray: The raster array with holes filled.
    Raises:
        None
    Example:
        >>> raster = np.array([[3, 3, 3],
        ...                    [1,-1, 3],
        ...                    [1, 1, 1]])
        >>> filled_raster = fillHoles(raster)

           [[3, 3, 3],
            [1, 2, 3],
            [1, 1, 1]]
     
    """
    if num_neighbors < 0 or num_neighbors > 9:
        print("fill_holes neighbor threshold must be in range of [1,9] for 3x3 footprint. Defaulting to 7.")
        num_neighbors = 7

    round = 1
    holesFilledLastRound = 1
    while (holesFilledLastRound > 0) and (num_iters == -1 or num_iters > 0):
        holesFilledLastRound = 0
        if num_iters > 0: # i.e not infinite
            num_iters -= 1

        def checkForAndFillHole(values):
            nonlocal holesFilledLastRound
            # Check to see if there is a hole in the center with elevation of 0
            if values[4] > 0 or (NaN_are_holes == True and ~numpy.isnan(values[4])):
                return values[4]

            # Count number of neighbors with elevations > 0
            neighborsGreaterThanZero = len(values[values > 0])

            # If 7 out of 8 neighbors are filled, fill the hole with the average.
            # This can be set to 8 out of 8 neighbors to only fill completely enclosed holes.
            # 7 out of 8 neighors allows cascading fills to solve diagonal holes and narrow 1xn length holes on repeating iterations.
            if neighborsGreaterThanZero >= num_neighbors:
                holesFilledLastRound += 1
                #print(values.reshape(3, 3))
                return numpy.nanmean(values)
            return values[4]

        footprint = numpy.array([[1,1,1],
                                 [1,1,1],
                                 [1,1,1]])
        
        raster = ndimage.generic_filter(raster, checkForAndFillHole, footprint=footprint, mode='nearest')
        #print(raster)

        if num_iters != -1:
            print(f"Round {round}: {holesFilledLastRound} holes filled.")
        else:
            print(f"Round {round}: {holesFilledLastRound} holes filled.")
        round += 1

        # fill negative values in the corners with 0 (nothing to do for NaN_are_holes)
        corners = [(0, 0), (0, -1), (-1, 0), (-1, -1)]
        if NaN_are_holes == False:
            for i, j in corners:
                    raster[i, j] = 0 if raster[i, j] < 0 else raster[i, j]


    return raster


def add_to_stl_list(stl, stl_list):
    stl_list.append(stl)
    return stl_list
    


def k3d_render_to_html(stl_list, folder, buffer=False):
    """stl_list is either a list of buffers or a list of filenames
    folder is the folder where the html file will be saved
    buffer is True if stl_list contains buffers not filenames
    returns the path to the html file so it can be opened in a browser if neeeded
    """

    plot = k3d.plot()
    color_mapping = {"red": 0xFF0000, "green": 0x00FF00, "blue": 0x0000FF, "yellow": 0xFFFF00, 
                    "cyan": 0x00FFFF, "magenta": 0xFF00FF, "orange": 0xFFA500, "purple": 0x800080}

    for stl in stl_list:
        if buffer == False:
            fp = open(stl, 'rb')
            buf = fp.read()
            fp.close()
        else:
            buf = stl

        random_color = random.choice(list(color_mapping.values()))
        plot += k3d.stl(buf, color=random_color) 



    # Save the plot to an HTML file
    html_file = folder + os.sep +"k3d_plot.html"
    with open(html_file, "w+") as f:
        ss = plot.get_snapshot()
        ss = ss.replace("[TIMESTAMP]", "TouchTerrain")
        f.write(ss)

    return html_file


def plot_DEM_histogram(npim, DEM_name, temp_folder):
    '''plot the DEM and a histogram of the elevation values, save as png'''
    fig, (ax1, ax2) = plt.subplots(nrows=2, figsize=(5, 10), 
                                gridspec_kw={'height_ratios': [1, 0.4]})
    
    npim_flt = npim.flatten() # 1D array
    elevmin, elevmax = numpy.nanmin(npim_flt), numpy.nanmax(npim_flt)



    imgplot = ax1.imshow(npim, aspect=u"equal", interpolation=u"spline36")
    ax1.xaxis.set_ticks([])
    ax1.yaxis.set_ticks([])
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.spines['bottom'].set_visible(False)
    ax1.spines['left'].set_visible(False)
    ax1.tick_params(axis='both', which='both', length=0)
    ax1.set_title("Elevation (m) by color for " + DEM_name)

    # set the colormap with 256 colors
    cmap_name = 'gist_earth' # gist_earth or terrain or nipy_spectral
    imgplot.set_clim(vmin=elevmin, vmax=elevmax) #
    imgplot.set_cmap(mpl.cm.get_cmap(cmap_name, 256)) 


    # calculate ticks at good intervals
    ticks = calculate_ticks(elevmin, elevmax)

    # Add a colorbar to the first subplot with min and max elevation values
    cbar = fig.colorbar(imgplot, ax=ax1, format='%d', orientation='horizontal', 
                        pad=0.1, ticks=ticks, shrink=1)
    cbar.ax.xaxis.set_ticks_position('top')
    cbar.ax.xaxis.set_label_position('top')
    #cbar.ax.xaxis.set_tick_params(width=0)

    # get optimal number of bins for histogram (Doane's formula ) also used for number of colors
    n = len(npim_flt)
    skewness = stats.skew(npim_flt, nan_policy='omit')
    sigma_g = np.sqrt((6 * (n - 2)) / ((n + 1) * (n + 3)))
    k = 1 + np.log2(n) + np.log2(1 + abs(skewness) / sigma_g)
    num_bins = int(np.ceil(k)) # number of bins

    num_bins = num_bins if num_bins <= 256 else 256 #  

    #
    # histogram with colored bars
    #
    n, bins = numpy.histogram(npim_flt, bins=num_bins, range=(elevmin, elevmax))
    bar = ax2.bar(bins[:-1], n, width=numpy.diff(bins), align='edge')

    # Create a colormap with num_bins colors
    histo_cmap = plt.get_cmap(cmap_name, num_bins)
    colors = histo_cmap(np.linspace(0, 1, num_bins))
    listed_cmap = ListedColormap(colors)

    # Normalize the colormap to span from elevmin to elevmax
    norm = mcolors.Normalize(vmin=elevmin, vmax=elevmax)

    # Apply the colormap to the bars
    for i, rect in enumerate(bar):
        color = listed_cmap(norm(bins[i]))
        rect.set_color(color)

    ax2.set_ylim([0, numpy.max(n)])
    ax2.set_xlim([elevmin, elevmax])
    ax2.set_xticks(ticks)
    ax2.grid(True, which='both', color='gray', linestyle='-', linewidth=0.5)
    ax2.set_facecolor((0.95, 0.95, 0.95))
    ax2.set_title("Histogram of Elevation")

    plt.draw() # needed to flush everything (?)
    #plt.show() # DEBUG
    plot_file_name = temp_folder + os.sep + DEM_name + "_elevation_plot_with_histogram.png"
    plt.savefig(plot_file_name, dpi=200)
    return plot_file_name


def dilate_array(raster, dilation_source=None, limit_mask=None):
    '''Will dilate raster (1 cell incl diagonals) with the corresponding cell values of the dilation_source.
    If dilation_source is None the dilation will be filled with the 3 x 3 nanmean
    returns the dilated raster'''
    
    if dilation_source is not None:
        
        # Convert raster to a binary array, where True represents non-NaN values
        nan_mask = ~np.isnan(raster) 

        # Perform the binary dilation operation
        dilated_nan_mask = binary_dilation(nan_mask, mask=limit_mask) 

        # Create a mask that is True for pixels in the dilation zone that are NaN in the bottom raster
        mask = dilated_nan_mask & ~nan_mask  

        # Create a new array that is the same as bottom, but with the pixels in the dilation zone replaced with the corresponding values from top
        dilated_raster = np.where(mask, dilation_source, raster)

        return dilated_raster
    
    else:
        # [[nan nan  1.  2.]  raster
        #  [nan nan  3.  4.]
        #  [ 9. 10. 11. 12.]]

        # Convert raster to a binary array, where True represents non-NaN values
        mask = ~np.isnan(raster)
        # [[False False  True  True]
        #  [False False  True  True]
        #  [ True  True  True  True]]

        dilated_mask = binary_dilation(mask, mask=limit_mask)   # Perform a binary dilation
        # [[False True  True  True]
        # [ True  True  True  True]
        # [ True  True  True  True]]

        unequal_mask = np.not_equal(mask, dilated_mask) # True where the dilated mask is different from the original mask
        # [[False True False False]
        # [ True  True False False]
        # [False False False False]]

        
        def nanmean(data):# if all are NaN return NaN, else return nanmean
            return np.nan if np.all(np.isnan(data)) else np.nanmean(data) # 
    
        # Compute the 3x3 (nan) mean for each cell in ras, ignoring partial NaNs
        mean_ras =  generic_filter(raster, nanmean, size=(3, 3))
        # [[nan 1.7 2.2 2.3]
        #  [9.3 6.8 6.1 5.7]
        #  [9.3 9.  9.1 9. ]]

        # Create a new array where the mean is applied to the cells selected by unequal_mask = True
        out = np.where(unequal_mask, mean_ras, raster)
        # [[ nan  1.7  1.   2. ]
        #  [ 9.3  6.8  3.   4. ]
        #  [ 9.  10.  11.  12. ]]
        
        return out

'''
# Test
numpy.set_printoptions(linewidth=numpy.inf)
nn = numpy.nan
r = numpy.array([
                        [ 23, nn,  33, 33, 20, 10, 33],
                        [ 21, -1, 23, 50, nn, 10, 22],
                        [ 12, 33, 33 ,23, nn, 10, 23],
                        [ 12, 23, 33 ,-1, 23, 10, 2 ],
                        [ -1, 20, 10, 23, 20, 10, 1 ],
                ])
print("\n", r)    
print(fillHoles(r, -1, 7, NaN_are_holes=True))
'''

