#!/usr/bin/env python3
"""Pinned, cached iOS static build. Every subprocess has a bounded timeout."""
import argparse, fcntl, hashlib, json, os, pathlib, subprocess, tarfile, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(); p.add_argument('--sdk', choices=['iphoneos','iphonesimulator'], required=True); p.add_argument('--output', required=True); p.add_argument('--source', required=True)
a = p.parse_args(); source_root = pathlib.Path(a.source).resolve(); out = pathlib.Path(a.output).resolve(); out.mkdir(parents=True, exist_ok=True)
# All SDKs share the download/source cache. Serialize build/cache mutation across Xcode tasks.
cache = ROOT/'build/imagemagick'; cache.mkdir(parents=True, exist_ok=True)
lock = (cache/'.build.lock').open('a+')
lock_deadline = time.monotonic() + 600
while True:
 try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); break
 except BlockingIOError:
  if time.monotonic() >= lock_deadline: raise RuntimeError('Native image build lock timed out after 600 seconds')
  print('Waiting for the other native image build...', flush=True); time.sleep(10)
manifest = json.loads((ROOT/'ios/dependencies.json').read_text())
def capture(cmd): return subprocess.check_output(cmd,text=True,timeout=30).strip()
sdk = capture(['xcrun','--sdk',a.sdk,'--show-sdk-path']); clang = capture(['xcrun','--find','clang']); clangxx = capture(['xcrun','--find','clang++'])
revision=capture(['git','-C',str(source_root),'rev-parse','HEAD'])
source_config = json.loads((ROOT/'ios/source.json').read_text())
if revision != source_config['revision']: raise RuntimeError('Source revision does not match ios/source.json')
compiler = capture([clang, '--version'])
dirty = capture(['git','-C',str(source_root),'diff','--binary','HEAD'])
if dirty: raise RuntimeError('Refusing to package modified ImageMagick source')
key=hashlib.sha256((pathlib.Path(__file__).read_text()+json.dumps(manifest,sort_keys=True)+json.dumps(source_config,sort_keys=True)+str(out)+str(ROOT)+sdk+compiler+revision+dirty).encode()).hexdigest()
products = {
 'jpeg': ('lib/libjpeg.a','include/jpeglib.h'), 'png': ('lib/libpng16.a','include/png.h'),
 'webp': ('lib/libwebp.a','include/webp/decode.h'), 'tiff': ('lib/libtiff.a','include/tiffio.h'),
 'aom': ('lib/libaom.a','include/aom/aom_codec.h'), 'heif': ('lib/libheif.a','include/libheif/heif.h'),
 'lcms': ('lib/liblcms2.a','include/lcms2.h'), 'freetype': ('lib/libfreetype.a','include/freetype2/ft2build.h')
}
required = [item for pair in products.values() for item in pair] + ['lib/libMagickCore-7.Q16HDRI.a','lib/libMagickWand-7.Q16HDRI.a','include/ImageMagick-7/MagickWand/MagickWand.h','lib/libwebpmux.a','lib/libwebpdemux.a','lib/libsharpyuv.a']
stamp=out/'build-key'
if stamp.exists() and stamp.read_text()==key and all((out/item).exists() for item in required): print('ImageMagick cache valid'); raise SystemExit(0)
cache=ROOT/'build/imagemagick'; sources=cache/'sources'; sources.mkdir(parents=True,exist_ok=True)
logs=out/'logs';logs.mkdir(exist_ok=True)
target='arm64-apple-ios'+source_config['deployment_target']+('-simulator' if a.sdk=='iphonesimulator' else '')
env=dict(os.environ, PATH='/opt/homebrew/bin:/usr/local/bin:'+os.environ['PATH'],CC=clang,CXX=clangxx,
 CFLAGS=f'-target {target} -isysroot {sdk} -Os -fvisibility=hidden',CXXFLAGS=f'-target {target} -isysroot {sdk} -Os -fvisibility=hidden',
 CPPFLAGS=f'-I{out}/include',LDFLAGS=f'-target {target} -isysroot {sdk} -L{out}/lib',
 PKG_CONFIG_LIBDIR=str(out/'lib/pkgconfig'),PKG_CONFIG_PATH=str(out/'lib/pkgconfig'))
env['ac_cv_func_getentropy']='no' # Apple declares getentropy without sys/random.h; use upstream fallback.
env['LIBS']='-laom -lsharpyuv -lc++ -lz -liconv'
env.pop('SDKROOT',None); env.pop('MACOSX_DEPLOYMENT_TARGET',None)
def run(cmd,name,cwd=None,timeout=300):
 print(name,flush=True)
 with (logs/(name+'.log')).open('w') as f:
  proc=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try: code=proc.wait(timeout=timeout)
  except subprocess.TimeoutExpired:
   import signal;os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10);raise RuntimeError(name+' timed out; inspect '+str(logs))
 if code: raise RuntimeError(name+' failed; inspect '+str(logs/(name+'.log')))
for name,dep in manifest.items():
 archive=cache/'downloads'/f'{name}.tar.gz'; archive.parent.mkdir(exist_ok=True)
 if not archive.exists(): run(['curl','-fL','--max-time','120',dep['url'],'-o',str(archive)],name+'-download',timeout=130)
 if hashlib.sha256(archive.read_bytes()).hexdigest()!=dep['sha256']: raise RuntimeError(name+' checksum mismatch')
 source=sources/name
 source_stamp=source/'.clawsy-source-sha'
 if not source_stamp.exists() or source_stamp.read_text()!=dep['sha256']:
  import shutil
  if source.exists(): shutil.rmtree(source)
  source.mkdir()
  with tarfile.open(archive) as tar:
   # Pinned official archives, reject traversal and extract one root.
   members=tar.getmembers(); root=members[0].name.split('/')[0]
   for m in members:
    parts=pathlib.PurePosixPath(m.name).parts
    if '..' in parts or m.name.startswith('/'): raise RuntimeError('unsafe archive')
   temp=sources/(name+'-unpack');temp.mkdir(exist_ok=True);tar.extractall(temp)
   import shutil
   shutil.rmtree(source);shutil.move(str(temp/root),source);shutil.rmtree(temp)
   source_stamp.write_text(dep['sha256'])
 opts={
 'jpeg':['-DENABLE_SHARED=OFF','-DENABLE_STATIC=ON','-DWITH_TURBOJPEG=OFF'],
 'png':['-DPNG_SHARED=OFF','-DPNG_TESTS=OFF','-DPNG_TOOLS=OFF'],
 'webp':['-DWEBP_BUILD_ANIM_UTILS=OFF','-DWEBP_BUILD_CWEBP=OFF','-DWEBP_BUILD_DWEBP=OFF','-DWEBP_BUILD_GIF2WEBP=OFF','-DWEBP_BUILD_IMG2WEBP=OFF','-DWEBP_BUILD_VWEBP=OFF','-DWEBP_BUILD_WEBPINFO=OFF','-DWEBP_BUILD_WEBPMUX=OFF','-DWEBP_BUILD_EXTRAS=OFF'],
 'tiff':['-Dtiff-tools=OFF','-Dtiff-tests=OFF','-Dtiff-contrib=OFF','-Dtiff-docs=OFF','-Dlzma=OFF','-Dzstd=OFF','-Djpeg=ON'],
 'aom':['-DENABLE_TESTS=OFF','-DENABLE_EXAMPLES=OFF','-DENABLE_TOOLS=OFF','-DENABLE_DOCS=OFF','-DCONFIG_RUNTIME_CPU_DETECT=1','-DHAVE_SVE=0','-DHAVE_SVE2=0','-DHAVE_NEON_DOTPROD=0','-DHAVE_NEON_I8MM=0','-DAOM_TARGET_CPU=arm64','-DENABLE_NASM=OFF'],
 'heif':['-DAOM_INCLUDE_DIR='+str(out/'include'),'-DAOM_LIBRARY='+str(out/'lib/libaom.a'),'-DWITH_EXAMPLES=OFF','-DBUILD_TESTING=OFF','-DENABLE_PLUGIN_LOADING=OFF','-DWITH_LIBDE265=OFF','-DWITH_X265=OFF','-DWITH_DAV1D=OFF','-DWITH_RAV1E=OFF','-DWITH_SvtEnc=OFF','-DWITH_GDK_PIXBUF=OFF','-DWITH_AOM_DECODER=ON','-DWITH_AOM_ENCODER=ON','-DWITH_AOM_DECODER_PLUGIN=OFF','-DWITH_AOM_ENCODER_PLUGIN=OFF'],
 'freetype':['-DFT_DISABLE_HARFBUZZ=ON','-DFT_DISABLE_BROTLI=ON','-DFT_DISABLE_BZIP2=ON'],
 }.get(name,[])
 build=out/('build-'+name);build.mkdir(exist_ok=True)
 dependency_key=hashlib.sha256((json.dumps(manifest,sort_keys=True)+sdk+compiler+env['CFLAGS']+env['CXXFLAGS']+str(opts)+str(out)+'arm64-v3').encode()).hexdigest()
 done=build/'clawsy-installed'
 if done.exists() and done.read_text()==dependency_key and all((out/item).exists() for item in products[name]): continue
 if name=='lcms':
  run([str(source/'configure'),'--host=aarch64-apple-darwin','--disable-shared','--enable-static','--without-jpeg','--without-tiff','--prefix='+str(out)],name+'-configure',build)
  run(['make','-j4'],name+'-build',build);run(['make','install'],name+'-install',build)
 else:
  run(['cmake','--fresh','-S',str(source),'-B',str(build),'-G','Ninja','-DCMAKE_SYSTEM_NAME=iOS','-DCMAKE_SYSTEM_PROCESSOR=arm64','-DCMAKE_OSX_SYSROOT='+sdk,'-DCMAKE_OSX_ARCHITECTURES=arm64','-DCMAKE_OSX_DEPLOYMENT_TARGET='+source_config['deployment_target'],'-DCMAKE_C_COMPILER='+clang,'-DCMAKE_CXX_COMPILER='+clangxx,'-DCMAKE_BUILD_TYPE=MinSizeRel','-DCMAKE_INSTALL_PREFIX='+str(out),'-DCMAKE_PREFIX_PATH='+str(out),'-DBUILD_SHARED_LIBS=OFF','-DCMAKE_POLICY_VERSION_MINIMUM=3.5']+opts,name+'-configure')
  run(['cmake','--build',str(build),'--parallel','4'],name+'-build',timeout=600)
  run(['cmake','--install',str(build)],name+'-install')
 done.write_text(dependency_key)
pc=out/'lib/pkgconfig/zlib.pc'
pc.write_text('Name: zlib\nDescription: Apple SDK zlib\nVersion: 1.2.12\nLibs: -lz\n')
# All pixel operations use upstream ImageMagick. No subprocess delegates, modules, or X11.
build=out/'build-magick';build.mkdir(exist_ok=True)
opts=['--host=aarch64-apple-darwin','--prefix='+str(out),'--disable-shared','--enable-static','--disable-openmp','--enable-zero-configuration','--without-modules','--without-perl','--without-x','--without-magick-plus-plus','--with-quantum-depth=16','--enable-hdri','--with-jpeg=yes','--with-png=yes','--with-webp=yes','--with-tiff=yes','--with-heic=yes','--with-lcms=yes','--with-freetype=yes','--without-fontconfig','--without-gslib','--without-gs-font-dir','--without-raw','--without-rsvg','--without-jxl','--without-openexr','--without-openjp2','--without-fftw','--without-lqr','--without-djvu','--without-wmf','--without-xml','--without-bzlib','--without-lzma','--without-zstd','--disable-dependency-tracking']
run([str(source_root/'configure')]+opts,'magick-configure',build)
# configure silently drops a delegate it cannot find (e.g. no pkg-config); fail instead of shipping it.
config=(build/'config/config.h').read_text()
missing=[d for d in ('FREETYPE','HEIC','JPEG','LCMS','PNG','TIFF','WEBP','ZLIB') if '#define '+d+'_DELEGATE 1' not in config]
if missing: raise RuntimeError('ImageMagick configure disabled '+', '.join(missing)+'; is pkg-config installed? inspect '+str(logs/'magick-configure.log'))
# Relink the optional CLI when a static delegate changed; make cannot track external archives.
cli=build/'utilities/magick'
if cli.exists(): cli.unlink()
run(['make','-j4'],'magick-build',build,timeout=600)
run(['make','install'],'magick-install',build)
stamp.write_text(key)
print('ImageMagick built: '+str(out))
