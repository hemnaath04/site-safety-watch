# Vendored three.js

- Package: `three`
- Version: `0.180.0`
- Source: https://registry.npmjs.org/three/-/three-0.180.0.tgz
- License: MIT, copied in `LICENSE`
- Files: `build/three.module.min.js`, its `build/three.core.min.js` dependency,
  `examples/jsm/controls/OrbitControls.js`, `examples/jsm/loaders/GLTFLoader.js` (as
  `GLTFLoader.js`) and its dependency `examples/jsm/utils/BufferGeometryUtils.js` (as
  `utils/BufferGeometryUtils.js`)

The import specifier `three` in OrbitControls, GLTFLoader and BufferGeometryUtils is changed to
the adjacent `three.module.min.js` file (`./three.module.min.js`, or `../three.module.min.js`
from `utils/`), and GLTFLoader imports `./utils/BufferGeometryUtils.js` instead of
`../utils/BufferGeometryUtils.js`, so the console runs offline without a package resolver or
import map. No functional code is changed.
