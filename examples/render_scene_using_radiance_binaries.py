# singular example using radiance binaries

"""
--- 1. ---
Use the below in the command prompt only not in powershell. Oconv required utf-8 encoding for the input files. 

    cd C:\Projects\archilume
    obj2rad inputs\87cowles_BLD_noWindows.obj > outputs\rad\87cowles_BLD_noWindows.rad
    obj2rad inputs\87cowles_site.obj > outputs\rad\87cowles_site.rad
    cd C:\Projects\archilume\outputs
    oconv -f rad\materials.mtl rad/87cowles_BLD_noWindows.rad rad\87cowles_site.rad > octree\87cowles_BLD_noWindows_with_site_skyless.oct
    oconv -i octree\87cowles_BLD_noWindows_with_site_skyless.oct sky/SS_0621_0900.sky > octree\87cowles_BLD_noWindows_with_site_SS_0621_0900.oct
    cd C:\Projects\archilume
    rpict -w -vtl -t 5 -vf outputs\views_grids\plan_L02.vp -x 2048 -y 2048 -ab 0 -ad 2048 -ar 256 -as 512 -ps 4 -lw 0.004 outputs\octree\87cowles_BLD_noWindows_with_site_SS_0621_0900.oct > outputs\images\87cowles_BLD_noWindows_with_site_SS_0621_0900.hdr
    ra_tiff -e -4 outputs\images\87cowles_BLD_noWindows_with_site_SS_0621_0900.hdr outputs\images\87cowles_BLD_noWindows_with_site_SS_0621_0900.tiff

    #FIXME: there is light leakes on the resulting hdr files of the walls of this obj file. It appears that potentially walls have been assigned as a glass type. Test this by altering the glass properties. 
    #TODO: investigate the use of an -af ambient.amb inimplementation in rpict to speed up the renderings of subseuqent levels using the same parameters and a differnet sky. 



    med  | rpict -vf view_description.vp -x 1024 -y 1024 -ab 1 -ad 1024 -ar 256 -as 256 -ps 5 octree_with_sky.oct > output.hdr
    high | rpict -vf view_description.vp -x 1024 -y 1024 -ab 2 -ad 1024 -ar 256 -as 256 -ps 5 octree_with_sky.oct > output.hdr

--- 2. ---
to be test on creation of ambient and direct rpict runs, where the ambient file could be re-used. for subeuent rendinergs. 
    cd C:\Projects\archilume
    gensky 12 21 12:00 -c -B 55.47 > outputs\sky\overcast_sky.rad
    oconv -i outputs\octree\87cowles_BLD_noWindows_with_site_skyless.oct outputs\sky\TenK_cie_overcast.rad > outputs\octree\87cowles_BLD_noWindows_with_site_TenK_cie_overcast.oct
    rpict -w -vtl -t 5 -vf outputs\views_grids\plan_L02.vp -x 1024 -y 1024 -ab 1 -ad 8192 -as 1024 -aa 0.05 -ar 512 -lr 12 -lw 0.002 -af outputs\images\indirect_overcast.amb -i outputs\octree\87cowles_BLD_noWindows_with_site_with_overcast.oct > outputs\images\87cowles_BLD_noWindows_with_site_with_overcast_indirect.hdr
    rpict -w -vtl -t 5 -vf outputs\views_grids\plan_L02.vp -x 1024 -y 1024 -ab 0 -dr 4 -dt 0.01 -ds 0.01 -dj 0.9 -dc 0.75 -dp 512 -st 0.1 outputs\octree\87cowles_BLD_noWindows_with_site_SS_0621_0900.oct > outputs\images\87cowles_BLD_noWindows_with_site_with_overcast_direct.hdr
    
    pcomb -e 'ro=ri(1)+ri(2);go=gi(1)+gi(2);bo=bi(1)+bi(2)' outputs\images\87cowles_BLD_noWindows_with_site_with_overcast_indirect.hdr outputs\images\87cowles_BLD_noWindows_with_site_with_overcast_direct.hdr > outputs\images\87cowles_BLD_noWindows_with_site_combined.hdr
    #TODO setup a direct rpict rendering and then a subseuent pcomb of these files to then generate a hdr file and
    ra_tiff outputs\images\87cowles_BLD_noWindows_with_site_with_overcast_indirect.hdr outputs\images\87cowles_BLD_noWindows_overcast_indirect.tiff

--- 3. ---
# Turn view into rays file that can be rendered in parallel. This route is not to be investigate it did not work intially but could be a point of speeding up the process in the future. A points.txt files would be more appropraite. I beleive the vwrays programme is generating an invalid ray.dat file. 

    # Generate rays in terminal in either binary option (-ff) or human readable format
    vwrays -vf outputs\views_grids\plan_L02.vp -x 2048 -y 2048 > outputs\views_grids\plan_L02_rays.txt

    # RGBE values at each point with more parameters for quality
    rtrace -h -ab 1 -ad 2048 -as 512 -ar 128 -aa 0.15 outputs\octree\87cowles_BLD_noWindows_with_site_skyless_SS_0621_0900.oct < outputs\views_grids\plan_L02_rays.txt > outputs\wpd\87cowles_BLD_noWindows_with_site_skyless_SS_0621_0900_plan_L02.txt

    # Create hdr image from text output
    TODO: test this option. FIXME there is an eror in the dimensions of the input vwrays and the output txt files in this situation only has dimenstions of 1908. 
    pvalue -r -h -x 1908 -y 1908 outputs\wpd\87cowles_BLD_noWindows_with_site_skyless_SS_0621_0900_plan_L02.txt > outputs\wpd\87cowles_BLD_noWindows_with_site_skyless_SS_0621_0900_plan_L02_rtrace.hdr



--- 4. ---
rpict defauls inputs are seen below, not all are utilised, but could be useful in future iteration of this code. 

Performance Impact of Each Parameter

Parameter    Slow Value    Fast Value    Speed Impact    Quality Impact
---------    ----------    ----------    ------------    --------------
-ad          8192          512-1024      HUGE            High
-as          1024          0-256         HIGH            Medium
-ps          1             4-8           HIGH            Medium
-x -y        2048          1024          4x faster       Visual only
-aa          0.08          0.2           Medium          Low-Medium
-ar          1024          128-256       Medium          Low
-pt          0.04          0.15          Medium          Low
-lr          12            4-6           Low-Medium      Low


rpict -defaults 
-vtv                            # view type perspective
-vp 0.000000 0.000000 0.000000  # view point
-vd 0.000000 1.000000 0.000000  # view direction
-vu 0.000000 0.000000 1.000000  # view up
-vh 45.000000                   # view horizontal size
-vv 45.000000                   # view vertical size
-vo 0.000000                    # view fore clipping plane
-va 0.000000                    # view aft clipping plane
-vs 0.000000                    # view shift
-vl 0.000000                    # view lift
-x  512                         # x resolution
-y  512                         # y resolution
-pa 1.000000                    # pixel aspect ratio
-pj 0.670000                    # pixel jitter
-pm 0.000000                    # pixel motion
-pd 0.000000                    # pixel depth-of-field
-ps 4                           # pixel sample
-pt 0.050000                    # pixel threshold
-t  0                           # time between reports
-w+                             # warning messages on
-i-                             # irradiance calculation off
-u-                             # correlated quasi-Monte Carlo sampling
-bv+                            # back face visibility on
-dt 0.050000                    # direct threshold
-dc 0.500000                    # direct certainty
-dj 0.000000                    # direct jitter
-ds 0.250000                    # direct sampling
-dr 1                           # direct relays
-dp 512                         # direct pretest density
-dv+                            # direct visibility on
-ss 1.000000                    # specular sampling
-st 0.150000                    # specular threshold
-av 0.000000 0.000000 0.000000  # ambient value
-aw 0                           # ambient value weight
-ab 0                           # ambient bounces
-aa 0.200000                    # ambient accuracy
-ar 64                          # ambient resolution
-ad 512                         # ambient divisions
-as 128                         # ambient super-samples
-me 0.00e+000 0.00e+000 0.00e+000       # mist extinction coefficient
-ma 0.000000 0.000000 0.000000  # mist scattering albedo
-mg 0.000000                    # mist scattering eccentricity
-ms 0.000000                    # mist sampling distance
-lr 7                           # limit reflection
-lw 4.00e-003                   # limit weight






"""