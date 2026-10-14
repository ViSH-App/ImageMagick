# iOS static packages

Development lives on `ios-support`. The upstream `main` branch and its workflow files are unchanged. The upstream workflows are disabled in this fork's Actions settings; only `iOS static libraries` is enabled.

`ios/source.json` pins the ImageMagick commit used by Clawsy, independently of the upstream source at the tip of this fork. `dependencies.json` pins eight delegate libraries by URL and SHA256. The build uses arm64, iOS 18.2, `-Os` (CMake `MinSizeRel`) for ImageMagick and every delegate, Q16 HDRI, static delegates, and zero-configuration mode. It does not load external XML, modules, or delegate programs. Apps must set their own security policy and supply explicit fonts.

## Publish

Run the `iOS static libraries` workflow manually on `ios-support` with a fresh tag such as `clawsy-ios-7.1.2-31-r1`. There are no push, schedule, or upstream-sync triggers. The two platform jobs build and verify independently; publication happens only after both succeed. GitHub Actions artifacts expire after one day; release assets remain available.

Each release contains `imagemagick-iphoneos-arm64.tar.gz`, `imagemagick-iphonesimulator-arm64.tar.gz`, and `SHA256SUMS`. The archives include the full static link closure, headers, license texts and `manifest.json` with every payload file's hash plus source, recipe and toolchain provenance. No local build cache, executable, or build-machine prefix is included in the public headers.

Consumers must pin the release and checksums. Use a new `rN` tag for recipe changes; never replace an existing release. When changing the source or dependencies, update Clawsy's source pin, fallback recipe and dependency notices together with its prebuilt manifest.

## Local build

Check out the commit from `source.json` into `build/source`, then install `cmake`, `ninja`, and `pkgconf` and run:

```sh
python3 ios/build.py --sdk iphoneos --source build/source --output build/imagemagick/iphoneos
python3 ios/package.py --sdk iphoneos --source build/source --output dist
python3 ios/verify.py --sdk iphoneos
```

Repeat with `iphonesimulator`; verification creates and deletes its own simulator and round-trips JPEG, PNG, WebP, AVIF, GIF, TIFF, BMP, and ICO. Python 3.12 or newer is required for the packaging verification scripts. Builds have per-command timeouts and logs in `build/imagemagick/<platform>/logs`.
