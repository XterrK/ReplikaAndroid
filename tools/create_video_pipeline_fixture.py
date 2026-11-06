#!/usr/bin/env python3
"""Wrap the already verified public GigaAM sample in small original video; no video in APK assets."""
import argparse
import hashlib
import json
import pathlib
import subprocess
from create_media_import_fixtures import native_path

SOURCE_SHA='d8aaaa18a5098d7c6de0595ae7ac1e64cacd0d4022af3595213bdaf23be77e69'
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=pathlib.Path,default=pathlib.Path('/mnt/f/ReplikaToolchain/russian-example.wav'))
parser.add_argument('--output',type=pathlib.Path,default=pathlib.Path('/mnt/f/ReplikaToolchain/integration-video-v15.mp4'))
parser.add_argument('--ffmpeg',default='/mnt/f/ReplikaToolchain/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe')
args=parser.parse_args()
assert hashlib.sha256(args.source.read_bytes()).hexdigest()==SOURCE_SHA,'Expected exact official public Russian GigaAM sample'
convert=native_path if args.ffmpeg.endswith('.exe') else str
command=[args.ffmpeg,'-y','-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x6979ae:s=128x128:r=2:d=11.4','-i',convert(args.source),'-map','0:v','-map','1:a','-c:v','mpeg4','-q:v','8','-c:a','aac','-b:a','64k','-avoid_negative_ts','make_zero',convert(args.output)]
subprocess.run(command,check=True)
report={'scope':'public Russian speech wrapped in original color video for actual Android import→production Worker→Room/export; no artificial transcript','sourceWavSha256':SOURCE_SHA,'sourceWavPath':str(args.source),'sourceOrigin':'official sherpa GigaAM Russian conversion public example.wav; same pinned sample used in PipelineTest','videoSha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),'videoBytes':args.output.stat().st_size,'videoPath':str(args.output),'command':command,'appAssets':False}
folder=ROOT/'docs/test-evidence/v1.5';folder.mkdir(parents=True,exist_ok=True)
(folder/'video-pipeline-fixture.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
