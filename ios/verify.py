#!/usr/bin/env python3
"""Link each packaged platform; run real format round trips on an isolated simulator."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from package import LIBRARIES, ROOT


def run(args, timeout=120, **kwargs):
    return subprocess.run(args, check=True, timeout=timeout, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', choices=['iphoneos', 'iphonesimulator'], required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='imagemagick-relocated-') as temp:
        root = Path(temp)
        with tarfile.open(ROOT / 'dist' / f'imagemagick-{args.sdk}-arm64.tar.gz') as tar:
            tar.extractall(root, filter='data')
        executable = root / 'smoke'
        sdk = subprocess.check_output(['xcrun', '--sdk', args.sdk, '--show-sdk-path'], text=True, timeout=30).strip()
        config = json.loads((ROOT / 'ios/source.json').read_text())
        target = 'arm64-apple-ios' + config['deployment_target']
        if args.sdk == 'iphonesimulator':
            target += '-simulator'
        run(['xcrun', 'clang', '-target', target, '-isysroot', sdk,
             '-DMAGICKCORE_HDRI_ENABLE=1', '-DMAGICKCORE_QUANTUM_DEPTH=16',
             '-I' + str(root / 'include/ImageMagick-7'), str(ROOT / 'ios/smoke.c'),
             '-L' + str(root / 'lib'), *['-l' + lib for lib in LIBRARIES],
             '-lc++', '-lz', '-liconv', '-o', str(executable)])
        if args.sdk == 'iphonesimulator':
            devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', '-j'], timeout=30))
            runtime = sorted((r for r in devices['runtimes'] if r['isAvailable'] and r['name'].startswith('iOS')), key=lambda r: tuple(map(int, r['version'].split('.'))))[-1]
            device = next(d for d in runtime['supportedDeviceTypes'] if d['name'].startswith('iPhone'))
            udid = subprocess.check_output(['xcrun', 'simctl', 'create', 'ImageMagick package smoke', device['identifier'], runtime['identifier']], text=True, timeout=30).strip()
            try:
                run(['xcrun', 'simctl', 'boot', udid])
                run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], timeout=180)
                run(['xcrun', 'simctl', 'spawn', udid, str(executable)], timeout=120)
            finally:
                subprocess.run(['xcrun', 'simctl', 'shutdown', udid], timeout=60)
                run(['xcrun', 'simctl', 'delete', udid], timeout=60)
        print('Verified relocated package:', args.sdk)


if __name__ == '__main__':
    main()
