#!/usr/bin/env python3
"""Package only relocatable headers, static libraries and license notices."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LIBRARIES = ['MagickWand-7.Q16HDRI', 'MagickCore-7.Q16HDRI', 'jpeg', 'png16',
             'webp', 'webpmux', 'webpdemux', 'sharpyuv', 'tiff', 'heif', 'aom', 'lcms2', 'freetype']


def capture(*args):
    return subprocess.check_output(args, text=True, timeout=30).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', choices=['iphoneos', 'iphonesimulator'], required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    config = json.loads((ROOT / 'ios/source.json').read_text())
    dependencies = ROOT / 'ios/dependencies.json'
    args.output.mkdir(parents=True, exist_ok=True)
    install = ROOT / 'build/imagemagick' / args.sdk
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        shutil.copytree(install / 'include', stage / 'include', symlinks=False)
        (stage / 'lib').mkdir()
        for library in LIBRARIES:
            shutil.copyfile(install / 'lib' / f'lib{library}.a', stage / 'lib' / f'lib{library}.a')
        # Zero-configuration builds do not read installed XML or delegate programs.
        # Remove the build-machine prefix from public configuration headers as well.
        for header in (stage / 'include').rglob('*.h'):
            header.write_text(header.read_text().replace(str(install), '/__imagemagick_ios__'))
        licenses = stage / 'licenses'
        licenses.mkdir()
        shutil.copyfile(source / 'LICENSE', licenses / 'ImageMagick.txt')
        extra = {'freetype': ['docs/FTL.TXT', 'docs/GPLv2.TXT'],
                 'jpeg': ['README.ijg'], 'aom': ['third_party/libyuv/LICENSE']}
        for name in json.loads(dependencies.read_text()):
            dep_source = ROOT / 'build/imagemagick/sources' / name
            files = [p for p in dep_source.iterdir() if p.is_file() and
                     any(word in p.name.lower() for word in ('license', 'copying', 'notice', 'patents'))]
            files += [dep_source / p for p in extra.get(name, [])]
            if not files:
                raise RuntimeError(f'No license notices for {name}')
            (licenses / name).mkdir()
            for file in sorted(set(files)):
                shutil.copyfile(file, licenses / name / str(file.relative_to(dep_source)).replace('/', '_'))
        shutil.copyfile(dependencies, stage / 'dependencies.json')
        metadata = {
            'schema': 1, 'platform': args.sdk, 'architecture': 'arm64',
            'deployment_target': config['deployment_target'],
            'version': config['version'], 'source_revision': config['revision'],
            'recipe_revision': capture('git', '-C', str(ROOT), 'rev-parse', 'HEAD'),
            'dependencies_sha256': hashlib.sha256(dependencies.read_bytes()).hexdigest(),
            'quantum_depth': 16, 'hdri': True, 'zero_configuration': True,
            'xcode': capture('xcodebuild', '-version'),
            'sdk_version': capture('xcrun', '--sdk', args.sdk, '--show-sdk-version'),
            'compiler': capture('xcrun', 'clang', '--version'),
            'files': {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(stage.rglob('*')) if p.is_file()},
        }
        (stage / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
        archive = output / f'imagemagick-{args.sdk}-arm64.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for child in sorted(stage.iterdir()):
                tar.add(child, arcname=child.name)
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        (output / (archive.name + '.sha256')).write_text(f'{checksum}  {archive.name}\n')
        print(f'{archive}: {archive.stat().st_size} bytes, SHA256 {checksum}')


if __name__ == '__main__':
    main()
