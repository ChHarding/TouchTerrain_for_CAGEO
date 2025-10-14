# TouchTerrain Refactoring Plan

**Status Legend:**
- ⬜ Not Started
- 🔄 In Progress
- ✅ Completed
- ⏸️ Paused/Blocked
- ❌ Cancelled

**Last Updated**: 2025-10-11

---

## Phase 1: Quick Wins (Safe, High Impact)

**Goal**: Remove technical debt and improve code clarity without breaking functionality.
**Estimated Time**: 8-12 hours
**Risk Level**: 🟢 Low
**Prerequisites**: None

### 1.1 Clean Up Coordinate_system_conv.py ⬜

**Time Estimate**: 2 hours

#### Tasks:
- [ ] ⬜ Remove 170-line CSV comment block (lines 125-248)
- [ ] ⬜ Remove debug print statements (lines 63, 83, 84)
- [ ] ⬜ Remove unused variables (`good_input`, `good_easting`, `good_northing`)
- [ ] ⬜ Move test code to `test/test_coordinate_conversion.py` (lines 249-275)
- [ ] ⬜ Fix return type error message typo (line 101: "In valid" → "Invalid")
- [ ] ⬜ Replace print() with logging.warning() for bounds warnings
- [ ] ⬜ Run existing tests to verify no breakage
- [ ] ⬜ Commit: "refactor: clean up Coordinate_system_conv.py - remove dead code"

**Success Criteria**:
- File reduced from 275 to ~105 lines
- All tests pass
- No functional changes

---

### 1.2 Remove DEV_MODE from TouchTerrainEarthEngine.py ⬜

**Time Estimate**: 1 hour

#### Tasks:
- [ ] ⬜ Remove DEV_MODE flag and sys.path manipulation (lines 24-30, 62-64)
- [ ] ⬜ Remove commented toggle line 26
- [ ] ⬜ Consolidate imports into proper PEP 8 order
- [ ] ⬜ Document in CLAUDE.md that editable install is the proper approach
- [ ] ⬜ Run smoke test (standalone script)
- [ ] ⬜ Commit: "refactor: remove DEV_MODE sys.path hack"

**Success Criteria**:
- sys.path not modified at runtime
- Imports follow PEP 8 grouping
- Standalone script still works

---

### 1.3 Reorganize Imports in TouchTerrainEarthEngine.py ⬜

**Time Estimate**: 1.5 hours

#### Tasks:
- [ ] ⬜ Group imports by type (stdlib, third-party, local)
- [ ] ⬜ Remove duplicate imports (`os.path`)
- [ ] ⬜ Move side effects out of import block (`numpy.set_printoptions`)
- [ ] ⬜ Alphabetize within groups
- [ ] ⬜ Run ruff to verify import order
- [ ] ⬜ Run tests
- [ ] ⬜ Commit: "refactor: organize imports per PEP 8"

**Success Criteria**:
- All imports at top of file
- Grouped: stdlib, third-party, local
- No duplicate imports
- Ruff check passes

---

### 1.4 Fix Function Names (Non-Breaking) ⬜

**Time Estimate**: 2 hours

#### Tasks:
- [ ] ⬜ Add snake_case aliases for public functions:
  - `latlon_to_utm = LatLon_to_UTM` (deprecated)
  - `arc_degree_in_meters = arcDegr_in_meter` (deprecated)
  - `utm_zone_to_epsg = UTM_zone_to_EPSG_code` (deprecated)
  - `fill_holes = fillHoles` (deprecated)
  - `rotate_dem = rotateDEM` (deprecated)
  - `resample_dem = resampleDEM` (deprecated)
- [ ] ⬜ Add deprecation warnings using `warnings.warn()`
- [ ] ⬜ Update internal calls to use new names
- [ ] ⬜ Update tests to use new names
- [ ] ⬜ Document deprecation in docstrings
- [ ] ⬜ Run full test suite
- [ ] ⬜ Commit: "refactor: add snake_case function aliases with deprecation warnings"

**Success Criteria**:
- Old names still work (backward compatible)
- New names available
- Deprecation warnings issued
- All tests pass

---

### 1.5 Split utils.py by Domain ⬜

**Time Estimate**: 2.5 hours

#### Tasks:
- [ ] ⬜ Create `touchterrain/common/image_utils.py`:
  - Move `save_tile_as_image()`
- [ ] ⬜ Create `touchterrain/common/array_processing.py`:
  - Move `clean_up_diags()`
  - Move `dilate_array()`
  - Move `fillHoles()` (and alias `fill_holes`)
- [ ] ⬜ Create `touchterrain/common/visualization.py`:
  - Move `plot_DEM_histogram()`
  - Move `k3d_render_to_html()`
- [ ] ⬜ Keep in `utils.py`:
  - `add_to_stl_list()`
  - Any truly generic utilities
- [ ] ⬜ Update imports in all files
- [ ] ⬜ Add backward-compatible imports in `utils.py`:
  ```python
  # Backward compatibility
  from touchterrain.common.image_utils import save_tile_as_image
  from touchterrain.common.array_processing import clean_up_diags, dilate_array
  # etc.
  ```
- [ ] ⬜ Run all tests
- [ ] ⬜ Commit: "refactor: split utils.py into domain-specific modules"

**Success Criteria**:
- utils.py reduced from 402 to ~100 lines
- New modules have clear purpose
- Backward compatible (imports still work)
- All tests pass

---

### 1.6 Add Basic Type Hints to Core Functions ⬜

**Time Estimate**: 2 hours

#### Tasks:
- [ ] ⬜ Add type hints to coordinate conversion functions
- [ ] ⬜ Add type hints to array processing functions
- [ ] ⬜ Add return type hints
- [ ] ⬜ Install and configure mypy
- [ ] ⬜ Run mypy on modified files
- [ ] ⬜ Fix any type errors found
- [ ] ⬜ Commit: "feat: add type hints to coordinate and array processing modules"

**Success Criteria**:
- All modified functions have type hints
- mypy passes with no errors on new code
- Documentation improved

---

## Phase 2: Prepare for Major Refactoring

**Goal**: Set up infrastructure and patterns for larger changes.
**Estimated Time**: 10-14 hours
**Risk Level**: 🟡 Medium
**Prerequisites**: Phase 1 complete

---

### 2.1 Create Configuration Dataclasses ⬜

**Time Estimate**: 3 hours

#### Tasks:
- [ ] ⬜ Create `touchterrain/common/models.py`:
  ```python
  from dataclasses import dataclass
  from typing import Optional, Literal

  @dataclass
  class BoundingBox:
      bottom_left_lat: float
      bottom_left_lon: float
      top_right_lat: float
      top_right_lon: float

  @dataclass
  class DEMConfig:
      source: str  # DEM_name or importedDEM path
      bounds: Optional[BoundingBox] = None
      projection: Optional[str] = None
      polygon: Optional[str] = None
      poly_url: Optional[str] = None
      poly_file: Optional[str] = None

  @dataclass
  class MeshConfig:
      tile_width: float = 100.0
      print_resolution: float = 1.0
      num_tiles_x: int = 1
      num_tiles_y: int = 1
      base_thickness: float = 2.0
      z_scale: float = 1.0
      file_format: Literal["STLb", "STLa", "obj", "GeoTiff"] = "STLb"
      tile_centered: bool = False
      no_bottom: bool = False
      no_normals: bool = True

  @dataclass
  class ProcessingConfig:
      cpu_cores: int = 0
      max_cells_for_memory: int = 500 * 500 * 4
      temp_folder: str = "tmp"
      zip_file_name: str = "terrain"
      ignore_leq: Optional[float] = None
      fill_holes: Optional[tuple] = None
      min_elev: Optional[float] = None
      clean_diags: bool = False
      dirty_triangles: bool = False
      smooth_borders: bool = True

  @dataclass
  class GPXConfig:
      imported_gpx: Optional[list] = None
      path_height: float = 25.0
      pixels_between_points: int = 10
      path_thickness: float = 1.0

  @dataclass
  class VisualizationConfig:
      k3d_render: bool = False
      map_img_filename: Optional[str] = None
      bottom_image: Optional[str] = None
  ```
- [ ] ⬜ Add type hints to all dataclasses
- [ ] ⬜ Add validation methods where appropriate
- [ ] ⬜ Write unit tests for dataclasses
- [ ] ⬜ Commit: "feat: add configuration dataclasses"

**Success Criteria**:
- All config dataclasses defined
- Type hints complete
- Tests pass
- Ready to use in refactored code

---

### 2.2 Create Helper Function to Convert Dict to Dataclasses ⬜

**Time Estimate**: 2 hours

#### Tasks:
- [ ] ⬜ Add conversion functions in `models.py`:
  ```python
  def dict_to_dem_config(params: dict) -> DEMConfig:
      """Convert legacy parameter dict to DEMConfig."""
      bounds = None
      if all(k in params for k in ['trlat', 'trlon', 'bllat', 'bllon']):
          bounds = BoundingBox(
              bottom_left_lat=params['bllat'],
              bottom_left_lon=params['bllon'],
              top_right_lat=params['trlat'],
              top_right_lon=params['trlon']
          )
      return DEMConfig(
          source=params.get('DEM_name') or params.get('importedDEM'),
          bounds=bounds,
          projection=params.get('projection'),
          polygon=params.get('polygon'),
          poly_url=params.get('polyURL'),
          poly_file=params.get('poly_file')
      )

  def dict_to_mesh_config(params: dict) -> MeshConfig:
      # ... similar conversion

  def dict_to_processing_config(params: dict) -> ProcessingConfig:
      # ... similar conversion
  ```
- [ ] ⬜ Write unit tests for conversion functions
- [ ] ⬜ Test with sample config files
- [ ] ⬜ Commit: "feat: add dict-to-dataclass conversion helpers"

**Success Criteria**:
- Conversion functions handle all parameters
- Backward compatible with existing dicts
- Tests pass

---

### 2.3 Increase Test Coverage to 25% ⬜

**Time Estimate**: 5 hours

#### Priority Areas to Test:
- [ ] ⬜ Array processing functions (clean_up_diags, dilate_array, fill_holes)
- [ ] ⬜ Coordinate conversion functions (complete coverage)
- [ ] ⬜ Vector math operations
- [ ] ⬜ Calculate ticks functionality
- [ ] ⬜ GPX processing (basic tests)
- [ ] ⬜ Configuration dataclass validation
- [ ] ⬜ Run coverage report and verify 25%+
- [ ] ⬜ Commit: "test: increase coverage to 25%"

**Success Criteria**:
- Test coverage ≥ 25%
- All new code has tests
- CI pipeline runs successfully

---

### 2.4 Set Up Mypy Configuration ⬜

**Time Estimate**: 1 hour

#### Tasks:
- [ ] ⬜ Create `mypy.ini`:
  ```ini
  [mypy]
  python_version = 3.12
  warn_return_any = True
  warn_unused_configs = True
  disallow_untyped_defs = False  # Start lenient
  ignore_missing_imports = True

  [mypy-touchterrain.common.models]
  disallow_untyped_defs = True  # Strict for new code

  [mypy-touchterrain.common.coordinate_conversion]
  disallow_untyped_defs = True
  ```
- [ ] ⬜ Add mypy to pre-commit hooks
- [ ] ⬜ Run mypy on codebase
- [ ] ⬜ Fix critical type errors
- [ ] ⬜ Document in CLAUDE.md
- [ ] ⬜ Commit: "chore: add mypy type checking configuration"

**Success Criteria**:
- mypy configured
- Passes on new code
- Integrated into CI

---

### 2.5 Document Refactoring Progress ⬜

**Time Estimate**: 1 hour

#### Tasks:
- [ ] ⬜ Update CLAUDE.md with refactoring status
- [ ] ⬜ Create CHANGELOG.md entry
- [ ] ⬜ Update this Planning.md with completion dates
- [ ] ⬜ Add migration guide for deprecated functions
- [ ] ⬜ Commit: "docs: update refactoring progress"

**Success Criteria**:
- Documentation up to date
- Migration path clear
- Team aligned

---

## Phase 3: Function Decomposition (Major Refactoring)

**Goal**: Break down monolithic `get_zipped_tiles()` function.
**Estimated Time**: 30-40 hours
**Risk Level**: 🔴 High
**Prerequisites**: Phase 2 complete, test coverage ≥ 25%

---

### 3.1 Extract DEM Acquisition Logic ⬜

**Time Estimate**: 6 hours

#### Tasks:
- [ ] ⬜ Create `touchterrain/common/dem_acquisition.py`
- [ ] ⬜ Extract functions:
  - `fetch_dem_from_earth_engine(config: DEMConfig) -> np.ndarray`
  - `load_dem_from_geotiff(filepath: str) -> np.ndarray`
  - `get_dem_metadata(source: str) -> dict`
- [ ] ⬜ Move Earth Engine initialization logic
- [ ] ⬜ Add comprehensive error handling
- [ ] ⬜ Write unit tests (with mocking for EE)
- [ ] ⬜ Update `get_zipped_tiles()` to use new functions
- [ ] ⬜ Run integration tests
- [ ] ⬜ Commit: "refactor: extract DEM acquisition into separate module"

**Lines Reduced**: ~200 lines from get_zipped_tiles()

**Success Criteria**:
- DEM acquisition isolated
- Tests pass (including mocked EE)
- get_zipped_tiles() shorter

---

### 3.2 Extract Polygon/Mask Processing Logic ⬜

**Time Estimate**: 5 hours

#### Tasks:
- [ ] ⬜ Create `touchterrain/common/polygon_processing.py`
- [ ] ⬜ Extract functions:
  - `load_polygon_from_kml(filepath: str) -> GeoJSON`
  - `load_polygon_from_url(url: str) -> GeoJSON`
  - `apply_polygon_mask(dem: np.ndarray, polygon: GeoJSON, transform) -> np.ndarray`
  - `validate_polygon_bounds(polygon: GeoJSON, bounds: BoundingBox) -> bool`
- [ ] ⬜ Consolidate KML/GeoJSON parsing
- [ ] ⬜ Write unit tests
- [ ] ⬜ Update `get_zipped_tiles()` to use new functions
- [ ] ⬜ Commit: "refactor: extract polygon processing into separate module"

**Lines Reduced**: ~150 lines from get_zipped_tiles()

**Success Criteria**:
- Polygon logic isolated
- Tests pass
- Clearer separation of concerns

---

### 3.3 Extract Projection Logic ⬜

**Time Estimate**: 5 hours

#### Tasks:
- [ ] ⬜ Create `touchterrain/common/projection.py`
- [ ] ⬜ Extract functions:
  - `determine_utm_projection(bounds: BoundingBox) -> str`
  - `get_projection_transform(source_epsg: str, target_epsg: str)`
  - `reproject_dem(dem: np.ndarray, transform) -> np.ndarray`
  - `calculate_resolution(bounds: BoundingBox, config: MeshConfig) -> float`
- [ ] ⬜ Write unit tests
- [ ] ⬜ Update `get_zipped_tiles()` to use new functions
- [ ] ⬜ Commit: "refactor: extract projection logic into separate module"

**Lines Reduced**: ~180 lines from get_zipped_tiles()

**Success Criteria**:
- Projection code isolated
- No GDAL errors
- Tests pass

---

### 3.4 Extract DEM Processing Logic ⬜

**Time Estimate**: 6 hours

#### Tasks:
- [ ] ⬜ Create `touchterrain/common/dem_processing.py`
- [ ] ⬜ Extract functions:
  - `apply_elevation_filter(dem: np.ndarray, ignore_leq: float) -> np.ndarray`
  - `fill_dem_holes(dem: np.ndarray, iterations: int, threshold: int) -> np.ndarray`
  - `apply_z_scale(dem: np.ndarray, scale: float) -> np.ndarray`
  - `apply_min_elevation(dem: np.ndarray, min_elev: float) -> np.ndarray`
  - `resample_dem(dem: np.ndarray, factor: float) -> np.ndarray`
  - `rotate_dem(dem: np.ndarray, degrees: float) -> np.ndarray`
- [ ] ⬜ Move from TouchTerrainEarthEngine.py
- [ ] ⬜ Write unit tests for each function
- [ ] ⬜ Update `get_zipped_tiles()` to use new functions
- [ ] ⬜ Commit: "refactor: extract DEM processing into separate module"

**Lines Reduced**: ~250 lines from get_zipped_tiles()

**Success Criteria**:
- Each processing step is a function
- Tests for each step
- Pipeline clearer

---

### 3.5 Extract Tiling Logic ⬜

**Time Estimate**: 4 hours

#### Tasks:
- [ ] ⬜ Create `touchterrain/common/tiling.py`
- [ ] ⬜ Extract functions:
  - `calculate_tile_bounds(dem: np.ndarray, num_tiles_x: int, num_tiles_y: int) -> List[Bounds]`
  - `split_dem_into_tiles(dem: np.ndarray, tile_bounds: List[Bounds]) -> List[np.ndarray]`
  - `get_tile_index(x: int, y: int, num_tiles_x: int) -> int`
  - `get_tile_filename(base_name: str, x: int, y: int, extension: str) -> str`
- [ ] ⬜ Write unit tests
- [ ] ⬜ Update `get_zipped_tiles()` to use new functions
- [ ] ⬜ Commit: "refactor: extract tiling logic into separate module"

**Lines Reduced**: ~120 lines from get_zipped_tiles()

**Success Criteria**:
- Tiling isolated
- Tests pass
- Multiprocessing still works

---

### 3.6 Extract GPX Overlay Logic ⬜

**Time Estimate**: 3 hours

#### Tasks:
- [ ] ⬜ Refactor `touchterrain/common/gpx_processing.py` (renamed from TouchTerrainGPX.py in Phase 1)
- [ ] ⬜ Ensure clean interface:
  - `load_gpx_file(filepath: str) -> GPXData`
  - `overlay_gpx_on_dem(dem: np.ndarray, gpx: GPXData, config: GPXConfig) -> np.ndarray`
- [ ] ⬜ Write unit tests
- [ ] ⬜ Update `get_zipped_tiles()` to use new interface
- [ ] ⬜ Commit: "refactor: clean up GPX processing interface"

**Lines Reduced**: ~100 lines from get_zipped_tiles()

**Success Criteria**:
- GPX logic isolated
- Tests pass
- Clear API

---

### 3.7 Extract Bottom Image Processing ⬜

**Time Estimate**: 2 hours

#### Tasks:
- [ ] ⬜ Move `make_bottom_raster_from_image()` to `image_utils.py`
- [ ] ⬜ Rename to `load_bottom_relief_image(filepath: str, shape: tuple) -> np.ndarray`
- [ ] ⬜ Write unit tests
- [ ] ⬜ Update `get_zipped_tiles()` to use new function
- [ ] ⬜ Commit: "refactor: extract bottom image processing"

**Lines Reduced**: ~50 lines from get_zipped_tiles()

**Success Criteria**:
- Image processing isolated
- Tests pass

---

### 3.8 Create Pipeline Orchestrator ⬜

**Time Estimate**: 8 hours

#### Tasks:
- [ ] ⬜ Create `touchterrain/common/pipeline.py`:
  ```python
  class DEMProcessingPipeline:
      """Orchestrates the DEM-to-mesh pipeline."""

      def __init__(
          self,
          dem_config: DEMConfig,
          mesh_config: MeshConfig,
          processing_config: ProcessingConfig,
          gpx_config: Optional[GPXConfig] = None,
          viz_config: Optional[VisualizationConfig] = None
      ):
          self.dem_config = dem_config
          self.mesh_config = mesh_config
          self.processing_config = processing_config
          self.gpx_config = gpx_config
          self.viz_config = viz_config

      def run(self) -> tuple[float, str]:
          """Execute full pipeline, return (zip_size_mb, zip_path)"""
          # Step 1: Acquire DEM
          dem = self._acquire_dem()

          # Step 2: Apply polygon mask if needed
          if self.dem_config.polygon:
              dem = self._apply_polygon_mask(dem)

          # Step 3: Reproject
          dem, transform = self._reproject_dem(dem)

          # Step 4: Process DEM
          dem = self._process_dem(dem)

          # Step 5: Apply GPX if needed
          if self.gpx_config and self.gpx_config.imported_gpx:
              dem = self._overlay_gpx(dem)

          # Step 6: Generate tiles
          tiles = self._split_into_tiles(dem)

          # Step 7: Generate meshes
          meshes = self._generate_meshes(tiles)

          # Step 8: Export and zip
          zip_path = self._export_and_zip(meshes)

          return self._get_zip_size(zip_path), zip_path

      def _acquire_dem(self) -> np.ndarray:
          # Call dem_acquisition module
          ...

      def _apply_polygon_mask(self, dem: np.ndarray) -> np.ndarray:
          # Call polygon_processing module
          ...

      # ... other pipeline steps
  ```
- [ ] ⬜ Implement all pipeline steps
- [ ] ⬜ Add logging at each step
- [ ] ⬜ Write integration tests
- [ ] ⬜ Refactor `get_zipped_tiles()` to use pipeline:
  ```python
  def get_zipped_tiles(**kwargs) -> tuple[float, str]:
      """Legacy function wrapper for backward compatibility."""
      # Convert kwargs to config objects
      dem_config = dict_to_dem_config(kwargs)
      mesh_config = dict_to_mesh_config(kwargs)
      processing_config = dict_to_processing_config(kwargs)

      # Run pipeline
      pipeline = DEMProcessingPipeline(
          dem_config, mesh_config, processing_config
      )
      return pipeline.run()
  ```
- [ ] ⬜ Commit: "refactor: create DEMProcessingPipeline orchestrator"

**Lines Reduced**: get_zipped_tiles() now ~100 lines (was 1,903)

**Success Criteria**:
- Pipeline class works end-to-end
- Old get_zipped_tiles() still works (wrapper)
- Tests pass
- Code is readable

---

### 3.9 Update Documentation for New Architecture ⬜

**Time Estimate**: 3 hours

#### Tasks:
- [ ] ⬜ Update CLAUDE.md with new architecture
- [ ] ⬜ Add architecture diagram
- [ ] ⬜ Document pipeline steps
- [ ] ⬜ Update migration guide
- [ ] ⬜ Add examples of using new API vs old API
- [ ] ⬜ Commit: "docs: update for new pipeline architecture"

**Success Criteria**:
- Clear architecture documentation
- Examples provided
- Migration path clear

---

## Phase 4: Class Refactoring

**Goal**: Improve class design and split large classes.
**Estimated Time**: 20-25 hours
**Risk Level**: 🔴 High
**Prerequisites**: Phase 3 complete

---

### 4.1 Rename Classes to PascalCase ⬜

**Time Estimate**: 3 hours

#### Tasks:
- [ ] ⬜ Rename in `mesh_generation.py` (formerly grid_tesselate.py):
  - `vertex` → `Vertex`
  - `quad` → `Quad`
  - `cell` → `Cell`
  - `grid` → `MeshGrid`
- [ ] ⬜ Add backward-compatible aliases:
  ```python
  vertex = Vertex  # Deprecated
  quad = Quad  # Deprecated
  cell = Cell  # Deprecated
  grid = MeshGrid  # Deprecated
  ```
- [ ] ⬜ Add deprecation warnings
- [ ] ⬜ Update all internal references
- [ ] ⬜ Update tests
- [ ] ⬜ Run full test suite
- [ ] ⬜ Commit: "refactor: rename classes to PascalCase (PEP 8)"

**Success Criteria**:
- All classes follow PEP 8
- Backward compatible
- Tests pass

---

### 4.2 Fix Class Attribute Misuse in Vertex ⬜

**Time Estimate**: 2 hours

#### Tasks:
- [ ] ⬜ Move `vertex_index_dict` from class attribute to parameter/context:
  ```python
  class Vertex:
      def __init__(self, x: float, y: float, z: float, index_dict: Optional[dict] = None):
          self.coords = (float(x), float(y), float(z))
          if index_dict is not None:
              if self.coords not in index_dict:
                  index_dict[self.coords] = len(index_dict)
  ```
- [ ] ⬜ Update MeshGrid to pass index_dict to vertices
- [ ] ⬜ Write tests verifying no shared state
- [ ] ⬜ Commit: "fix: remove class attribute misuse in Vertex"

**Success Criteria**:
- No shared state between grid instances
- Tests pass
- Thread-safe

---

### 4.3 Split MeshGrid Class - Extract Exporters ⬜

**Time Estimate**: 8 hours

#### Tasks:
- [ ] ⬜ Create `touchterrain/common/mesh_exporters/`:
  - `__init__.py`
  - `base.py` (abstract exporter interface)
  - `stl_exporter.py`
  - `obj_exporter.py`
  - `geotiff_exporter.py`
- [ ] ⬜ Define abstract interface:
  ```python
  # base.py
  from abc import ABC, abstractmethod

  class MeshExporter(ABC):
      @abstractmethod
      def export(self, mesh: 'MeshGrid', filepath: str) -> None:
          """Export mesh to file."""
          pass
  ```
- [ ] ⬜ Implement STLExporter:
  - Move ASCII STL logic
  - Move binary STL logic
  - Move normal calculations
- [ ] ⬜ Implement OBJExporter:
  - Move OBJ export logic
  - Move texture coordinate logic
- [ ] ⬜ Implement GeoTIFFExporter:
  - Move GeoTIFF export logic
- [ ] ⬜ Update MeshGrid to use exporters:
  ```python
  class MeshGrid:
      def export(self, filepath: str, format: str) -> None:
          exporter = self._get_exporter(format)
          exporter.export(self, filepath)

      def _get_exporter(self, format: str) -> MeshExporter:
          if format in ['STLb', 'STLa']:
              return STLExporter(binary=(format == 'STLb'))
          elif format == 'obj':
              return OBJExporter()
          elif format == 'GeoTiff':
              return GeoTIFFExporter()
  ```
- [ ] ⬜ Write unit tests for each exporter
- [ ] ⬜ Commit: "refactor: extract mesh exporters into separate modules"

**Lines Reduced**: MeshGrid from ~1,237 to ~400-500 lines

**Success Criteria**:
- Each export format is a class
- Easy to add new formats
- Tests pass
- MeshGrid much smaller

---

### 4.4 Split MeshGrid Class - Extract Mesh Generation ⬜

**Time Estimate**: 6 hours

#### Tasks:
- [ ] ⬜ Create `touchterrain/common/mesh_generator.py`
- [ ] ⬜ Extract tessellation logic:
  ```python
  class MeshGenerator:
      """Generates 3D mesh from DEM raster."""

      def generate(
          self,
          top_array: np.ndarray,
          bottom_array: np.ndarray,
          config: MeshConfig
      ) -> MeshGrid:
          """Generate mesh from top and bottom arrays."""
          mesh = MeshGrid()
          self._generate_top_surface(mesh, top_array)
          self._generate_bottom_surface(mesh, bottom_array)
          self._generate_walls(mesh, top_array, bottom_array)
          return mesh

      def _generate_top_surface(self, mesh: MeshGrid, array: np.ndarray):
          # Tessellation logic
          ...

      def _generate_bottom_surface(self, mesh: MeshGrid, array: np.ndarray):
          ...

      def _generate_walls(self, mesh: MeshGrid, top: np.ndarray, bottom: np.ndarray):
          ...
  ```
- [ ] ⬜ Move tessellation algorithms
- [ ] ⬜ Write unit tests
- [ ] ⬜ Update pipeline to use MeshGenerator
- [ ] ⬜ Commit: "refactor: extract mesh generation logic"

**Lines Reduced**: MeshGrid from ~400-500 to ~200 lines

**Success Criteria**:
- Mesh generation isolated
- MeshGrid is just data structure
- Tests pass
- Clear separation

---

### 4.5 Increase Test Coverage to 50% ⬜

**Time Estimate**: 6 hours

#### Priority Areas:
- [ ] ⬜ Test all exporters (STL, OBJ, GeoTIFF)
- [ ] ⬜ Test mesh generation
- [ ] ⬜ Test pipeline steps
- [ ] ⬜ Test error handling
- [ ] ⬜ Mock Earth Engine and GDAL where needed
- [ ] ⬜ Run coverage report
- [ ] ⬜ Commit: "test: increase coverage to 50%"

**Success Criteria**:
- Coverage ≥ 50%
- All refactored code tested
- CI passes

---

## Phase 5: File Renaming (Breaking Changes)

**Goal**: Rename files to follow consistent conventions.
**Estimated Time**: 6-8 hours
**Risk Level**: 🔴 High (Breaking)
**Prerequisites**: Phase 4 complete, prepare major version bump

---

### 5.1 Plan Breaking Changes Release ⬜

**Time Estimate**: 2 hours

#### Tasks:
- [ ] ⬜ Document all breaking changes
- [ ] ⬜ Prepare migration guide
- [ ] ⬜ Plan version bump (e.g., 2.0.0 → 3.0.0)
- [ ] ⬜ Communicate to users/team
- [ ] ⬜ Create release branch
- [ ] ⬜ Update CHANGELOG.md
- [ ] ⬜ Commit: "docs: prepare for v3.0.0 breaking changes"

**Success Criteria**:
- Team aware of changes
- Migration guide ready
- Release plan clear

---

### 5.2 Rename Module Files ⬜

**Time Estimate**: 3 hours

#### Tasks:
- [ ] ⬜ Rename files (git mv):
  - `Coordinate_system_conv.py` → `coordinate_conversion.py`
  - `TouchTerrainEarthEngine.py` → `earth_engine.py`
  - `TouchTerrainGPX.py` → `gpx_processing.py`
  - `grid_tesselate.py` → `mesh_generation.py` (fix typo)
- [ ] ⬜ Update all imports throughout codebase
- [ ] ⬜ Update tests
- [ ] ⬜ Update CLAUDE.md
- [ ] ⬜ Run full test suite
- [ ] ⬜ Commit: "refactor!: rename modules to snake_case (BREAKING)"

**Success Criteria**:
- All files follow snake_case
- No import errors
- Tests pass

---

### 5.3 Remove Deprecated Aliases ⬜

**Time Estimate**: 2 hours

#### Tasks:
- [ ] ⬜ Remove old function name aliases (LatLon_to_UTM, etc.)
- [ ] ⬜ Remove old class name aliases (vertex, quad, cell, grid)
- [ ] ⬜ Remove backward-compatible imports from old locations
- [ ] ⬜ Update any remaining old-style usage
- [ ] ⬜ Run tests
- [ ] ⬜ Commit: "refactor!: remove deprecated aliases (BREAKING)"

**Success Criteria**:
- Only new names exist
- No deprecated code
- Tests pass

---

### 5.4 Release Version 3.0.0 ⬜

**Time Estimate**: 1 hour

#### Tasks:
- [ ] ⬜ Final test suite run
- [ ] ⬜ Update version in `pyproject.toml`
- [ ] ⬜ Tag release: `git tag v3.0.0`
- [ ] ⬜ Update CHANGELOG.md with release date
- [ ] ⬜ Push to main branch
- [ ] ⬜ Deploy to production (if applicable)
- [ ] ⬜ Announce release

**Success Criteria**:
- Version tagged
- Release published
- Users notified

---

## Phase 6: Polish and Documentation

**Goal**: Add comprehensive documentation and final improvements.
**Estimated Time**: 15-20 hours
**Risk Level**: 🟢 Low
**Prerequisites**: Phase 5 complete

---

### 6.1 Add Comprehensive Docstrings ⬜

**Time Estimate**: 8 hours

#### Tasks:
- [ ] ⬜ Add docstrings to all public functions (Google or NumPy style)
- [ ] ⬜ Add docstrings to all classes
- [ ] ⬜ Add module-level docstrings
- [ ] ⬜ Include examples in docstrings
- [ ] ⬜ Run pydocstyle to check compliance
- [ ] ⬜ Commit: "docs: add comprehensive docstrings"

**Success Criteria**:
- All public APIs documented
- Examples provided
- pydocstyle passes

---

### 6.2 Generate API Documentation ⬜

**Time Estimate**: 3 hours

#### Tasks:
- [ ] ⬜ Set up Sphinx or mkdocs
- [ ] ⬜ Configure auto-generation from docstrings
- [ ] ⬜ Add tutorials and guides
- [ ] ⬜ Add architecture diagrams
- [ ] ⬜ Build and review docs
- [ ] ⬜ Host on ReadTheDocs or GitHub Pages
- [ ] ⬜ Commit: "docs: add API documentation site"

**Success Criteria**:
- Documentation site live
- Easy to navigate
- Comprehensive

---

### 6.3 Add Type Hints to Entire Codebase ⬜

**Time Estimate**: 6 hours

#### Tasks:
- [ ] ⬜ Add type hints to all remaining functions
- [ ] ⬜ Configure mypy to strict mode for all modules
- [ ] ⬜ Fix all type errors
- [ ] ⬜ Run mypy in CI
- [ ] ⬜ Commit: "feat: complete type hint coverage"

**Success Criteria**:
- 100% type hint coverage on public APIs
- mypy strict mode passes
- CI enforces type checking

---

### 6.4 Increase Test Coverage to 60%+ ⬜

**Time Estimate**: 8 hours

#### Focus Areas:
- [ ] ⬜ Edge cases in coordinate conversion
- [ ] ⬜ Error handling paths
- [ ] ⬜ Integration tests for full pipeline
- [ ] ⬜ Multiprocessing tests
- [ ] ⬜ Mock Earth Engine thoroughly
- [ ] ⬜ Performance regression tests
- [ ] ⬜ Run coverage report
- [ ] ⬜ Commit: "test: achieve 60%+ test coverage"

**Success Criteria**:
- Coverage ≥ 60%
- Critical paths covered
- CI enforces coverage minimum

---

### 6.5 Performance Benchmarking ⬜

**Time Estimate**: 4 hours

#### Tasks:
- [ ] ⬜ Set up pytest-benchmark
- [ ] ⬜ Create benchmark suite for key operations
- [ ] ⬜ Run before/after comparisons
- [ ] ⬜ Document any performance changes
- [ ] ⬜ Optimize hot paths if needed
- [ ] ⬜ Commit: "perf: add benchmarking suite"

**Success Criteria**:
- Benchmarks established
- No performance regression
- Hot paths identified

---

## Phase 7: Advanced Improvements (Optional)

**Goal**: Advanced architectural improvements (nice-to-haves).
**Estimated Time**: 20-30 hours
**Risk Level**: 🟡 Medium
**Prerequisites**: Phase 6 complete

---

### 7.1 Add Dependency Injection ⬜

**Time Estimate**: 6 hours

#### Tasks:
- [ ] ⬜ Create abstract interfaces for external dependencies:
  ```python
  class DEMSource(ABC):
      @abstractmethod
      def fetch(self, config: DEMConfig) -> np.ndarray:
          pass

  class EarthEngineSource(DEMSource):
      def fetch(self, config: DEMConfig) -> np.ndarray:
          # Real Earth Engine API calls
          ...

  class MockDEMSource(DEMSource):
      def fetch(self, config: DEMConfig) -> np.ndarray:
          # Return test data
          return np.random.rand(100, 100)
  ```
- [ ] ⬜ Update pipeline to accept injected dependencies
- [ ] ⬜ Update tests to use mocks
- [ ] ⬜ Commit: "refactor: add dependency injection for testability"

**Success Criteria**:
- Tests don't need real Earth Engine
- Easy to swap implementations
- More testable

---

### 7.2 Add Logging Strategy ⬜

**Time Estimate**: 3 hours

#### Tasks:
- [ ] ⬜ Replace all print() with logging calls
- [ ] ⬜ Set up structured logging
- [ ] ⬜ Add log levels appropriately (DEBUG, INFO, WARNING, ERROR)
- [ ] ⬜ Configure log output (console, file)
- [ ] ⬜ Document logging configuration
- [ ] ⬜ Commit: "feat: implement comprehensive logging strategy"

**Success Criteria**:
- No print() statements
- Logs are useful
- Configurable log levels

---

### 7.3 Add Async Support for I/O Operations ⬜

**Time Estimate**: 10 hours

#### Tasks:
- [ ] ⬜ Identify I/O-bound operations (Earth Engine, file I/O)
- [ ] ⬜ Add async versions of key functions
- [ ] ⬜ Use asyncio for concurrent operations
- [ ] ⬜ Benchmark performance improvement
- [ ] ⬜ Commit: "feat: add async support for I/O operations"

**Success Criteria**:
- I/O operations non-blocking
- Performance improved
- Backward compatible

---

### 7.4 Add Caching Layer ⬜

**Time Estimate**: 5 hours

#### Tasks:
- [ ] ⬜ Add caching for expensive operations (DEM fetches)
- [ ] ⬜ Use `functools.lru_cache` or `diskcache`
- [ ] ⬜ Make cache configurable
- [ ] ⬜ Add cache invalidation
- [ ] ⬜ Document caching behavior
- [ ] ⬜ Commit: "feat: add caching layer for DEM operations"

**Success Criteria**:
- Repeated operations faster
- Configurable cache
- No stale data issues

---

### 7.5 Add CLI Improvements ⬜

**Time Estimate**: 4 hours

#### Tasks:
- [ ] ⬜ Use `click` or `typer` for CLI
- [ ] ⬜ Add progress bars (`rich` or `tqdm`)
- [ ] ⬜ Better error messages
- [ ] ⬜ Add `--help` text for all options
- [ ] ⬜ Commit: "feat: improve CLI with rich interface"

**Success Criteria**:
- CLI is user-friendly
- Progress visible
- Help is comprehensive

---

### 7.6 Add Configuration File Support ⬜

**Time Estimate**: 3 hours

#### Tasks:
- [ ] ⬜ Support YAML config files (in addition to JSON)
- [ ] ⬜ Add validation with `pydantic` or `marshmallow`
- [ ] ⬜ Support config inheritance/includes
- [ ] ⬜ Document config schema
- [ ] ⬜ Commit: "feat: add YAML config support with validation"

**Success Criteria**:
- YAML configs work
- Validation catches errors
- Schema documented

---

## Completion Checklist

### Phase 1: Quick Wins ⬜
- [ ] 1.1 Clean Up Coordinate_system_conv.py
- [ ] 1.2 Remove DEV_MODE
- [ ] 1.3 Reorganize Imports
- [ ] 1.4 Fix Function Names (Non-Breaking)
- [ ] 1.5 Split utils.py
- [ ] 1.6 Add Basic Type Hints

### Phase 2: Infrastructure ⬜
- [ ] 2.1 Create Configuration Dataclasses
- [ ] 2.2 Create Conversion Helpers
- [ ] 2.3 Increase Test Coverage to 25%
- [ ] 2.4 Set Up Mypy
- [ ] 2.5 Document Progress

### Phase 3: Function Decomposition ⬜
- [ ] 3.1 Extract DEM Acquisition
- [ ] 3.2 Extract Polygon Processing
- [ ] 3.3 Extract Projection Logic
- [ ] 3.4 Extract DEM Processing
- [ ] 3.5 Extract Tiling Logic
- [ ] 3.6 Extract GPX Logic
- [ ] 3.7 Extract Bottom Image Processing
- [ ] 3.8 Create Pipeline Orchestrator
- [ ] 3.9 Update Documentation

### Phase 4: Class Refactoring ⬜
- [ ] 4.1 Rename Classes to PascalCase
- [ ] 4.2 Fix Class Attribute Misuse
- [ ] 4.3 Split MeshGrid - Extract Exporters
- [ ] 4.4 Split MeshGrid - Extract Generation
- [ ] 4.5 Increase Test Coverage to 50%

### Phase 5: Breaking Changes ⬜
- [ ] 5.1 Plan Breaking Changes Release
- [ ] 5.2 Rename Module Files
- [ ] 5.3 Remove Deprecated Aliases
- [ ] 5.4 Release Version 3.0.0

### Phase 6: Polish ⬜
- [ ] 6.1 Add Comprehensive Docstrings
- [ ] 6.2 Generate API Documentation
- [ ] 6.3 Complete Type Hints
- [ ] 6.4 Increase Test Coverage to 60%+
- [ ] 6.5 Performance Benchmarking

### Phase 7: Advanced (Optional) ⬜
- [ ] 7.1 Add Dependency Injection
- [ ] 7.2 Add Logging Strategy
- [ ] 7.3 Add Async Support
- [ ] 7.4 Add Caching Layer
- [ ] 7.5 Add CLI Improvements
- [ ] 7.6 Add Configuration File Support

---

## Progress Tracking

| Phase | Status | Started | Completed | Time Spent | Notes |
|-------|--------|---------|-----------|------------|-------|
| Phase 1 | ⬜ Not Started | - | - | 0h | Quick wins |
| Phase 2 | ⬜ Not Started | - | - | 0h | Infrastructure |
| Phase 3 | ⬜ Not Started | - | - | 0h | Function decomposition |
| Phase 4 | ⬜ Not Started | - | - | 0h | Class refactoring |
| Phase 5 | ⬜ Not Started | - | - | 0h | Breaking changes |
| Phase 6 | ⬜ Not Started | - | - | 0h | Polish |
| Phase 7 | ⬜ Not Started | - | - | 0h | Advanced (optional) |

**Total Estimated Time**: 110-149 hours (not including Phase 7)
**Total Estimated Time with Phase 7**: 130-179 hours

---

## Risk Mitigation

### For Each Phase:
1. **Create feature branch** before starting
2. **Run tests frequently** (after each task)
3. **Commit small changes** (not big batches)
4. **Code review** before merging
5. **Backup/tag** before risky changes
6. **Document** as you go

### Rollback Plan:
- Each phase can be reverted independently
- Git tags at phase boundaries
- Keep deprecated code until Phase 5
- Maintain backward compatibility until breaking release

---

## Notes

- Update this file as each task is completed
- Mark tasks with ✅ when done
- Add actual time spent for future estimation
- Document any blockers or issues encountered
- Celebrate milestones! 🎉

---

**Last Updated**: 2025-10-11
**Next Review**: After Phase 1 completion
