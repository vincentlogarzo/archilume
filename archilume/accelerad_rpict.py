"""
GPU-accelerated rendering using Accelerad.

Equivalent to accelerad_rpict.ps1 script. Manages GPU rendering with quality presets.
"""

# Archilume imports
from archilume import config

# Standard library imports
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
import subprocess
import time
import re
import os

# Third-party imports


# Constants
QUALITY_PRESETS = {
    #       draft   stand   prod    final   4k      custom  fast    med     high    detailed
    'aa': [ 0.01,   0.01,   0.01,   0.01,   0.02,   0.01,   0.06,   0.03,   0.01,   0       ],
    'ab': [ 3,      3,      3,      3,      3,      8,      3,      3,      3,      2       ],
    'ad': [ 2048,   1792,   1536,   1280,   1024,   2048,   512,    1024,   1536,   2048    ],
    'as': [ 1024,   896,    768,    640,    512,    1024,   256,    512,    512,    1024    ],
    'ar': [ 1024,   1024,   1024,   1024,   1024,   1024,   128,    256,    512,    1024    ],
    'ps': [ 4,      2,      2,      1,      1,      1,      2,      2,      1,      1       ],
    'pt': [ 0.15,   0.12,   0.10,   0.07,   0.05,   0.05,   0.10,   0.08,   0.05,   0.02    ],
    'lr': [ 5,      5,      5,      5,      5,      12,     12,     12,     12,     12      ],
    'lw': [ 0.001,  0.001,  0.001,  0.001,  0.001,  0.0001, 0.001,  0.001,  0.001,  0.0001  ],
    'dj': [ 0.0,    0.5,    0.7,    0.9,    1.0,    0.7,    None,   None,   None,   None    ],
    'ds': [ 0.25,   0.35,   0.50,   0.70,   0.90,   0.50,   None,   None,   None,   None    ],
    'dt': [ 0.50,   0.35,   0.25,   0.15,   0.05,   0.25,   None,   None,   None,   None    ],
    'dc': [ 0.25,   0.40,   0.50,   0.75,   0.90,   0.50,   None,   None,   None,   None    ],
    'dr': [ 0,      1,      1,      2,      3,      1,      None,   None,   None,   None    ],
    'dp': [ 512,    256,    256,    128,    64,     256,    None,   None,   None,   None    ],
}
QUALITY_NAMES = ['draft', 'stand', 'prod', 'final', '4k', 'custom', 'fast', 'med', 'high', 'detailed']


@dataclass
class AcceleradRpict:
    """
    GPU renderer using Accelerad with quality presets.

    Attributes:
        octree_name: Octree file name (without .oct extension)
        quality: Quality preset (draft, stand, prod, final, 4k, custom, fast, med, high, detailed)
        resolution: Image resolution in pixels (default: 1024)
        view_name: Specific view to render, or None for all views
    """
    octree_name: str
    quality: str = 'draft'
    resolution: int = 1024
    view_name: Optional[str] = None

    accelerad_exe: Path = field(init=False)
    octree_file: Path = field(init=False)
    params: dict = field(init=False)

    def __post_init__(self):
        """Initialize paths, validate inputs, configure GPU."""
        if not self.octree_name:
            raise ValueError("octree_name cannot be empty")
        if not 128 <= self.resolution <= 8192:
            raise ValueError(f"resolution must be 128-8192, got {self.resolution}")

        # Paths
        self.accelerad_exe = Path(__file__).parent.parent / '.devcontainer' / 'accelerad_07_beta_Windows' / 'bin' / 'accelerad_rpict.exe'
        self.octree_file = config.OCTREE_DIR / f"{self.octree_name}.oct"

        if not self.accelerad_exe.exists():
            raise FileNotFoundError(f"Accelerad not found: {self.accelerad_exe}")
        if not self.octree_file.exists():
            raise FileNotFoundError(f"Octree not found: {self.octree_file}")

        # Load quality preset
        if self.quality.lower() not in QUALITY_NAMES:
            raise ValueError(f"Unknown quality: {self.quality}. Valid: {', '.join(QUALITY_NAMES)}")
        idx = QUALITY_NAMES.index(self.quality.lower())
        self.params = {k: v[idx] for k, v in QUALITY_PRESETS.items()}

        # Configure GPU
        self._configure_gpu()

    def _configure_gpu(self):
        """Set CUDA environment variables based on GPU VRAM."""
        print("Checking for GPU...")
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.total', '--format=csv,nounits,noheader'],
                                  capture_output=True, text=True, check=False)
            if result.returncode == 0 and result.stdout.strip().isdigit():
                vram_mb = int(result.stdout.strip())
                vram_gb = vram_mb // 1024
                cache_mb = min(int(vram_mb * 0.3), 16384)
                os.environ.update({
                    'CUDA_CACHE_MAXSIZE': str(cache_mb * 1024 * 1024),
                    'CUDA_CACHE_DISABLE': '0',
                    'CUDA_FORCE_PTX_JIT': '1'
                })
                print(f"GPU: {vram_gb} GB ({vram_mb} MB), Cache: {cache_mb} MB")
                return
        except FileNotFoundError:
            pass
        print("WARNING: GPU not detected, using defaults")
        os.environ.update({'CUDA_CACHE_MAXSIZE': '1073741824', 'CUDA_CACHE_DISABLE': '0', 'CUDA_FORCE_PTX_JIT': '1'})

    def _get_views(self) -> List[Path]:
        """Get list of view files to render."""
        if self.view_name:
            view_path = config.VIEW_DIR / f"{self.view_name}.vp"
            if not view_path.exists():
                raise FileNotFoundError(f"View not found: {view_path}")
            print(f"Mode: Single view '{self.view_name}'")
            return [view_path]
        print("Mode: Batch render ALL views")
        views = list(config.VIEW_DIR.glob("*.vp"))
        if not views:
            raise FileNotFoundError(f"No views found in {config.VIEW_DIR}")
        return views

    def _parse_paths(self, view_name: str) -> Tuple[Path, Path]:
        """Parse octree name to generate output paths: {building}_{view}__{sky}.hdr"""
        match = re.match(r'(.+)_with_site_(.+)', self.octree_name)
        if match:
            building, sky = match.groups()
            amb = config.IMAGE_DIR / f"{building}_with_site_{view_name}__{sky}.amb"
            hdr = config.IMAGE_DIR / f"{building}_{view_name}__{sky}.hdr"
        else:
            amb = config.IMAGE_DIR / f"{self.octree_name}_{view_name}.amb"
            hdr = config.IMAGE_DIR / f"{self.octree_name}_{view_name}.hdr"
        return amb, hdr

    def _build_command(self, view_path: Path, amb_file: Path) -> List[str]:
        """Build accelerad_rpict command with quality parameters."""
        cmd = [str(self.accelerad_exe), '-w', '-t', '1', '-vf', str(view_path),
               '-x', str(self.resolution), '-y', str(self.resolution),
               '-aa', str(self.params['aa']), '-ab', str(self.params['ab']),
               '-ad', str(self.params['ad']), '-as', str(self.params['as']),
               '-ar', str(self.params['ar'])]

        # Add optional parameters
        for key in ['ps', 'pt', 'lr', 'lw', 'dj', 'ds', 'dt', 'dc', 'dr', 'dp']:
            if self.params[key] is not None:
                cmd.extend([f'-{key}', str(self.params[key])])

        cmd.extend(['-i', '-af', str(amb_file), str(self.octree_file)])
        return cmd

    def render(self) -> int:
        """Execute GPU rendering for all views. Returns number of rendered views."""
        views = self._get_views()
        print(f"Found {len(views)} view(s), Quality: {self.quality}, Resolution: {self.resolution}px\n")
        print("=" * 80)
        print("GPU RENDERING - All views")
        print("=" * 80 + "\n")

        start = time.time()
        rendered = 0

        for idx, view_file in enumerate(views, 1):
            view_name = view_file.stem
            amb_file, hdr_file = self._parse_paths(view_name)

            print(f"[{idx}/{len(views)}] {view_name}")
            print(f"  Rendering {self.resolution}px: {hdr_file}")

            view_start = time.time()
            cmd = self._build_command(view_file, amb_file)

            try:
                with open(hdr_file, 'wb') as f:
                    result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, check=False)
                if result.returncode != 0:
                    print(f"  ERROR: Render failed (exit code {result.returncode})")
                else:
                    rendered += 1
                    elapsed = time.time() - view_start
                    print(f"  Complete: {int(elapsed // 60)}m {int(elapsed % 60)}s")
            except Exception as e:
                print(f"  ERROR: {e}")
            print("")

        total = time.time() - start
        print("=" * 80)
        print(f"Rendering Complete: {rendered} views in {int(total // 60)}m {int(total % 60)}s")
        print("=" * 80)
        return rendered
