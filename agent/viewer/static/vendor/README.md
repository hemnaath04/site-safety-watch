# Vendored three.js

- Package: `three`
- Version: `0.180.0`
- Source: https://registry.npmjs.org/three/-/three-0.180.0.tgz
- License: MIT, copied in `LICENSE`
- Files: `build/three.module.min.js`, its `build/three.core.min.js` dependency, and
  `examples/jsm/controls/OrbitControls.js`

The OrbitControls import specifier is changed from the package name `three` to the adjacent
`./three.module.min.js` file so the console runs offline without a package resolver or import
map. No functional OrbitControls code is changed.
