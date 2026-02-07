# singular example using radiance binaries

"""
--- 1. ---
Use the below in the command prompt only not in powershell. Oconv required utf-8 encoding for the input files. 

    cd C:/Projects/archilume

    obj2rad inputs/22041_AR_T01_BLD.obj > outputs/rad/22041_AR_T01_BLD.rad
    obj2rad inputs/87cowles_BLD_noWindows.obj > outputs/rad/87cowles_BLD_noWindows.rad
    obj2rad inputs/87cowles_site.obj > outputs/rad/87cowles_site.rad
    
    obj2mesh inputs/22041_AR_T01_BLD.obj outputs/rad/22041_AR_T01_BLD.rtm
    obj2mesh inputs/87cowles_BLD_noWindows.obj outputs/rad/87cowles_BLD_noWindows.rtm

    rad2mgf outputs/rad/87cowles_site.rad > outputs/rad/87cowles_site.mgf
    obj2rad -n inputs/87cowles_site.obj > outputs/rad/87cowles_site.qual 
    obj2rad -n inputs/22041_T3_R25_BLD_COARSE.obj > outputs/rad/22041_T3_R25_BLD_COARSE.qual

    oconv -f outputs/rad/materials.mtl outputs/rad/22041_T3_R25_BLD_COARSE.rad > outputs/octree/22041_T3_R25_BLD_COARSE.oct
    oconv inputs/default_mat.rad outputs/rad/87cowles_BLD_noWindows.rtm > outputs/octree/87cowles_BLD_noWindows.oct

    oconv -i octree/87cowles_BLD_noWindows_with_site_skyless.oct sky/SS_0621_0900.sky > octree/87cowles_BLD_noWindows_with_site_SS_0621_0900.oct


    rpict -w -t 5 -vf views_grids/plan_L02.vp -x 2048 -y 2048 -ab 0 -ad 2048 -ar 256 -as 512 -ps 4 -lw 0.004 octree/87cowles_BLD_noWindows_with_site_SS_0621_0900.oct > images/87cowles_BLD_noWindows_with_site_plan_L02_SS_0621_0900.hdr
    ra_tiff -e -4 outputs/images/87cowles_BLD_noWindows_with_site_SS_0621_0900.hdr outputs/images/87cowles_BLD_noWindows_with_site_SS_0621_0900.tiff
 
--- 2. ---
to be test on creation of ambient and direct rpict runs, where the ambient file is intially run as an overture and then reused to speed up seubsequent runs 
    cd C:/Projects/archilume
    oconv -i outputs/octree/87cowles_BLD_noWindows_with_site_skyless.oct outputs/sky/TenK_cie_overcast.rad > outputs/octree/87cowles_BLD_noWindows_with_site_TenK_cie_overcast.oct
    rpict -w -t 5 -vf outputs/views_grids/plan_L02.vp -x 64 -y 64 -aa 0.1 -ab 1 -ad 4096 -ar 1024 -as 1024 -ps 4 -pt 0.05 -pj 1 -dj 0.7 -lr 12 -lw 0.002 -af outputs/images/indirect_overcast_plan_L02.amb -i outputs/octree/87cowles_BLD_noWindows_with_site_TenK_cie_overcast.oct
    rpict -w -t 5 -vf outputs/views_grids/plan_L02.vp -x 2048 -y 2048 -aa 0.1 -ab 1 -ad 4096 -ar 1024 -as 1024 -ps 4 -pt 0.05 -pj 1 -dj 0.7 -lr 12 -lw 0.002 -af outputs/images/indirect_overcast.amb -i outputs/octree/87cowles_BLD_noWindows_with_site_TenK_cie_overcast.oct > outputs/images/87cowles_BLD_noWindows_with_site_TenK_cie_overcast_indirect.hdr
    pcomb -e 'ro=ri(1)+ri(2);go=gi(1)+gi(2);bo=bi(1)+bi(2)' outputs/images/87cowles_BLD_noWindows_with_site_with_overcast_indirect.hdr outputs/images/87cowles_BLD_noWindows_with_site_with_overcast_direct.hdr > outputs/images/87cowles_BLD_noWindows_with_site_combined.hdr
    ra_tiff outputs/images/87cowles_BLD_noWindows_with_site_with_overcast_indirect.hdr outputs/images/87cowles_BLD_noWindows_overcast_indirect.tiff
        combined workflow
            pcomb -e "ro=ri(1)+ri(2); go=gi(1)+gi(2); bo=bi(1)+bi(2)" outputs\images\87cowles_BLD_noWindows_with_site_plan_L00__TenK_cie_overcast.hdr outputs\images\87cowles_BLD_noWindows_with_site_plan_L00_SS_0621_0900.hdr | ra_tiff -e -2 - outputs\images\87cowles_BLD_noWindows_with_site_plan_L00_SS_0621_0900.tiff
    pcond -h outputs\images\87cowles_BLD_noWindows_with_site_plan_L02__TenK_cie_overcast.hdr > outputs\images\87cowles_BLD_noWindows_with_site_plan_L02__TenK_cie_overcast_visual_human.hdr


--- 3. ---
# testing rtpict versus rpict, where rtpict uses rtrace and multiprocessors to produce the image. rtpictwill only work on linux machine or connected to wsl in vs code in a dev container
    3.1. Rendering process
        # Recommend resolutions: 64, 128, 256, 512, 1024, 2048, 4096
            IMAGE_NAME="image1_shg_12ab"
            RES=$((2048))
            rtpict -n 19 -vf inputs/view.vp -x $RES -y $RES @inputs/${IMAGE_NAME}.rdp -af outputs/image/${IMAGE_NAME}.amb inputs/model.oct > outputs/image/${IMAGE_NAME}.hdr

        
    3.2. Post-processing
        3.2.1 # Create separate legend for reporting
            pcomb -e 'ro=1;go=1;bo=1' -x 1 -y 1 | falsecolor -s 4 -n 10 -l "DF%" -lw 400 -lh 1600 | ra_tiff - outputs/image/df_false_legend.tiff
            pcomb -e 'ro=1;go=1;bo=1' -x 1 -y 1 | falsecolor -cl -s 2 -n 4 -l "DF%" -lw 400 -lh 1600 | ra_tiff - outputs/image/df_cntr_legend.tiff

        
        3.2.2 # Smooth image use could be effective for final visualisation. Source image must be used for results. 
            IMAGE_NAME="image1_shg_12ab"
            pfilt -x /2 -y /2 outputs/image/${IMAGE_NAME}.hdr > outputs/image/${IMAGE_NAME}_smooth.hdr
            pcomb -s 0.01 outputs/image/${IMAGE_NAME}.hdr | falsecolor -s 4 -n 10 -l "DF %" -lw 0 > outputs/image/${IMAGE_NAME}_df_false.hdr
            pcomb -s 0.01 outputs/image/${IMAGE_NAME}.hdr \
                | falsecolor -cl -s 2 -n 4 -l "DF %" -lw 0 \
                | tee outputs/image/${IMAGE_NAME}_df_cntr.hdr \
                | pcomb \
                    -e 'cond=ri(2)+gi(2)+bi(2)' \
                    -e 'ro=if(cond-.01,ri(2),ri(1))' \
                    -e 'go=if(cond-.01,gi(2),gi(1))' \
                    -e 'bo=if(cond-.01,bi(2),bi(1))' \
                    <(pfilt -e 0.5 outputs/image/${IMAGE_NAME}.hdr) \
                    - \
                | ra_tiff - outputs/image/${IMAGE_NAME}_df_cntr_overlay.tiff

    
--- 5. ---
# testing of post processing of HDR images extracted at other view points into colourfill images. 
    pcomb -m 100/10000 input.hdr | falsecolour -s 1 -n 10 -l % > output.hdr

    falsecolor -i "C:\Projects\archilume\outputs\images\87Cowles_BLD_withWindows_with_site_TenK_cie_overcast__plan_L02_detailed_filtered.hdr" -s 1000 -l lux -n 10 | ra_tiff -e -2 - "C:\Projects\archilume\outputs\images\87Cowles_BLD_withWindows_with_site_TenK_cie_overcast__plan_L02_detailed_filtered.tiff"

    
FUTURE implementaiton A of RenderingPipelines
   
    rpict -w -t 2 -vf outputs\views_grids\plan_L01.vp -x 1024 -y 1024 -aa 0.1 -ab 1 -ad 4096 -ar 1024 -as 1024 -ps 4 -pt 0.05 -pj 1 -dj 0.7 -lr 12 -lw 0.002 -af outputs\images\87Cowles_BLD_withWindows_with_site_TenK_cie_overcast.amb -i outputs\octree\87Cowles_BLD_withWindows_with_site_TenK_cie_overcast.oct > outputs\images\87Cowles_BLD_withWindows_with_site_TenK_cie_overcast.hdr && echo "First command succeeded" && falsecolor -i outputs\images\87Cowles_BLD_withWindows_with_site_TenK_cie_overcast.hdr -s 1000 -l lux -n 10 -lw 0 | ra_tiff -e -2 - outputs\images\87Cowles_BLD_withWindows_with_site_TenK_cie_overcast.tiff
    
--- 6. ---
# Testing using of accelerad binaries. 
# Paste below command into terminal to maintain GPU cuda build for subsequent process efficiency.
    .\archilume\accelerad_rpict.ps1 87Cowles_BLD_withWindows_with_site_TenK_cie_overcast high 512

    




rpict quality settings reference 
----------------------------------------------------------------------------

The following table provides a guide to adjusting rpict parameters for faster rendering times while maintaining acceptable quality. The "Slow Value" column represents settings for high-quality renders, while the "Fast Value" column suggests settings for quicker renders. The "Speed Impact" and "Quality Impact" columns indicate the relative effects of these adjustments.

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

accelerad_rpict -defaults
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
-g+                             # GPU acceleration on
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
-al 0                           # ambient sample spacing (GPU only)
-ag -1                          # ambient infill divisions (GPU only)
-az 0                           # ambient grid density (GPU only)
-ac 4096                        # ambient k-means clusters (GPU only)
-an 100                         # ambient k-means iterations (GPU only)
-at 0.050000                    # ambient k-means threshold (GPU only)
-ax 1.000000                    # ambient k-means weighting factor (GPU only)
-me 0.00e+000 0.00e+000 0.00e+000       # mist extinction coefficient
-ma 0.000000 0.000000 0.000000  # mist scattering albedo
-mg 0.000000                    # mist scattering eccentricity
-ms 0.000000                    # mist sampling distance
-lr 7                           # limit reflection
-lw 1.00e-003                   # limit weight
-am 0.0                         # max photon search radius


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
