"""
Parallel processing utilities that combine PyRadiance with custom parallel execution.
Maintains backward compatibility while leveraging official PyRadiance functions.
"""

# Archilume imports
from .utils import run_commands_parallel  # Fallback to your existing implementation

# Standard library imports
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple, Callable, Any

# Third-party imports
import pyradiance

try:
    import pyradiance as pr
    PYRADIANCE_AVAILABLE = True
except ImportError:
    PYRADIANCE_AVAILABLE = False
    logging.warning("PyRadiance not available. Falling back to subprocess calls.")


class PyRadianceParallel:
    """
    Parallel execution wrapper for PyRadiance functions.
    Falls back to subprocess commands if PyRadiance is not available.
    """
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.use_pyradiance = PYRADIANCE_AVAILABLE
    
    def oconv_parallel(self, 
                      material_files: List[str], 
                      geometry_files: List[str], 
                      output_files: List[str],
                      freeze: bool = True) -> List[bool]:
        """
        Run multiple oconv operations in parallel using PyRadiance.
        
        Args:
            material_files: List of material file paths
            geometry_files: List of geometry file paths  
            output_files: List of output octree file paths
            freeze: Whether to freeze the octree (-f flag)
            
        Returns:
            List of success/failure booleans for each operation
        """
        if not self.use_pyradiance:
            return self._fallback_oconv_parallel(material_files, geometry_files, output_files, freeze)
            
        def _single_oconv(args: Tuple[str, str, str]) -> bool:
            mat_file, geom_file, output_file = args
            try:
                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                
                # Use PyRadiance oconv function
                pr.oconv(
                    scene_files=[mat_file, geom_file],
                    output=output_file,
                    freeze=freeze
                )
                logging.info(f"Successfully generated: {output_file}")
                return True
            except Exception as e:
                logging.error(f"Error running oconv for {output_file}: {e}")
                return False
        
        # Prepare arguments for parallel execution
        args_list = list(zip(material_files, geometry_files, output_files))
        
        return self._execute_parallel(_single_oconv, args_list)
    
    def oconv_with_sky_parallel(self,
                               base_octrees: List[str],
                               sky_files: List[str], 
                               output_octrees: List[str]) -> List[bool]:
        """
        Combine base octrees with sky files in parallel.
        Equivalent to: oconv -i base.oct sky.sky > output.oct
        
        Args:
            base_octrees: List of base octree file paths
            sky_files: List of sky file paths
            output_octrees: List of output octree file paths
            
        Returns:
            List of success/failure booleans for each operation
        """
        if not self.use_pyradiance:
            return self._fallback_oconv_sky_parallel(base_octrees, sky_files, output_octrees)
        
        def _single_oconv_sky(args: Tuple[str, str, str]) -> bool:
            base_oct, sky_file, output_oct = args
            try:
                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_oct), exist_ok=True)
                
                # Use PyRadiance oconv with -i flag (include existing octree)
                pr.oconv(
                    scene_files=[sky_file],
                    octree=base_oct,  # Include existing octree
                    output=output_oct
                )
                logging.info(f"Successfully combined {base_oct} + {sky_file} -> {output_oct}")
                return True
            except Exception as e:
                logging.error(f"Error combining octree {base_oct} with sky {sky_file}: {e}")
                return False
        
        args_list = list(zip(base_octrees, sky_files, output_octrees))
        return self._execute_parallel(_single_oconv_sky, args_list)
    
    def rpict_parallel(self,
                      octree_files: List[str],
                      view_files: List[str], 
                      output_files: List[str],
                      x_res: int = 1024,
                      y_res: int = 1024,
                      ambient_bounces: int = 2,
                      ambient_divisions: int = 128,
                      **kwargs) -> List[bool]:
        """
        Run multiple rpict rendering operations in parallel.
        
        Args:
            octree_files: List of octree file paths
            view_files: List of view file paths
            output_files: List of output HDR file paths
            x_res: X resolution
            y_res: Y resolution  
            ambient_bounces: Ambient bounces (-ab)
            ambient_divisions: Ambient divisions (-ad)
            **kwargs: Additional rpict parameters
            
        Returns:
            List of success/failure booleans for each operation
        """
        if not self.use_pyradiance:
            return self._fallback_rpict_parallel(octree_files, view_files, output_files, 
                                               x_res, y_res, ambient_bounces, ambient_divisions, **kwargs)
        
        def _single_rpict(args: Tuple[str, str, str]) -> bool:
            octree, view_file, output_file = args
            try:
                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                
                # Use PyRadiance rpict function
                pr.rpict(
                    octree=octree,
                    view_file=view_file,
                    output=output_file,
                    x_resolution=x_res,
                    y_resolution=y_res,
                    ambient_bounces=ambient_bounces,
                    ambient_divisions=ambient_divisions,
                    **kwargs
                )
                logging.info(f"Successfully rendered: {output_file}")
                return True
            except Exception as e:
                logging.error(f"Error rendering {octree} with view {view_file}: {e}")
                return False
        
        args_list = list(zip(octree_files, view_files, output_files))
        return self._execute_parallel(_single_rpict, args_list)
    
    def _execute_parallel(self, func: Callable, args_list: List[Any]) -> List[bool]:
        """Execute function in parallel with ThreadPoolExecutor."""
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_args = {executor.submit(func, args): args for args in args_list}
            
            # Collect results as they complete
            for future in as_completed(future_to_args):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logging.error(f"Parallel execution error: {e}")
                    results.append(False)
        
        return results
    
    def _fallback_oconv_parallel(self, material_files: List[str], geometry_files: List[str], 
                                output_files: List[str], freeze: bool = True) -> List[bool]:
        """Fallback to subprocess-based oconv commands."""
        commands = []
        for mat_file, geom_file, output_file in zip(material_files, geometry_files, output_files):
            freeze_flag = "-f" if freeze else ""
            cmd = f"oconv {freeze_flag} {mat_file} {geom_file} > {output_file}"
            commands.append(cmd)
        
        run_commands_parallel(commands, self.max_workers)
        return [True] * len(commands)  # Assume success for backward compatibility
    
    def _fallback_oconv_sky_parallel(self, base_octrees: List[str], sky_files: List[str], 
                                    output_octrees: List[str]) -> List[bool]:
        """Fallback to subprocess-based oconv with sky commands."""
        commands = []
        for base_oct, sky_file, output_oct in zip(base_octrees, sky_files, output_octrees):
            cmd = f"oconv -i {base_oct} {sky_file} > {output_oct}"
            commands.append(cmd)
        
        run_commands_parallel(commands, self.max_workers)
        return [True] * len(commands)
    
    def _fallback_rpict_parallel(self, octree_files: List[str], view_files: List[str], 
                                output_files: List[str], x_res: int, y_res: int,
                                ambient_bounces: int, ambient_divisions: int, **kwargs) -> List[bool]:
        """Fallback to subprocess-based rpict commands."""
        commands = []
        for octree, view_file, output_file in zip(octree_files, view_files, output_files):
            cmd = (f"rpict -vf {view_file} -x {x_res} -y {y_res} "
                  f"-ab {ambient_bounces} -ad {ambient_divisions} "
                  f"{octree} > {output_file}")
            commands.append(cmd)
        
        run_commands_parallel(commands, self.max_workers)
        return [True] * len(commands)